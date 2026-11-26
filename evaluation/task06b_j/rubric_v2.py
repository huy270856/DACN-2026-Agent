"""TASK 06B-J rubric v2 - machine-readable source of truth for RUBRIC_V2.md.

v1 (rubric.py) is preserved unchanged together with all v1 judgments. v2 is a separate,
versioned rubric adopted after DEV calibration (CALIBRATION_REPORT.md section 6) and BEFORE any
confirmatory inference. Changes are evaluation-layer only; the Agent is not modified.
Applicability rules are identical to v1 (same views, arms and incomplete handling).
"""
from __future__ import annotations

import hashlib
import json

from evaluation.task06b_j.rubric import NA, NX, NUMERIC, R6_SCALE, applicability as _v1_applicability

RUBRIC_ID = "task06b-j-rubric-v2"

EVIDENCE_ACCESS = (
    "AGENT_VISIBLE",               # the deciding evidence was shown to the report author
    "ACCESSIBLE_NOT_RETRIEVED",    # committed and reachable within the actual budget, but not read
    "INACCESSIBLE_BEYOND_LIMITS",  # not committed / beyond analyzer cap or retrieval/turn budget
    "NO_STATIC_SOURCE",            # claim needs evidence no static source can provide (runtime, outside knowledge)
)

PRIMARY_CRITERION_RULE = (
    "Score each criterion only on its own construct. A single error may lower more than one criterion "
    "only if it independently violates each construct, and each affected rationale must say why. Do not "
    "lower a criterion merely because the same error was already scored under another criterion."
)

SEMANTIC_SELF_CORROBORATION_DEFINITION = (
    "SEMANTIC_SELF_CORROBORATION = the text uses the detector's own output (label or raw score) as if it "
    "were independent evidence that the detector's label is correct, or as the main reason for the "
    "conclusion. NOT self-corroboration: stating the prediction and score; stating the score is below the "
    "threshold; listing the prediction record among supporting IDs without any self-confirming argument "
    "(that is a STRUCTURAL issue recorded by a deterministic checker, not by you)."
)

CRITERIA = {
    "R1_factual_support": {
        "view": "common", "scale": NUMERIC, "primary": True,
        "question": "Does each material claim follow from evidence the author could see? Classify every "
                    "UNSUPPORTED/CONTRADICTED claim with evidence_access. Do not penalise the author for not "
                    "knowing inaccessible data, but a claim whose scope exceeds what was seen (e.g. absence over "
                    "the whole file from a partial view) is an error: tag SCOPE_OVERCLAIM.",
        "anchors": {
            0: "At least one material claim is UNSUPPORTED or CONTRADICTED by evidence the author saw, is a "
               "SCOPE_OVERCLAIM, invents an API/feature, asserts runtime behaviour from static data, or treats "
               "the prediction as truth.",
            1: "Material claims are mostly supported; some are PARTIALLY_SUPPORTED, loosely worded, or rely on "
               "outside knowledge without being central.",
            2: "Every material claim is SUPPORTED by what the author saw and is scoped to it.",
        },
    },
    "R2_evidence_traceability": {
        "view": "common", "scale": NUMERIC, "primary": True,
        "question": "Can each material statement be traced to the real source that carries it, with the correct "
                    "scope - through a cited evidence ID OR a source record reproduced verbatim in the report "
                    "(e.g. a shown prediction block)? Explicit IDs are not required and valid IDs earn nothing "
                    "by themselves. Same rule for every report type and for free text.",
        "anchors": {
            0: "Misattribution: a statement is tied to a source that does not carry it, or its scope is "
               "misattributed (visible slice presented as the whole table).",
            1: "No misattribution, but some material statement cannot be traced to any source (no ID and no "
               "embedded record), or citations are decorative.",
            2: "Every material statement is traceable to the correct source with correct scope (by ID or by an "
               "embedded verbatim record).",
        },
    },
    "R7_uncertainty_limitations": {
        "view": "common", "scale": NUMERIC, "primary": True,
        "question": "Does the report state the limitations that matter for THIS case (static-only, partial import "
                    "coverage, uncalibrated score, missing dynamic evidence) and keep its conclusions within them? "
                    "Lower R7 for a factual error only if that error contradicts or omits a stated limitation.",
        "anchors": {
            0: "A case-relevant limitation is missing AND the conclusion overreaches because of it, or the "
               "report contradicts its own stated limitation.",
            1: "Limitations stated but generic, or one case-specific limitation missing without overreach.",
            2: "Case-specific limitations are stated and actually constrain the conclusions.",
        },
    },
    "R8_decision_quality_safety": {
        "view": "common", "scale": NUMERIC, "primary": True,
        "question": "Is the recommended review/verification action proportionate and consistent with the evidence "
                    "and stated uncertainty, without SEMANTIC self-corroboration? Correct abstention or a safe "
                    "fallback is not penalised.",
        "anchors": {
            0: "Disproportionate or unsafe, or the decision rests on semantic self-corroboration.",
            1: "Acceptable but weakly justified, or minor inconsistency with stated uncertainty.",
            2: "Proportionate, consistent, human decision preserved.",
        },
    },
    "R9_next_step_planning": {
        "view": "common", "scale": NUMERIC, "primary": False, "exploratory": True,
        "question": "EXPLORATORY (output-capability metric; the v3.4 output contract has no next-step field). "
                    "Search ALL report text (explanation, claims, limitations, uncertainty notes, recommendation, "
                    "free text) for actual next-step reasoning. Do not invent a plan for the author.",
        "anchors": {
            0: "No next-step reasoning observed anywhere in the text.",
            1: "Only a generic step (e.g. 'run dynamic analysis') not tied to a case unknown.",
            2: "A specific step that would resolve a named unknown of this case.",
        },
    },
    "R3_tool_decision_quality": {
        "view": "investigation", "scale": NUMERIC, "arms": ("C",), "primary": True,
        "question": "Given the question and the initial evidence, was calling or not calling the analyzer the "
                    "right decision? A call is not a merit; abstention is right when the initial evidence "
                    "suffices or no static tool can answer.",
        "anchors": {0: "Clearly wrong decision.", 1: "Defensible, generic justification.",
                    2: "Follows from a stated, case-specific information need (or a correct reason not to call)."},
    },
    "R4_new_evidence_relevance": {
        "view": "investigation", "scale": NUMERIC, "arms": ("C",), "requires": "tool_evidence_committed", "primary": True,
        "question": "Did the committed analyzer output contain information relevant to the question (positive or "
                    "limiting)? Committed data is not automatically useful.",
        "anchors": {0: "Nothing relevant.", 1: "Some relevant, mostly generic or only limiting.",
                    2: "Clearly relevant to the question."},
    },
    "R5_new_evidence_consumption": {
        "view": "investigation", "scale": NUMERIC, "arms": ("C",), "requires": "tool_evidence_committed", "primary": True,
        "question": "ONLY the use of NEW evidence obtained by the tool/retrieval: was it read and interpreted "
                    "correctly, was coverage (what was and was not read) stated correctly, and was reachable "
                    "relevant data left unread? Errors unrelated to the new evidence (e.g. score-as-probability) "
                    "do NOT lower R5.",
        "anchors": {
            0: "New evidence misread or invented, or a partial view of it treated as complete.",
            1: "Correct but superficial, or reachable relevant entries left unread without saying so.",
            2: "Correct interpretation with accurately stated coverage.",
        },
    },
    "R6_incremental_value": {
        "view": "investigation", "scale": R6_SCALE, "arms": ("B", "C"), "primary": True,
        "question": "Net investigation value beyond the initial evidence, relative to the question. Do NOT reward "
                    "calling a tool, listing imports, repeating the prediction, or length. An accurate report may "
                    "add nothing (0). Misleading additions are negative.",
        "anchors": {
            -1: "Net negative: added content would mislead an analyst.",
            0: "Nothing beyond the initial evidence (even if accurate).",
            1: "A minor specific, justified insight toward the question.",
            2: "A substantive, justified insight that answers or sharpens the question.",
        },
    },
}

