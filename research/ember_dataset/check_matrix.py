"""Read-only checks for a prepared research matrix; never trains or parses PE files."""
import argparse
import json
from pathlib import Path

import numpy as np

from prepare import rows, digest


def check(data, matrix, vectorizer=None):
    complete = json.loads((matrix / 'COMPLETE.json').read_text(encoding='utf-8'))
    report = {'splits': {}, 'source_hashes_verified': False}
    for split in ('train', 'test'):
        X = np.load(matrix / f'X_{split}.npy', mmap_mode='r')
        y = np.load(matrix / f'y_{split}.npy', mmap_mode='r')
        expected = sum(complete['splits'][split]['labels'].get(str(k), 0) for k in (0, 1))
        if X.shape != (expected, 2381) or y.shape != (expected,):
            raise ValueError(f'{split}: matrix shape mismatch')
        if X.dtype != np.dtype('float32') or y.dtype != np.dtype('int8'):
            raise ValueError(f'{split}: dtype mismatch')
        counts = {0: 0, 1: 0}
        for start in range(0, expected, 4096):
            if not np.isfinite(X[start:start + 4096]).all():
                raise ValueError(f'{split}: nonfinite matrix values')
            labels = y[start:start + 4096]
            if not np.isin(labels, [0, 1]).all():
                raise ValueError(f'{split}: nonbinary labels')
            for label in counts:
                counts[label] += int(np.count_nonzero(labels == label))
        paths = sorted(data.glob('train_features_*.jsonl')) if split == 'train' else [data / 'test_features.jsonl']
        source = (r for r in rows(paths) if r['label'] != -1)
        seen = vector_rows = 0
        with (matrix / f'{split}_metadata.jsonl').open(encoding='utf-8') as stream:
            for i, record in enumerate(source):
                line = stream.readline()
                if not line:
                    raise ValueError(f'{split}: missing metadata row {i}')
                metadata = json.loads(line)
                if metadata != {k: record.get(k) for k in ('sha256', 'appeared', 'label')}:
                    raise ValueError(f'{split}: metadata/source mismatch at row {i}')
                if i >= expected or int(y[i]) != record['label']:
                    raise ValueError(f'{split}: label/source mismatch at row {i}')
                if vectorizer is not None and (i % 25000 == 0 or i == expected - 1):
                    vector = np.asarray(vectorizer(record), dtype='float32')
                    if vector.shape != (2381,) or not np.array_equal(X[i], vector):
                        raise ValueError(f'{split}: vector/source mismatch at row {i}')
                    vector_rows += 1
                seen += 1
            if stream.readline() or seen != expected:
                raise ValueError(f'{split}: metadata count mismatch')
        for file in complete['splits'][split]['files']:
            if digest(data / file['name']) != file['sha256']:
                raise ValueError(f'{split}: source digest changed')
        report['splits'][split] = {'shape': list(X.shape), 'dtype': str(X.dtype),
                                 'label_dtype': str(y.dtype), 'labels': counts,
                                 'all_finite': True, 'metadata_rows_verified': seen,
                                 'vector_rows_recomputed': vector_rows}
    report['source_hashes_verified'] = True
    report['files'] = [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': digest(p)}
                       for p in sorted(matrix.iterdir()) if p.is_file()]
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check-vectors', action='store_true', help='Recompute rows 0,25000,... and last per split')
    args = parser.parse_args()
    vectorizer = None
    if args.check_vectors:
        import ember
        vectorizer = ember.PEFeatureExtractor(feature_version=2).process_raw_features
    result = check(args.data, args.matrix, vectorizer)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
