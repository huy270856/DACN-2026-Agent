"""Static-only baseline (branch A): FROZEN, rule-based, no LLM.

Produces a deterministic explanation + recommendation from the LightGBM static
prediction and the real evidence projection ONLY. The template and the
recommendation rules are frozen here and versioned by hash; they are defined
before any benchmark result is seen and never tuned to outcomes. Ground truth is
never used.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping

# Near-threshold margin: within this of the threshold -> MANUAL_REVIEW.
NEAR_THRESHOLD_MARGIN = 0.10


def _find(obs: List[Mapping[str, Any]], facet: str):
    for o in obs:
        if o.get("facet") == facet:
            return o
    return None


def baseline_recommendation(label: str, score: float, threshold: float) -> Dict[str, Any]:
    near = abs(score - threshold) < NEAR_THRESHOLD_MARGIN
    if near:
        action, priority = "MANUAL_REVIEW", "MEDIUM"
        reason = ("Score nằm gần ngưỡng quyết định (|score-threshold| < "
                  f"{NEAR_THRESHOLD_MARGIN}); cần rà soát thủ công.")
    elif label == "malicious":
        action, priority = "CONSIDER_QUARANTINE", "HIGH"
        reason = "Mô hình tĩnh phân loại MALICIOUS với score vượt ngưỡng."
    else:
        action, priority = "MONITOR", "LOW"
        reason = "Mô hình tĩnh phân loại BENIGN; theo dõi theo quy trình."
    return {"action": action, "priority": priority, "explanation": reason,
            "requires_human_decision": True, "execution_status": "NOT_EXECUTED",
            "near_threshold": near}


def static_only_report(prediction: Mapping[str, Any],
                       projection: Mapping[str, Any]) -> Dict[str, Any]:
    obs = projection["observations"]
    label = prediction["predicted_label"]
    score = float(prediction["raw_score"])
    threshold = float(prediction["threshold"])

    cited: List[str] = []
    lines: List[str] = []
    pred_ev = _find(obs, "static.pe_malware_prediction")
    if pred_ev:
        cited.append(pred_ev["evidence_id"])
    lines.append(
        f"Mô hình LightGBM ({prediction['model_id']}) phân loại tĩnh: {label.upper()} "
        f"(raw score {score:.4f} so với threshold {threshold:.4f}; "
        f"score >= threshold ⇒ malicious). Raw score KHÔNG phải xác suất đã hiệu chỉnh.")

    sec = _find(obs, "static.sections")
    if sec:
        cited.append(sec["evidence_id"])
        v = sec["value"]
        lines.append(
            f"Quan sát tĩnh về sections: {v['section_count']} section, "
            f"{v['high_entropy_section_count_ge7']} section entropy≥7 (có thể do nén/đóng gói), "
            f"{v['writable_and_executable_section_count']} section vừa ghi vừa thực thi.")
    imp = _find(obs, "static.imports_summary")
    if imp:
        cited.append(imp["evidence_id"])
        v = imp["value"]
        lines.append(f"Imports tĩnh: {v['library_count']} thư viện, "
                     f"{v['total_imported_functions']} hàm import (khả năng tĩnh, không phải hành vi đã chạy).")
    st = _find(obs, "static.strings_summary")
    if st:
        cited.append(st["evidence_id"])
        v = st["value"]
        lines.append(f"Chuỗi tĩnh: {v['url_occurrences']} lần khớp URL, "
                     f"{v['registry_key_occurrences']} khớp khóa registry, "
                     f"{v['embedded_MZ_occurrences']} MZ nhúng (chỉ là chỉ dấu tĩnh).")

    explanation = " ".join(lines)
    limitations = [
        "Chỉ phân tích tĩnh; không quan sát hành vi runtime/network/process.",
        "Raw score chưa hiệu chỉnh; không phải xác suất.",
        "Không suy luận feature importance từ score (baseline chỉ trích dẫn observations có thật).",
        "FEATURE_RECORD_REPLAY: chạy trên feature record, KHÔNG phải raw-PE E2E.",
    ]
    reco = baseline_recommendation(label, score, threshold)
    return {
        "branch": "STATIC_ONLY",
        "schema_version": "static-only-report-v1",
        "static_label": label,
        "explanation": explanation,
        "evidence_refs": cited,
        "limitations": limitations,
        "recommendation": reco,
        "notes": ["Nhãn tĩnh là kết quả có thẩm quyền; baseline không có đánh giá của LLM."],
    }


def baseline_version() -> Dict[str, str]:
    """Stable version hash of the frozen baseline logic (this module's source)."""
    import inspect
    src = inspect.getsource(static_only_report) + inspect.getsource(baseline_recommendation)
    return {"baseline_id": "static-only-baseline-v1",
            "source_sha256": hashlib.sha256(src.encode()).hexdigest()[:16],
            "near_threshold_margin": str(NEAR_THRESHOLD_MARGIN)}
