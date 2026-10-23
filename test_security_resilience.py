"""P0 security/resilience audit for Node C v1 (stdlib unittest).

PASS = tested property holds. expected failure = known security gap, NOT a pass.
Run from repo root: .\.venv\Scripts\python.exe -m unittest -v test_security_resilience
"""
import copy
import secrets
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import case_manager as cm
import case_state as cs


class P0SecurityResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='dacn-p0-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = {'pid': 43127, 'start_time_epoch': 123456.25}
        self.ctx = {
            'schema_version': 'context-v1', 'collector_version': '1.1.0',
            'collection_id': 'COL-p0-first', 'target_type': 'PROCESS',
            'target': copy.deepcopy(self.target), 'status': 'SUCCESS',
            'facets': {'name': {'status': 'SUCCESS', 'value': 'sample.exe'}},
            'errors': [], 'limitations': [],
        }
        self.path = cs.save_case_state(cs.build_case_state(self.ctx), self.root)
        self.keys = {'tool': secrets.token_bytes(32), 'approval': secrets.token_bytes(32)}

    def read(self):
        return cm.read_json(self.path)

    def trusted(self, op, payload):
        proof = cm.sign_for_trusted_boundary(self.read()['case_id'], op, payload, self.keys['tool' if op == 'tool-result' else 'approval'])
        return cm.apply_update(self.path, op, payload, authorization=proof, trusted_keys=self.keys)

    def register(self):
        cm.apply_update(self.path, 'register-tool', {'name': 'static_analyzer', 'description': 'static analysis'})

    def tool_result(self, run_id='RUN-p0-001', facet='pe_entropy', value=7.1, **kwargs):
        result = {'tool_run_id': run_id, 'tool': 'static_analyzer',
                  'status': 'SUCCESS', 'target_type': 'PROCESS',
                  'target': copy.deepcopy(self.target),
                  'observations': [{'facet': facet, 'status': 'SUCCESS', 'value': value}]}
        result.update(kwargs)
        return result

    def test_p0_01_malformed_tool_result_does_not_modify_case(self):
        self.register()
        bad = self.tool_result(observations=[{'facet': 'pe_entropy', 'status': 'FAILED', 'value': 99}])
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.trusted('tool-result', bad)
        self.assertEqual(self.path.read_bytes(), before)

    def test_p0_02_pid_identity_mismatch_does_not_modify_case(self):
        self.register()
        bad = self.tool_result(target={'pid': self.target['pid'], 'start_time_epoch': 123456.26})
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.trusted('tool-result', bad)
        self.assertEqual(self.path.read_bytes(), before)

    def test_p0_03_real_subprocess_concurrency_no_lost_updates(self):
        """Eight real OS processes contend for same lock, each appends unique NOTE."""
        count = 8
        gate = self.root / 'start.flag'
        worker = r'''
import sys, time
from pathlib import Path
import case_manager as cm
path, gate, i = sys.argv[1:]
limit = time.monotonic() + 20
while not Path(gate).exists():
    if time.monotonic() > limit: raise RuntimeError('start gate timeout')
    time.sleep(.01)
cm.apply_update(path, 'action', {'event_id': 'P0-NOTE-' + i, 'action': 'NOTE', 'actor': 'concurrency_test'})
'''
        env = dict(os.environ)
        env['PYTHONPATH'] = str(Path(cm.__file__).resolve().parent) + os.pathsep + env.get('PYTHONPATH', '')
        procs = [subprocess.Popen([sys.executable, '-c', worker, str(self.path), str(gate), str(i)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                 for i in range(count)]
        gate.write_text('go', encoding='utf-8')
        try:
            for i, proc in enumerate(procs):
                out, err = proc.communicate(timeout=25)
                self.assertEqual(proc.returncode, 0, f'worker {i}: {out} {err}')
        finally:
            for proc in procs:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()
        state = self.read()
        self.assertEqual(state['revision'], 1 + count)
        self.assertEqual(len(state['action_history']), count)
        self.assertEqual({x['event_id'] for x in state['action_history']},
                         {f'P0-NOTE-{i}' for i in range(count)})

    def test_p0_04_process_crash_before_atomic_replace_keeps_old_json(self):
        """Crash injected after temp file flush, before os.replace; original remains intact.
        NOTE: This does not prove recovery of an abandoned .lock.
        """
        before = self.path.read_bytes()
        worker = r'''
import os, sys
import case_manager as cm
cm.os.replace = lambda *args, **kwargs: os._exit(87)
cm.apply_update(sys.argv[1], 'action', {'event_id': 'P0-CRASH', 'action': 'NOTE'})
'''
        env = dict(os.environ)
        env['PYTHONPATH'] = str(Path(cm.__file__).resolve().parent) + os.pathsep + env.get('PYTHONPATH', '')
        p = subprocess.run([sys.executable, '-c', worker, str(self.path)],
                           capture_output=True, text=True, timeout=15, env=env)
        self.assertEqual(p.returncode, 87, p.stderr)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.read()['revision'], 1)
        # A stale lock after crash is a known v1 limitation, not silently treated as safe.
        self.assertTrue(self.path.with_suffix('.json.lock').exists())

    def test_p0_05_conflicting_observations_preserve_provenance(self):
        self.register()
        self.trusted('tool-result', self.tool_result('RUN-conflict-a', value=3.0))
        self.trusted('tool-result', self.tool_result('RUN-conflict-b', value=8.0))
        vals = [(e['value'], e.get('tool_run_id')) for e in self.read()['evidence'] if e['facet'] == 'pe_entropy']
        self.assertEqual(vals, [(3.0, 'RUN-conflict-a'), (8.0, 'RUN-conflict-b')])

    def test_p0_06_conflicting_success_evidence_must_be_flagged(self):
        """REGRESSION: same facet different values are preserved but not flagged."""
        self.register()
        self.trusted('tool-result', self.tool_result('RUN-conflict-a', value=3.0))
        self.trusted('tool-result', self.tool_result('RUN-conflict-b', value=8.0))
        state = self.read()
        self.assertTrue(any(x.get('facet') == 'pe_entropy' for x in state.get('evidence_conflicts', [])),
                        'CaseManager must explicitly flag conflicting successful observations')

    def test_p0_07_stale_assessment_must_not_ignore_later_conflict(self):
        """REGRESSION: assessment cites old success despite later conflicting success."""
        self.register()
        self.trusted('tool-result', self.tool_result('RUN-old', value=3.0))
        old_id = next(e['evidence_id'] for e in self.read()['evidence'] if e.get('tool_run_id') == 'RUN-old')
        self.trusted('tool-result', self.tool_result('RUN-new', value=8.0))
        cm.apply_update(self.path, 'action', {'event_id': 'P0-START', 'action': 'START_INVESTIGATION'})
        with self.assertRaises(ValueError):
            cm.apply_update(self.path, 'assessment', {
                'verdict': 'BENIGN', 'confidence': .95, 'evidence_ids': [old_id],
                'rationale': 'Old observation is contradicted by a newer observation'})

    def test_p0_08_untrusted_caller_cannot_impersonate_registered_tool(self):
        """REGRESSION: registering a tool name is not authenticating the result producer."""
        self.register()
        before = self.path.read_bytes()
        forged = self.tool_result('RUN-forged', facet='malware_score', value=0.0)
        # No proof of which runner produced this payload; secure ingestion must reject it.
        with self.assertRaises((ValueError, PermissionError)):
            cm.apply_update(self.path, 'tool-result', forged)
        self.assertEqual(self.path.read_bytes(), before)

    def test_p0_09_human_approval_must_be_verified_not_self_asserted(self):
        """REGRESSION: human_approved:true + arbitrary approver string is not authentication."""
        cm.apply_update(self.path, 'action', {'event_id': 'P0-START', 'action': 'START_INVESTIGATION'})
        with self.assertRaises((ValueError, PermissionError)):
            cm.apply_update(self.path, 'response', {
                'status': 'APPROVED', 'description': 'quarantine',
                'human_approved': True, 'approver': 'anyone-can-write-this'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
