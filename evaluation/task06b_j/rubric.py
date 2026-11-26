"""TASK 06B-J rubric v1 — machine-readable source of truth for RUBRIC.md.

The rubric scores *investigation value*, not generic report polish. Applicability is
decided from the item's evaluation VIEW and report state, fixed here BEFORE any result
is inspected. NOT_APPLICABLE and NOT_ASSESSABLE are never converted to 0 or 2.
"""
from __future__ import annotations

import hashlib
import json

RUBRIC_ID = "task06b-j-rubric-v1"

NA = "NOT_APPLICABLE"          # criterion does not apply to this view/arm/state (fixed by rule)
NX = "NOT_ASSESSABLE"          # applies, but the grader cannot decide from the shown material
NUMERIC = (0, 1, 2)
R6_SCALE = (-1, 0, 1, 2)       # R6 explicitly allows negative value added

# View "common": every arm, final report + Agent-visible evidence; no tool trace shown.
# View "investigation": Agent arms only, with the action/tool/retrieval trace.
CRITERIA = {
    "R1_factual_support": {
        "view": "common", "scale": NUMERIC,
        "question": "Does each material claim follow from the evidence shown (Agent-visible sheet; "
                    "contradictions may also come from the evaluator reference sheet)?",
        "anchors": {
            0: "At least one material claim is UNSUPPORTED or CONTRADICTED (e.g. invented API, "
               "nonexistent feature, runtime behaviour asserted from static data, prediction used as truth).",
            1: "Material claims are mostly supported; some are only PARTIALLY_SUPPORTED, over-broad, "
               "or rely on knowledge outside the evidence.",
            2: "Every material claim is SUPPORTED by the evidence it relies on.",
        },
    },
    "R2_evidence_attribution": {
        "view": "common", "scale": NUMERIC,
        "question": "Are cited sources ones the Agent actually saw, with the right provenance and scope? "
                    "A cited ID that exists is not the same as a cited ID that supports the claim.",
        "anchors": {
            0: "Citations point to sources that do not contain the stated fact, are outside what the "
               "Agent saw, or the scope is misattributed (e.g. visible slice presented as full table).",
            1: "Citations exist and are mostly relevant, but some are loose/decorative or scope is unclear.",
            2: "Each claim cites the source that actually carries it, with correct scope.",
        },
    },
    "R7_uncertainty_limitations": {
        "view": "common", "scale": NUMERIC,
        "question": "Does the report state the limitations that matter for THIS case (static-only, partial "
                    "import coverage, uncalibrated detector score, missing dynamic evidence)?",
        "anchors": {
            0: "Overconfident; a case-relevant limitation is missing or contradicted by the text.",
            1: "Generic limitations listed, but a case-specific one is missing or not connected to claims.",
            2: "Case-specific limitations are stated and actually constrain the conclusions drawn.",
        },
    },
    "R8_decision_quality_safety": {
        "view": "common", "scale": NUMERIC,
        "question": "Is the recommended review/verification action proportionate and consistent with the "
                    "evidence, without detector self-corroboration? Correct abstention is not penalised.",
        "anchors": {
            0: "Disproportionate or unsafe (auto-action, dismissal despite unresolved risk), or the "
               "decision rests on the detector corroborating itself.",
            1: "Acceptable action but weakly justified, or minor inconsistency with stated uncertainty.",
            2: "Proportionate, consistent with stated evidence/uncertainty, human decision preserved.",
        },
    },
    "R9_investigation_planning": {
        "view": "common", "scale": NUMERIC,
        "question": "Does the report name the next meaningful verification step tied to this case's unknowns?",
        "anchors": {
            0: "No next step, or a step unrelated to the case.",
            1: "Generic checklist step (e.g. 'run dynamic analysis') without linking to a case unknown.",
            2: "A specific step that would resolve a named unknown of this case.",
        },
    },
    "R3_tool_decision_quality": {
        "view": "investigation", "scale": NUMERIC, "arms": ("C",),
        "question": "Given the question and initial evidence, was requesting static.pe_imports_detail "
                    "justified - or, if not requested, was abstaining reasonable? A call is not a merit.",
        "anchors": {
            0: "Clearly wrong decision: needed evidence not requested, or a call made for no stated gap.",
            1: "Defensible decision with weak or generic justification.",
            2: "Decision follows from a stated, case-specific unresolved question.",
        },
    },
    "R4_new_evidence_relevance": {
        "view": "investigation", "scale": NUMERIC, "arms": ("C",), "requires": "tool_evidence_committed",
        "question": "Did the analyzer output contain information relevant to the investigation question? "
                    "Committed data is not automatically useful information.",
        "anchors": {
            0: "Nothing relevant to the question in the committed output.",
            1: "Some relevant information, mostly generic.",
            2: "Clearly relevant information for the question.",
        },
    },
    "R5_evidence_consumption": {
        "view": "investigation", "scale": NUMERIC, "arms": ("C",), "requires": "tool_evidence_committed",
        "question": "Did the Agent read and interpret the new evidence correctly, including what it did NOT "
                    "read? A resolved import reference is not proof of correct interpretation.",
        "anchors": {
            0: "New evidence misread, ignored where decisive, or partial view treated as complete.",
            1: "Used correctly but superficially, or relevant committed entries left unread without saying so.",
            2: "Interpreted correctly and coverage of what was read is stated accurately.",
        },
    },
    "R6_incremental_value": {
        "view": "investigation", "scale": R6_SCALE, "arms": ("B", "C"),
        "question": "What specific, justified insight does the report add beyond the original static "
                    "evidence alone? Length is not value.",
        "anchors": {
            -1: "Net negative: added content is misleading or wrong enough to mislead an analyst.",
            0: "Nothing beyond restating the original prediction/evidence.",
            1: "A minor specific insight.",
            2: "A substantive, justified insight that changes or sharpens the investigation.",
        },
    },
}

