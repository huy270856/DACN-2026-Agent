"""D1 - Orchestrator Core for the D.0 Trusted Tool Orchestrator.

D1 COMPOSES the real modules; it does not reimplement D2-D9. It drives one tool
call through the documented lifecycle (docs/d0/02_CONTRACTS_AND_LIFECYCLE.md):

    PROPOSED -> VALIDATED -> POLICY_EVALUATED
        | DENY            -> note + REJECTED (no execution)
        | REQUIRE_APPROVAL-> WAITING_APPROVAL (no execution here)
        | ALLOW
        v
    ADMITTED -> TARGET_REVALIDATED -> RUNNING (D5/D6)
        -> VALIDATE (D7) -> SIGN (D8) -> COMMIT (D9, revision-aware) -> Node C

Guarantees:
  * Fail-closed: any error/uncertainty yields REJECTED/FAILED, never execution.
  * Idempotency: a durable JSONL run ledger keyed by call_id + canonical payload
    digest. Same call_id + same payload that already reached a terminal state is
    returned without re-executing; same call_id + different payload raises
    IdempotencyConflict. No blind retry of a call that already started.
  * Concurrency: the final COMMIT uses D9's revision-aware compare-and-swap
    (expected_revision under the Node C lock). A stale revision aborts safely
    (CASE_REVISION_STALE) rather than overwriting a newer case; the caller replans.
  * Cancellation/timeout: a threading.Event is threaded down to D5/D6.
  * Durable audit: every terminal run is appended to the run ledger.

Trust: provider/tool output is UNTRUSTED_CONTENT; D1 never interprets it as
instructions. Signing keys come from D8 and are never exposed to tools/Agent.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

import case_manager as cm
from d0.validate import digest
from orchestrator import registry as d2
from orchestrator.input_validator import validate_tool_call, ValidationError
from orchestrator.policy_engine import PolicyEngine, PolicyError
from orchestrator.provider_install import ProviderInstallError
from orchestrator.result_validator import ResultValidationError
from orchestrator.case_bridge import CaseBridge, StaleRevisionError
from orchestrator.execution_adapter import ember_result_from_execution


class OrchestratorError(Exception):
    """Base error for the D1 orchestrator."""


class IdempotencyConflict(OrchestratorError):
    """Same call_id re-submitted with a different canonical payload."""


# Default per-tool D5->D7 normalizers (extend for new tools; no generic fake builder).
DEFAULT_RESULT_ADAPTERS: Dict[str, Callable] = {
    "static.ember_features": ember_result_from_execution,
}

_TERMINAL = {"SUCCESS", "PARTIAL", "FAILED", "TIMEOUT", "CANCELLED", "DENY", "REJECTED"}


@dataclass
class RunRecord:
    call_id: Optional[str]
    phase: str                      # terminal phase reached
    outcome: str                    # SUCCESS/PARTIAL/FAILED/TIMEOUT/CANCELLED/DENY/REQUIRE_APPROVAL/REJECTED
    reason_code: Optional[str] = None
    run_id: Optional[str] = None
    decision_id: Optional[str] = None
    revision: Optional[int] = None
    payload_digest: Optional[str] = None
    error: Optional[str] = None
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_terminal(self) -> bool:
        return self.outcome in _TERMINAL


class Orchestrator:
    """Composes D2/D3/D4/D8/D5/D6/D7/D9 to run one tool call end to end."""

    def __init__(self, *, registry, policy: PolicyEngine, signer, installation,
                 bridge: CaseBridge, artifact_root: Path | str, run_ledger_path: Path | str,
                 executor_factory: Optional[Callable] = None,
                 result_adapters: Optional[Mapping[str, Callable]] = None):
        self._registry = registry
        self._policy = policy
        self._signer = signer
        self._installation = installation
        self._bridge = bridge
        self._artifact_root = Path(artifact_root)
        self._ledger_path = Path(run_ledger_path)
        self._result_adapters = dict(result_adapters or DEFAULT_RESULT_ADAPTERS)
        self._lock = threading.Lock()
        if executor_factory is None:
            from orchestrator.executor import ToolExecutor
            executor_factory = lambda root: ToolExecutor(root)
        self._executor_factory = executor_factory

    # -- public API ---------------------------------------------------------
    def run_tool_call(self, call: Mapping[str, Any], case_path: Path | str, *,
                      cancel: Optional[threading.Event] = None,
                      input_schemas: Optional[Mapping[str, Any]] = None) -> RunRecord:
        call = dict(call)
        case_path = Path(case_path)
        call_id = call.get("call_id")
        payload_digest = digest(call)

        # 1. PROPOSED - idempotency against the durable run ledger.
        prior = self._lookup(call_id, payload_digest)
        if prior is not None:
            return prior

        record = self._run(call, case_path, call_id, payload_digest, cancel, input_schemas)
        self._append(record)
        return record

    # -- lifecycle ----------------------------------------------------------
    def _run(self, call, case_path, call_id, payload_digest, cancel, input_schemas) -> RunRecord:
        def rejected(phase, code, error=None, **kw):
            return RunRecord(call_id=call_id, phase=phase, outcome="REJECTED",
                             reason_code=code, payload_digest=payload_digest, error=error, **kw)

        # 2. Read the case snapshot from Node C.
        try:
            state = cm.validate_case(cm.read_json(case_path))
            snapshot = {"case_id": state["case_id"], "revision": state.get("revision", 1),
                        "target_ref": state["target_ref"]}
        except Exception as exc:
            return rejected("PROPOSED", "INTERNAL_ERROR", f"Case unreadable: {exc}")

        # 3. VALIDATED - D2 lookup + D3 validation.
        try:
            spec = self._registry.get_tool(call["tool_id"], call.get("tool_version"),
                                           require_enabled=True)
        except d2.ToolDisabledError as exc:
            return rejected("VALIDATED", "TOOL_DISABLED", str(exc))
        except d2.ToolUnknownError as exc:
            return rejected("VALIDATED", "TOOL_UNKNOWN", str(exc))
        except d2.RegistryError as exc:
            return rejected("VALIDATED", "INTERNAL_ERROR", str(exc))
        provider_available = self._registry.is_provider_available(spec["provider"]["id"])
        try:
            validate_tool_call(call, spec, snapshot, input_schemas=input_schemas,
                               provider_available=provider_available)
        except ValidationError as exc:
            return rejected("VALIDATED", exc.code, exc.message)

        # 4. POLICY_EVALUATED - D4.
        try:
            decision = self._policy.evaluate(call, spec, snapshot)
        except PolicyError as exc:
            return rejected("POLICY_EVALUATED", "POLICY_DENIED", str(exc))
        decision_id = decision["decision_id"]
        if decision["outcome"] == "DENY":
            self._note_denied(case_path, call, decision)
            return RunRecord(call_id=call_id, phase="POLICY_EVALUATED", outcome="DENY",
                             reason_code=decision["reason_code"], decision_id=decision_id,
                             revision=snapshot["revision"], payload_digest=payload_digest)
        if decision["outcome"] == "REQUIRE_APPROVAL":
            # Tool-call approval gate: not admitted here. No execution. An authenticated
            # analyst step (out-of-band) must re-submit; D.0 defines no tool-call
            # approval wire schema, so we fail closed to WAITING_APPROVAL.
            return RunRecord(call_id=call_id, phase="WAITING_APPROVAL", outcome="REQUIRE_APPROVAL",
                             reason_code=decision["reason_code"], decision_id=decision_id,
                             revision=snapshot["revision"], payload_digest=payload_digest)

        # 5. ADMITTED -> TARGET_REVALIDATED -> RUNNING (D5/D6).
        try:
            adapter = self._installation.pinned_adapter_for(spec)
        except ProviderInstallError as exc:
            return rejected("ADMITTED", "PROVIDER_UNAVAILABLE", str(exc), decision_id=decision_id)
        executor = self._executor_factory(self._artifact_root)
        try:
            output = executor.execute(call, spec, decision, snapshot, adapter, cancel=cancel)
        except Exception as exc:
            code = getattr(exc, "code", "INTERNAL_ERROR")
            return rejected("RUNNING", code, str(exc), decision_id=decision_id)

        # 6. VALIDATE (D7) via the per-tool normalizer.
        normalizer = self._result_adapters.get(call["tool_id"])
        if normalizer is None:
            return rejected("VALIDATE", "RESULT_INVALID",
                            f"No D7 normalizer registered for {call['tool_id']}",
                            run_id=output.receipt.get("run_id"), decision_id=decision_id)
        try:
            tool_result = normalizer(output, call, spec, artifact_root=executor.root)
        except ResultValidationError as exc:
            return rejected("VALIDATE", exc.code, exc.message,
                            run_id=output.receipt.get("run_id"), decision_id=decision_id)

        # 7. SIGN (D8) + 8. COMMIT (D9, revision-aware).
        try:
            commit = self._bridge.commit_tool_result(
                case_path, tool_result, output.receipt,
                trusted_key=self._signer.tool_key(),
                expected_revision=snapshot["revision"])
        except StaleRevisionError as exc:
            # Concurrent writer changed the case; caller must replan (no overwrite).
            return rejected("COMMIT", "CASE_REVISION_STALE", str(exc),
                            run_id=output.receipt.get("run_id"), decision_id=decision_id)
        except Exception as exc:
            return rejected("COMMIT", "INTERNAL_ERROR", str(exc),
                            run_id=output.receipt.get("run_id"), decision_id=decision_id)

        return RunRecord(
            call_id=call_id, phase="COMMITTED", outcome=tool_result["status"],
            reason_code=None, run_id=output.receipt.get("run_id"), decision_id=decision_id,
            revision=commit["revision"], payload_digest=payload_digest,
            error=(tool_result.get("error") or {}).get("code") if tool_result.get("error") else None)

    # -- helpers ------------------------------------------------------------
    def _note_denied(self, case_path, call, decision) -> None:
        """Record a policy denial as a Node C NOTE (never as a tool success)."""
        try:
            cm.apply_update(case_path, "action", {
                "event_id": f"NOTE-POLICY-DENY-{decision['decision_id'][:28]}",
                "action": "NOTE", "actor": "D4_POLICY_ENGINE",
                "reason": f"Tool call {call.get('call_id')} DENIED: {decision['reason_code']}"})
        except Exception:
            # Denial record is best-effort; the run ledger still captures the DENY.
            pass

    def _lookup(self, call_id, payload_digest) -> Optional[RunRecord]:
        if not self._ledger_path.exists() or call_id is None:
            return None
        with self._lock:
            for raw in self._ledger_path.read_text(encoding="utf-8").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                rec = json.loads(raw)
                if rec.get("call_id") == call_id:
                    if rec.get("payload_digest") == payload_digest:
                        return RunRecord(**rec)
                    raise IdempotencyConflict(
                        f"call_id {call_id} re-submitted with a different payload")
        return None

    def _append(self, record: RunRecord) -> None:
        if not record.is_terminal():
            return
        with self._lock:
            self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
                f.flush()
