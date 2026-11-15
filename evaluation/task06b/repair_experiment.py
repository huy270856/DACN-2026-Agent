"""06B-R DEV A/B/C/D. Exclusive outputs, fresh SHA strata, actual Qwen only."""
import argparse
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import time

from agent.config import AgentConfig
from dacn.config import AppConfig
from dacn import investigation as inv
import case_manager as cm
from investigation_v3 import application, workflow, repair_workflow, audit
from investigation_v3.import_adapter import inspect_file
from investigation_v3.imports_tool import file_sha, TOOL_ID, FACET
from evaluation.task06a.experiment import read, write_new
from evaluation.task06b.experiment import ROOT, RUNTIME, ollama

CANDIDATES = ['hostname.exe','tracert.exe','findstr.exe','fc.exe','compact.exe','sort.exe',
 'auditpol.exe','bcdedit.exe','bitsadmin.exe','makecab.exe','dsregcmd.exe','esentutl.exe','expand.exe',
 'tzutil.exe','setx.exe','cmd.exe','timeout.exe','winver.exe','colorcpl.exe','lodctr.exe','fltmc.exe',
 'verifier.exe','extrac32.exe','robocopy.exe','notepad.exe','subst.exe','doskey.exe','label.exe',
 'shutdown.exe','chcp.com','more.com','help.exe','tree.com','finger.exe','print.exe','choice.exe',
 'computerdefaults.exe','wscript.exe','cscript.exe','openfiles.exe','query.exe','qwinsta.exe']
CFG = AgentConfig(max_iterations=5,max_tool_calls=1,max_context_chars=24000,num_predict=2048,
                  inference_timeout_s=90,wall_clock_s=180)
PROTOCOL = ROOT/'evaluation/task06b/REPAIR_PROTOCOL.md'


def sources():
    names = subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    names += [p.relative_to(ROOT).as_posix() for folder in ('investigation_v3','evaluation/task06b')
              for p in (ROOT/folder).rglob('*.py') if not {'results','runtime','__pycache__'} & set(p.parts)]
    return {n:file_sha(ROOT/n) for n in sorted(set(names))
            if (n.endswith('.py') or n=='evaluation/task06b/REPAIR_PROTOCOL.md')
            and not {'results','runtime'} & set(Path(n).parts)}


def select():
    old=set(); prefix=set(); scanned=[]
    for folder in ('task05c','task05d','task06a','task06b'):
        for p in (ROOT/'evaluation'/folder).rglob('*.json'):
            if 'runtime' in p.parts:continue
            text=p.read_text(encoding='utf8')
            old.update(re.findall(r'\b[0-9a-f]{64}\b',text))
            prefix.update(re.findall(r'\b[0-9a-f]{12}\b',text))
    rich=[];small=[]
    # Inspect all fixed candidates; record missing strata without replacing by mocks.
    for name in CANDIDATES:
        path=Path('C:/Windows/System32')/name
        if not path.exists():scanned.append({'name':name,'reason':'missing'});continue
        sha=file_sha(path)
        if sha in old or sha[:12] in prefix:
            scanned.append({'name':name,'reason':'historical_overlap'});continue
        if path.stat().st_size>8*1024*1024:
            scanned.append({'name':name,'reason':'size_budget'});continue
        command="$s=Get-AuthenticodeSignature -LiteralPath '"+str(path).replace("'","''")+"'; @{status=[string]$s.Status;subject=[string]$s.SignerCertificate.Subject}|ConvertTo-Json -Compress"
        sig=json.loads(subprocess.check_output(['powershell','-NoProfile','-NonInteractive','-Command',command],text=True,timeout=30))
        if sig['status']!='Valid' or 'Microsoft' not in sig['subject']:
            scanned.append({'name':name,'reason':'signature_not_valid_Microsoft'});continue
        detail=inspect_file(path)
        item={'filename':name,'source':str(path),'sha256':sha,'signature':sig,
              'total_imports':detail['total_entries'],'has_ordinal_in_retained':any(e['ordinal'] is not None for e in detail['entries']),
              'true_label_EVALUATOR_ONLY':'benign','label_basis':'OS + valid Microsoft signature; not absolute safety'}
        (small if detail['total_entries']<=16 else rich).append(item)
        scanned.append({'name':name,'reason':'eligible','imports':detail['total_entries']})
        old.add(sha)
    chosen=rich[:3]+small[:1]
    if not chosen:raise ValueError('NO_FRESH_AUTHORIZED_PE')
    return chosen,scanned,{'rich_candidates':len(rich),'small_candidates':len(small),
                         'missing_small_stratum':not small,'full_sha_and_probe_prefix_checked':True}


