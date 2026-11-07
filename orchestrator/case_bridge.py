"""D9 - Case Bridge implementation for DACN D.0 Orchestrator.

Bridges D.0 validated and signed ToolResult + ExecutionReceipt into
Node C v1.2 CaseState while preserving full fidelity in an append-only
audit ledger. Enforces expected_revision preconditions and status/name projections.
"""
from __future__ import annotations
import copy
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from d0.validate import validate, digest, ContractError
import case_manager as cm
from bc_contracts import same_target_ref, validate_target_ref


class CaseBridgeError(Exception):
    """Base exception for Case Bridge operations."""
    pass


class StaleRevisionError(CaseBridgeError):
    """Raised when current Case revision does not match expected_revision."""
    pass


class DeniedToolResultCommitError(CaseBridgeError):
    """Raised when attempting to commit a DENIED result as a tool success."""
    pass


class ReceiptIntegrityError(CaseBridgeError):
    """Raised when receipt hash or binding does not match ToolResult."""
    pass


class TargetMismatchBridgeError(CaseBridgeError):
    """Raised when target_ref in result does not match Case target_ref."""
    pass


class ToolMappingError(CaseBridgeError):
    """Raised when canonical tool ID mapping fails or collides."""
    pass


# Mapping from D.0 run status to Node C v1.2 legacy status
D0_TO_LEGACY_STATUS = {
    'SUCCESS': 'SUCCESS',
    'PARTIAL': 'DEGRADED',
    'TIMEOUT': 'FAILED',
    'CANCELLED': 'FAILED',
    'FAILED': 'FAILED',
    'UNAVAILABLE': 'UNAVAILABLE',
}

# Mapping from D.0 facet observation status to Node C v1.2 status
D0_OBSERVATION_STATUS_MAP = {
    'SUCCESS': 'SUCCESS',
    'PARTIAL': 'DEGRADED',
    'FAILED': 'FAILED',
    'UNAVAILABLE': 'UNAVAILABLE',
    # 'NOT_COLLECTED' is retained in D.0 audit ledger, omitted from legacy observations
}


