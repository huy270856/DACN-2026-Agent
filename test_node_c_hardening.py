"""Additional Node C security regressions. No malware samples required."""
import copy
import json
from pathlib import Path
import secrets
import tempfile
import time
import unittest

import case_manager as cm
import case_state as cs


class NodeCHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ctx = {'schema_version':'context-v1','collector_version':'1.1.0',
            'collection_id':'COL-harden-1','target_type':'PROCESS',
            'target':{'pid':5432,'start_time_epoch':456.25}, 'status':'SUCCESS',
            'facets':{'name':{'status':'SUCCESS','value':'demo.exe'}},
            'errors':[], 'limitations':[]}
        self.path = cs.save_case_state(cs.build_case_state(self.ctx), self.root)
        self.keys = {'tool':secrets.token_bytes(32),'approval':secrets.token_bytes(32)}
        cm.apply_update(self.path,'register-tool',{'name':'static_analyzer','description':'analysis'})

    def state(self): return cm.read_json(self.path)

    def payload(self, run, value, facet='pe_entropy'):
        return {'tool_run_id':run,'tool':'static_analyzer','status':'SUCCESS',
            'target_type':'PROCESS','target':self.ctx['target'],
            'observations':[{'facet':facet,'status':'SUCCESS','value':value}]}

    def signed(self, op, data, key=None, **opts):
        key = key or self.keys['tool' if op == 'tool-result' else 'approval']
        return cm.sign_for_trusted_boundary(self.state()['case_id'],op,data,key,**opts)

    def submit(self, op, data, proof=None):
        return cm.apply_update(self.path,op,data,authorization=proof or self.signed(op,data),trusted_keys=self.keys)

    def test_01_unsigned_tool_result_denied_unchanged(self):
        before=self.path.read_bytes()
        with self.assertRaises(PermissionError): cm.apply_update(self.path,'tool-result',self.payload('RUN-aaa',3))
        self.assertEqual(before,self.path.read_bytes())

    def test_02_tampered_signed_tool_result_denied(self):
        data=self.payload('RUN-aaa',3)
        proof=self.signed('tool-result',data)
        data['observations'][0]['value']=0
        before=self.path.read_bytes()
        with self.assertRaises(PermissionError): self.submit('tool-result',data,proof)
        self.assertEqual(before,self.path.read_bytes())

    def test_03_wrong_signing_key_denied(self):
        data=self.payload('RUN-aaa',3)
        with self.assertRaises(PermissionError): self.submit('tool-result',data,self.signed('tool-result',data,secrets.token_bytes(32)))

    def test_04_expired_signature_denied(self):
        data=self.payload('RUN-aaa',3)
        with self.assertRaises(PermissionError): self.submit('tool-result',data,self.signed('tool-result',data,issued_at=time.time()-1000))

    def test_05_future_signature_denied(self):
        data=self.payload('RUN-aaa',3)
        with self.assertRaises(PermissionError): self.submit('tool-result',data,self.signed('tool-result',data,issued_at=time.time()+1000))

    def test_06_signature_replay_denied_even_new_run_id(self):
        data=self.payload('RUN-aaa',3)
        proof=self.signed('tool-result',data)
        self.submit('tool-result',data,proof)
        before=self.path.read_bytes()
        with self.assertRaises(PermissionError): self.submit('tool-result',data,proof)
        self.assertEqual(before,self.path.read_bytes())

    def test_07_signed_tool_success(self):
        self.submit('tool-result',self.payload('RUN-aaa',3))
        s=self.state()
        self.assertEqual(s['evidence'][-1]['value'],3)
        self.assertEqual(s['authorization_audit'][-1]['role'],'tool')
        self.assertNotIn('mac',str(s['authorization_audit']))

    def test_08_conflict_flag_and_preserve_both(self):
        self.submit('tool-result',self.payload('RUN-aaa',3))
        self.submit('tool-result',self.payload('RUN-bbb',8))
        s=self.state()
        self.assertEqual(len(s['evidence_conflicts']),1)
        self.assertEqual(s['evidence_conflicts'][0]['status'],'UNRESOLVED')
        self.assertEqual([e['value'] for e in s['evidence'] if e['facet']=='pe_entropy'],[3,8])

    def test_09_equal_values_do_not_conflict(self):
        self.submit('tool-result',self.payload('RUN-aaa',3))
        self.submit('tool-result',self.payload('RUN-bbb',3))
        self.assertFalse(self.state()['evidence_conflicts'])

    def test_10_stale_assessment_after_new_conflict(self):
        self.submit('tool-result',self.payload('RUN-aaa',3))
        cm.apply_update(self.path,'action',{'event_id':'E-start','action':'START_INVESTIGATION'})
        evid=self.state()['evidence'][-1]['evidence_id']
        cm.apply_update(self.path,'assessment',{'verdict':'SUSPICIOUS','confidence':0.5,
            'evidence_ids':[evid],'rationale':'Preliminary evaluation'})
        self.assertEqual(self.state()['assessment']['validity'],'CURRENT')
        self.submit('tool-result',self.payload('RUN-bbb',8))
        self.assertEqual(self.state()['assessment']['validity'],'STALE_CONFLICT')
        with self.assertRaises(ValueError):
            cm.apply_update(self.path,'action',{'event_id':'E-close','action':'CLOSE_CASE'})

    def test_11_conflicting_collection_facets_flagged(self):
        newer=copy.deepcopy(self.ctx)
        newer['collection_id']='COL-harden-2'
        newer['facets']['name']['value']='other.exe'
        cm.apply_update(self.path,'collection',newer)
        self.assertEqual(self.state()['evidence_conflicts'][0]['facet'],'name')

    def test_12_unsigned_approval_denied(self):
        cm.apply_update(self.path,'action',{'event_id':'E-start','action':'START_INVESTIGATION'})
        data={'status':'APPROVED','description':'Quarantine proposal only','human_approved':True,'approver':'alice'}
        with self.assertRaises(PermissionError): cm.apply_update(self.path,'response',data)
        self.assertEqual(self.state()['response_history'],[])

    def test_13_signed_approval_succeeds_as_audit_record_only(self):
        cm.apply_update(self.path,'action',{'event_id':'E-start','action':'START_INVESTIGATION'})
        data={'status':'APPROVED','description':'Quarantine proposal only','human_approved':True,'approver':'alice'}
        self.submit('response',data)
        self.assertEqual(self.state()['response_history'][0]['approver'],'alice')
        self.assertEqual(self.state()['authorization_audit'][-1]['role'],'approval')

    def test_14_approval_role_cannot_authorize_tool_result(self):
        data=self.payload('RUN-aaa',3)
        with self.assertRaises(PermissionError): self.submit('tool-result',data,self.signed('response',
            {'status':'APPROVED','description':'test','human_approved':True,'approver':'alice'}))

    def test_15_signed_approval_cannot_change_approver(self):
        cm.apply_update(self.path,'action',{'event_id':'E-start','action':'START_INVESTIGATION'})
        data={'status':'APPROVED','description':'Quarantine','human_approved':True,'approver':'alice'}
        proof=self.signed('response',data)
        data['approver']='mallory'
        with self.assertRaises(PermissionError): self.submit('response',data,proof)

    def test_16_corrupt_case_json_does_not_overwrite(self):
        self.path.write_text('{bad json',encoding='utf-8')
        before=self.path.read_bytes()
        with self.assertRaises(json.JSONDecodeError):
            cm.apply_update(self.path,'action',{'event_id':'E-note','action':'NOTE'})
        self.assertEqual(before,self.path.read_bytes())

    def test_17_large_evidence_and_revision(self):
        # Stress sequential writes without approaching 8 MiB file cap.
        for i in range(60):
            cm.apply_update(self.path,'action',{'event_id':f'E-note-{i}','action':'NOTE'})
        s=self.state()
        self.assertEqual(len(s['action_history']),60)
        self.assertEqual(s['revision'],62)

    def test_18_public_cli_rejects_protected_tool_result(self):
        data=self.payload('RUN-aaa',3)
        f=self.root/'payload.json'
        f.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(SystemExit) as e:
            cm.main(['tool-result','--case',str(self.path),'--input',str(f)])
        self.assertEqual(e.exception.code,1)


    # Conflict resolution and reassessment regressions
    def test_19_verified_conflict_resolution_and_reassessment(self):
        self.submit('tool-result',self.payload('RUN-aaa',3))
        cm.apply_update(self.path,'action',{'event_id':'E-start','action':'START_INVESTIGATION'})
        old_id=self.state()['evidence'][-1]['evidence_id']
        cm.apply_update(self.path,'assessment',{'verdict':'SUSPICIOUS','confidence':.5,
            'evidence_ids':[old_id],'rationale':'Initial observation'})
        self.submit('tool-result',self.payload('RUN-bbb',8))
        state=self.state()
        conflict=state['evidence_conflicts'][0]
        newer=next(e['evidence_id'] for e in state['evidence'] if e.get('tool_run_id')=='RUN-bbb')
        with self.assertRaises(PermissionError):
            cm.apply_update(self.path,'resolve-conflict',{'conflict_id':conflict['conflict_id'],
                'selected_evidence_id':newer,'reason':'Checked newer sample','approver':'alice'})
        resolution={'conflict_id':conflict['conflict_id'],'selected_evidence_id':newer,
            'reason':'Validated the newer observation against source artifact', 'approver':'alice'}
        self.submit('resolve-conflict',resolution)
        self.assertEqual(self.state()['evidence_conflicts'][0]['status'],'RESOLVED')
        cm.apply_update(self.path,'assessment',{'verdict':'UNKNOWN','confidence':.2,
            'evidence_ids':[newer],'rationale':'Conflicting evidence was reviewed'})
        self.assertEqual(self.state()['assessment']['validity'],'CURRENT')
        self.assertEqual(len(self.state()['assessment_history']),1)
        cm.apply_update(self.path,'action',{'event_id':'E-close','action':'CLOSE_CASE'})
        self.assertEqual(self.state()['lifecycle_status'],'CLOSED')

    def test_20_unresolved_conflict_prevents_reassessment(self):
        self.submit('tool-result',self.payload('RUN-aaa',3))
        cm.apply_update(self.path,'action',{'event_id':'E-start','action':'START_INVESTIGATION'})
        evid=self.state()['evidence'][-1]['evidence_id']
        cm.apply_update(self.path,'assessment',{'verdict':'UNKNOWN','confidence':.2,
            'evidence_ids':[evid],'rationale':'Initial review'})
        self.submit('tool-result',self.payload('RUN-bbb',8))
        with self.assertRaises(ValueError):
            cm.apply_update(self.path,'assessment',{'verdict':'UNKNOWN','confidence':.2,
                'evidence_ids':[],'rationale':'Trying to ignore unresolved conflict'})


if __name__=='__main__': unittest.main(verbosity=2)
