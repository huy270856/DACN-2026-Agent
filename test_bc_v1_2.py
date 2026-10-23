"""BC v1.2 compatibility, identity and scoped-unknown regression tests."""
import copy
from pathlib import Path
import secrets
import tempfile
import unittest

import bc_contracts as bc
import case_manager as cm
import case_state as cs
import context_collector as collector


def file_context(path='C:/samples/a.exe', *, col='COL-A', ino=1, digest='a'*64, size=20):
    return {'schema_version': 'context-v1', 'collector_version': '1.2.0',
            'collection_id': col, 'target_type': 'FILE', 'target': {'path': path},
            'status': 'SUCCESS', 'facets': {
                'file_identity': {'status': 'SUCCESS', 'value': {'device': 3, 'inode': ino, 'size_bytes': size, 'mtime_ns': 123}},
                'file_unchanged_during_collection': {'status': 'SUCCESS', 'value': True},
                'sha256': {'status': 'SUCCESS', 'value': digest}},
            'errors': [], 'limitations': ['No full PE validation']}


class BCV12Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def case(self, ctx):
        return cs.save_case_state(cs.build_case_state(ctx), self.root)

    def test_01_collector_real_file_ref_and_hash(self):
        f = self.root / 'file.bin'
        f.write_bytes(b'MZ' + b'0'*1024)
        ctx = collector.collect_file_context(f)
        ref = ctx['target_ref']
        self.assertEqual(ref['kind'], 'FILE')
        self.assertEqual(ref['verified_digest']['algorithm'], 'sha256')
        self.assertEqual(len(ref['verified_digest']['value']), 64)
        self.assertEqual(ref['snapshot']['size_bytes'], f.stat().st_size)

    def test_02_no_partial_digest_promoted(self):
        ctx = file_context()
        ctx['facets']['sha256'] = {'status': 'UNAVAILABLE', 'reason': 'hash_timeout'}
        self.assertIsNone(bc.target_ref_from_context(ctx)['verified_digest'])

    def test_03_file_replaced_same_path_denied(self):
        a = file_context()
        path = self.case(a)
        b = file_context(col='COL-B', ino=2, digest='b'*64)
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'snapshot/digest'):
            cm.apply_update(path, 'collection', b)
        self.assertEqual(before, path.read_bytes())

    def test_04_changed_hash_same_metadata_denied(self):
        path = self.case(file_context())
        newer = file_context(col='COL-B', digest='b'*64)
        with self.assertRaisesRegex(ValueError, 'snapshot/digest'):
            cm.apply_update(path, 'collection', newer)

    def test_05_equal_file_snapshot_can_append(self):
        path = self.case(file_context())
        newer = file_context(col='COL-B')
        cm.apply_update(path, 'collection', newer)
        self.assertEqual(len(cm.read_json(path)['collection_ids']), 2)

    def test_06_nested_child_unknown_not_resolved_by_primary_tool(self):
        ctx = {'schema_version':'context-v1','collection_id':'COL-P','target_type':'PROCESS',
               'target':{'pid':17,'start_time_epoch':12.5}, 'status':'SUCCESS',
               'facets':{'name':{'status':'SUCCESS','value':'x.exe'}}, 'errors':[], 'limitations':[],
               'backing_file_context':{'schema_version':'context-v1','collection_id':'COL-F',
               'target_type':'FILE','target':{'path':'C:/x.exe'}, 'status':'DEGRADED',
               'facets':{'sha256':{'status':'UNAVAILABLE','reason':'hash_timeout'},
                         'runtime_modules':{'status':'UNAVAILABLE','reason':'not_collected'}},
               'errors':[], 'limitations':[]}}
        path = self.case(ctx)
        cm.apply_update(path, 'register-tool', {'name':'runtime_tool','description':'mock'})
        data = {'tool_run_id':'RUN-abc','tool':'runtime_tool','status':'SUCCESS',
                'target_type':'PROCESS','target':ctx['target'],
                'observations':[{'facet':'runtime_modules','status':'SUCCESS','value':[]}]}
        key = secrets.token_bytes(32)
        proof = cm.sign_for_trusted_boundary(cm.read_json(path)['case_id'], 'tool-result', data, key)
        cm.apply_update(path, 'tool-result', data, authorization=proof, trusted_keys={'tool':key})
        s = cm.read_json(path)
        self.assertTrue(any(g['collection_id']=='COL-F' and g['facet']=='runtime_modules' for g in s['residual_unknowns']))
        self.assertFalse(any(g['collection_id']=='COL-P' and g['facet']=='runtime_modules' for g in s['residual_unknowns']))

    def test_07_evidence_v2_provenance_and_untrusted(self):
        s = cs.build_case_state(file_context())
        e = s['evidence'][0]
        self.assertEqual(e['evidence_schema_version'], 'evidence-v2')
        self.assertEqual(e['source']['kind'], 'collector')
        self.assertEqual(e['source']['version'], '1.2.0')
        self.assertEqual(e['trust_level'], 'UNTRUSTED_CONTENT')
        self.assertIn('No full PE validation', e['limitations'])

    def test_08_legacy_context_and_case_still_readable(self):
        ctx = file_context()
        ctx['facets'].pop('file_identity')
        ctx['facets'].pop('file_unchanged_during_collection')
        s = cs.build_case_state(ctx)
        self.assertIsNone(s['target_ref']['verified_digest'])
        s.pop('target_ref')
        for e in s['evidence']:
            for k in ('evidence_schema_version','target_ref','source','provider','limitations','trust_level','content_origin','parent_evidence_ids','analysis_profile'):
                e.pop(k, None)
        p = cs.save_case_state(s, self.root)
        self.assertEqual(cm.validate_case(cm.read_json(p))['schema_version'], 'casestate-v1')

    def test_09_malformed_claimed_digest_denied(self):
        ctx = file_context()
        ctx['target_ref'] = bc.target_ref_from_context(ctx)
        ctx['target_ref']['verified_digest']['value'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'verified digest'):
            cs.build_case_state(ctx)

    def test_10_success_false_and_empty_remain_evidence(self):
        ctx = file_context()
        ctx['facets']['running'] = {'status':'SUCCESS','value':False}
        ctx['facets']['modules'] = {'status':'SUCCESS','value':[]}
        e = {x['facet']:x for x in cs.build_case_state(ctx)['evidence']}
        self.assertIs(e['running']['value'],False)
        self.assertEqual(e['modules']['value'],[])

    def test_11_spoofed_target_snapshot_denied(self):
        ctx = file_context()
        ctx['target_ref'] = bc.target_ref_from_context(ctx)
        ctx['target_ref']['snapshot']['inode'] = 9000
        with self.assertRaisesRegex(ValueError, 'snapshot/strength'):
            cs.build_case_state(ctx)

    def test_12_replaced_real_file_same_path_new_case_binding(self):
        file = self.root / 'replace.bin'
        file.write_bytes(b'A'*1024)
        first = collector.collect_file_context(file)
        path = self.case(first)
        file.unlink()
        file.write_bytes(b'B'*1024)
        second = collector.collect_file_context(file)
        self.assertEqual(first['target']['path'], second['target']['path'])
        with self.assertRaisesRegex(ValueError, 'snapshot/digest'):
            cm.apply_update(path, 'collection', second)

    def test_13_tool_result_mismatched_target_ref_denied(self):
        ctx = file_context()
        path = self.case(ctx)
        cm.apply_update(path, 'register-tool', {'name':'static_analyzer','description':'mock'})
        bad_ref = bc.target_ref_from_context(file_context(ino=999))
        payload = {'tool_run_id':'RUN-bad','tool':'static_analyzer','status':'SUCCESS',
                   'target_type':'FILE','target':ctx['target'],'target_ref':bad_ref,
                   'observations':[{'facet':'score','status':'SUCCESS','value':0.1}]}
        key = secrets.token_bytes(32)
        proof = cm.sign_for_trusted_boundary(cm.read_json(path)['case_id'], 'tool-result', payload, key)
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'TargetRef mismatch'):
            cm.apply_update(path,'tool-result',payload,authorization=proof,trusted_keys={'tool':key})
        self.assertEqual(before,path.read_bytes())

    def test_14_legacy_case_can_be_updated(self):
        ctx = file_context()
        state = cs.build_case_state(ctx)
        state.pop('target_ref')
        state.pop('contract_version')
        path = cs.save_case_state(state, self.root)
        cm.apply_update(path, 'action', {'event_id':'E-legacy','action':'NOTE','reason':'compatibility'})
        self.assertEqual(cm.read_json(path)['target_ref']['identity_strength'], 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
