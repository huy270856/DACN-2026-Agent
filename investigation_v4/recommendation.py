"""TASK 07B (D2): NO new recommendation policy. Deterministic mapping onto the existing
`evaluation.task06a.consistency.safe_recommendation`. recommendation-policy-v4.0 is deferred to 07C.

detector_relation AGREES -> CONSISTENT, CONFLICTS -> CONFLICT, NOT_INFORMATIVE -> INSUFFICIENT_EVIDENCE.
Any verifier flag, or no accepted final, -> MANUAL_REVIEW. Never executes containment.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from evaluation.task06a.consistency import is_near_threshold, safe_recommendation

POLICY = "task06a-safe-recommendation (unchanged) via investigation-v4.0 relation mapping"
ALIGNMENT = {"AGREES": "CONSISTENT", "CONFLICTS": "CONFLICT", "NOT_INFORMATIVE": "INSUFFICIENT_EVIDENCE"}


def derive(final: Optional[Dict[str, Any]], verification: Optional[Dict[str, Any]],
           detector: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    label = (detector or {}).get("predicted_label")
    score, threshold = (detector or {}).get("raw_score"), (detector or {}).get("threshold")
    near = is_near_threshold(score, threshold) if threshold is not None else False
    if final is None:
        rec = safe_recommendation(label, None, near)
        rec.update(action="MANUAL_REVIEW")
        rec["derivation"] = rec["derivation"] + ["no accepted final -> MANUAL_REVIEW"]
    else:
        value = (final.get("detector_relation") or {}).get("value")
        alignment = ALIGNMENT.get(value)
        rec = safe_recommendation(label, alignment, near)
        rec["derivation"] = [f"detector_relation={value} -> alignment={alignment}"] + rec["derivation"]
        if verification and verification.get("has_flags"):
            rec.update(action="MANUAL_REVIEW")
            rec["derivation"].append("verifier flags " + ",".join(verification["flags"]) + " -> MANUAL_REVIEW")
    rec = copy.deepcopy(rec)
    rec.update(policy=POLICY, review_required=rec["action"] == "MANUAL_REVIEW", requires_human_decision=True,
               execution_status="NOT_EXECUTED")
    return rec
