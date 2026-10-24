"""Unit and integration acceptance tests for D9 - Case Bridge."""
import copy
import json
import secrets
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bc_contracts as bc
import case_manager as cm
import case_state as cs
from d0.validate import digest, validate
from orchestrator.case_bridge import (
    CaseBridge,
    DeniedToolResultCommitError,
    ReceiptIntegrityError,
    StaleRevisionError,
    TargetMismatchBridgeError,
    ToolMappingError,
)


def load_fixture(name: str) -> dict:
    return json.loads((ROOT / 'd0' / 'fixtures' / f'{name}.json').read_text(encoding='utf8'))


def make_file_context(path='C:\\samples\\fixture.exe', *, digest='a' * 64, ino=1, size=1024):
    return {
        'schema_version': 'context-v1',
        'collector_version': '1.2.0',
        'collection_id': 'COL-001',
        'target_type': 'FILE',
        'target': {'path': path},
        'status': 'SUCCESS',
        'facets': {
            'file_identity': {
                'status': 'SUCCESS',
                'value': {'device': 1, 'inode': ino, 'size_bytes': size, 'mtime_ns': 123456789}
            },
            'file_unchanged_during_collection': {'status': 'SUCCESS', 'value': True},
            'sha256': {'status': 'SUCCESS', 'value': digest}
        },
        'errors': [],
        'limitations': []
    }