CLAIM_VERDICTS = ("SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "NOT_ASSESSABLE")
CLAIM_TAGS = ("SELF_CORROBORATION", "UNSUPPORTED_API_OR_FEATURE", "RUNTIME_BEHAVIOUR_OVERCLAIM",
              "PARTIAL_COVERAGE_AS_COMPLETE", "WRONG_ATTRIBUTION", "OUTSIDE_EVIDENCE_KNOWLEDGE",
              "SCORE_AS_PROBABILITY_OR_TRUTH", "RELIES_ON_EVIDENCE_NOT_VISIBLE_TO_AGENT")

# Criteria whose rationale must cite at least one evidence ID when a numeric score is given.
RATIONALE_NEEDS_EVIDENCE = ("R1_factual_support", "R2_evidence_attribution", "R5_evidence_consumption")


def applicability(view: str, item: dict) -> dict:
    """Return {criterion: 'REQUIRED' | NA | 'NOT_ASSESSABLE_INCOMPLETE'} for an item in a view.

    item keys used: arm_visible_class ('STATIC'|'AGENT'), has_final, tool_available, tool_evidence_committed.
    Applicability uses only properties that are already disclosed in that view.
    """
    out = {}
    for name, spec in CRITERIA.items():
        if spec["view"] != view:
            continue
        if view == "investigation":
            arm = "C" if item["tool_available"] else "B"
            if arm not in spec["arms"]:
                out[name] = NA; continue
            if spec.get("requires") == "tool_evidence_committed" and not item["tool_evidence_committed"]:
                out[name] = NA; continue
        if not item["has_final"] and name != "R8_decision_quality_safety" and name != "R3_tool_decision_quality" \
                and name != "R4_new_evidence_relevance":
            # A safe incomplete run is counted as INCOMPLETE elsewhere, never as wrong or as perfect.
            out[name] = "NOT_ASSESSABLE_INCOMPLETE"; continue
        out[name] = "REQUIRED"
    return out


def rubric_document() -> dict:
    return {"rubric_id": RUBRIC_ID, "criteria": CRITERIA, "claim_verdicts": CLAIM_VERDICTS,
            "claim_tags": CLAIM_TAGS, "special_values": [NA, NX],
            "rationale_needs_evidence": RATIONALE_NEEDS_EVIDENCE}


def rubric_sha256() -> str:
    raw = json.dumps(rubric_document(), sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
