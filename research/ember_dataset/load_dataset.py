"""Load completed EMBER matrices read-only; no model training."""
import argparse
import json
from pathlib import Path

import numpy as np


def load_split(root, split):
    root = Path(root)
    if split not in ('train', 'test'):
        raise ValueError('split must be train or test')
    report = json.loads((root / 'COMPLETE.json').read_text(encoding='utf-8'))
    count = sum(report['splits'][split]['labels'].get(str(k), 0) for k in (0, 1))
    X = np.load(root / f'X_{split}.npy', mmap_mode='r', allow_pickle=False)
    y = np.load(root / f'y_{split}.npy', mmap_mode='r', allow_pickle=False)
    if X.shape != (count, 2381) or X.dtype != np.dtype('float32'):
        raise ValueError('Unexpected feature matrix shape/dtype')
    if y.shape != (count,) or y.dtype != np.dtype('int8') or not np.isin(y, [0, 1]).all():
        raise ValueError('Unexpected labels')
    return X, y


def metadata_rows(root, split):
    if split not in ('train', 'test'):
        raise ValueError('split must be train or test')
    with (Path(root) / f'{split}_metadata.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', required=True, type=Path)
    args = parser.parse_args()
    for split in ('train', 'test'):
        X, y = load_split(args.matrix, split)
        labels, counts = np.unique(y, return_counts=True)
        print(json.dumps({'split': split, 'shape': list(X.shape), 'dtype': str(X.dtype),
                          'labels': {str(int(k)): int(v) for k, v in zip(labels, counts)}}))
