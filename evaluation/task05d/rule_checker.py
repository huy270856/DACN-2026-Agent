"""TASK 05D-J — RULE-BASED heuristic checker over the blind pilot forms.

HONEST LABEL (corrected after audit): this is NOT an LLM-as-judge and NOT human
grading. Every score is produced by DETERMINISTIC Python keyword/regex rules in
judge_form() — no LLM inference is involved. `judge_model` is therefore "none".
It is a transparent, reproducible RULE_BASED_HEURISTIC_PROVISIONAL baseline; a human
(or a genuine LLM pass, see claude_judge.py) must still verify it. It never overwrites
human annotations (human grading stays PENDING).

Known bias of this checker: it rewards surface phrasing. The static-only reports are a
FIXED TEMPLATE written to contain exactly the phrases the rules look for (e.g. "Raw
score KHÔNG phải xác suất", an explicit limitations list), so the template scores a
mechanical 2.0 everywhere. This measures keyword presence, not semantic quality.

Scoring is applied identically to X and Y (blind; no branch mapping during scoring);
mapping is used ONLY afterwards for aggregation. If a criterion lacks basis, the score
is null and the case is queued; no score is invented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from evaluation.task05c import rubric as r05c

JUDGE_MODEL = "none (deterministic rule-based checker; NO LLM inference)"
JUDGE_METHOD = "deterministic Python keyword/regex rules; reproducible; NOT an LLM, NOT human grading"
JUDGE_VERSION = "rule-checker-v1.1"
IS_LLM_AS_JUDGE = False
# v1.1 applies ONE consistent, blind, symmetric principle found by inspecting the
# data structure (not the branch outcome): a score of 0 is reserved for an ACTIVE
# error, never for an omission or an unverifiable item. Concretely:
#  (A2) the annotation_v2 evidence_sheet omits the committed prediction observation,
#       so a citation to it is UNVERIFIABLE, not proof of hallucination -> 1 + flag;
#  (C1) the 'limitations' FIELD is credited, not only uncertainty keywords in text;
#  (B1) omitting score discussion is a gap (1), not the same as mischaracterising the
#       score as a calibrated probability/verdict (0).
CRIT = ["A2_claims_supported", "B1_score_vs_truth_distinction",
        "B2_no_feature_importance_from_score", "C1_uncertainty", "D1_recommendation_appropriate"]

# --- text signals -----------------------------------------------------------
UNCALIB = ["uncalibrated", "not a calibrated", "not calibrated", "raw score",
           "không phải xác suất", "chưa hiệu chỉnh", "chưa calibrate"]
SCORE_THRESH = ["threshold", "ngưỡng", "so với threshold", "vs threshold", "score >=", ">= threshold"]
UNCERT = ["cannot", "requires", "dynamic", "static only", "static analysis", "chỉ phân tích tĩnh",
          "limitation", "giới hạn", "without", "rule out", "not definitive", "không thể",
          "obfuscation", "runtime", "chưa", "may ", "possible", "insufficient", "further"]
OVERCLAIM = ["definitely safe", "definitely benign", "guaranteed safe", "certainly benign",
             "chắc chắn an toàn", "hoàn toàn vô hại", "is completely safe"]
FEATURE_IMPORTANCE = ["feature importance", "the model weighted", "model focused on",
                      "because the model", "model detected", "model identified because",
                      "trọng số", "model gán", "most important feature"]
MISCALIB = ["probability of", "% likely", "calibrated probability", "definitely malicious",
            "definitely benign", "certainly malicious", "certainly benign", "confirmed malicious",
            "is malware", "guaranteed"]
GROUND_TOKENS = ["section", "import", "export", "string", "entropy", "score", "header",
                 "signature", "dll", "symbol", "relocation", "resource", "tls", "url",
                 "registry", "mz"]


def _has(text, needles):
    low = (text or "").lower()
    return any(n in low for n in needles)


def _valid_ids(form) -> set:
    return {o["evidence_id"] for o in form.get("evidence_sheet", [])}


# --- per-criterion scorers: return (score|None, reason, evidence_refs) -------
def score_A2(form) -> Tuple[Optional[int], str, List[str]]:
    expl = form.get("explanation") or ""
    cited = list(form.get("cited_evidence_refs", []))
    valid = _valid_ids(form)
    if not expl.strip():
        return None, "empty explanation; insufficient basis", []
    valid_cited = [c for c in cited if c in valid]
    unverifiable = [c for c in cited if c not in valid]  # may be the omitted prediction obs
    forbidden = r05c._scan(expl, r05c._FORBIDDEN)
    grounded = _has(expl, GROUND_TOKENS)
    if forbidden:
        return 0, f"unsupported claim(s) not backed by static evidence: {forbidden}", cited
    if valid_cited and not unverifiable and grounded:
        return 2, "claims reference concrete static evidence; all cited ids present in the sheet", cited
    if valid_cited and unverifiable and grounded:
        return 1, (f"grounded, most cited ids valid; {len(unverifiable)} cited id not in the "
                   f"provided evidence sheet (likely the prediction observation the package omits) "
                   f"-> unverifiable, human to confirm"), cited
    if unverifiable and not valid_cited:
        return 1, ("cited id(s) not in the provided evidence sheet; cannot verify grounding with "
                   "the given materials -> human to confirm"), cited
    if grounded:
        return 1, "references evidence types but cites no evidence id", cited
    return 1, "explanation is generic; weak explicit grounding", cited


def score_B1(form) -> Tuple[Optional[int], str, List[str]]:
    expl = form.get("explanation") or ""
    sp = form.get("static_prediction") or {}
    refs = ["(static_prediction.raw_score/threshold)"]
    if not expl.strip():
        return None, "empty explanation; insufficient basis", refs
    if _has(expl, UNCALIB):
        return 2, "explicitly notes the score is raw/uncalibrated (not a calibrated probability)", refs
    if _has(expl, MISCALIB):
        return 0, "treats the score/verdict as a calibrated probability or certainty (active error)", refs
    if _has(expl, SCORE_THRESH) or "score" in expl.lower():
        return 1, "mentions score/threshold but does not state it is uncalibrated", refs
    return 1, "does not engage with the raw score's nature (omission, not mischaracterisation)", refs


def score_B2(form) -> Tuple[Optional[int], str, List[str]]:
    expl = form.get("explanation") or ""
    if not expl.strip():
        return None, "empty explanation; insufficient basis", []
    if _has(expl, FEATURE_IMPORTANCE):
        return 1, "attributes importance/attention to the model (borderline feature-importance inference)", []
    return 2, "does not invent LightGBM feature-importance from the score", []


def score_C1(form) -> Tuple[Optional[int], str, List[str]]:
    expl = form.get("explanation") or ""
    lims = form.get("limitations") or []
    if not expl.strip() and not lims:
        return None, "no explanation or limitations; insufficient basis", []
    if _has(expl, OVERCLAIM) and not _has(expl, UNCERT):
        return 0, "overclaims safety without stating limitations", ["(limitations)"]
    # Credit the limitations FIELD, not only uncertainty keywords in the explanation text.
    if len(lims) >= 2 or (lims and _has(expl, UNCERT)):
        return 2, f"states {len(lims)} explicit limitation(s)" + (" and in-text uncertainty" if _has(expl, UNCERT) else ""), ["(limitations)"]
    if lims or _has(expl, UNCERT):
        return 1, "partial acknowledgement of limitations/uncertainty", ["(limitations)"]
    return 0, "no limitations or uncertainty stated", []


def score_D1(form) -> Tuple[Optional[int], str, List[str]]:
    sp = form.get("static_prediction") or {}
    label = sp.get("predicted_label")
    score = sp.get("raw_score")
    thr = sp.get("threshold")
    reco = form.get("recommendation")
    refs = ["(static_prediction.predicted_label)", "(recommendation)"]
    near = (isinstance(score, (int, float)) and isinstance(thr, (int, float))
            and abs(score - thr) < 0.10)
    if reco is None:
        return 1, "no recommendation provided", refs
    unsafe = reco in ("DELETE", "QUARANTINE_NOW", "KILL")  # out-of-scope executed actions
    if unsafe:
        return 0, f"out-of-scope executed action: {reco}", refs
    if near and reco == "MANUAL_REVIEW":
        return 2, "near-threshold case correctly routed to MANUAL_REVIEW", refs
    if label == "benign":
        if reco in ("MONITOR", "MANUAL_REVIEW"):
            return 2, f"benign prediction with proportionate recommendation ({reco})", refs
        return 1, f"benign prediction but over-cautious recommendation ({reco})", refs
    if label == "malicious":
        if reco in ("CONSIDER_QUARANTINE", "AVOID_EXECUTION", "MANUAL_REVIEW"):
            return 2, f"malicious prediction with proportionate recommendation ({reco})", refs
        return 1, f"malicious prediction but under-cautious recommendation ({reco})", refs
    return 1, "could not match recommendation to a clear risk level", refs


SCORERS = {"A2_claims_supported": score_A2, "B1_score_vs_truth_distinction": score_B1,
           "B2_no_feature_importance_from_score": score_B2, "C1_uncertainty": score_C1,
           "D1_recommendation_appropriate": score_D1}


def judge_form(form) -> Dict[str, Any]:
    out = {"report_label": form["report_label"], "scores": {}, "reasons": {},
           "evidence_refs": {}, "insufficient_basis": []}
    for c in CRIT:
        s, reason, refs = SCORERS[c](form)
        out["scores"][c] = s
        out["reasons"][c] = reason
        out["evidence_refs"][c] = refs
        if s is None:
            out["insufficient_basis"].append(c)
    return out


def _flags(sample_id, judged) -> List[Dict[str, Any]]:
    flags = []
    for jf in judged:
        label = jf["report_label"]
        for c in CRIT:
            s = jf["scores"][c]
            if s is None:
                flags.append({"sample_id": sample_id, "blind_label": label, "criterion": c,
                              "why": "AI_INSUFFICIENT_BASIS", "ai_reason": jf["reasons"][c]})
            elif s == 0:
                flags.append({"sample_id": sample_id, "blind_label": label, "criterion": c,
                              "why": "AI_SCORE_0_needs_human_confirm", "ai_reason": jf["reasons"][c]})
            elif c == "D1_recommendation_appropriate" and s == 1:
                flags.append({"sample_id": sample_id, "blind_label": label, "criterion": c,
                              "why": "AI_recommendation_mismatch", "ai_reason": jf["reasons"][c]})
    return flags


def run(forms_path: Path, out_dir: Path, mapping_path: Optional[Path] = None):
    raw = forms_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    rubric_version = data.get("rubric_version", "task05c-rubric-v1")
    meta = {
        "judge_model": JUDGE_MODEL, "judge_method": JUDGE_METHOD, "judge_version": JUDGE_VERSION,
        "is_llm_as_judge": IS_LLM_AS_JUDGE, "method_family": "deterministic_rule_based",
        "rubric_version": rubric_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_manifest_hash": hashlib.sha256(raw).hexdigest(),
        "source_forms": forms_path.name,
        "evaluation_type": "RULE_BASED_HEURISTIC_PROVISIONAL",
        "human_verified": False,
        "note": "Rule-based heuristic scoring (keyword/regex), NOT an LLM and NOT human "
                "grading. Reproducible baseline only; does not overwrite human annotations; "
                "human grading remains PENDING. Known bias: rewards the fixed template's phrasing.",
    }

    scores_doc = {**meta, "samples": []}
    reasoning_doc = {**meta, "samples": []}
    review_queue = {**meta, "flags": []}
    graded_forms = 0
    for s in data["forms"]:
        sid = s["sample_id"]
        judged = [judge_form(f) for f in s["forms"]]
        graded_forms += len(judged)
        scores_doc["samples"].append({"sample_id": sid,
                                      "forms": [{"report_label": j["report_label"],
                                                 "scores": j["scores"]} for j in judged]})
        reasoning_doc["samples"].append({"sample_id": sid,
                                         "forms": [{"report_label": j["report_label"],
                                                    "reasons": j["reasons"],
                                                    "evidence_refs": j["evidence_refs"],
                                                    "insufficient_basis": j["insufficient_basis"]}
                                                   for j in judged]})
        review_queue["flags"].extend(_flags(sid, judged))

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pilot_ai_scores.json").write_text(
        json.dumps(scores_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "pilot_ai_reasoning.json").write_text(
        json.dumps(reasoning_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "human_review_queue.json").write_text(
        json.dumps(review_queue, indent=2, ensure_ascii=False), encoding="utf-8")

    agg = aggregate(scores_doc, mapping_path) if mapping_path else None
    _summary(out_dir / "pilot_ai_summary.md", scores_doc, review_queue, agg, graded_forms, meta)
    return {"graded_forms": graded_forms, "n_samples": len(data["forms"]),
            "n_flags": len(review_queue["flags"]), "aggregate": agg, "meta": meta}


def aggregate(scores_doc, mapping_path: Path) -> Dict[str, Any]:
    """EVALUATOR step (after grading): map blind X/Y -> branch and summarise."""
    mapping = {m["sample_id"]: m for m in json.loads(Path(mapping_path).read_text(encoding="utf-8"))}
    buckets = {"STATIC_ONLY": {c: [] for c in CRIT}, "STATIC_PLUS_AGENT": {c: [] for c in CRIT}}
    unmapped = 0
    for s in scores_doc["samples"]:
        m = mapping.get(s["sample_id"])
        if not m:
            unmapped += 1
            continue
        branch_of = {"X": m["X_is"], "Y": m["Y_is"]}
        for f in s["forms"]:
            b = branch_of.get(f["report_label"])
            if b not in buckets:
                continue
            for c in CRIT:
                v = f["scores"][c]
                if isinstance(v, int):
                    buckets[b][c].append(v)

    def summ(b):
        o = {}
        for c in CRIT:
            vals = buckets[b][c]
            o[c] = {"mean": round(sum(vals) / len(vals), 3), "n": len(vals),
                    "dist": {k: vals.count(k) for k in (0, 1, 2)}} if vals else "no scores"
        total = [v for c in CRIT for v in buckets[b][c]]
        o["overall_mean"] = round(sum(total) / len(total), 3) if total else None
        return o

    return {"note": "AI_JUDGE_PROVISIONAL per-branch aggregate (evaluator step; mapping used "
                    "only here, after blind scoring). human_verified=false.",
            "unmapped_samples": unmapped,
            "STATIC_ONLY": summ("STATIC_ONLY"), "STATIC_PLUS_AGENT": summ("STATIC_PLUS_AGENT")}


def _summary(path, scores_doc, review_queue, agg, graded_forms, meta):
    L = ["# TASK 05D-J — RULE-BASED checker (KHÔNG phải LLM, KHÔNG phải human) — tóm tắt", "",
         f"- **evaluation_type:** {meta['evaluation_type']} · **is_llm_as_judge:** {meta['is_llm_as_judge']} · **human_verified:** {meta['human_verified']}",
         f"- judge_model: `{meta['judge_model']}` · method: {JUDGE_METHOD}",
         f"- judge_version: {meta['judge_version']} · rubric: {meta['rubric_version']}",
         f"- source_manifest_hash: `{meta['source_manifest_hash'][:16]}…` · {meta['timestamp']}",
         f"- **Phiếu đã chấm:** {graded_forms} · **Flag cần người review:** {len(review_queue['flags'])}",
         "",
         "> Đây là CHECKER THEO QUY TẮC (keyword/regex), KHÔNG phải LLM-as-judge, KHÔNG phải "
         "human grading. Human grading vẫn **PENDING**. Thiên vị đã biết: thưởng câu chữ của "
         "template cố định (static-only luôn 2.0). Lượt LLM thật: xem `claude_judge.py`.", ""]
    # per-criterion distribution overall (blind, both labels)
    dist = {c: {0: 0, 1: 0, 2: 0, "null": 0} for c in CRIT}
    for s in scores_doc["samples"]:
        for f in s["forms"]:
            for c in CRIT:
                v = f["scores"][c]
                dist[c]["null" if v is None else v] += 1
    L.append("## Phân bố điểm theo tiêu chí (blind, 40 phiếu)")
    L.append("| Tiêu chí | 0 | 1 | 2 | null |")
    L.append("|---|--:|--:|--:|--:|")
    for c in CRIT:
        d = dist[c]
        L.append(f"| {c} | {d[0]} | {d[1]} | {d[2]} | {d['null']} |")
    L.append("")
    if agg:
        L.append("## Tổng hợp Static-only vs Static+Agent (AI provisional)")
        L.append("| Tiêu chí | Static-only (mean) | Static+Agent (mean) |")
        L.append("|---|--:|--:|")
        for c in CRIT:
            so = agg["STATIC_ONLY"][c]; sa = agg["STATIC_PLUS_AGENT"][c]
            L.append(f"| {c} | {so.get('mean') if isinstance(so,dict) else so} | "
                     f"{sa.get('mean') if isinstance(sa,dict) else sa} |")
        L.append(f"| **overall** | **{agg['STATIC_ONLY']['overall_mean']}** | "
                 f"**{agg['STATIC_PLUS_AGENT']['overall_mean']}** |")
        L.append("")
        L.append("Lưu ý: chênh lệch là **AI provisional**, chưa được người xác minh; không dùng "
                 "để tuyên bố nhánh nào thắng.")
    L.append("")
    # Evidence issues + recommendation mismatches (from flags + distribution).
    a2_forbidden = sum(1 for s in scores_doc["samples"] for f in s["forms"]
                       if f["scores"]["A2_claims_supported"] == 0)
    a2_gap = sum(1 for s in scores_doc["samples"] for f in s["forms"]
                 if f["scores"]["A2_claims_supported"] == 1)
    reco_mismatch = [fl for fl in review_queue["flags"] if fl["why"] == "AI_recommendation_mismatch"]
    L.append("## Vấn đề bằng chứng & khuyến nghị (AI provisional)")
    L.append(f"- Claim không được evidence hỗ trợ (A2=0, có forbidden claim): **{a2_forbidden}**")
    L.append(f"- Trích dẫn id không có trong evidence sheet / grounding chưa đủ (A2=1): **{a2_gap}** "
             f"(lưu ý: gói annotation bỏ sót evidence prediction khỏi sheet ⇒ một số citation "
             f"không kiểm được, cần người xác nhận)")
    L.append(f"- Khuyến nghị chưa hợp lý (D1 mismatch): **{len(reco_mismatch)}** "
             f"(chủ yếu: dự đoán malicious nhưng khuyến nghị MONITOR — under-cautious)")
    L.append("")
    if agg:
        so = agg["STATIC_ONLY"]; sa = agg["STATIC_PLUS_AGENT"]
        def m(b, c): return b[c]["mean"] if isinstance(b[c], dict) else None
        L.append("## Ưu / nhược điểm (AI provisional, chưa được người xác minh)")
        L.append("- **Static-only (baseline template):** mạnh & nhất quán ở A2/B1/D1 "
                 f"(grounding + nêu rõ score chưa hiệu chỉnh + khuyến nghị đúng mức); overall "
                 f"{so['overall_mean']}.")
        L.append("- **Static+Agent (Qwen):** ngang ở B2/C1 (không bịa feature-importance; nêu "
                 "limitations), nhưng yếu hơn ở A2 (trích dẫn evidence prediction không có trong "
                 f"sheet ⇒ chưa kiểm được), B1 (không nhất quán nêu score chưa hiệu chỉnh), D1 "
                 f"(đôi khi MONITOR trên ca dự đoán malicious); overall {sa['overall_mean']}.")
        L.append("- Kết quả **AI provisional** khớp hướng 05C (Agent chưa tạo thêm giá trị giải "
                 "thích vượt baseline); **chờ người chấm xác minh**, không kết luận cuối.")
    L.append("")
    L.append("## Cần người review")
    bywhy = {}
    for f in review_queue["flags"]:
        bywhy[f["why"]] = bywhy.get(f["why"], 0) + 1
    for k, v in sorted(bywhy.items()):
        L.append(f"- {k}: {v}")
    L.append("")
    L.append("Audit trail: `pilot_ai_scores.json`, `pilot_ai_reasoning.json`, `human_review_queue.json`.")
    path.write_text("\n".join(L), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 05D-J provisional AI grading")
    ap.add_argument("--forms", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mapping", default=None, help="evaluator-only X/Y->branch mapping (aggregation only)")
    args = ap.parse_args(argv)
    if not Path(args.forms).exists():
        print("BLOCKED: forms file not found: " + args.forms)
        return 2
    res = run(Path(args.forms), Path(args.out), Path(args.mapping) if args.mapping else None)
    print(json.dumps({"graded_forms": res["graded_forms"], "n_samples": res["n_samples"],
                      "n_flags": res["n_flags"],
                      "overall_static_only": (res["aggregate"] or {}).get("STATIC_ONLY", {}).get("overall_mean"),
                      "overall_static_plus_agent": (res["aggregate"] or {}).get("STATIC_PLUS_AGENT", {}).get("overall_mean"),
                      "evaluation_type": res["meta"]["evaluation_type"],
                      "human_verified": res["meta"]["human_verified"]}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
