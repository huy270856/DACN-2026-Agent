"""TASK 05D-J — REAL LLM (Claude) semantic grading of the blind pilot forms.

PROVENANCE / HONESTY:
  * These scores were produced by an LLM — Claude (claude-opus-4-8) — reasoning over
    each of the 40 blind forms DIRECTLY, in an interactive, human-directed session on
    2026-11-15. The model read each form's explanation, evidence sheet, cited refs,
    limitations, recommendation and static prediction, and assigned 0/1/2 per criterion
    with a reason. The judgments are embedded below as the model's output.
  * This is NOT human grading (human grading stays PENDING) and NOT a deterministic/
    reproducible scripted call: re-running an LLM can yield slightly different scores.
  * Scoring was blind to the branch mapping / ground truth / strata; the mapping is used
    ONLY afterwards for aggregation.
  * This is a SECOND, independent provisional method alongside the rule-based checker
    (rule_checker.py). Neither is human-verified.

Meta-caveat the model flags: the 5 rubric criteria are fully satisfiable by boilerplate.
The static-only reports are a fixed template engineered to satisfy exactly these criteria
(explicit "uncalibrated", a standard limitations list, accurate observation counts,
rule-matched recommendations), so they legitimately earn ~2.0 here — but that reflects the
rubric's ceiling being reachable by formula, not deeper insight. A criterion rewarding
specificity/insight (not in this rubric) would likely favour a strong free-form agent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

CRIT = ["A2_claims_supported", "B1_score_vs_truth_distinction",
        "B2_no_feature_importance_from_score", "C1_uncertainty", "D1_recommendation_appropriate"]

JUDGE_MODEL = "claude-opus-4-8"
JUDGE_METHOD = ("direct semantic reasoning by the LLM (Claude) reading each form in an "
                "interactive human-directed session; blind to branch mapping/ground truth; "
                "NOT deterministic and NOT a reproducible scripted API call")

# Default judgment = all 2 (every form: references real evidence, notes the raw score is
# uncalibrated in explanation or limitations, invents no feature-importance, lists explicit
# limitations, and gives a proportionate recommendation). CLAUDE_JUDGMENTS below records the
# specific weaknesses the model found by reading each form; reasons are the model's own.


def _base():
    return {c: 2 for c in CRIT}


# (sample_id|report_label) -> {criterion: (score, reason)} for non-default judgments.
CLAUDE_JUDGMENTS: Dict[str, Dict[str, Any]] = {
    "S-7c2ea2e8f0|Y": {"A2_claims_supported": (1, "labels the imports as 'CRM imports/exports' "
        "— an interpretive claim not supported by the provided evidence sheet")},
    "S-37cfb6694f|Y": {"A2_claims_supported": (1, "cites 'MFC imports' specifically; the evidence "
        "sheet does not name MFC, so this is over-specific/unsupported (high-entropy claim is ok)")},
    "S-bf43ef03ff|Y": {"A2_claims_supported": (1, "names specific imports 'ExitProcess/MoveFileA' "
        "not present in the provided evidence sheet — fabricated specificity"),
        "D1_recommendation_appropriate": (1, "malicious prediction (0.845) but recommends only "
        "MONITOR — under-cautious for a malicious label")},
    "S-5327b8b93a|X": {"A2_claims_supported": (1, "claims 'high entropy sections' but this sample "
        "has 0 sections with entropy>=7 per the evidence — unsupported/contradicted claim")},
    # --- D1: under-cautious MONITOR on a malicious-predicted or near-threshold case -----
    "S-61d5f9a581|X": {"D1_recommendation_appropriate": (1, "malicious prediction (0.979) but "
        "recommends only MONITOR — under-cautious")},
    "S-a0d702616c|X": {"D1_recommendation_appropriate": (1, "benign but near-threshold (0.8299 vs "
        "0.8322); MONITOR under-calls a borderline case where MANUAL_REVIEW fits")},
    "S-d4da6e170f|Y": {"D1_recommendation_appropriate": (1, "malicious prediction (0.9997) but "
        "recommends only MONITOR — under-cautious")},
    "S-65a766fc1c|X": {"D1_recommendation_appropriate": (1, "malicious prediction (0.949) but "
        "recommends only MONITOR — under-cautious")},
    "S-8042ae7321|Y": {"D1_recommendation_appropriate": (1, "malicious prediction (0.836) but "
        "recommends only MONITOR — under-cautious")},
    "S-08261f2a73|X": {"D1_recommendation_appropriate": (1, "benign but near-threshold (0.8225 vs "
        "0.8322); MONITOR under-calls a borderline case")},
}

DEFAULT_REASON = {
    "A2_claims_supported": "claims reference real evidence (sections/imports/strings/entropy/"
                           "prediction) accurately; no fabricated specifics",
    "B1_score_vs_truth_distinction": "states the raw score is uncalibrated / not a probability "
                                     "(in explanation or limitations) and relates it to the threshold",
    "B2_no_feature_importance_from_score": "does not invent LightGBM feature-importance from the score",
    "C1_uncertainty": "explicitly states limitations (static-only, uncalibrated, replay, no dynamic)",
    "D1_recommendation_appropriate": "recommendation is proportionate to the predicted label/score",
}


def judge(sample_id, label):
    key = f"{sample_id}|{label}"
    scores = _base()
    reasons = dict(DEFAULT_REASON)
    for c, (s, r) in CLAUDE_JUDGMENTS.get(key, {}).items():
        scores[c] = s
        reasons[c] = r
    return scores, reasons


def run(forms_path: Path, out_dir: Path, mapping_path: Path = None,
        rule_results: Path = None):
    raw = forms_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    meta = {
        "judge_model": JUDGE_MODEL, "judge_method": JUDGE_METHOD,
        "is_llm_as_judge": True, "reproducible": False, "method_family": "llm_semantic",
        "judge_version": "claude-judge-v1",
        "rubric_version": data.get("rubric_version", "task05c-rubric-v1"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_manifest_hash": hashlib.sha256(raw).hexdigest(),
        "source_forms": forms_path.name,
        "evaluation_type": "AI_LLM_JUDGE_PROVISIONAL",
        "human_verified": False,
        "note": "Real LLM (Claude) semantic judgment, provisional. NOT human grading; human "
                "grading remains PENDING. Not deterministic/reproducible. Blind to branch mapping.",
    }
    scores_doc = {**meta, "samples": []}
    reasoning_doc = {**meta, "samples": []}
    graded = 0
    for s in data["forms"]:
        sid = s["sample_id"]
        sc_forms, rs_forms = [], []
        for f in s["forms"]:
            scores, reasons = judge(sid, f["report_label"])
            graded += 1
            sc_forms.append({"report_label": f["report_label"], "scores": scores})
            rs_forms.append({"report_label": f["report_label"], "reasons": reasons})
        scores_doc["samples"].append({"sample_id": sid, "forms": sc_forms})
        reasoning_doc["samples"].append({"sample_id": sid, "forms": rs_forms})

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "claude_scores.json").write_text(json.dumps(scores_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "claude_reasoning.json").write_text(json.dumps(reasoning_doc, indent=2, ensure_ascii=False), encoding="utf-8")

    agg = aggregate(scores_doc, mapping_path) if mapping_path else None
    _summary(out_dir / "claude_summary.md", scores_doc, agg, None, graded, meta)
    return {"graded_forms": graded, "aggregate": agg, "meta": meta}


def aggregate(scores_doc, mapping_path: Path):
    mapping = {m["sample_id"]: m for m in json.loads(Path(mapping_path).read_text(encoding="utf-8"))}
    buckets = {"STATIC_ONLY": {c: [] for c in CRIT}, "STATIC_PLUS_AGENT": {c: [] for c in CRIT}}
    for s in scores_doc["samples"]:
        m = mapping.get(s["sample_id"])
        if not m:
            continue
        branch_of = {"X": m["X_is"], "Y": m["Y_is"]}
        for f in s["forms"]:
            b = branch_of.get(f["report_label"])
            if b in buckets:
                for c in CRIT:
                    buckets[b][c].append(f["scores"][c])

    def summ(b):
        o = {}
        for c in CRIT:
            v = buckets[b][c]
            o[c] = {"mean": round(sum(v) / len(v), 3), "dist": {k: v.count(k) for k in (0, 1, 2)}} if v else None
        tot = [x for c in CRIT for x in buckets[b][c]]
        o["overall_mean"] = round(sum(tot) / len(tot), 3) if tot else None
        return o
    return {"STATIC_ONLY": summ("STATIC_ONLY"), "STATIC_PLUS_AGENT": summ("STATIC_PLUS_AGENT"),
            "note": "LLM (Claude) provisional per-branch aggregate; human_verified=false."}


def _summary(path, scores_doc, agg, comparison, graded, meta):
    L = ["# TASK 05D-J — LLM (Claude) semantic grading (PROVISIONAL) — tóm tắt", "",
         f"- **evaluation_type:** {meta['evaluation_type']} · **is_llm_as_judge:** {meta['is_llm_as_judge']} · "
         f"**reproducible:** {meta['reproducible']} · **human_verified:** {meta['human_verified']}",
         f"- judge_model: `{meta['judge_model']}` (lượt LLM thật, suy luận từng phiếu)",
         f"- method: {JUDGE_METHOD}",
         f"- rubric: {meta['rubric_version']} · source_manifest_hash: `{meta['source_manifest_hash'][:16]}…` · {meta['timestamp']}",
         f"- **Phiếu đã chấm:** {graded}/40",
         "",
         "> Đây là lượt **LLM thật (Claude) chấm từng phiếu**, KHÁC với rule-based checker. "
         "Vẫn **KHÔNG** phải human grading (human vẫn PENDING) và **không tái lập chính xác** "
         "(chạy lại LLM có thể khác nhẹ). Blind với branch mapping.", ""]
    if agg:
        so, sa = agg["STATIC_ONLY"], agg["STATIC_PLUS_AGENT"]
        L.append("## Static-only vs Static+Agent (LLM Claude, provisional)")
        L.append("| Tiêu chí | Static-only | Static+Agent |")
        L.append("|---|--:|--:|")
        for c in CRIT:
            L.append(f"| {c} | {so[c]['mean']} | {sa[c]['mean']} |")
        L.append(f"| **overall** | **{so['overall_mean']}** | **{sa['overall_mean']}** |")
        L.append("")
        L.append("**Nhận định (Claude):** Static-only (template cố định) đạt ~2.0 vì được viết để "
                 "thỏa đúng 5 tiêu chí (nêu rõ uncalibrated, liệt kê limitations, trích dẫn số liệu "
                 "chính xác, khuyến nghị khớp luật). Static+Agent gần bằng: mạnh ở B1/B2/C1 (nêu "
                 "uncalibrated + limitations đầy đủ — rule-checker đã chấm thấp oan vì chỉ soi câu "
                 "chữ trong explanation, bỏ qua limitations), nhưng thấp hơn ở **A2** (đôi khi bịa "
                 "chi tiết: 'MFC imports', 'ExitProcess/MoveFileA', 'high entropy' khi không có) và "
                 "**D1** (đôi khi khuyến nghị MONITOR cho ca dự đoán malicious / near-threshold — "
                 "under-cautious).")
        L.append("")
        L.append("**Meta-caveat:** rubric 5 tiêu chí này có thể thỏa bằng boilerplate ⇒ template đạt "
                 "trần điểm không phải vì sâu sắc. Một tiêu chí 'độ cụ thể/insight' (không có trong "
                 "rubric) có thể đảo lợi thế về phía agent tự do. Cần người chấm xác minh.")
    L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 05D-J real LLM (Claude) semantic grading")
    ap.add_argument("--forms", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mapping", default=None)
    ap.add_argument("--rule-results", default=None)
    args = ap.parse_args(argv)
    res = run(Path(args.forms), Path(args.out), Path(args.mapping) if args.mapping else None,
              args.rule_results)
    agg = res["aggregate"] or {}
    print(json.dumps({"graded_forms": res["graded_forms"],
                      "evaluation_type": res["meta"]["evaluation_type"],
                      "is_llm_as_judge": res["meta"]["is_llm_as_judge"],
                      "reproducible": res["meta"]["reproducible"],
                      "human_verified": res["meta"]["human_verified"],
                      "overall_static_only": agg.get("STATIC_ONLY", {}).get("overall_mean"),
                      "overall_static_plus_agent": agg.get("STATIC_PLUS_AGENT", {}).get("overall_mean")},
                     indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
