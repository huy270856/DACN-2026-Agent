"""Vectorize a small deterministic sample of JSON feature records, never PE bytes."""
import argparse
import hashlib
from itertools import islice
import json
from pathlib import Path
import platform

import ember
import lief
import numpy as np
import sklearn

from prepare import rows


def preflight(data, per_file=20):
    extractor = ember.PEFeatureExtractor(feature_version=2)
    if extractor.dim != 2381:
        raise ValueError('Extractor must have 2381 dimensions')
    paths = sorted(data.glob('train_features_*.jsonl')) + [data / 'test_features.jsonl']
    if len(paths) != 7:
        raise ValueError('Expected seven JSONL shards')
    samples = []
    for path in paths:
        for index, record in enumerate(islice(rows([path]), per_file)):
            vector = np.asarray(extractor.process_raw_features(record), dtype='float32')
            if vector.shape != (2381,) or not np.isfinite(vector).all():
                raise ValueError(f'Invalid vector: {path.name}:{index + 1}')
            repeated = np.asarray(extractor.process_raw_features(record), dtype='float32')
            if not np.array_equal(vector, repeated):
                raise ValueError('Nondeterministic vectorization')
            samples.append({'file': path.name, 'line': index + 1, 'sha256': record['sha256'],
                            'vector_sha256': hashlib.sha256(vector.tobytes()).hexdigest()})
    if len(samples) != per_file * 7:
        raise ValueError('Insufficient preflight records')
    return {'rows_checked': len(samples), 'columns': 2381, 'dtype': 'float32',
            'all_finite': True, 'deterministic': True,
            'runtime': {'python': platform.python_version(), 'numpy': np.__version__,
                        'lief': lief.__version__, 'sklearn': sklearn.__version__, 'ember': ember.__file__},
            'samples': samples}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = preflight(args.data)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'samples'}, indent=2))
