"""06B-R2 DEBUG diagnostic: one live v3.4 pass on the SAME tracert/findstr/fc that
served v3.1-v3.3 development. Per R2_PROTOCOL this is DEBUG/root-cause only (task
spec 12.1), NOT confirmatory and NOT an independent holdout. No prompt tuning, no
re-run-until-pass; the single pass is written once and never overwritten. Exclusive
outputs; frozen repair_dev_v4 is never touched.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import time

from agent.config import AgentConfig
from dacn.config import AppConfig
from dacn import investigation as inv
import case_manager as cm
from investigation_v3 import application, workflow_v34, audit, final_v34
from investigation_v3.imports_tool import file_sha, TOOL_ID, FACET
from evaluation.task06a.experiment import read, write_new
from evaluation.task06b.experiment import ROOT, RUNTIME, ollama

CFG = AgentConfig(max_iterations=5, max_tool_calls=1, max_context_chars=24000, num_predict=2048,
                  inference_timeout_s=90, wall_clock_s=180)
FROZEN = ROOT / 'evaluation/task06b/results/repair_dev_v4'


def source_hashes():
    mods = ['investigation_v3/final_v34.py', 'investigation_v3/workflow_v34.py',
            'investigation_v3/repair_context.py', 'investigation_v3/retrieval.py',
            'investigation_v3/imports_tool.py', 'investigation_v3/grounding.py',
            'investigation_v3/context.py', 'evaluation/task06b/r2_debug.py']
    return {m: file_sha(ROOT / m) for m in mods}


def run(out):
    if out.exists():
        raise ValueError('NEW_VERSION_REQUIRED')  # never overwrite a saved DEBUG pass
    man = read(FROZEN / 'manifest_EVALUATOR_ONLY.json')
    model = next(m for m in ollama('tags')['models'] if m['name'] == CFG.model)
    mm = inv.load_model_manifest()
    out.mkdir(parents=True)
    rows = []
    for i, item in enumerate(man['dev'][:3]):
        src = Path(item['source'])
        if file_sha(src) != item['sha256']:
            raise ValueError('TARGET_DRIFT ' + item['filename'])
        home = AppConfig.from_home(RUNTIME / out.name / f'{i:02d}_E')
        start = time.monotonic()
        path, reg, orch, policy, events = application.prepare(home, file=str(src))
        static_latency = time.monotonic() - start
        state = cm.validate_case(cm.read_json(path))
        write_new(out / f'{i:02d}_initial_state.json', state)
        report = workflow_v34.run(path, CFG, reg, orch, policy, events=events)
        report['end_to_end_latency_s'] = report['latency_s'] + static_latency
        report['filename'] = item['filename']
        write_new(out / f'{i:02d}_E.json', report)
        v = report.get('verification', {}) or {}
        tm = report.get('trusted_metadata', {}) or {}
        rows.append({'index': i, 'filename': item['filename'], 'sha256': item['sha256'],
                     'status': report['status'], 'final_present': report['final'] is not None,
                     'first_pass_final': report['final'] is not None and not report.get('repair_attempts', 0),
                     'tools': report['tool_attempts'], 'reads': report.get('retrieval_attempts', 0),
                     'repairs': report.get('repair_attempts', 0),
                     'D9_commits': sum(e['stage'] == 'D9_COMMITTED' for e in report['events'][report['agent_event_start']:]),
                     'revision_before': report['initial_revision'], 'revision_after': report['final_revision'],
                     'resolved_import_refs': len(tm.get('resolved_import_refs', [])),
                     'literal_new_fact_uses': len(v.get('literal_new_fact_uses', [])),
                     'suspected_grounding_flags': v.get('flags', []),
                     'suspected_claim_flags': v.get('claim_flags', []),
                     'consistency_flags': v.get('consistency', {}).get('flags', []),
                     'effective_action': report['effective_recommendation']['action'],
                     'latency_s': report['latency_s'], 'end_to_end_latency_s': report['end_to_end_latency_s'],
                     'prompt_tokens': report['prompt_tokens'], 'output_tokens': report['output_tokens'],
                     'failure': report.get('failure'),
                     'turn_errors': [t.get('error') or t.get('validation_error') for t in report['turns']
                                     if t.get('error') or t.get('validation_error')],
                     'semantic_grounding': 'PENDING_INDEPENDENT_REVIEW'})
        print(i, item['filename'], report['status'], 'final', report['final'] is not None,
              'tools', report['tool_attempts'], 'reads', report.get('retrieval_attempts'),
              'repairs', report.get('repair_attempts'),
              'resolved_refs', len(tm.get('resolved_import_refs', [])), flush=True)
    write_new(out / 'freeze.json', {'created_utc': datetime.now(timezone.utc).isoformat(),
        'track': 'R2_DEBUG_DIAGNOSTIC_ON_DEVELOPMENT_SHAS', 'confirmatory': 'NOT_RUN',
        'independent_holdout': 'NO_REUSES_v3.1_v3.3_DEVELOPMENT_FILES', 'human_grading': 'PENDING',
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'contract_version': final_v34.VERSION, 'system_prompt_sha256': file_sha_text(final_v34.SYSTEM),
        'source_hashes': source_hashes(), 'config': asdict(CFG),
        'model_sha256': mm['model_sha256'], 'threshold': mm['threshold_selection']['primary_threshold'],
        'ollama_model': model, 'ollama_version': ollama('version'), 'python': platform.python_version(),
        'reused_from': str(FROZEN), 'dev_shas': [it['sha256'] for it in man['dev'][:3]]})
    write_new(out / 'summary.json', {'cases': rows, 'n': len(rows), 'track': 'R2_DEBUG_DIAGNOSTIC',
        'confirmatory': 'NOT_RUN', 'note': 'Single live pass, no tuning; reuses development files; '
        'not evidence of generalization. MOCK integration proven separately in tests/test_v34.py.'})
    print(json.dumps(rows, indent=2))


def file_sha_text(text):
    import hashlib
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=('run',))
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    run(args.out)
