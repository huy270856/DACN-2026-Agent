"""TASK 07B: v4 controller over the existing Controller → D4 → D5/D6 → D7 → D8 → D9 path.

Unlike `investigation_v3.workflow.InvestigationController` (frozen; hardcodes the v3 imports tool),
the follow-up tools are given by TRUSTED configuration as ToolBinding(tool_id, facet, arguments).
The model never supplies arguments: proposals only name a listed tool, and the trusted
arguments are filled here. Default-deny is unchanged (D4 still decides on every call).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping

from agent.controller import Controller


@dataclass(frozen=True)
class ToolBinding:
    tool_id: str
    facet: str
    arguments: Mapping[str, Any]

    def args(self) -> Dict[str, Any]:
        return copy.deepcopy(dict(self.arguments))


class V4Controller(Controller):
    """Uses Controller private helpers `_seen_toolcalls`, `_denied_tools`, `_toolcall_key`,
    `_build_toolcall` (stable since TASK 04; covered by tests here)."""

    def __init__(self, registry, orch, cfg, state, policy, tools: Iterable[ToolBinding]):
        super().__init__(registry, orch, cfg)
        self.policy = policy
        self.tools: List[ToolBinding] = list(tools)
        attempted = {r.get("tool") for r in state.get("tool_runs", [])}
        for b in self.tools:
            spec = self._spec(b.tool_id)
            if spec is None:
                continue
            # A facet already committed (or a persisted run) is never offered again.
            if (any(e.get("facet") == b.facet for e in state.get("evidence", []))
                    or b.tool_id.replace(".", "_") in attempted or b.tool_id in attempted):
                self._seen_toolcalls.add(self._toolcall_key(spec["tool_id"], spec["tool_version"],
                                                            spec["provider"]["id"], b.args(), state["target_ref"]))

    def _spec(self, tool_id):
        for spec in self._registry.list_tools(only_enabled=True):
            if spec["tool_id"] == tool_id:
                return spec
        return None

    def binding(self, tool_id) -> ToolBinding:
        for b in self.tools:
            if b.tool_id == tool_id:
                return b
        raise KeyError(tool_id)

    def available_tools(self, state) -> List[Dict[str, Any]]:
        out = []
        for b in self.tools:
            spec = self._spec(b.tool_id)
            if spec is None or not self._registry.is_provider_available(spec["provider"]["id"]):
                continue
            identity = (spec["tool_id"], spec["tool_version"], spec["provider"]["id"])
            if identity in self._denied_tools:
                continue
            if self._toolcall_key(*identity, b.args(), state["target_ref"]) in self._seen_toolcalls:
                continue
            tool = dict(zip(("tool_id", "tool_version", "provider_id"), identity), arguments=b.args())
            if self.policy.evaluate(self._build_toolcall(tool, state), spec, state)["outcome"] == "ALLOW":
                out.append(spec)
        return out

    def tool_proposal(self, spec, state, reason: str) -> Dict[str, Any]:
        """Controller-shaped TOOL_CALL with TRUSTED arguments for an offered spec."""
        b = self.binding(spec["tool_id"])
        return {"action": "TOOL_CALL", "case_id": state["case_id"], "case_revision": state["revision"],
                "reason": reason or "agent-selected analyzer", "evidence_refs": [], "unknowns_targeted": [],
                "tool": {"tool_id": spec["tool_id"], "tool_version": spec["tool_version"],
                         "provider_id": spec["provider"]["id"], "arguments": b.args()}}

    @staticmethod
    def finish_proposal(state, rationale: str) -> Dict[str, Any]:
        """Controller-shaped FINISH; the substantive verdict stays INSUFFICIENT_EVIDENCE (no relabel)."""
        return {"action": "FINISH", "case_id": state["case_id"], "case_revision": state["revision"],
                "reason": (rationale or "answer")[:600], "evidence_refs": [], "unknowns_targeted": [],
                "finding": {"verdict": "INSUFFICIENT_EVIDENCE", "confidence": 0.0,
                            "rationale": (rationale or "answer")[:900], "limitations": []}}
