"""REPAIR #1 — blind annotation package v2 (full evidence for human grading).

Regenerates a richer blind package from SAVED artifacts (no Qwen re-run): each
form now carries the static prediction, the relevant evidence observations (with
evidence_id + facet + value), the cited references, full explanation, limitations,
recommendation + priority, the human-decision flag, the FEATURE_RECORD_REPLAY
note, and explicit 0/1/2 scoring guidance per semantic criterion.

Hard rules:
  * No ground-truth label and no TP/TN/FP/FN strata in grader-facing forms.
  * No branch identity in report text/metadata; X/Y mapping is evaluator-only.
  * Semantic scores stay CHƯA CHẤM (never auto-filled, never LLM-judged).
  * Versioned output dir; the v1 package is never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from evaluation.task05c import evidence_projection as proj

SCORING_GUIDANCE = {
    "A2_claims_supported": {
        "0": "Có claim quan trọng KHÔNG được evidence trích dẫn hỗ trợ.",
        "1": "Phần lớn claim được hỗ trợ, còn vài chỗ thiếu/không rõ nguồn.",
        "2": "Mọi claim thực chất đều được evidence (có ID) hỗ trợ."},
    "B1_score_vs_truth_distinction": {
        "0": "Coi score là sự thật / xác suất đã hiệu chỉnh / ground truth.",
        "1": "Phân biệt chưa đầy đủ score vs prediction.",
        "2": "Phân biệt rõ score/threshold/prediction; nêu score chưa hiệu chỉnh."},
    "B2_no_feature_importance_from_score": {
        "0": "Bịa feature importance của LightGBM từ score.",
        "1": "Có suy diễn mơ hồ về tầm quan trọng feature.",
        "2": "Không suy diễn feature importance từ score."},
    "C1_uncertainty": {
        "0": "Khẳng định quá mức, không nêu giới hạn.",
        "1": "Nêu một phần giới hạn/thiếu hụt evidence.",
        "2": "Nêu rõ giới hạn (static-only, uncalibrated, replay, thiếu dynamic)."},
    "D1_recommendation_appropriate": {
        "0": "Khuyến nghị không phù hợp hoặc ngoài phạm vi (đòi auto-action, v.v.).",
        "1": "Khuyến nghị chấp nhận được.",
        "2": "Khuyến nghị phù hợp dữ liệu + mức rủi ro, trong phạm vi (human quyết định)."},
}


FROZEN_THRESHOLD = 0.8321860386013389  # TASK 05A model threshold (unchanged)


def _anon_id(sha: str) -> str:
    return "S-" + hashlib.sha256(("anon:" + sha).encode()).hexdigest()[:10]


def _evidence_sheet(projection) -> List[Dict[str, Any]]:
    return [{"evidence_id": o["evidence_id"], "facet": o["facet"], "value": o["value"],
             "limitations": o.get("limitations", [])} for o in projection["observations"]]


def _static_form(row, projection, pred, label):
    rep = row["static"]["report"]
    return {
        "report_label": label,
        "static_prediction": pred,
        "feature_record_replay": True,
        "evidence_sheet": _evidence_sheet(projection),
        "cited_evidence_refs": rep["evidence_refs"],
        "explanation": rep["explanation"],
        "limitations": rep["limitations"],
        "recommendation": rep["recommendation"]["action"],
        "priority": rep["recommendation"]["priority"],
        "requires_human_decision": rep["recommendation"]["requires_human_decision"],
    }


def _agent_form(row, projection, pred, label):
    ass = row["agent"]["report"].get("assessment") or {}
    return {
        "report_label": label,
        "static_prediction": pred,
        "feature_record_replay": True,
        "evidence_sheet": _evidence_sheet(projection),
        "cited_evidence_refs": ass.get("evidence_refs", []),
        "explanation": ass.get("explanation", ""),
        "limitations": ass.get("limitations", []),
        "recommendation": ass.get("agent_recommendation"),
        "priority": None,
        "requires_human_decision": True,
    }


def generate(samples_dir: Path, records_cache: Path, out_dir: Path):
    rows = {json.loads(p.read_text(encoding="utf-8"))["sha256"]:
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(samples_dir.glob("*.json"))}
    records = {}
    for line in records_cache.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            records[r["sha256"]] = r

    forms, mapping = [], []
    for sha, row in sorted(rows.items()):
        rec = records.get(sha)
        if rec is None:
            continue
        projection = proj.project_record(rec)
        # Static prediction is identical for both branches, so it is allowed on both forms.
        prediction = {
            "predicted_label": row["predicted_label"],
            "raw_score": row["score"],
            "threshold": FROZEN_THRESHOLD,
            "score_is_calibrated_probability": False,
        }
        aid = _anon_id(sha)
        swap = int(hashlib.sha256((sha + "blindv2").encode()).hexdigest(), 16) % 2
        a_label, b_label = ("X", "Y") if swap == 0 else ("Y", "X")
        forms.append({"sample_id": aid,
                      "forms": [_static_form(row, projection, prediction, a_label),
                                _agent_form(row, projection, prediction, b_label)],
                      "scores_to_fill": {label: {c: "CHƯA CHẤM" for c in SCORING_GUIDANCE}
                                         for label in (a_label, b_label)},
                      "grader_notes": {a_label: "", b_label: ""}})
        mapping.append({"sample_id": aid,
                        "X_is": "STATIC_ONLY" if swap == 0 else "STATIC_PLUS_AGENT",
                        "Y_is": "STATIC_PLUS_AGENT" if swap == 0 else "STATIC_ONLY"})

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "annotation_forms_blind_v2.json").write_text(
        json.dumps({"scoring_guidance": SCORING_GUIDANCE, "forms": forms},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "branch_mapping_EVALUATOR_ONLY.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "README.md").write_text(
        "# Gói chấm blind v2 (TASK 05C-R)\n\n"
        f"- {len(forms)} mẫu; mỗi mẫu 2 phiếu X/Y (ẩn nhánh) + evidence sheet đầy đủ.\n"
        "- Mỗi phiếu có: static prediction, evidence observations (ID+facet+value), "
        "references trích dẫn, giải thích đầy đủ, limitations, recommendation+priority, "
        "cờ human-decision, ghi chú FEATURE_RECORD_REPLAY.\n"
        "- Chấm 5 tiêu chí semantic (A2/B1/B2/C1/D1) thang 0-2 theo `scoring_guidance`.\n"
        "- KHÔNG có ground-truth, KHÔNG có strata, KHÔNG lộ nhánh trong phiếu.\n"
        "- `branch_mapping_EVALUATOR_ONLY.json` chỉ mở sau khi chấm xong.\n"
        "- Không dùng LLM chấm; không tự chấm nhánh của mình.\n"
        "- Tổng hợp sau khi điền: `python -m evaluation.task05c.repair.grading_aggregate`.\n",
        encoding="utf-8")
    return len(forms)


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 05C-R annotation package v2")
    ap.add_argument("--samples", required=True)
    ap.add_argument("--records-cache", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    n = generate(Path(args.samples), Path(args.records_cache), Path(args.out))
    print(f"wrote annotation package v2 with {n} samples (2 blind forms each)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