def prepare(out, reuse_selection=None):
    if out.exists():raise ValueError('NEW_VERSION_REQUIRED')
    model=next(m for m in ollama('tags')['models'] if m['name']==CFG.model)
    mm=inv.load_model_manifest()
    if reuse_selection:
        previous=read(reuse_selection/'manifest_EVALUATOR_ONLY.json')
        selected=previous['dev'];scanned=previous['scanned'];limits=dict(previous['limitations'])
        limits['reuse_after_development_feedback']=str(reuse_selection)
    else:
        selected,scanned,limits=select()
    out.mkdir(parents=True)
    cases=[]
    for i,item in enumerate(selected):
        homes={arm:AppConfig.from_home(RUNTIME/out.name/f'{i:02d}_{arm}') for arm in ('B','C','D')}
        start=time.monotonic()
        path,reg,orch,policy,events=application.prepare(homes['C'],file=item['source'])
        elapsed=time.monotonic()-start
        state=cm.validate_case(cm.read_json(path));cases_paths={}
        for arm,cfg in homes.items():
            if arm=='C':cases_paths[arm]=str(path);continue
            cfg.cases_dir.mkdir(parents=True,exist_ok=True)
            dest=cm.case_path(cfg.cases_dir,state['case_id']);dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(path.read_bytes())
            cases_paths[arm]=str(dest)
        write_new(out/f'{i:02d}_initial_state.json',state)
        write_new(out/f'{i:02d}_initial_trusted_trace.json',events)
        pred=inv.read_prediction_evidence(state)['value']
        write_new(out/f'{i:02d}_A.json',{'method':'STATIC_TEMPLATE_06B_R','model_prediction':pred,
            'explanation':'Static prediction only; raw score uncalibrated; concrete imports unavailable.',
            'recommendation':inv.derive_recommendation(pred['predicted_label'],None),'latency_s':elapsed})
        cases.append({'index':i,'sha256':item['sha256'],'initial_file':f'{i:02d}_initial_state.json',
                      'case_paths':cases_paths,'homes':{k:str(v.home) for k,v in homes.items()},'static_latency_s':elapsed})
    write_new(out/'cases.json',cases)
    write_new(out/'manifest_EVALUATOR_ONLY.json',{'dev':selected,'selection':CANDIDATES,'scanned':scanned,
        'limitations':limits,'track':'RAW_PE_E2E_BENIGN_DEV','confirmatory':'NOT_RUN','human_grading':'PENDING'})
    write_new(out/'source_snapshot.json',{n:(ROOT/n).read_bytes().decode('utf8') for n in sources()})
    write_new(out/'freeze.json',{'created_utc':datetime.now(timezone.utc).isoformat(),
        'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'sources':sources(),'config':asdict(CFG),'model_sha256':mm['model_sha256'],
        'threshold':mm['threshold_selection']['primary_threshold'],'ollama_model':model,'ollama_version':ollama('version'),
        'python':platform.python_version(),'protocol_sha256':file_sha(PROTOCOL),
        'adapter_pins':dict(orch._installation.pinned_adapter_for(reg.get_tool(TOOL_ID,'0.1.0')).pins),
        'initial_hashes':{p.name:file_sha(p) for p in out.glob('*.json')},
        'C':'Reviewed legacy workflow/context/schema unchanged; shared backend post-review compatible opt-in additions only',
        'ordering':'B then C/D even; B then D/C odd; independent same-initial-state branches'})
    print('FROZEN',len(cases),'cases',limits,flush=True)


def validate(out):
    f=read(out/'freeze.json')
    if f['sources']!=sources() or file_sha(PROTOCOL)!=f['protocol_sha256']:raise ValueError('SOURCE_PROTOCOL_DRIFT')
    for n,h in f['initial_hashes'].items():
        if file_sha(out/n)!=h:raise ValueError('INPUT_DRIFT')
    mm=inv.load_model_manifest()
    if mm['model_sha256']!=f['model_sha256'] or mm['threshold_selection']['primary_threshold']!=f['threshold']:raise ValueError('MODEL_DRIFT')
    if any(file_sha(p)!=h for p,h in f['adapter_pins'].items()):raise ValueError('TOOL_DRIFT')
    model=next(m for m in ollama('tags')['models'] if m['name']==CFG.model)
    if model['digest']!=f['ollama_model']['digest'] or ollama('version')!=f['ollama_version']:raise ValueError('QWEN_DRIFT')
    return f