class CaseBridge:
    """Bridges D.0 orchestrator outputs to Node C CaseManager (D9).
    
    Guarantees:
    - Canonical tool ID -> legacy snake_case mapping with collision detection.
    - Lossless preservation: raw ToolResult + ExecutionReceipt written to append-only audit ledger.
    - Status projection: PARTIAL -> DEGRADED, TIMEOUT/CANCELLED -> FAILED.
    - DENIED is never committed as a tool-result; recorded as policy action/audit instead.
    - Atomic expected_revision validation before committing update to Node C.
    - Signs payload with trusted backend HMAC key before calling apply_update.
    """

    def __init__(self, audit_ledger_root: Optional[Path | str] = None) -> None:
        self.audit_ledger_root = Path(audit_ledger_root) if audit_ledger_root else None
        # Explicit override map for tool names if needed
        self._custom_tool_map: Dict[str, str] = {
            'static.ember_features': 'static_ember_features'
        }
        self._reverse_tool_map: Dict[str, str] = {
            'static_ember_features': 'static.ember_features'
        }

    def canonical_to_legacy_tool_name(self, tool_id: str) -> str:
        """Map canonical dot-separated tool ID to Node C legacy snake_case tool name.

        Example:
            'static.ember_features' -> 'static_ember_features'

        Raises:
            ToolMappingError: If tool_id format is invalid or produces collision.
        """
        if not tool_id or not isinstance(tool_id, str):
            raise ToolMappingError("tool_id must be a non-empty string")

        if tool_id in self._custom_tool_map:
            return self._custom_tool_map[tool_id]

        # Replace dots and hyphens with underscores
        legacy_name = tool_id.replace('.', '_').replace('-', '_')

        # Check collision with existing different canonical ID
        if legacy_name in self._reverse_tool_map:
            existing = self._reverse_tool_map[legacy_name]
            if existing != tool_id:
                raise ToolMappingError(
                    f"Tool name collision: '{tool_id}' and '{existing}' both map to '{legacy_name}'"
                )

        self._custom_tool_map[tool_id] = legacy_name
        self._reverse_tool_map[legacy_name] = tool_id
        return legacy_name

    def legacy_to_canonical_tool_name(self, legacy_name: str) -> str:
        """Reverse lookup from legacy snake_case name to canonical tool ID."""
        return self._reverse_tool_map.get(legacy_name, legacy_name)

    def project_tool_result_to_node_c(
        self,
        tool_result: Dict[str, Any],
        execution_receipt: Dict[str, Any],
        case_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Project a D.0 ToolResult into the legacy Node C payload structure.

        Args:
            tool_result: Validated D.0 tool_result dictionary.
            execution_receipt: Validated D.0 execution_receipt dictionary.
            case_state: Current Node C CaseState dictionary.

        Returns:
            Dictionary payload ready for cm.apply_update(path, 'tool-result', payload).

        Raises:
            DeniedToolResultCommitError: If status is DENIED.
            ReceiptIntegrityError: If receipt digest does not match tool_result.
            TargetMismatchBridgeError: If TargetRef does not match CaseState.
        """
        # Validate D.0 contracts
        validate('tool_result', tool_result)
        validate('execution_receipt', execution_receipt)

        # Disallow committing DENIED as tool success (ADR-001, ADR-007)
        if tool_result['status'] == 'DENIED':
            raise DeniedToolResultCommitError(
                "A DENIED policy outcome cannot be committed to Node C as a tool-result. "
                "Use record_denied_action() instead."
            )

        # Verify receipt SHA256 integrity linkage
        calculated_receipt_hash = digest(execution_receipt)
        if tool_result['receipt_sha256'] != calculated_receipt_hash:
            raise ReceiptIntegrityError(
                f"Receipt digest mismatch: tool_result has {tool_result['receipt_sha256']}, "
                f"computed receipt hash is {calculated_receipt_hash}"
            )

        # Verify TargetRef identity match with CaseState
        case_target_ref = case_state.get('target_ref')
        if case_target_ref:
            if not same_target_ref(case_target_ref, tool_result['target_ref']):
                raise TargetMismatchBridgeError(
                    "ToolResult target_ref does not match CaseState target_ref"
                )

        # Map tool name
        legacy_tool = self.canonical_to_legacy_tool_name(tool_result['tool_id'])

        # Map status
        d0_status = tool_result['status']
        legacy_status = D0_TO_LEGACY_STATUS.get(d0_status, 'FAILED')

        # Map observations: Node C v1.2 only accepts SUCCESS, DEGRADED, FAILED, UNAVAILABLE
        legacy_observations: List[Dict[str, Any]] = []
        for ob in tool_result.get('observations', []):
            facet_status = ob.get('status')
            if facet_status == 'NOT_COLLECTED':
                # Skip per-facet NOT_COLLECTED in Node C v1.2 projection (kept in audit ledger)
                continue

            mapped_facet_status = D0_OBSERVATION_STATUS_MAP.get(facet_status, 'UNAVAILABLE')
            entry: Dict[str, Any] = {
                'facet': ob['facet'],
                'status': mapped_facet_status,
                'coverage': ob.get('coverage', 'limited'),
                'limitations': ob.get('limitations', []),
                'artifact_ref': ob.get('artifact_ref')
            }
            if mapped_facet_status == 'SUCCESS':
                entry['value'] = ob.get('value')
            else:
                entry['value'] = None

            legacy_observations.append(entry)

        # Form Node C payload matching case_manager._append_tool
        payload: Dict[str, Any] = {
            'tool_run_id': tool_result['run_id'],
            'tool': legacy_tool,
            'status': legacy_status,
            'target_type': case_state['target_type'],
            'target': case_state['target'],
            'target_ref': copy.deepcopy(tool_result['target_ref']),
            'tool_version': tool_result['tool_version'],
            'provider': copy.deepcopy(tool_result['provider']),
            'observations': legacy_observations,
            'observed_at': execution_receipt.get('finished_at', cm.now())
        }
        if tool_result.get('error'):
            payload['error'] = tool_result['error']

        return payload

    def commit_tool_result(
        self,
        case_path: Path | str,
        tool_result: Dict[str, Any],
        execution_receipt: Dict[str, Any],
        *,
        trusted_key: bytes,
        expected_revision: Optional[int] = None,
        tool_description: Optional[str] = None,
        audit_ledger_path: Optional[Path | str] = None
    ) -> Dict[str, Any]:
        """Commit a D.0 ToolResult into Node C CaseState with atomic revision protection.

        Args:
            case_path: Path to case_state.json.
            tool_result: D.0 ToolResult dict.
            execution_receipt: D.0 ExecutionReceipt dict.
            trusted_key: 32+ bytes HMAC key for backend signing.
            expected_revision: Expected revision number of the case before commit.
            tool_description: Optional description when auto-registering legacy tool in case.
            audit_ledger_path: Optional custom path for audit ledger append.

        Returns:
            Dict containing case_id, revision, added_evidence, and audit_id.

        Raises:
            StaleRevisionError: If current case revision != expected_revision.
            DeniedToolResultCommitError: If tool_result status is DENIED.
            ReceiptIntegrityError: If receipt digest mismatch.
            CaseBridgeError: On any other validation or commit failure.
        """
        case_file = Path(case_path)
        if not case_file.exists():
            raise CaseBridgeError(f"Case file not found: {case_file}")

        # Read current case state (only to decide auto-registration and to compute
        # the expected revision for the final guarded write). The real optimistic-
        # concurrency gate is enforced atomically INSIDE case_manager.apply_update
        # via expected_revision, under the case lock - not by this pre-read.
        current_state = cm.read_json(case_file)
        case_id = current_state['case_id']
        legacy_tool_name = self.canonical_to_legacy_tool_name(tool_result['tool_id'])
        audit_id = f"AUDIT-{uuid.uuid4().hex}"

        # Phase 1 - write-ahead PENDING marker BEFORE touching Node C, fsync'd, so a
        # crash between here and the commit is detectable by reconcile_ledger().
        self._append_to_audit_ledger(
            case_dir=case_file.parent, case_id=case_id, tool_result=tool_result,
            execution_receipt=execution_receipt, projected_payload=None,
            revision_committed=None, custom_ledger_path=audit_ledger_path,
            phase='PENDING', audit_id=audit_id)

        try:
            tool_result_expected = expected_revision
            # Auto-register the legacy tool if absent, guarding that write with the
            # same expected_revision. Our own registration advances the revision by
            # exactly one, so the tool-result write must then expect that new value;
            # any third-party write in between makes the revisions disagree and the
            # guarded tool-result aborts safely (no lost update).
            if legacy_tool_name not in current_state.get('available_tools', {}):
                desc = tool_description or f"Auto-registered for D.0 tool {tool_result['tool_id']}"
                reg = cm.apply_update(
                    case_file, 'register-tool',
                    {'name': legacy_tool_name, 'description': desc},
                    expected_revision=expected_revision)
                if tool_result_expected is not None:
                    tool_result_expected = reg['revision']
                current_state = cm.read_json(case_file)

            node_c_payload = self.project_tool_result_to_node_c(
                tool_result, execution_receipt, current_state)
            proof = cm.sign_for_trusted_boundary(case_id, 'tool-result', node_c_payload, trusted_key)
            commit_result = cm.apply_update(
                case_file, 'tool-result', node_c_payload,
                authorization=proof, trusted_keys={'tool': trusted_key},
                expected_revision=tool_result_expected)
        except cm.StaleRevisionError as exc:
            self._append_to_audit_ledger(
                case_dir=case_file.parent, case_id=case_id, tool_result=tool_result,
                execution_receipt=execution_receipt, projected_payload=None,
                revision_committed=None, custom_ledger_path=audit_ledger_path,
                phase='ABORTED', audit_id=audit_id, denial_reason=str(exc))
            raise StaleRevisionError(str(exc)) from exc
        except BaseException as exc:
            self._append_to_audit_ledger(
                case_dir=case_file.parent, case_id=case_id, tool_result=tool_result,
                execution_receipt=execution_receipt, projected_payload=None,
                revision_committed=None, custom_ledger_path=audit_ledger_path,
                phase='ABORTED', audit_id=audit_id,
                denial_reason=f'{type(exc).__name__}: {exc}')
            raise

        new_revision = commit_result['revision']
        # Phase 2 - durable COMMITTED record with full fidelity, after Node C accepted.
        audit_record = self._append_to_audit_ledger(
            case_dir=case_file.parent, case_id=case_id, tool_result=tool_result,
            execution_receipt=execution_receipt, projected_payload=node_c_payload,
            revision_committed=new_revision, custom_ledger_path=audit_ledger_path,
            phase='COMMITTED', audit_id=audit_id)

        return {
            'case_id': case_id,
            'revision': new_revision,
            'added_evidence': commit_result.get('added_evidence', 0),
            'tool_run_id': tool_result['run_id'],
            'legacy_tool': legacy_tool_name,
            'canonical_tool_id': tool_result['tool_id'],
            'audit_id': audit_id,
            'audit_path': str(audit_record['audit_path'])
        }

    def record_denied_action(
        self,
        case_path: Path | str,
        tool_result: Dict[str, Any],
        execution_receipt: Dict[str, Any],
        *,
        reason: str = "Policy denied",
        audit_ledger_path: Optional[Path | str] = None
    ) -> Dict[str, Any]:
        """Record a policy DENIED decision into Node C actions and the audit ledger.

        Args:
            case_path: Path to case_state.json.
            tool_result: D.0 ToolResult with status DENIED.
            execution_receipt: D.0 ExecutionReceipt.
            reason: Explanation of the denial.
            audit_ledger_path: Optional path for audit log.

        Returns:
            Dict with action record and audit reference.
        """
        case_file = Path(case_path)
        state = cm.read_json(case_file)

        event_id = f"NOTE-DENIED-{tool_result['run_id'][:20]}-{uuid.uuid4().hex[:6]}"
        action_data = {
            'event_id': event_id,
            'action': 'NOTE',
            'actor': 'D4_POLICY_ENGINE',
            'reason': f"Tool execution DENIED for {tool_result['tool_id']}: {reason}"
        }

        # Apply action note to Node C
        update_result = cm.apply_update(case_file, 'action', action_data)

        # Append to audit ledger (DENIED is never a committed tool-result).
        audit_record = self._append_to_audit_ledger(
            case_dir=case_file.parent,
            case_id=state['case_id'],
            tool_result=tool_result,
            execution_receipt=execution_receipt,
            projected_payload=None,
            revision_committed=update_result['revision'],
            custom_ledger_path=audit_ledger_path,
            denial_reason=reason,
            phase='DENIED'
        )

        return {
            'case_id': state['case_id'],
            'revision': update_result['revision'],
            'action_event_id': event_id,
            'audit_id': audit_record['audit_id']
        }

    def _ledger_file_for(self, case_dir: Path, case_id: str,
                         custom_ledger_path: Optional[Path | str]) -> Path:
        if custom_ledger_path:
            return Path(custom_ledger_path)
        if self.audit_ledger_root:
            return self.audit_ledger_root / case_id / 'd0_audit_ledger.jsonl'
        return case_dir / 'd0_audit_ledger.jsonl'

    def _append_to_audit_ledger(
        self,
        case_dir: Path,
        case_id: str,
        tool_result: Dict[str, Any],
        execution_receipt: Dict[str, Any],
        projected_payload: Optional[Dict[str, Any]],
        revision_committed: Optional[int],
        custom_ledger_path: Optional[Path | str] = None,
        denial_reason: Optional[str] = None,
        phase: str = 'COMMITTED',
        audit_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append one phase line to the append-only audit ledger (full fidelity).

        The ledger is a SEPARATE file from Node C's CaseState; the two are NOT a
        single atomic transaction and this code does not pretend they are.
        Instead each commit writes a two-phase trail sharing one audit_id:
          * PENDING   - written BEFORE the Node C commit is attempted;
          * COMMITTED - written AFTER Node C durably accepted the update;
          * ABORTED   - written if the Node C commit raised (no durable change);
          * DENIED    - a policy-denied result recorded as a note, never committed.
        A PENDING with no later COMMITTED/ABORTED marks a crash window that
        reconcile_ledger() resolves against the actual CaseState.
        """
        ledger_file = self._ledger_file_for(case_dir, case_id, custom_ledger_path)
        ledger_file.parent.mkdir(parents=True, exist_ok=True)
        audit_id = audit_id or f"AUDIT-{uuid.uuid4().hex}"
        entry = {
            'audit_id': audit_id,
            'phase': phase,
            'recorded_at': datetime.now(timezone.utc).isoformat(),
            'case_id': case_id,
            'call_id': tool_result.get('call_id'),
            'run_id': tool_result.get('run_id'),
            'canonical_tool_id': tool_result.get('tool_id'),
            'tool_version': tool_result.get('tool_version'),
            'd0_status': tool_result.get('status'),
            'receipt_sha256': tool_result.get('receipt_sha256'),
            'revision_committed': revision_committed,
            'raw_tool_result': tool_result,
            'execution_receipt': execution_receipt,
            'projected_payload': projected_payload,
            'denial_reason': denial_reason,
        }
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n'
        # Flush+fsync so a PENDING marker survives a crash before the Node C write.
        with open(ledger_file, 'a', encoding='utf-8') as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        return {'audit_id': audit_id, 'audit_path': ledger_file}

    def reconcile_ledger(
        self,
        case_path: Path | str,
        audit_ledger_path: Optional[Path | str] = None,
    ) -> Dict[str, Any]:
        """Reconcile PENDING ledger entries against the actual CaseState.

        For each audit_id whose latest phase is PENDING (i.e. a crash happened
        between the write-ahead marker and the COMMITTED/ABORTED record), decide
        the real outcome by checking whether the tool_run_id is present in the
        case's tool_runs, then append a terminal RECONCILED_COMMITTED or
        RECONCILED_ABORTED line. This never mutates CaseState; it only repairs the
        audit trail to reflect what Node C actually did. Returns a summary.
        """
        case_file = Path(case_path)
        ledger_file = self._ledger_file_for(
            case_file.parent, cm.read_json(case_file)['case_id'], audit_ledger_path)
        if not ledger_file.exists():
            return {'scanned': 0, 'pending': 0, 'reconciled_committed': 0, 'reconciled_aborted': 0}
        state = cm.read_json(case_file)
        committed_runs = {r.get('tool_run_id') for r in state.get('tool_runs', [])}
        latest_phase: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        with open(ledger_file, 'r', encoding='utf-8') as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                rec = json.loads(raw)
                aid = rec.get('audit_id')
                if aid not in latest_phase:
                    order.append(aid)
                latest_phase[aid] = rec
        pending = [aid for aid in order if latest_phase[aid].get('phase') == 'PENDING']
        reconciled_committed = reconciled_aborted = 0
        for aid in pending:
            rec = latest_phase[aid]
            run_id = rec.get('run_id')
            terminal = 'RECONCILED_COMMITTED' if run_id in committed_runs else 'RECONCILED_ABORTED'
            if terminal == 'RECONCILED_COMMITTED':
                reconciled_committed += 1
                revision = state.get('revision')
            else:
                reconciled_aborted += 1
                revision = None
            self._append_to_audit_ledger(
                case_dir=case_file.parent, case_id=state['case_id'],
                tool_result=rec.get('raw_tool_result') or {},
                execution_receipt=rec.get('execution_receipt') or {},
                projected_payload=None, revision_committed=revision,
                custom_ledger_path=audit_ledger_path, phase=terminal, audit_id=aid,
                denial_reason='reconciliation: inferred from CaseState tool_runs')
        return {'scanned': len(order), 'pending': len(pending),
                'reconciled_committed': reconciled_committed,
                'reconciled_aborted': reconciled_aborted}
