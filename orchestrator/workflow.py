"""D1 - Deterministic Workflow Engine (routing).

Emits a ``workflow_decision`` that routes an investigation through the workflow
state machine (docs/d0/02_CONTRACTS_AND_LIFECYCLE.md, ADR-001). Routing is
DETERMINISTIC and independent of any LLM: the Agent may only choose follow-ups
WITHIN these gates (``agent_role = FOLLOWUP_WITHIN_POLICY``), never override
static-first or VM isolation.

State machine:
    INTAKE -> REPUTATION
      KNOWN_BENIGN / KNOWN_MALICIOUS, fresh & consistent -> ASSESSMENT
      UNKNOWN / UNAVAILABLE / CONFLICT                    -> STATIC
    STATIC -> ASSESSMENT        (sufficient and policy permits)
    STATIC -> DYNAMIC           (more evidence needed AND isolated VM ready)
    STATIC -> HUMAN_REVIEW      (dynamic needed but VM unavailable)
    DYNAMIC -> ASSESSMENT or HUMAN_REVIEW
    ASSESSMENT -> RESPONSE -> ... (handled via response approval, not here)

Core rules: no inference from missing evidence to benign; UNKNOWN is not benign;
a VM-unavailable dynamic need routes to HUMAN_REVIEW, never host execution.
"""
from __future__ import annotations

import secrets
from typing import Any, Dict, Mapping

from d0.validate import validate

REPUTATIONS = {"KNOWN_MALICIOUS", "KNOWN_BENIGN", "UNKNOWN", "UNAVAILABLE", "CONFLICT"}


class WorkflowEngine:
    """Deterministic router producing schema-valid workflow_decision documents."""

    def decide(self, case_snapshot: Mapping[str, Any], *, phase: str, reputation: str,
               reputation_fresh_and_consistent: bool = False,
               static_sufficient: bool = False,
               dynamic_needed: bool = False,
               vm_ready: bool = False) -> Dict[str, Any]:
        if reputation not in REPUTATIONS:
            raise ValueError(f"Unknown reputation {reputation!r}")
        next_step, reason = self._route(
            phase, reputation, reputation_fresh_and_consistent,
            static_sufficient, dynamic_needed, vm_ready)
        decision = {
            "schema_version": "d0-v1",
            "workflow_id": "WF-" + secrets.token_hex(12),
            "case_id": case_snapshot["case_id"],
            "case_revision": int(case_snapshot["revision"]),
            "reputation": reputation,
            "phase": phase,
            "next_step": next_step,
            "reason_code": reason,
            "agent_role": "FOLLOWUP_WITHIN_POLICY",
        }
        validate("workflow_decision", decision)
        return decision

    def _route(self, phase, reputation, fresh_consistent, static_sufficient,
               dynamic_needed, vm_ready):
        if phase in ("INTAKE", "REPUTATION"):
            # Known + fresh + consistent may skip to assessment; otherwise static-first.
            if reputation in ("KNOWN_BENIGN", "KNOWN_MALICIOUS") and fresh_consistent:
                return "FINAL_ASSESSMENT", "known_reputation_fresh_consistent"
            # UNKNOWN / UNAVAILABLE / CONFLICT (and stale/inconsistent known) -> static.
            return "STATIC_ANALYSIS", "static_first_unknown_or_unverified"
        if phase == "STATIC":
            if not dynamic_needed and static_sufficient:
                return "FINAL_ASSESSMENT", "static_sufficient"
            if dynamic_needed and vm_ready:
                return "DYNAMIC_ANALYSIS", "dynamic_required_vm_ready"
            if dynamic_needed and not vm_ready:
                return "HUMAN_REVIEW", "dynamic_required_vm_unavailable"
            return "HUMAN_REVIEW", "static_inconclusive"
        if phase == "DYNAMIC":
            if static_sufficient or vm_ready:
                return "FINAL_ASSESSMENT", "dynamic_complete"
            return "HUMAN_REVIEW", "dynamic_inconclusive"
        if phase == "ASSESSMENT":
            return "STOP", "assessment_recorded"
        if phase in ("RESPONSE", "CLOSED"):
            return "STOP", "terminal_phase"
        # Fail safe: never infer benign; route to human review.
        return "HUMAN_REVIEW", "unrecognized_state_fail_safe"
