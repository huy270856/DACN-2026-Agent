"""Score one committed EMBER feature observation without changing CaseState.

This research sidecar is not a D.0 prediction ToolResult and does not set a
malware verdict. It uses the exact feature evidence produced by D5/D7/D9.
"""
import argparse
import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np


def score(case_path, run_id, model_dir):
    case = json.loads(Path(case_path).read_text(encoding='utf-8'))
    runs = [r for r in case.get('tool_runs', []) if r.get('tool_run_id') == run_id]
    if len(runs) != 1 or runs[0].get('status') != 'SUCCESS':
        raise ValueError('Expected one successful committed tool run')
    matches = [e for e in case.get('evidence', [])
               if e.get('tool_run_id') == run_id and e.get('facet') == 'static.ember_features']
    if len(matches) != 1:
        raise ValueError('Expected one EMBER feature observation for the run')
    evidence = matches[0]
    if (evidence.get('status') != 'SUCCESS' or
            evidence.get('source_tool') != 'static_ember_features' or
            evidence.get('content_origin') != 'provider_output' or
            evidence.get('trust_level') != 'UNTRUSTED_CONTENT' or
            (evidence.get('provider') or {}).get('id') != 'ember_v2_real' or
            (evidence.get('target_ref') or {}).get('verified_digest') !=
            case['target_ref']['verified_digest']):
        raise ValueError('Evidence is not from the real EMBER provider')
    payload = evidence.get('value')
    if not isinstance(payload, dict):
        raise ValueError('Expected inline feature payload; artifact-backed output needs a reader')
    case_sha = case['target_ref']['verified_digest']['value']
    if (payload.get('schema_version') != 'ember-output-v1' or
            payload.get('feature_version') != 2 or payload.get('feature_count') != 2381 or
            payload.get('target_sha256') != case_sha):
        raise ValueError('EMBER payload/version/target binding mismatch')
    vector = np.asarray(payload['features'], dtype=np.float32)
    if vector.shape != (2381,) or not np.isfinite(vector).all():
        raise ValueError('Invalid feature vector')
    model_dir = Path(model_dir)
    model_report = json.loads((model_dir / 'REPORT.json').read_text(encoding='utf-8'))
    if model_report['feature_version'] != 2 or model_report['feature_count'] != 2381:
        raise ValueError('Model feature version/count mismatch')
    model_path = model_dir / 'model.txt'
    model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if model_sha != model_report['model']['sha256']:
        raise ValueError('Model checksum mismatch')
    booster = lgb.Booster(model_file=str(model_path))
    if booster.num_feature() != 2381:
        raise ValueError('Model dimensions mismatch')
    probability_like_score = float(booster.predict(vector.reshape(1, -1))[0])
    if not np.isfinite(probability_like_score):
        raise ValueError('Nonfinite model score')
    threshold = float(model_report['validation']['threshold'])
    return {'case_id': case['case_id'], 'case_revision': case['revision'],
            'tool_run_id': run_id, 'feature_evidence_id': evidence['evidence_id'],
            'target_sha256': case_sha, 'feature_version': 2, 'feature_count': 2381,
            'model_sha256': model_sha, 'score': probability_like_score,
            'decision_threshold': threshold,
            'predicted_label': int(probability_like_score >= threshold),
            'note': 'Research sidecar only; CaseState assessment/verdict is unchanged.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = score(args.case, args.run_id, args.model_dir)
    if args.output:
        if args.output.exists():
            raise FileExistsError('Output already exists: {}'.format(args.output))
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
