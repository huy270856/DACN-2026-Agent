"""Versioned action wrapper around the unchanged 06A assessment v2.1."""
import copy
import json
from jsonschema import Draft202012Validator, ValidationError
from evaluation.task06a.schema_v2 import OLLAMA_FORMAT_SCHEMA_V2

IDS = {"type": "array", "maxItems": 3, "uniqueItems": True, "items": {"type": "string", "minLength": 1}}
FORMAT = {"type": "object", "additionalProperties": False,
          "required": ["action", "case_id", "case_revision", "reason", "evidence_refs"],
          "properties": {
              "action": {"type": "string", "enum": ["TOOL_CALL", "FINISH", "REQUEST_MORE_EVIDENCE"]},
              "case_id": {"type": "string"}, "case_revision": {"type": "integer", "minimum": 1},
              "reason": {"type": "string", "minLength": 1}, "evidence_refs": IDS,
              "tool": {"type": "object", "additionalProperties": False,
                       "required": ["tool_id", "tool_version", "provider_id", "arguments"],
                       "properties": {"tool_id": {"type": "string"}, "tool_version": {"type": "string"},
                                      "provider_id": {"type": "string"}, "arguments": {"type": "object",
                                        "additionalProperties": False, "required": ["max_entries"],
                                        "properties": {"max_entries": {"const": 64}}}}},
              "assessment": copy.deepcopy(OLLAMA_FORMAT_SCHEMA_V2["properties"]["assessment"]),
              "old_evidence_ids": IDS, "new_evidence_ids": IDS,
              "new_fact_uses": {"type": "array", "maxItems": 3, "items": {
                  "type": "object", "additionalProperties": False,
                  "required": ["evidence_id", "library", "symbol", "why_relevant"],
                  "properties": {k: {"type": "string", "minLength": 1} for k in ("evidence_id", "library", "symbol", "why_relevant")}}},
              "assessment_changed": {"type": "boolean"}, "change_explanation": {"type": "string", "minLength": 1},
              "stop_reason": {"type": "string", "minLength": 1}}}


def parse(raw):
    obj = json.loads(raw)
    try:
        Draft202012Validator(FORMAT).validate(obj)
    except ValidationError as exc:
        raise ValueError("Invalid action schema: " + exc.message) from exc
    if obj["action"] == "TOOL_CALL" and "tool" not in obj:
        raise ValueError("TOOL_CALL requires tool")
    if obj["action"] == "FINISH":
        for key in ("assessment", "old_evidence_ids", "new_evidence_ids", "new_fact_uses", "assessment_changed", "change_explanation", "stop_reason"):
            if key not in obj:
                raise ValueError("FINISH requires " + key)
    return obj


def for_context(ctx):
    """Capability mask only: FINISH remains an option when a tool is available."""
    contract = copy.deepcopy(FORMAT)
    tools = ctx["facts"]["available_tools"]
    if not tools:
        contract["properties"]["action"]["enum"] = ["FINISH", "REQUEST_MORE_EVIDENCE"]
        contract["properties"].pop("tool")
    elif len(tools) == 1:
        for key in ("tool_id", "tool_version", "provider_id"):
            contract["properties"]["tool"]["properties"][key] = {"const": tools[0][key]}
    return contract
