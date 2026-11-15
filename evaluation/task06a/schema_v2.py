"""TASK 06A — Agent v2 structured evidence-assessment schema (ADDITIVE, versioned).

This schema is SEPARATE from the frozen production `agent/schema.py` (v1). It is
used only by the task06a assessment protocol; it does not touch production code or
the D0 contracts.

The central difference from v1: the assessment is no longer a single `alignment`
enum plus free text. The model must separately and explicitly list, by evidence_id:

  * supporting_evidence_ids   — observable evidence that SUPPORTS the static label
  * contradicting_evidence_ids — observable evidence that CONTRADICTS the static label
  * uncertainty_notes          — what is unknown / too thin to judge

`alignment` is then required to be consistent with that structure (checked
deterministically in consistency.py, not trusted from the model):

  * CONSISTENT  -> at least one supporting id AND no contradicting id
  * CONFLICT    -> at least one contradicting id
  * INSUFFICIENT_EVIDENCE -> neither side is substantive

This directly attacks the v1 failure where "CONSISTENT" was emitted by default as
mere absence-of-disconfirmation. The model's text remains DATA: every id is
re-checked against the real projection, every specific claim is re-checked by the
grounding verifier, and the final recommendation is re-derived deterministically.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

ALIGNMENTS = ("CONSISTENT", "CONFLICT", "INSUFFICIENT_EVIDENCE")
RECOMMENDATIONS = ("MANUAL_REVIEW", "MONITOR", "AVOID_EXECUTION", "CONSIDER_QUARANTINE")
CONF_LEVELS = ("LOW", "MEDIUM", "HIGH")

SCHEMA_ID = "task06a-assessment-v2"

# JSON schema handed to Ollama for constrained decoding (best-effort; re-validated here).
OLLAMA_FORMAT_SCHEMA_V2: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["case_id", "case_revision", "assessment"],
    "properties": {
        "case_id": {"type": "string", "minLength": 1},
        "case_revision": {"type": "integer", "minimum": 1},
        "assessment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["alignment", "supporting_evidence_ids", "contradicting_evidence_ids",
                         "uncertainty_notes", "review_required", "recommendation",
                         "confidence_in_assessment", "explanation"],
            "properties": {
                "alignment": {"type": "string", "enum": list(ALIGNMENTS)},
                "supporting_evidence_ids": {"type": "array", "items": {"type": "string"},
                                            "maxItems": 4},
                "contradicting_evidence_ids": {"type": "array", "items": {"type": "string"},
                                               "maxItems": 4},
                "uncertainty_notes": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "review_required": {"type": "boolean"},
                "recommendation": {"type": "string", "enum": list(RECOMMENDATIONS)},
                # Qualitative confidence in the ASSESSMENT reasoning — never the raw score.
                "confidence_in_assessment": {"type": "string", "enum": list(CONF_LEVELS)},
                "explanation": {"type": "string", "minLength": 1},
            },
        },
    },
}


class AssessmentErrorV2(ValueError):
    """Raised when a v2 model output cannot be parsed or fails shape validation."""


def parse_action_v2(raw: str) -> Dict[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        raise AssessmentErrorV2("Empty model output")
    try:
        obj = json.loads(raw.strip())
    except (ValueError, TypeError) as exc:
        raise AssessmentErrorV2(f"Model output is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise AssessmentErrorV2("Model output JSON must be an object")
    return obj


def validate_shape_v2(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Structural (shape) validation only. Live-system facts checked elsewhere."""
    from jsonschema import Draft202012Validator
    errors = list(Draft202012Validator(OLLAMA_FORMAT_SCHEMA_V2).iter_errors(obj))
    if errors:
        raise AssessmentErrorV2(errors[0].message)
    a = obj["assessment"]
    # Enforce list-of-strings (schema covers it, but keep an explicit guard).
    for key in ("supporting_evidence_ids", "contradicting_evidence_ids", "uncertainty_notes"):
        v = a.get(key, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            raise AssessmentErrorV2(f"assessment.{key} must be a list of strings")
    if not a.get("explanation", "").strip():
        raise AssessmentErrorV2("assessment.explanation is required")
    return obj


def parse_and_validate_v2(raw: str) -> Dict[str, Any]:
    return validate_shape_v2(parse_action_v2(raw))
