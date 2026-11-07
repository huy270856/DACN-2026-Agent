"""D4 - Policy Engine for the D.0 Trusted Tool Orchestrator.

Pure, deterministic, side-effect-free authorization of a *tool call*. Produces a
``policy_decision`` (ALLOW / DENY / REQUIRE_APPROVAL) from a trusted
``PolicyConfig`` and the observed call/spec/case snapshot. It performs NO IO, NO
execution, NO signing and NO CaseState mutation.

Design invariants (docs/d0/01_ARCHITECTURE_AND_ADRS.md, 02_CONTRACTS_AND_LIFECYCLE.md):
  * Deny by default; every decision carries a stable ``reason_code``.
  * Authorization is derived ONLY from the trusted PolicyConfig and observed
    facts. Any ``budget`` / allowlist / "approved" hints that a ToolCall or Agent
    might carry are NEVER read as permission — the engine only reads the *request*
    and checks it against config. An Agent therefore cannot forge a ToolCall to
    self-approve or bypass D4.
  * Fail closed: any uncertainty or exception yields DENY.
  * Foreign-code / mutation / filesystem-writing tools require an isolated VM,
    which is not available in this milestone, so they are DENIED (ADR-003); no
    host execution of untrusted code is ever authorized.

This module does not decide *response-action* approval; that is D8
(``orchestrator.trust.ApprovalService``). ``REQUIRE_APPROVAL`` here means a tool
call needs an authenticated analyst gate before admission.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple

from d0.validate import validate, ContractError

_LIMIT_KEYS = ("timeout_ms", "max_output_bytes", "max_artifact_bytes", "max_concurrency")
_EFFECT_HOST_FORBIDDEN = ("executes_foreign_code", "mutates_target", "writes_filesystem")


class PolicyError(Exception):
    """Raised only when a call is too malformed to even reference in a decision.

    D1 MUST treat this as a fail-closed rejection (no execution), exactly like a
    DENY outcome.
    """


@dataclass(frozen=True)
class PolicyConfig:
    """Trusted operator configuration. NEVER sourced from Agent/ToolCall input.

    tool_allowlist: set of (tool_id, tool_version, provider_id) permitted to run.
    approval_required_capabilities: capabilities that force REQUIRE_APPROVAL.
    budget_caps: hard upper bounds per limit key (effective budget clamped to min
                 of spec limits, these caps, and the call's requested budget).
    require_verified_digest_for_file: FILE targets must carry a verified digest.
    policy_version: identifier recorded in every decision.
    """
    tool_allowlist: FrozenSet[Tuple[str, str, str]] = frozenset()
    approval_required_capabilities: FrozenSet[str] = frozenset()
    budget_caps: Mapping[str, int] = field(default_factory=lambda: {
        "timeout_ms": 60000, "max_output_bytes": 1 << 20,
        "max_artifact_bytes": 1 << 22, "max_concurrency": 1})
    require_verified_digest_for_file: bool = True
    policy_version: str = "policy-v1"


class PolicyEngine:
    """Deterministic deny-by-default policy evaluator (D4)."""

    def __init__(self, config: PolicyConfig) -> None:
        self._config = config

    def evaluate(self, call: Mapping[str, Any], spec: Mapping[str, Any],
                 case_snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        """Return a schema-valid ``policy_decision`` for this tool call.

        The decision is bound to the call's ``call_id``/``case_id``/
        ``expected_revision`` exactly as observed; D5 later refuses a policy whose
        binding does not match the call it is handed.
        """
        try:
            return self._evaluate(call, spec, case_snapshot)
        except Exception as exc:  # fail closed on ANY internal error
            try:
                return self._decision(call, "DENY", "internal_error",
                                      [f"Policy evaluation failed: {type(exc).__name__}"],
                                      self._clamp_limits(spec, call))
            except Exception as exc2:
                raise PolicyError(
                    "Call too malformed to reference in a decision; rejecting"
                ) from exc2

    # -- internals ----------------------------------------------------------
    def _evaluate(self, call, spec, case_snapshot):
        cfg = self._config
        # 1. Structural sanity of the inputs we authorize against (fail closed).
        for name, value in (("tool_call", call), ("tool_spec", spec)):
            try:
                validate(name, value)
            except (ContractError, ValueError, TypeError):
                return self._decision(call, "DENY", "schema_invalid",
                                      [f"Invalid {name} document"], cfg.budget_caps)

        effective = self._clamp_limits(spec, call)

        # 2. Allowlist (ADR-005: immutable, no silent fallback).
        identity = (call.get("tool_id"), call.get("tool_version"), call.get("provider_id"))
        if identity not in cfg.tool_allowlist:
            return self._decision(call, "DENY", "tool_not_allowlisted",
                                  [f"Tool/provider {identity} is not allowlisted"], effective)

        # 3. Effects that need an isolated VM are denied on host (ADR-003).
        effects = spec.get("effects", {})
        host_forbidden = [k for k in _EFFECT_HOST_FORBIDDEN if effects.get(k)]
        if host_forbidden:
            return self._decision(call, "DENY", "vm_required_unavailable",
                                  [f"Effect(s) {host_forbidden} require an isolated VM "
                                   "which is unavailable; host execution refused"], effective)

        # 4. Tools explicitly flagged for human approval, or whose capability is in
        #    the approval-required set, gate on an authenticated analyst (D8).
        capability = spec.get("capability")
        if effects.get("requires_human_approval") or capability in cfg.approval_required_capabilities:
            return self._decision(call, "REQUIRE_APPROVAL", "analyst_approval_required",
                                  ["Tool requires an authenticated analyst approval before admission"],
                                  effective)

        # 5. Target identity sufficiency for read-only FILE analysis.
        target_ref = call.get("target_ref", {})
        if target_ref.get("kind") == "FILE" and cfg.require_verified_digest_for_file:
            if (target_ref.get("identity_strength") == "UNAVAILABLE"
                    or not target_ref.get("verified_digest")):
                return self._decision(call, "DENY", "target_identity_insufficient",
                                      ["FILE target lacks a verified digest / strong identity"],
                                      effective)

        # 6. Hard budget ceiling: a request exceeding a cap is denied (not clamped).
        budget = call.get("budget", {})
        for key, requested in budget.items():
            cap = cfg.budget_caps.get(key)
            if cap is not None and isinstance(requested, int) and requested > cap:
                return self._decision(call, "DENY", "budget_exceeds_policy",
                                      [f"Requested {key}={requested} exceeds policy cap {cap}"],
                                      effective)

        # 7. Read-only, allowlisted, verified target, within budget -> ALLOW.
        return self._decision(call, "ALLOW", "static_readonly_allowed",
                              ["Read-only allowlisted tool on a verified target within budget"],
                              effective)

    def _clamp_limits(self, spec, call) -> Dict[str, int]:
        caps = self._config.budget_caps
        spec_limits = spec.get("limits", {}) if isinstance(spec, Mapping) else {}
        budget = call.get("budget", {}) if isinstance(call, Mapping) else {}
        out: Dict[str, int] = {}
        for key in _LIMIT_KEYS:
            candidates = [v for v in (spec_limits.get(key), caps.get(key), budget.get(key))
                          if isinstance(v, int) and not isinstance(v, bool)]
            out[key] = min(candidates) if candidates else int(caps.get(key, 1))
        return out

    def _decision(self, call, outcome, reason_code, reasons, effective_limits) -> Dict[str, Any]:
        decision = {
            "schema_version": "d0-v1",
            "decision_id": "POL-" + uuid.uuid4().hex,
            "call_id": call.get("call_id") if isinstance(call, Mapping) else None,
            "case_id": call.get("case_id") if isinstance(call, Mapping) else None,
            "expected_revision": call.get("expected_revision") if isinstance(call, Mapping) else None,
            "outcome": outcome,
            "reason_code": reason_code,
            "reasons": list(reasons),
            "effective_limits": {k: int(effective_limits[k]) for k in _LIMIT_KEYS},
            "policy_version": self._config.policy_version,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Defensive: a decision that is not schema-valid must fail closed, never be
        # emitted as a usable ALLOW.
        try:
            validate("policy_decision", decision)
        except (ContractError, ValueError, TypeError) as exc:
            raise ValueError(f"PolicyEngine produced an invalid decision: {exc}") from exc
        return decision