class TestD9CaseBridge(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix='dacn-d9-test-'))
        self.bridge = CaseBridge(audit_ledger_root=self.tmp_dir / 'ledgers')
        self.trusted_key = secrets.token_bytes(32)

        # Base fixtures
        self.tool_result = load_fixture('tool_result')
        self.execution_receipt = load_fixture('execution_receipt')

        # Build consistent context and target_ref
        ctx = make_file_context(path=self.tool_result['target_ref']['observed']['path'])
        self.target_ref = bc.target_ref_from_context(ctx)

        self.tool_result['target_ref'] = copy.deepcopy(self.target_ref)
        self.execution_receipt['target_binding']['observed_ref'] = copy.deepcopy(self.target_ref)
        self.tool_result['receipt_sha256'] = digest(self.execution_receipt)

        # Build initial case state
        self.initial_state = cs.build_case_state(ctx)
        self.case_path = cs.save_case_state(self.initial_state, self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_tool_name_canonical_to_legacy_mapping(self):
        legacy = self.bridge.canonical_to_legacy_tool_name('static.ember_features')
        self.assertEqual(legacy, 'static_ember_features')
        canonical = self.bridge.legacy_to_canonical_tool_name('static_ember_features')
        self.assertEqual(canonical, 'static.ember_features')

    def test_02_tool_name_mapping_collision_detected(self):
        # Register a tool
        self.bridge.canonical_to_legacy_tool_name('tool.analyzer.v1')
        # Attempt to map a different tool that collides with the same legacy name
        with self.assertRaises(ToolMappingError):
            self.bridge.canonical_to_legacy_tool_name('tool-analyzer-v1')

    def test_03_project_tool_result_status_mapping(self):
        # SUCCESS -> SUCCESS
        payload = self.bridge.project_tool_result_to_node_c(
            self.tool_result, self.execution_receipt, self.initial_state
        )
        self.assertEqual(payload['status'], 'SUCCESS')
        self.assertEqual(payload['tool'], 'static_ember_features')

        # PARTIAL -> DEGRADED
        partial_res = copy.deepcopy(self.tool_result)
        partial_receipt = copy.deepcopy(self.execution_receipt)
        partial_receipt['outcome'] = 'PARTIAL'
        partial_res['status'] = 'PARTIAL'
        partial_res['receipt_sha256'] = digest(partial_receipt)
        payload_partial = self.bridge.project_tool_result_to_node_c(
            partial_res, partial_receipt, self.initial_state
        )
        self.assertEqual(payload_partial['status'], 'DEGRADED')

        # TIMEOUT -> FAILED
        timeout_res = copy.deepcopy(self.tool_result)
        timeout_receipt = copy.deepcopy(self.execution_receipt)
        timeout_receipt['outcome'] = 'TIMEOUT'
        timeout_res['status'] = 'TIMEOUT'
        timeout_res['error'] = {'code': 'timeout', 'message': 'Operation timed out'}
        timeout_res['receipt_sha256'] = digest(timeout_receipt)
        payload_timeout = self.bridge.project_tool_result_to_node_c(
            timeout_res, timeout_receipt, self.initial_state
        )
        self.assertEqual(payload_timeout['status'], 'FAILED')

    def test_04_no_denied_committed_as_tool_success(self):
        denied_res = copy.deepcopy(self.tool_result)
        denied_res['status'] = 'DENIED'
        denied_res['error'] = {'code': 'policy_denied', 'message': 'Execution not approved'}
        denied_receipt = copy.deepcopy(self.execution_receipt)
        denied_receipt['outcome'] = 'DENIED'
        denied_res['receipt_sha256'] = digest(denied_receipt)

        with self.assertRaises(DeniedToolResultCommitError):
            self.bridge.commit_tool_result(
                self.case_path, denied_res, denied_receipt,
                trusted_key=self.trusted_key
            )

    def test_05_record_denied_action_logs_to_case_and_ledger(self):
        denied_res = copy.deepcopy(self.tool_result)
        denied_res['status'] = 'DENIED'
        denied_res['error'] = {'code': 'policy_denied', 'message': 'Execution not approved'}
        denied_receipt = copy.deepcopy(self.execution_receipt)
        denied_receipt['outcome'] = 'DENIED'
        denied_res['receipt_sha256'] = digest(denied_receipt)

        record = self.bridge.record_denied_action(
            self.case_path, denied_res, denied_receipt,
            reason="Foreign code execution requires elevated human approval"
        )
        self.assertIn('action_event_id', record)
        self.assertIn('audit_id', record)

        case_state = cm.read_json(self.case_path)
        self.assertTrue(any('DENIED' in a.get('event_id', '') for a in case_state['action_history']))

    def test_06_receipt_integrity_mismatch_denied(self):
        tampered_res = copy.deepcopy(self.tool_result)
        tampered_res['receipt_sha256'] = '0' * 64

        with self.assertRaises(ReceiptIntegrityError):
            self.bridge.commit_tool_result(
                self.case_path, tampered_res, self.execution_receipt,
                trusted_key=self.trusted_key
            )

    def test_07_stale_revision_precondition_rejected(self):
        # Current revision is 1, expect 99
        with self.assertRaises(StaleRevisionError):
            self.bridge.commit_tool_result(
                self.case_path, self.tool_result, self.execution_receipt,
                trusted_key=self.trusted_key, expected_revision=99
            )

    def test_08_end_to_end_commit_and_audit_ledger(self):
        # Register and commit tool result into Node C
        result = self.bridge.commit_tool_result(
            self.case_path,
            self.tool_result,
            self.execution_receipt,
            trusted_key=self.trusted_key,
            expected_revision=1,
            tool_description="Static Ember PE feature extractor"
        )

        self.assertEqual(result['case_id'], self.initial_state['case_id'])
        self.assertEqual(result['legacy_tool'], 'static_ember_features')
        self.assertGreater(result['revision'], 1)
        self.assertGreater(result['added_evidence'], 0)

        # Verify case file state has the tool run and new evidence
        updated_case = cm.read_json(self.case_path)
        self.assertTrue(any(r.get('tool_run_id') == self.tool_result['run_id'] for r in updated_case['tool_runs']))
        self.assertTrue(any(e.get('facet') == 'ember_feature_count' for e in updated_case['evidence']))

        # Verify audit ledger exists and contains complete D.0 result
        ledger_path = Path(result['audit_path'])
        self.assertTrue(ledger_path.exists())
        lines = [json.loads(line) for line in ledger_path.read_text(encoding='utf8').splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        entry = lines[0]
        self.assertEqual(entry['canonical_tool_id'], 'static.ember_features')
        self.assertEqual(entry['receipt_sha256'], self.tool_result['receipt_sha256'])
        self.assertEqual(entry['raw_tool_result']['observations'][0]['trust_level'], 'UNTRUSTED_CONTENT')

    def test_09_target_ref_mismatch_denied(self):
        mismatched_res = copy.deepcopy(self.tool_result)
        mismatched_res['target_ref']['verified_digest']['value'] = 'e' * 64
        mismatched_receipt = copy.deepcopy(self.execution_receipt)
        mismatched_receipt['target_binding']['observed_ref']['verified_digest']['value'] = 'e' * 64
        mismatched_res['receipt_sha256'] = digest(mismatched_receipt)

        with self.assertRaises(TargetMismatchBridgeError):
            self.bridge.commit_tool_result(
                self.case_path, mismatched_res, mismatched_receipt,
                trusted_key=self.trusted_key
            )


if __name__ == '__main__':
    unittest.main()
