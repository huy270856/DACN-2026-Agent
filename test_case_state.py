import copy
import json
from pathlib import Path
import tempfile
import unittest
import case_state as cs


class CaseStateTests(unittest.TestCase):
    def fixture(self, target_type='FILE'):
        target = {'path': 'C:/test/sample.exe'} if target_type == 'FILE' else {'pid': 123, 'start_time_epoch': 100.0}
        return {'schema_version': 'context-v1', 'collector_version': '1.1.0',
                'collection_id': 'COL-parent', 'target_type': target_type, 'target': target,
                'status': 'SUCCESS', 'started_at': '2026-10-23T00:00:00Z',
                'facets': {'sha256': {'status': 'SUCCESS', 'value': 'a' * 64},
                           'pe_header': {'status': 'SUCCESS', 'value': {'is_pe': False}}},
                'errors': [], 'limitations': ['minimum PE only']}

    def test_successful_false_is_observation_not_unknown(self):
        state = cs.build_case_state(self.fixture())
        pe = next(x for x in state['evidence'] if x['facet'] == 'pe_header')
        self.assertEqual(pe['value'], {'is_pe': False})
        self.assertNotIn('pe_header', [x['facet'] for x in state['residual_unknowns']])
        self.assertIsNone(state['assessment'])
        self.assertEqual(state['available_tools'], {})

    def test_timeout_gap_and_no_partial_digest(self):
        ctx = self.fixture()
        ctx['status'] = 'DEGRADED'
        ctx['facets']['sha256'] = {'status': 'UNAVAILABLE', 'value': None, 'reason': 'hash_timeout'}
        state = cs.build_case_state(ctx)
        sha = next(x for x in state['evidence'] if x['facet'] == 'sha256')
        self.assertIsNone(sha['value'])
        self.assertTrue(any(x['facet'] == 'sha256' and x['reason'] == 'hash_timeout'
                            for x in state['residual_unknowns']))

    def test_pid_without_backing_file_is_not_collected(self):
        ctx = self.fixture('PROCESS')
        ctx['facets'] = {'running': {'status': 'SUCCESS', 'value': True}}
        state = cs.build_case_state(ctx)
        self.assertTrue(any(x['facet'] == 'backing_file_sha256' and x['state'] == 'NOT_COLLECTED'
                            for x in state['residual_unknowns']))

    def test_nested_backing_file_is_linked_and_not_recollected(self):
        ctx = self.fixture('PROCESS')
        ctx['facets'] = {'backing_file_collection': {'status': 'SUCCESS', 'value': 'COL-child'}}
        child = self.fixture()
        child['collection_id'] = 'COL-child'
        ctx['backing_file_context'] = child
        state = cs.build_case_state(ctx)
        self.assertEqual(state['collection_ids'], ['COL-parent', 'COL-child'])
        self.assertTrue(any(e['parent_collection_id'] == 'COL-parent' for e in state['evidence']))
        self.assertFalse(any(g['facet'] == 'backing_file_sha256' for g in state['residual_unknowns']))

    def test_failed_collection_remains_open(self):
        ctx = self.fixture()
        ctx['status'] = 'FAILED'
        ctx['errors'] = [{'code': 'PermissionError', 'message': 'denied'}]
        state = cs.build_case_state(ctx)
        self.assertEqual(state['lifecycle_status'], 'NEEDS_CONTEXT')
        self.assertEqual(state['collection_errors'][0]['code'], 'PermissionError')

    def test_bad_schema_rejected(self):
        ctx = self.fixture()
        ctx['schema_version'] = 'unknown'
        with self.assertRaises(ValueError):
            cs.build_case_state(ctx)

    def test_saved_case_state_roundtrip(self):
        state = cs.build_case_state(self.fixture())
        with tempfile.TemporaryDirectory() as tmp:
            path = cs.save_case_state(state, tmp)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['case_id'], state['case_id'])
            with self.assertRaises(FileExistsError):
                cs.save_case_state(state, tmp)


if __name__ == '__main__':
    unittest.main(verbosity=2)
