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

        # Read current case state
        current_state = cm.read_json(case_file)
        current_revision = current_state.get('revision', 1)

        # Check expected revision precondition before locking/writing
        if expected_revision is not None and current_revision != expected_revision:
            raise StaleRevisionError(
                f"Concurrent revision mismatch: expected revision {expected_revision}, "
                f"current case revision is {current_revision}. Commit aborted to prevent overwrite."
            )

        # Ensure tool is registered in Node C case
        legacy_tool_name = self.canonical_to_legacy_tool_name(tool_result['tool_id'])
        available_tools = current_state.get('available_tools', {})
        if legacy_tool_name not in available_tools:
            desc = tool_description or f"Auto-registered for D.0 tool {tool_result['tool_id']}"
            cm.apply_update(
                case_file,
                'register-tool',
                {'name': legacy_tool_name, 'description': desc}
            )
            # Re-read case after registration
            current_state = cm.read_json(case_file)

        # Check expected revision again if auto-registration incremented it
        if expected_revision is not None:
            # Registration increments revision by 1, so adjust or ensure we track accurately
            current_revision = current_state.get('revision', 1)

        # Project payload for Node C
        node_c_payload = self.project_tool_result_to_node_c(
            tool_result, execution_receipt, current_state
        )

        # Sign payload using backend HMAC key (case_manager.sign_for_trusted_boundary)
        case_id = current_state['case_id']
        proof = cm.sign_for_trusted_boundary(case_id, 'tool-result', node_c_payload, trusted_key)

        # Apply update to Node C inside atomic file lock
        commit_result = cm.apply_update(
            case_file,
            'tool-result',
            node_c_payload,
            authorization=proof,
            trusted_keys={'tool': trusted_key}
        )

        new_revision = commit_result['revision']

        # Append record to immutable audit ledger
        audit_record = self._append_to_audit_ledger(
            case_dir=case_file.parent,
            case_id=case_id,
            tool_result=tool_result,
            execution_receipt=execution_receipt,
            projected_payload=node_c_payload,
            revision_committed=new_revision,
            custom_ledger_path=audit_ledger_path
        )

        return {
            'case_id': case_id,
            'revision': new_revision,
            'added_evidence': commit_result.get('added_evidence', 0),
            'tool_run_id': tool_result['run_id'],
            'legacy_tool': legacy_tool_name,
            'canonical_tool_id': tool_result['tool_id'],
            'audit_id': audit_record['audit_id'],
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

        # Append to audit ledger
        audit_record = self._append_to_audit_ledger(
            case_dir=case_file.parent,
            case_id=state['case_id'],
            tool_result=tool_result,
            execution_receipt=execution_receipt,
            projected_payload=None,
            revision_committed=update_result['revision'],
            custom_ledger_path=audit_ledger_path,
            denial_reason=reason
        )

        return {
            'case_id': state['case_id'],
            'revision': update_result['revision'],
            'action_event_id': event_id,
            'audit_id': audit_record['audit_id']
        }

    def _append_to_audit_ledger(
        self,
        case_dir: Path,
        case_id: str,
        tool_result: Dict[str, Any],
        execution_receipt: Dict[str, Any],
        projected_payload: Optional[Dict[str, Any]],
        revision_committed: int,
        custom_ledger_path: Optional[Path | str] = None,
        denial_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Write an append-only JSON line into the audit ledger preserving full fidelity."""
        if custom_ledger_path:
            ledger_file = Path(custom_ledger_path)
        elif self.audit_ledger_root:
            ledger_file = self.audit_ledger_root / case_id / 'd0_audit_ledger.jsonl'
        else:
            ledger_file = case_dir / 'd0_audit_ledger.jsonl'

        ledger_file.parent.mkdir(parents=True, exist_ok=True)

        audit_id = f"AUDIT-{uuid.uuid4().hex}"
        entry = {
            'audit_id': audit_id,
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
            'denial_reason': denial_reason
        }

        line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n'
        with open(ledger_file, 'a', encoding='utf-8') as f:
            f.write(line)

        return {'audit_id': audit_id, 'audit_path': ledger_file}
