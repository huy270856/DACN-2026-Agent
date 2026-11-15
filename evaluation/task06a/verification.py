"""Bounded screening against exactly what the model saw, NOT a semantic judge.

No flag means 'not detected by these rules', never 'all claims verified'.
Original records remain separate so projection loss can be audited.
"""
from __future__ import annotations

import json
import re
from .grounding import check_grounding
from .consistency import check_consistency


def visible_projection(facts):
    observations, incomplete = [], []
    for ev in facts["evidence"]:
        value = ev.get("value")
        try:
            value = json.loads(value) if isinstance(value, str) else value
        except ValueError:
            incomplete.append(ev["evidence_id"])
            value = {}
        if ev.get("status") != "SUCCESS" or not isinstance(value, dict):
            incomplete.append(ev["evidence_id"])
            value = {}
        observations.append({**ev, "value": value})
    return {"observations": observations}, sorted(set(incomplete))


def screen(assessment, facts, prediction):
    projection, incomplete = visible_projection(facts)
    ids = {e["evidence_id"] for e in facts["evidence"]}
    pred_ids = {e["evidence_id"] for e in facts["evidence"]
                if e["facet"] == "static.pe_malware_prediction"}
    refs = (assessment.get("evidence_refs", []) + assessment.get("supporting_evidence_ids", [])
            + assessment.get("contradicting_evidence_ids", [])
            + [i for c in assessment.get("claims", []) for i in c["evidence_ids"]])
    text = " ".join(str(assessment.get(k, "")) for k in ("explanation", "rationale"))
    grounding = check_grounding(text, refs, projection)
    # When a whole value was cut, absence from the parsed value cannot disprove a claim.
    # Keep these legacy regex flags as suspects, explicitly unverified.
    claim_flags = []
    for n, claim in enumerate(assessment.get("claims", [])):
        cited = set(claim["evidence_ids"])
        if claim["kind"] == "OBSERVED":
            if not cited:
                claim_flags.append([n, "observed_without_source"])
            if cited & set(incomplete):
                claim_flags.append([n, "source_incomplete_requires_verification"])
            local = {"observations": [e for e in projection["observations"] if e["evidence_id"] in cited]}
            result = check_grounding(claim["text"], claim["evidence_ids"], local)
            if not result["grounded"]:
                claim_flags.append([n, "specific_not_supported_by_cited_visible_source"])
    flags = []
    if set(refs) - ids:
        flags.append("unknown_or_not_visible_evidence_id")
    if (set(assessment.get("supporting_evidence_ids", []))
            | set(assessment.get("contradicting_evidence_ids", []))) & pred_ids:
        flags.append("prediction_used_as_own_corroboration")
    if assessment.get("alignment") == "INSUFFICIENT_EVIDENCE" and assessment.get("confidence_in_assessment") == "HIGH":
        # High certainty of insufficiency can be legitimate; require an explicit limitation.
        if not assessment.get("uncertainty_notes"):
            flags.append("high_confidence_without_limitation")
    if re.search(r"\b(?:\d+(?:\.\d+)?%\s*(?:probability|chance|certain)|calibrated probability of|definitely (?:benign|malicious))", text, re.I):
        flags.append("false_confidence_or_probability_claim_suspected")
    consistency = check_consistency(assessment, static_label=prediction["predicted_label"],
                                    raw_score=prediction["raw_score"], threshold=prediction["threshold"])
    effective = dict(consistency["safe_recommendation"])
    if flags or claim_flags or not grounding["grounded"]:
        effective.update(action="MANUAL_REVIEW", priority="HIGH", review_required=True)
        effective["derivation"] = effective["derivation"] + ["evidence screening requires human verification"]
    return {"citation_count": len(refs), "valid_citation_count": sum(i in ids for i in refs),
            "invalid_ids": sorted(set(refs) - ids), "grounding_screen": grounding,
            "claim_flags": claim_flags, "flags": flags,
            "incomplete_visible_ids": incomplete, "consistency": consistency,
            "effective_recommendation": effective,
            "semantic_grounding": "NOT_ESTABLISHED_RULE_SCREEN_ONLY"}