def run(out):
    from dataclasses import replace
    f=validate(out);cfg=AgentConfig(**f['config'])
    # Only hashes of evaluator labels are checked; not parsed by inference.
    for item in read(out/'cases.json'):
        i=item['index']
        for arm in (('B','C','D') if i%2==0 else ('B','D','C')):
            dest=out/f'{i:02d}_{arm}.json'
            if dest.exists():continue
            path=Path(item['case_paths'][arm]);state=cm.read_json(path)
            initial=read(out/item['initial_file'])
            if state!=initial:raise ValueError('STATE_CHANGED_WITHOUT_SAVED_TRACE_NO_RETRY')
            if file_sha(state['target_ref']['observed']['path'])!=item['sha256']:raise ValueError('TARGET_DRIFT')
            config=AppConfig.from_home(item['homes'][arm])
            reg,orch=inv.build_detector_backend(config,include_imports=True);events=[];policy=audit.attach(orch,events)
            fn=workflow.run if arm=='C' else repair_workflow.run
            report=fn(path,replace(cfg,max_iterations=3) if arm=='C' else cfg,reg,orch,policy,
                      tool_enabled=arm!='B',events=events)
            report['end_to_end_latency_s']=report['latency_s']+item['static_latency_s']
            write_new(dest,report)
            print(i,arm,report['status'],'turns',len(report['turns']),'tools',report['tool_attempts'],
                  'reads',report.get('retrieval_attempts'),'repair',report.get('repair_attempts'),flush=True)
            # Capture portable stdout, never target.bin or secrets/private signing key.
            for stdout in config.artifacts_dir.rglob('stdout.bin'):
                folder=out/'provider_stdout';folder.mkdir(exist_ok=True)
                target=folder/(arm+'_'+stdout.parent.name+'.json')
                if not target.exists():target.write_bytes(stdout.read_bytes())
            ledgers=out/'audit_ledgers';ledgers.mkdir(exist_ok=True)
            for ledger in config.home.rglob('*.jsonl'):
                target=ledgers/f'{i:02d}_{arm}_{ledger.name}'
                if not target.exists():target.write_bytes(ledger.read_bytes())
        d=read(out/f'{i:02d}_D.json')
        if d['tool_attempts'] and any(e['facet']==FACET and e['status']=='SUCCESS' for e in d['final_state']['evidence']):
            dest=out/f'{i:02d}_resume.json'
            if not dest.exists():
                config=AppConfig.from_home(item['homes']['D']);reg,orch=inv.build_detector_backend(config,include_imports=True)
                events=[];policy=audit.attach(orch,events)
                report=repair_workflow.run(item['case_paths']['D'],cfg,reg,orch,policy,events=events)
                write_new(dest,report)
                print(i,'resume',report['status'],'tools',report['tool_attempts'],flush=True)
    validate(out)


def summarize(out):
    # Analysis only, no model inference; frozen outputs retained.
    rows=[]
    for item in read(out/'cases.json'):
        row={'index':item['index'],'sha256':item['sha256']}
        for arm in ('A','B','C','D','resume'):
            p=out/f"{item['index']:02d}_{arm}.json"
            if not p.exists():continue
            r=read(p)
            if arm=='A':row[arm]={'latency_s':r['latency_s']};continue
            stages=r['events'][r['agent_event_start']:];v=r.get('verification',{})
            bindings=r.get('trusted_metadata',{}).get('claim_literal_bindings',[])
            row[arm]={'status':r['status'],'final_present':r['final'] is not None,
                'first_pass_final':r['final'] is not None and not r.get('repair_attempts',0),
                'tools':r['tool_attempts'],'reads':r.get('retrieval_attempts',0),'repairs':r.get('repair_attempts',0),
                'D9_commits':sum(e['stage']=='D9_COMMITTED' for e in stages),
                'revision_before':r['initial_revision'],'revision_after':r['final_revision'],
                'literal_new_fact_uses':len(v.get('literal_new_fact_uses',[])),
                'literal_bound_claims':len(bindings),'consistency_flags':v.get('consistency',{}).get('flags',[]),
                'suspected_grounding_flags':v.get('flags',[]),'suspected_claim_flags':v.get('claim_flags',[]),
                'effective_action':r['effective_recommendation']['action'],
                'latency_s':r['latency_s'],'end_to_end_latency_s':r.get('end_to_end_latency_s'),
                'prompt_tokens':r['prompt_tokens'],'output_tokens':r['output_tokens'],
                'failure':r.get('failure'),'turn_errors':[t.get('error') or t.get('validation_error') for t in r['turns'] if t.get('error') or t.get('validation_error')],
                'semantic_grounding':'PENDING_INDEPENDENT_REVIEW'}
        rows.append(row)
    write_new(out/'summary.json',{'cases':rows,'n':len(rows),'human_review':'PENDING','confirmatory':'NOT_RUN',
              'malicious_raw_pe':'BLOCKED_NO_APPROVED_SAMPLES','USD_cost':'N/A local; actual tokens/latency reported'})
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=('prepare','run','summarize'))
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--reuse-selection',type=Path);args=ap.parse_args()
    if args.action=='prepare':prepare(args.out,args.reuse_selection)
    else:{'run':run,'summarize':summarize}[args.action](args.out)
