import copy
import secrets
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import case_state as cs
import case_manager as cm


class CaseManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ctx = {'schema_version': 'context-v1', 'collector_version': '1.1.0',
            'collection_id': 'COL-one', 'target_type': 'PROCESS',
            'target': {'pid': 77, 'start_time_epoch': 123.5}, 'status': 'SUCCESS',
            'facets': {'name': {'status': 'SUCCESS', 'value': 'app.exe'}},
            'errors': [], 'limitations': []}
        self.path = cs.save_case_state(cs.build_case_state(self.ctx), self.root)
        self.keys = {'tool': secrets.token_bytes(32), 'approval': secrets.token_bytes(32)}

    def read(self):
        return cm.read_json(self.path)

    def apply(self, op, data):
        if op in ('tool-result', 'response'):
            proof = cm.sign_for_trusted_boundary(self.read()['case_id'], op, data, self.keys['tool' if op == 'tool-result' else 'approval'])
            return cm.apply_update(self.path, op, data, authorization=proof, trusted_keys=self.keys)
        return cm.apply_update(self.path, op, data)

    def register(self):
        self.apply('register-tool', {'name': 'static_analyzer', 'description': 'PE features'})

    def result(self, **kw):
        data = {'tool_run_id': 'RUN-001', 'tool': 'static_analyzer', 'status': 'SUCCESS',
            'target_type': 'PROCESS', 'target': self.ctx['target'],
            'observations': [{'facet': 'runtime_modules', 'status': 'SUCCESS', 'value': []}]}
        data.update(kw)
        return data

    def test_init_ready_not_investigating(self):
        self.assertEqual(self.read()['lifecycle_status'], 'READY_FOR_INVESTIGATION')
        self.assertEqual(self.read()['revision'], 1)

    def test_tool_registration_and_success_resolves_gap(self):
        self.register()
        self.apply('tool-result', self.result())
        s = self.read()
        self.assertEqual(len(s['tool_runs']), 2)
        self.assertFalse(any(g['facet'] == 'runtime_modules' for g in s['residual_unknowns']))
        self.assertTrue(any(g['facet'] == 'runtime_modules' for g in s['resolved_unknowns']))
        self.assertEqual(s['revision'], 3)

    def test_tool_not_registered_rejected_without_mutation(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.apply('tool-result', self.result())
        self.assertEqual(self.path.read_bytes(), before)

    def test_tool_run_idempotency(self):
        self.register()
        self.apply('tool-result', self.result())
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.apply('tool-result', self.result())
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_tool_does_not_fabricate_evidence(self):
        self.register()
        bad = self.result(status='FAILED', observations=[{'facet': 'runtime_modules', 'status': 'FAILED', 'reason': 'access_denied'}])
        self.apply('tool-result', bad)
        s = self.read()
        ev = next(e for e in s['evidence'] if e.get('tool_run_id') == 'RUN-001')
        self.assertIsNone(ev['value'])
        self.assertTrue(any(g['facet'] == 'runtime_modules' for g in s['residual_unknowns']))

    def test_partial_value_on_failure_rejected(self):
        self.register()
        bad = self.result(observations=[{'facet': 'x', 'status': 'FAILED', 'value': 'fake'}])
        with self.assertRaises(ValueError):
            self.apply('tool-result', bad)

    def test_pid_reuse_rejected(self):
        self.register()
        wrong = self.result(target={'pid': 77, 'start_time_epoch': 555.5})
        with self.assertRaises(ValueError):
            self.apply('tool-result', wrong)

    def test_append_collection_and_resolve_hash(self):
        ctx = copy.deepcopy(self.ctx)
        ctx['collection_id'] = 'COL-two'
        ctx['facets'] = {'backing_file_collection': {'status': 'SUCCESS', 'value': 'COL-child'}}
        child = {'schema_version': 'context-v1', 'collection_id': 'COL-child',
            'target_type': 'FILE', 'target': {'path': 'C:/app.exe'}, 'status': 'SUCCESS',
            'facets': {'sha256': {'status': 'SUCCESS', 'value': 'a' * 64}},
            'errors': [], 'limitations': []}
        ctx['backing_file_context'] = child
        self.apply('collection', ctx)
        s = self.read()
        self.assertEqual(s['collection_ids'], ['COL-one', 'COL-two', 'COL-child'])
        self.assertFalse(any(g['facet'] == 'backing_file_sha256' for g in s['residual_unknowns']))
        self.assertTrue(any(e['parent_collection_id'] == 'COL-two' for e in s['evidence']))

    def test_duplicate_collection_rejected(self):
        with self.assertRaises(ValueError):
            self.apply('collection', self.ctx)

    def test_collection_wrong_target_rejected(self):
        ctx = copy.deepcopy(self.ctx)
        ctx['collection_id'] = 'COL-two'
        ctx['target']['start_time_epoch'] = 999
        with self.assertRaises(ValueError):
            self.apply('collection', ctx)

    def test_lifecycle_and_evidence_cited_assessment(self):
        self.apply('action', {'event_id': 'E-1', 'action': 'START_INVESTIGATION', 'actor': 'test'})
        with self.assertRaises(ValueError):
            self.apply('assessment', {'verdict': 'BENIGN', 'confidence': 0.9, 'evidence_ids': [], 'rationale': 'none'})
        ev_id = self.read()['evidence'][0]['evidence_id']
        self.apply('assessment', {'verdict': 'UNKNOWN', 'confidence': 0.1, 'evidence_ids': [ev_id], 'rationale': 'No malware analysis'})
        self.assertFalse(any(g['facet'] == 'malware_assessment' for g in self.read()['residual_unknowns']))
        self.apply('action', {'event_id': 'E-2', 'action': 'REQUEST_APPROVAL'})
        self.apply('action', {'event_id': 'E-3', 'action': 'CLOSE_CASE'})
        self.assertEqual(self.read()['lifecycle_status'], 'CLOSED')
        with self.assertRaises(ValueError):
            self.apply('action', {'event_id': 'E-4', 'action': 'NOTE'})

    def test_no_response_without_human_approval(self):
        self.apply('action', {'event_id': 'E-1', 'action': 'START_INVESTIGATION'})
        with self.assertRaises(ValueError):
            self.apply('response', {'status': 'APPROVED', 'description': 'Quarantine'})
        self.apply('response', {'status': 'APPROVED', 'description': 'Quarantine proposal only',
            'human_approved': True, 'approver': 'analyst'})
        self.assertEqual(len(self.read()['response_history']), 1)

    def test_unsafe_case_id_rejected(self):
        with self.assertRaises(ValueError):
            cm.case_path(self.root, '../../etc/passwd')

    def test_large_json_rejected(self):
        p = self.root / 'big.json'
        p.write_bytes(b' ' * (cm.MAX_JSON_BYTES + 1))
        with self.assertRaises(ValueError):
            cm.read_json(p)

    def test_lock_conflict_fails(self):
        lock = self.path.with_suffix('.json.lock')
        lock.write_text('busy')
        with patch.object(cm.time, 'monotonic', side_effect=[0, 10]):
            with self.assertRaises(TimeoutError):
                cm.apply_update(self.path, 'action', {'event_id': 'E-1', 'action': 'NOTE'})
        lock.unlink()

    def test_cli_show(self):
        self.assertEqual(cm.main(['show', '--case', str(self.path)]), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
