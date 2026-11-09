"""Read a PE file as data and score it with a trained EMBER2018-v2 model.

This standalone research CLI never executes the target. It does not write a
D.0 ToolResult or a CaseState malware verdict.
"""
import argparse
import hashlib
import json
from pathlib import Path

import ember
import lief
import lightgbm as lgb
import numpy as np


def infer(model_dir, target, max_bytes=100_000_000):
    model_dir = Path(model_dir)
    target = Path(target).resolve(strict=True)
    report = json.loads((model_dir / 'REPORT.json').read_text(encoding='utf-8'))
    if report['feature_version'] != 2 or report['feature_count'] != 2381:
        raise ValueError('Model is not EMBER v2 / 2381 features')
    model_file = model_dir / 'model.txt'
    model_bytes = model_file.read_bytes()
    if hashlib.sha256(model_bytes).hexdigest() != report['model']['sha256']:
        raise ValueError('Model checksum mismatch')
    with target.open('rb') as stream:
        file_bytes = stream.read(max_bytes + 1)
        if len(file_bytes) > max_bytes:
            raise ValueError('Target exceeds configured read limit')
    if not file_bytes.startswith(b'MZ'):
        raise ValueError('Target does not have a PE DOS magic header')
    try:
        parsed = lief.PE.parse(list(file_bytes))
    except (lief.bad_format, lief.bad_file, lief.pe_error, lief.parser_error,
            lief.read_out_of_bound, RuntimeError) as error:
        raise ValueError('PE parser rejected target') from error
    if parsed is None:
        raise ValueError('PE parser rejected target')
    del parsed
    extractor = ember.PEFeatureExtractor(feature_version=2)
    if extractor.dim != 2381:
        raise ValueError('Unexpected extractor dimensions')
    vector = np.asarray(extractor.feature_vector(file_bytes), dtype=np.float32)
    if vector.shape != (2381,) or not np.isfinite(vector).all():
        raise ValueError('Invalid extracted feature vector')
    booster = lgb.Booster(model_file=str(model_file))
    if booster.num_feature() != 2381:
        raise ValueError('Model dimensions do not match extractor')
    score = float(booster.predict(vector.reshape(1, -1))[0])
    if not np.isfinite(score):
        raise ValueError('Nonfinite model score')
    # The actual score threshold is selected from benign validation scores.
    score_threshold = float(report['validation']['threshold'])
    return {'target_path': str(target), 'target_sha256': hashlib.sha256(file_bytes).hexdigest(),
            'target_bytes': len(file_bytes), 'feature_version': 2, 'feature_count': 2381,
            'score': score, 'decision_threshold': score_threshold,
            'predicted_label': 1 if score >= score_threshold else 0,
            'validation_target_fpr': float(report['threshold_selection']['target_max_fpr']),
            'model_sha256': report['model']['sha256'],
            'note': 'Research model output only; no CaseState verdict or safety guarantee.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--max-bytes', type=int, default=100_000_000)
    args = parser.parse_args()
    if args.max_bytes < 1:
        parser.error('max-bytes must be positive')
    result = infer(args.model_dir, args.file, args.max_bytes)
    if args.output:
        if args.output.exists():
            raise FileExistsError('Output already exists: {}'.format(args.output))
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
