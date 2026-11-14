"""Structured action contract for the investigation Agent.

The model proposes exactly one action per turn as JSON. This module parses and
shape-validates that JSON. Shape validity is necessary but NOT sufficient: the
Controller re-checks every id/revision/tool/param against the live system. The
model's text is data, never a command.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple

ACTIONS = ("TOOL_CALL", "FINISH", "REQUEST_DYNAMIC_ANALYSIS")
VERDICTS = ("MALICIOUS", "SUSPICIOUS", "BENIGN", "UNKNOWN", "INSUFFICIENT_EVIDENCE")

# JSON Schema handed to Ollama for constrained decoding (best-effort; re-validated here).
OLLAMA_FORMAT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "reason": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "unknowns_targeted": {"type": "array", "items": {"type": "string"}},
        "case_id": {"type": "string"},
        "case_revision": {"type": "integer"},
        "tool": {
            "type": "object",
            "properties": {
                "tool_id": {"type": "string"},
                "tool_version": {"type": "string"},
                "provider_id": {"type": "string"},
                "arguments": {"type": "object"},
            },
        },
        "finding": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": list(VERDICTS)},
                "confidence": {"type": "number"},
                "rationale": {"type": "string"},
                "limitations": {"type": "array", "items": {"type": "string"}},
                # Optional (TASK 05B): the agent's alignment ASSESSMENT relative to the
                # authoritative static LightGBM prediction. The agent never overrides the
                # static label; this only records agreement + a suggested handling.
                "assessment": {
                    "type": "object",
                    "properties": {
                        "alignment": {"type": "string",
                                      "enum": ["CONSISTENT", "CONFLICT", "INSUFFICIENT_EVIDENCE"]},
                        "review_required": {"type": "boolean"},
                        "recommendation": {"type": "string",
                                           "enum": ["MANUAL_REVIEW", "MONITOR",
                                                    "AVOID_EXECUTION", "CONSIDER_QUARANTINE"]},
                        "explanation": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
        },
    },
    "required": ["action", "reason", "case_id", "case_revision"],
}


class ActionError(ValueError):
    """Raised when the model output cannot be parsed or fails shape validation."""


def parse_action(raw: str) -> Dict[str, Any]:
    """Parse the model's raw text into a JSON object. No code is ever executed."""
    if not isinstance(raw, str) or not raw.strip():
        raise ActionError("Empty model output")
    text = raw.strip()
    try:
        obj = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ActionError(f"Model output is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ActionError("Model output JSON must be an object")
    return obj


def validate_shape(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the structural contract (not the live-system facts)."""
    from jsonschema import Draft202012Validator
    errors = list(Draft202012Validator(OLLAMA_FORMAT_SCHEMA).iter_errors(obj))
    if errors:
        raise ActionError(errors[0].message)
    action = obj.get("action")
    if action not in ACTIONS:
        raise ActionError(f"Unknown action: {action!r}")
    if not isinstance(obj.get("reason"), str) or not obj["reason"].strip():
        raise ActionError("reason is required")
    if not isinstance(obj.get("case_id"), str):
        raise ActionError("case_id is required")
    if type(obj.get("case_revision")) is not int:
        raise ActionError("case_revision must be an integer")
    for key in ("evidence_refs", "unknowns_targeted"):
        v = obj.get(key, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            raise ActionError(f"{key} must be a list of strings")
        obj.setdefault(key, [])

    if action == "TOOL_CALL":
        tool = obj.get("tool")
        if not isinstance(tool, dict):
            raise ActionError("TOOL_CALL requires a tool object")
        for f in ("tool_id", "tool_version", "provider_id"):
            if not isinstance(tool.get(f), str) or not tool[f]:
                raise ActionError(f"tool.{f} is required for TOOL_CALL")
        if not isinstance(tool.get("arguments", {}), dict):
            raise ActionError("tool.arguments must be an object")
        tool.setdefault("arguments", {})
    elif action == "FINISH":
        finding = obj.get("finding")
        if not isinstance(finding, dict):
            raise ActionError("FINISH requires a finding object")
        if finding.get("verdict") not in VERDICTS:
            raise ActionError("finding.verdict is invalid")
        conf = finding.get("confidence", 0.0)
        if not isinstance(conf, (int, float)) or isinstance(conf, bool) or not 0 <= conf <= 1:
            raise ActionError("finding.confidence must be between 0 and 1")
        if not isinstance(finding.get("rationale"), str) or not finding["rationale"].strip():
            raise ActionError("finding.rationale is required")
        finding.setdefault("limitations", [])
        if not isinstance(finding["limitations"], list) or any(not isinstance(x, str) for x in finding["limitations"]):
            raise ActionError("finding.limitations must be strings")
    # REQUEST_DYNAMIC_ANALYSIS needs only the common fields.
    return obj


def parse_and_validate(raw: str) -> Dict[str, Any]:
    return validate_shape(parse_action(raw))

# Constrain action-specific fields at decoding time as well as in Python.
OLLAMA_FORMAT_SCHEMA["required"] += ["evidence_refs", "unknowns_targeted"]
OLLAMA_FORMAT_SCHEMA["additionalProperties"] = False
for field, required in (("tool", ["tool_id", "tool_version", "provider_id", "arguments"]),
                        ("finding", ["verdict", "confidence", "rationale", "limitations"])):
    OLLAMA_FORMAT_SCHEMA["properties"][field]["required"] = required
    OLLAMA_FORMAT_SCHEMA["properties"][field]["additionalProperties"] = False

OLLAMA_FORMAT_SCHEMA["properties"]["evidence_refs"]["maxItems"] = 3

OLLAMA_FORMAT_SCHEMA["properties"]["case_revision"]["minimum"] = 1
OLLAMA_FORMAT_SCHEMA["properties"]["finding"]["properties"]["confidence"].update(minimum=0, maximum=1)
for key in ("case_id", "reason"):
    OLLAMA_FORMAT_SCHEMA["properties"][key]["minLength"] = 1
OLLAMA_FORMAT_SCHEMA["allOf"] = [
    {"if": {"properties": {"action": {"const": action}}},
     "then": {"required": required, "not": {"anyOf": [{"required": [f]} for f in forbidden]}}}
    for action, required, forbidden in (("TOOL_CALL", ["tool"], ["finding"]),
        ("FINISH", ["finding"], ["tool"]), ("REQUEST_DYNAMIC_ANALYSIS", [], ["tool", "finding"]))]
