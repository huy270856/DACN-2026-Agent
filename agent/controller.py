"""Deterministic Controller: validates every model proposal and drives D1-D9.

The Controller is the trust gate between the (untrusted) model and the trusted
orchestrator. It NEVER executes model text; it only builds a schema-valid
ToolCall from a fully-validated proposal and calls Orchestrator.run_tool_call.
It enforces budgets, duplicate detection, revision checks and workflow gates.
It never edits effects to get past a D4 DENY.
"""
from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .config import AgentConfig


class ControllerReject(Exception):
    """A proposal was rejected deterministically (fed back to the model, not executed)."""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass
class Budget:
    cfg: AgentConfig
    started: float = field(default_factory=time.monotonic)
    iterations: int = 0
    tool_calls: int = 0
    tokens: int = 0

    def tick_iteration(self) -> None:
        self.iterations += 1

    def exhausted(self) -> Optional[str]:
        if self.tokens >= self.cfg.max_tokens:
            return "max_tokens"
        if self.iterations >= self.cfg.max_iterations:
            return "max_iterations"
        if self.tool_calls >= self.cfg.max_tool_calls:
            return "max_tool_calls"
        if time.monotonic() - self.started >= self.cfg.wall_clock_s:
            return "wall_clock"
        return None


class Controller:
    def __init__(self, registry, orchestrator, cfg: AgentConfig):
        self._registry = registry
        self._orch = orchestrator
        self._cfg = cfg
        self._denied_tools = set()
        self._seen_toolcalls: set[str] = set()

    # -- validation ---------------------------------------------------------
    def validate(self, proposal: Mapping[str, Any], state: Mapping[str, Any]) -> Dict[str, Any]:
        """Raise ControllerReject on any problem; else return the normalized proposal."""
        from .schema import validate_shape
        proposal = validate_shape(dict(proposal))
        if proposal["case_id"] != state["case_id"]:
            raise ControllerReject("CASE_MISMATCH", "case_id does not match the case")
        current_rev = state.get("revision", 1)
        if proposal["case_revision"] != current_rev:
            raise ControllerReject("CASE_REVISION_STALE",
                                   f"case_revision {proposal['case_revision']} != current {current_rev}")
        # Evidence refs must exist.
        known = {e.get("evidence_id") for e in state.get("evidence", [])}
        missing = [r for r in proposal.get("evidence_refs", []) if r not in known]
        if missing:
            raise ControllerReject("EVIDENCE_UNKNOWN", f"unknown evidence_refs: {missing}")

        unknowns = {u.get("facet") for u in state.get("residual_unknowns", [])}
        if set(proposal["unknowns_targeted"]) - unknowns:
            raise ControllerReject("UNKNOWN_FACET", "unknowns_targeted must name residual_unknowns facets")
        from orchestrator.workflow import WorkflowEngine
        static = [e for e in state.get("evidence", [])
                  if str(e.get("facet", "")).startswith("static.") and e.get("status") == "SUCCESS"]
        digest = (state.get("target_ref", {}).get("verified_digest") or {}).get("value")
        reputation = self._cfg.known_reputations.get(digest, "UNAVAILABLE")
        if reputation not in {"KNOWN_BENIGN", "KNOWN_MALICIOUS", "UNKNOWN", "UNAVAILABLE", "CONFLICT"}:
            reputation = "UNAVAILABLE"
        known_fresh = reputation in {"KNOWN_BENIGN", "KNOWN_MALICIOUS"}
        gate = WorkflowEngine().decide(state, phase="STATIC" if static else "REPUTATION",
                                      reputation=reputation, reputation_fresh_and_consistent=known_fresh,
                                      dynamic_needed=proposal["action"] == "REQUEST_DYNAMIC_ANALYSIS")
        if proposal["action"] == "REQUEST_DYNAMIC_ANALYSIS" and gate["next_step"] != "HUMAN_REVIEW":
            raise ControllerReject("STATIC_FIRST", "Static evidence required before escalation")
        if proposal["action"] == "FINISH" and not static and not known_fresh and not self._seen_toolcalls:
            raise ControllerReject("STATIC_FIRST", "Unknown reputation requires an approved static follow-up before assessment")
        if proposal["action"] == "FINISH" and proposal["finding"]["verdict"] not in ("UNKNOWN", "INSUFFICIENT_EVIDENCE"):
            expected = {"KNOWN_BENIGN": "BENIGN", "KNOWN_MALICIOUS": "MALICIOUS"}.get(reputation)
            cited = [e for e in state.get("evidence", []) if e.get("evidence_id") in proposal["evidence_refs"]]
            if not known_fresh or proposal["finding"]["verdict"] != expected or not any(
                    e.get("facet") == "sha256" and e.get("status") == "SUCCESS" and e.get("value") == digest for e in cited):
                raise ControllerReject("INSUFFICIENT_EVIDENCE", "Substantive verdict requires trusted hash reputation and successful digest citation")
        if proposal["action"] in ("FINISH", "REQUEST_DYNAMIC_ANALYSIS"):
            return dict(proposal)

        # TOOL_CALL: verify the tool against the live registry.
        tool = proposal["tool"]
        tid, tver, pid = tool["tool_id"], tool["tool_version"], tool["provider_id"]
        if (tid, tver, pid) in self._denied_tools:
            raise ControllerReject("TOOL_PREVIOUSLY_DENIED", "Policy denial cannot be retried with altered arguments")
        try:
            spec = self._registry.get_tool(tid, tver, require_enabled=True)
        except Exception as exc:
            raise ControllerReject("TOOL_UNKNOWN", f"tool not registered/enabled: {exc}")
        if spec["provider"]["id"] != pid:
            raise ControllerReject("PROVIDER_MISMATCH",
                                   f"provider {pid} != registered {spec['provider']['id']}")
        if state["target_ref"]["kind"] not in spec.get("supported_targets", []):
            raise ControllerReject("TARGET_UNSUPPORTED", "tool does not support this target kind")
        # Workflow gate (ADR-001): foreign-code/dynamic tools are not run on host;
        # the model must use REQUEST_DYNAMIC_ANALYSIS instead.
        if spec.get("effects", {}).get("executes_foreign_code"):
            raise ControllerReject("DYNAMIC_NOT_ALLOWED",
                                   "foreign-code tool requires REQUEST_DYNAMIC_ANALYSIS, not TOOL_CALL")
        # Duplicate detection.
        key = self._toolcall_key(tid, tver, pid, tool.get("arguments", {}),
                                 state["target_ref"])
        if key in self._seen_toolcalls:
            raise ControllerReject("DUPLICATE_TOOL_CALL", "this exact tool call was already attempted")
        if not str(spec.get("capability", "")).startswith("static.") or any(
                spec.get("effects", {}).get(k) for k in ("mutates_target", "requires_human_approval")):
            raise ControllerReject("WORKFLOW_GATE", "Only static follow-ups are enabled")
        from orchestrator.input_validator import validate_tool_call, ValidationError
        try:
            validate_tool_call(self._build_toolcall(tool, state), spec, state)
        except ValidationError as exc:
            raise ControllerReject(exc.code, exc.message) from exc
        return dict(proposal)

    # -- execution ----------------------------------------------------------
    def run_tool(self, proposal: Mapping[str, Any], state: Mapping[str, Any], case_path, remaining_s=None) -> Any:
        tool = proposal["tool"]
        call = self._build_toolcall(tool, state)
        if remaining_s is not None:
            if remaining_s < 0.001:
                raise ControllerReject("DEADLINE", "No execution time remains")
            call["budget"]["timeout_ms"] = min(call["budget"]["timeout_ms"], max(1, int(remaining_s * 1000)))
        key = self._toolcall_key(tool["tool_id"], tool["tool_version"], tool["provider_id"],
                                 tool.get("arguments", {}), state["target_ref"])
        self._seen_toolcalls.add(key)
        record = self._orch.run_tool_call(call, case_path)
        if record.outcome == "DENY":
            self._denied_tools.add((tool["tool_id"], tool["tool_version"], tool["provider_id"]))
        return record

    def _build_toolcall(self, tool: Mapping[str, Any], state: Mapping[str, Any]) -> Dict[str, Any]:
        spec = self._registry.get_tool(tool["tool_id"], tool["tool_version"], require_enabled=True)
        limits = spec["limits"]
        budget = {"timeout_ms": min(30000, limits["timeout_ms"]),
                  "max_output_bytes": min(200000, limits["max_output_bytes"])}
        return {
            "schema_version": "d0-v1",
            "call_id": "CALL-agent-" + uuid.uuid4().hex[:16],
            "case_id": state["case_id"],
            "expected_revision": state.get("revision", 1),
            "tool_id": tool["tool_id"], "tool_version": tool["tool_version"],
            "provider_id": tool["provider_id"],
            "target_ref": copy.deepcopy(state["target_ref"]),
            "arguments": copy.deepcopy(tool.get("arguments", {})),
            "reason": "agent-proposed investigation step",
            "requested_by": "agent",
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "budget": budget,
        }

    @staticmethod
    def _toolcall_key(tid, tver, pid, args, target_ref) -> str:
        import json
        return json.dumps([tid, tver, pid, args, target_ref.get("observed")],
                          sort_keys=True, ensure_ascii=False)
