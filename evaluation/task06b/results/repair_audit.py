"""Post-hoc deterministic artifact audit; NOT inference, semantic judge or grading.

Kept beside results so adding an evaluator does not alter frozen inference inputs.
Run from repo root: python evaluation/task06b/results/repair_audit.py
Writes a NEW audit file only; never modifies historic freezes/responses.
"""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from d0.validate import digest,verify_receipt_result
from evaluation.task06a.experiment import read,write_new
from investigation_v3.imports_tool import file_sha,FACET


def run():
    output=ROOT/'evaluation/task06b/results'
    protected=read(ROOT/'evaluation/task06a/results/task06a_r/integrity_before.json')['protected_sha256']
    assert all(file_sha(ROOT/p)==h for p,h in protected.items())
    subprocess.run(['git','diff','--exit-code','bfdfd80','--','README.md','agent','research/independent_static_ml',
                    'evaluation/task05c','evaluation/task05d','evaluation/task06a','investigation_v3/workflow.py',
                    'investigation_v3/context.py','investigation_v3/schema.py','investigation_v3/import_adapter.py',
                    'investigation_v3/imports_tool.py'],cwd=ROOT,check=True)
    result={'method':'POST_HOC_DETERMINISTIC_AUDIT_NO_MODEL_NO_SEMANTIC_GRADING',
            'auditor_sha256':file_sha(Path(__file__)), 'protected_unchanged':len(protected),'versions':{}}
    for name in ('dev_v1','dev_v2','repair_dev_v2','repair_dev_v3','repair_dev_v4'):
        out=output/name;f=read(out/'freeze.json');snap=read(out/'source_snapshot.json')
        hashes=f.get('sources',f.get('source_sha256'))
        assert all(hashlib.sha256(snap[p].encode('utf8')).hexdigest()==h for p,h in hashes.items())
        initials=f.get('initial_hashes',f.get('initial_artifacts_sha256'))
        assert all(file_sha(out/p)==h for p,h in initials.items())
        stats={'source_snapshot_files':len(hashes),'initial_hashes_verified':len(initials),'arms':{},'cases':[]}
        if not name.startswith('repair_'):
            result['versions'][name]=stats;continue
        for item in read(out/'cases.json'):
            row={'index':item['index']}
            initial_states=[read(out/f"{item['index']:02d}_{arm}.json")['initial_state'] for arm in ('B','C','D')]
            assert initial_states[0]==initial_states[1]==initial_states[2]
            a=read(out/f"{item['index']:02d}_A.json")
            stats['arms'].setdefault('A',{'latency_s':[]})['latency_s'].append(a['latency_s'])
            for arm in ('B','C','D','resume'):
                p=out/f"{item['index']:02d}_{arm}.json"
                if not p.exists():continue
                r=read(p);stages=r['events'][r['agent_event_start']:]
                calls=[e['call'] for e in stages if e['stage']=='D1_TOOL_CALL']
                receipts=[e['receipt'] for e in stages if e['stage']=='D5_D6_RECEIPT']
                results=[e['result'] for e in stages if e['stage']=='D7_VALIDATED']
                commits=[e['commit'] for e in stages if e['stage']=='D9_COMMITTED']
                for rec,res in zip(receipts,results):
                    call=next(c for c in calls if c['call_id']==rec['call_id'])
                    assert verify_receipt_result(rec,res,call)
                    assert res['receipt_sha256']==digest(rec)
                    if res['status']=='SUCCESS':
                        ev=next(e for e in r['final_state']['evidence'] if e.get('tool_run_id')==rec['run_id'] and e['facet']==FACET)
                        assert ev['value']==res['observations'][0]['value']
                        assert ev['value']['target_sha256']==item['sha256']
                        assert any(c['tool_run_id']==rec['run_id'] for c in commits)
                        assert any(any(e['evidence_id']==ev['evidence_id'] for e in t['context']['facts']['evidence'])
                                   and t['context']['facts']['case_revision']==r['final_revision'] for t in r['turns'][1:])
                literal=0
                for bind in r.get('trusted_metadata',{}).get('claim_literal_bindings',[]):
                    turn=next(t for t in reversed(r['turns']) if t.get('proposal')==r['final'])
                    source=next(e for e in turn['context']['facts']['evidence'] if e['evidence_id']==bind['evidence_id'])
                    entry=next(e for e in source['value']['entries'] if e['entry_index']==bind['entry_index'])
                    claim=r['final']['assessment']['claims'][bind['claim_index']]
                    assert bind['evidence_id'] in claim['evidence_ids'] and entry['library'] in claim['text']
                    assert (entry['symbol'] or '#'+str(entry['ordinal'])) in claim['text']
                    literal+=1
                raw_bindings=[]
                for turn in r['turns']:
                    obj=turn.get('proposal',{})
                    if obj.get('action')!='FINISH' or 'assessment' not in obj:continue
                    visible={e['evidence_id']:e for e in turn['context']['facts']['evidence']}
                    for binding in obj.get('import_bindings',[]):
                        claims=obj['assessment']['claims'];ci=binding['claim_index']
                        ev=visible.get(binding['evidence_id'],{})
                        entry=next((e for e in (ev.get('value') or {}).get('entries',[])
                                    if e.get('entry_index')==binding['entry_index']),None)
                        valid=(ci<len(claims) and ev.get('facet')==FACET and entry is not None
                               and binding['evidence_id'] in claims[ci]['evidence_ids']
                               and entry['library'] in claims[ci]['text']
                               and (entry['symbol'] or '#'+str(entry['ordinal'])) in claims[ci]['text'])
                        raw_bindings.append({'turn':turn['iteration'],'claim_index':ci,'evidence_id':binding['evidence_id'],
                                             'entry_index':binding['entry_index'],'literal_match':bool(valid)})
                row[arm]={'status':r['status'],'failure':r.get('failure'),'tools':r['tool_attempts'],
                          'D9_commits':len(commits),'reads':r.get('retrieval_attempts',0),
                          'repairs':r.get('repair_attempts',0),'literal_bound_claims':literal,
                          'raw_bindings_all_final_attempts':raw_bindings,
                          'errors':[t.get('validation_error') or t.get('error') for t in r['turns'] if t.get('validation_error') or t.get('error')]}
                s=stats['arms'].setdefault(arm,{'n':0,'finals':0,'status_FINISHED_count':0,'tools':0,'D9_commits':0,'reads':0,
                    'repairs':0,'first_pass_finals':0,'literal_bound_claims':0,'tokens_prompt':0,'tokens_output':0,
                    'latency_s':[],'end_to_end_s':[],'calls':0,'effective_review':0,'literal_new_fact_uses':0,
                    'raw_binding_attempts':0,'raw_binding_literal_matches':0})
                s['n']+=1;s['finals']+=r['final'] is not None;s['status_FINISHED_count']+=r['status']=='FINISHED'
                s['first_pass_finals']+=r['final'] is not None and not r.get('repair_attempts',0)
                s['tools']+=r['tool_attempts'];s['D9_commits']+=len(commits);s['reads']+=r.get('retrieval_attempts',0)
                s['repairs']+=r.get('repair_attempts',0);s['literal_bound_claims']+=literal
                s['raw_binding_attempts']+=len(raw_bindings)
                s['raw_binding_literal_matches']+=sum(b['literal_match'] for b in raw_bindings)
                s['literal_new_fact_uses']+=len(r.get('verification',{}).get('literal_new_fact_uses',[]))
                s['tokens_prompt']+=r['prompt_tokens'];s['tokens_output']+=r['output_tokens'];s['calls']+=len(r['turns'])
                s['latency_s'].append(r['latency_s']);s['effective_review']+=r['effective_recommendation']['review_required']
                if 'end_to_end_latency_s' in r:s['end_to_end_s'].append(r['end_to_end_latency_s'])
            stats['cases'].append(row)
        for s in stats['arms'].values():
            for key in ('latency_s','end_to_end_s'):
                if s.get(key):s['mean_'+key]=statistics.mean(s[key])
        result['versions'][name]=stats
    result['clarification']='status_FINISHED_count is raw status, NOT proof of unflagged grounding; earlier audit used misleading name unflagged_status for legacy C. Original audit retained.'
    write_new(output/'repair_artifact_audit_v2.json',result)
    print(json.dumps({k:v.get('arms',{}) for k,v in result['versions'].items()},indent=2))


if __name__=='__main__':run()