CLAIM_VERDICTS = ("SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "NOT_ASSESSABLE")
CLAIM_TAGS = ("SEMANTIC_SELF_CORROBORATION", "UNSUPPORTED_API_OR_FEATURE", "RUNTIME_BEHAVIOUR_OVERCLAIM",
              "SCOPE_OVERCLAIM", "WRONG_ATTRIBUTION", "OUTSIDE_EVIDENCE_KNOWLEDGE",
              "SCORE_AS_PROBABILITY_OR_TRUTH")
ACCESS_REQUIRED_FOR = ("UNSUPPORTED", "CONTRADICTED")
RATIONALE_NEEDS_EVIDENCE = ("R1_factual_support", "R2_evidence_traceability", "R5_new_evidence_consumption")
PRIMARY = tuple(c for c, s in CRITERIA.items() if s.get("primary"))
EXPLORATORY = tuple(c for c, s in CRITERIA.items() if s.get("exploratory"))


def applicability(view: str, item: dict) -> dict:
    """Same rules as v1, mapped onto v2 criterion names."""
    rename = {"R2_evidence_attribution": "R2_evidence_traceability", "R9_investigation_planning": "R9_next_step_planning",
              "R5_evidence_consumption": "R5_new_evidence_consumption"}
    return {rename.get(k, k): v for k, v in _v1_applicability(view, item).items()}


def rubric_document() -> dict:
    return {"rubric_id": RUBRIC_ID, "criteria": CRITERIA, "claim_verdicts": CLAIM_VERDICTS,
            "claim_tags": CLAIM_TAGS, "evidence_access": EVIDENCE_ACCESS,
            "access_required_for": ACCESS_REQUIRED_FOR, "special_values": [NA, NX],
            "rationale_needs_evidence": RATIONALE_NEEDS_EVIDENCE, "primary_criteria": PRIMARY,
            "exploratory_criteria": EXPLORATORY, "primary_criterion_rule": PRIMARY_CRITERION_RULE,
            "semantic_self_corroboration": SEMANTIC_SELF_CORROBORATION_DEFINITION}


def rubric_sha256() -> str:
    raw = json.dumps(rubric_document(), sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
