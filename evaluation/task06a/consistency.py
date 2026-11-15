"""TASK 06A — deterministic decision-consistency checker + fail-safe recommendation.

The Agent supplies the *evidence reasoning* (alignment + which evidence supports /
contradicts the static label + uncertainty). This module is the deterministic
guardrail that (a) checks that reasoning is internally coherent and (b) derives the
final handling recommendation so an unsafe or malformed model suggestion can never
silently become MONITOR.

Documented v1 failures this targets:
  * MONITOR recommended on a malicious-predicted sample (under-cautious),
  * CONFLICT alignment with review_required = false,
  * near-threshold score waved through as MONITOR without review,
  * recommendation / review_required incoherence,
  * `alignment = CONSISTENT` that the supporting/contradicting structure does not
    actually justify (the core "absence-of-disconfirmation" bug).

Score is uncalibrated: proximity is measured in raw-score space only and labelled
as such. The checker never changes the static label and never auto-executes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional
import math

# Raw-score proximity band around the threshold. The score is NOT a probability;
# this is only "the detector was near its own decision boundary".
NEAR_THRESHOLD_MARGIN = 0.05

_PRIORITY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def is_near_threshold(raw_score: Optional[float], threshold: float,
                      margin: float = NEAR_THRESHOLD_MARGIN) -> bool:
    if raw_score is None:
        return False
    try:
        return math.isfinite(float(raw_score)) and abs(float(raw_score) - float(threshold)) < margin
    except (TypeError, ValueError):
        return False


def safe_recommendation(static_label: str, alignment: Optional[str],
                        near_threshold: bool) -> Dict[str, Any]:
    """Deterministic, fail-safe handling suggestion. Never auto-executes."""
    label = (static_label or "").lower()
    if label == "malicious":
        action, priority = "CONSIDER_QUARANTINE", "HIGH"
    elif label == "benign":
        action, priority = "MONITOR", "LOW"
    else:
        action, priority = "MANUAL_REVIEW", "MEDIUM"

    reasons = [f"base: static label = {label or 'unknown'}"]
    # A reported conflict always escalates to human review.
    if alignment == "CONFLICT":
        action, priority = "MANUAL_REVIEW", "HIGH"
        reasons.append("alignment=CONFLICT -> human review")
    # Near the detector's own boundary: never a quiet MONITOR.
    if near_threshold and action == "MONITOR":
        action, priority = "MANUAL_REVIEW", "MEDIUM"
        reasons.append("near-threshold (raw score) -> escalate MONITOR to MANUAL_REVIEW")
    # Insufficient evidence on a non-benign label should see a human.
    if alignment not in {"CONSISTENT", "CONFLICT"}:
        action, priority = "MANUAL_REVIEW", "MEDIUM"
        reasons.append("insufficient/unknown evidence assessment -> MANUAL_REVIEW")
    return {
        "action": action, "priority": priority,
        "requires_human_decision": True, "execution_status": "NOT_EXECUTED",
        "derivation": reasons,
        "note": "Deterministic fail-safe recommendation; the system never auto-quarantines/kills.",
    }


def check_consistency(assessment: Mapping[str, Any], *, static_label: str,
                      raw_score: Optional[float], threshold: float) -> Dict[str, Any]:
    """Return consistency flags + the deterministic fail-safe recommendation.

    `assessment` may be a v2 assessment (with supporting/contradicting ids) or a
    v1-shaped dict (alignment + recommendation + review_required); missing lists
    are treated as empty so v1 is still gradeable on the shared structural rules.
    """
    alignment = assessment.get("alignment") or assessment.get("evidence_alignment")
    recommendation = assessment.get("recommendation") or assessment.get("agent_recommendation")
    review_required = assessment.get("review_required")
    supporting = list(assessment.get("supporting_evidence_ids", []) or [])
    contradicting = list(assessment.get("contradicting_evidence_ids", []) or [])

    near = is_near_threshold(raw_score, threshold)
    flags: List[str] = []
    try:
        valid_score = (not isinstance(raw_score, bool) and raw_score is not None
                       and math.isfinite(float(raw_score)) and math.isfinite(float(threshold))
                       and 0 <= float(raw_score) <= 1 and 0 <= float(threshold) <= 1)
    except (ValueError, TypeError):
        valid_score = False
    if not valid_score:
        flags.append("invalid_or_missing_score")
    elif static_label not in {"benign", "malicious"} or (float(raw_score) >= float(threshold)) != (static_label == "malicious"):
        flags.append("label_score_threshold_mismatch")
    if alignment not in {"CONSISTENT", "CONFLICT", "INSUFFICIENT_EVIDENCE"}:
        flags.append("invalid_or_missing_alignment")
    if type(review_required) is not bool:
        flags.append("invalid_or_missing_review_flag")

    # --- structural alignment coherence (v2 has the lists; v1 cannot be checked here) ---
    has_structure = ("supporting_evidence_ids" in assessment
                     or "contradicting_evidence_ids" in assessment)
    if has_structure:
        if alignment == "CONSISTENT" and (not supporting or contradicting):
            flags.append("alignment_consistent_not_justified_by_structure")
        if alignment == "CONFLICT" and not contradicting:
            flags.append("alignment_conflict_without_contradicting_evidence")

    # --- recommendation safety vs label ---
    valid_recos = {"MANUAL_REVIEW", "MONITOR", "AVOID_EXECUTION", "CONSIDER_QUARANTINE"}
    if recommendation not in valid_recos:
        flags.append("invalid_or_missing_recommendation")
    else:
        if (static_label or "").lower() == "malicious" and recommendation == "MONITOR":
            flags.append("under_cautious_monitor_on_malicious")
        if alignment == "CONFLICT" and recommendation == "MONITOR":
            flags.append("monitor_despite_conflict")
        if near and recommendation == "MONITOR":
            flags.append("monitor_on_near_threshold")

    # --- review_required coherence ---
    if review_required is False:
        if alignment == "INSUFFICIENT_EVIDENCE":
            flags.append("insufficient_evidence_without_review")
        if alignment == "CONFLICT":
            flags.append("conflict_without_review")
        if (static_label or "").lower() == "malicious":
            flags.append("malicious_without_review")
        if near:
            flags.append("near_threshold_without_review")
    if recommendation == "MANUAL_REVIEW" and review_required is False:
        flags.append("manual_review_recommended_but_review_required_false")

    safe = safe_recommendation(static_label, alignment, near)
    if flags:
        safe.update(action="MANUAL_REVIEW", priority="HIGH")
        safe["derivation"].append("validation flags -> human review; preserve raw suggestion")
    safe["review_required"] = safe["action"] != "MONITOR"
    agent_matches_safe = (recommendation == safe["action"])

    return {
        "near_threshold": near,
        "flags": flags,
        "consistent": not flags,
        "safe_recommendation": safe,
        "agent_recommendation": recommendation,
        "agent_matches_safe_recommendation": agent_matches_safe,
    }
