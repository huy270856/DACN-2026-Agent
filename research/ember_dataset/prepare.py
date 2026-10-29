"""Offline research utility; does not import or modify D1-D9."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import re
import tempfile
import sqlite3
import tarfile
import urllib.request

URL = 'https://ember.elastic.co/ember_dataset_2018_2.tar.bz2'
SHA = 'b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812'
GROUPS = ('histogram', 'byteentropy', 'strings', 'general', 'header', 'section', 'imports', 'exports', 'datadirectories')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def fetch(root):
    root.mkdir(parents=True, exist_ok=True)
    archive = root / 'ember_dataset_2018_2.tar.bz2'
    if not archive.exists():
        partial = archive.with_suffix('.part')
        with urllib.request.urlopen(URL, timeout=60) as response, partial.open('wb') as f:
            shutil.copyfileobj(response, f, 1024 * 1024)
        if digest(partial) != SHA:
            raise ValueError('Archive SHA256 mismatch; partial retained for diagnosis')
        partial.rename(archive)
    if digest(archive) != SHA:
        raise ValueError('Archive SHA256 mismatch')
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': SHA}))
    # Copy only expected JSONL files; no archive-controlled filesystem paths.
    with tarfile.open(archive, 'r:bz2') as tar:
        seen = set()
        for member in tar:
            name = Path(member.name).name
            if name not in {f'train_features_{i}.jsonl' for i in range(6)} | {'test_features.jsonl'}:
                continue
            if not member.isfile() or name in seen:
                raise ValueError('Unexpected duplicate or non-file member')
            seen.add(name)
            destination = root / name
            if destination.exists():
                raise ValueError(f'Refusing to overwrite {destination}')
            with tar.extractfile(member) as source, destination.open('xb') as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
        if len(seen) != 7:
            raise ValueError('Expected six train files and one test file')


def rows(paths):
    for path in paths:
        with path.open(encoding='utf-8') as f:
            for line, text in enumerate(f, 1):
                try:
                    obj = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON: ' + value)))
                    if not isinstance(obj, dict):
                        raise ValueError('Record is not an object')
                    yield obj
                except (ValueError, TypeError) as exc:
                    raise ValueError(f'{path}:{line}: {exc}') from exc


def audit(root):
    report = {'dataset': 'EMBER2018 v2 candidate', 'expected_feature_version': 2, 'verified_feature_version': None,
              'version_note': 'Expected source release; verify official archive digest separately. Field presence is not proof of extractor equivalence.', 'splits': {}}
    with tempfile.TemporaryDirectory() as temp:
        db = sqlite3.connect(str(Path(temp) / 'hashes.sqlite'))
        db.execute('CREATE TABLE hashes (sha TEXT PRIMARY KEY, split TEXT)')
        try:
            _audit_splits(root, report, db)
        finally:
            db.close()
    return report


def _audit_splits(root, report, db):
    for split in ('train', 'test'):
        paths = sorted(root.glob('train_features_*.jsonl')) if split == 'train' else [root / 'test_features.jsonl']
        if not paths or any(not p.is_file() for p in paths):
            raise ValueError(f'Missing {split} JSONL')
        counts, missing, total = Counter(), Counter(), 0
        invalid_hashes = duplicates = overlap = 0
        declared = Counter()
        for r in rows(paths):
            total += 1
            sha = r.get('sha256')
            if not isinstance(sha, str) or not re.fullmatch('[a-fA-F0-9]{64}', sha):
                invalid_hashes += 1
            else:
                sha = sha.lower()
                previous = db.execute('SELECT split FROM hashes WHERE sha=?', (sha,)).fetchone()
                if previous:
                    duplicates += 1
                    overlap += previous[0] != split
                else:
                    db.execute('INSERT INTO hashes VALUES (?,?)', (sha, split))
            declared[str(r.get('feature_version', 'absent'))] += 1
            label = r.get('label')
            key = str(label) if type(label) is int and label in (-1, 0, 1) else ('missing_or_null' if label is None else 'invalid')
            counts[key] += 1
            for group in GROUPS:
                if group not in r or r[group] is None:
                    missing[group] += 1
        report['splits'][split] = {'rows': total, 'invalid_sha256': invalid_hashes, 'duplicate_rows': duplicates, 'cross_split_overlap_rows': overlap, 'declared_feature_versions': dict(declared), 'labels': dict(counts), 'missing_feature_groups': dict(missing),
                                   'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': digest(p)} for p in paths]}
    db.commit()


def verify(root):
    archive = root / 'ember_dataset_2018_2.tar.bz2'
    if digest(archive) != SHA:
        raise ValueError('Official archive checksum mismatch')
    matched = set()
    with tarfile.open(archive, 'r:bz2') as tar:
        for member in tar:
            name = Path(member.name).name
            if name not in {f'train_features_{i}.jsonl' for i in range(6)} | {'test_features.jsonl'}:
                continue
            if not member.isfile() or name in matched:
                raise ValueError('Duplicate/non-file archive member')
            h = hashlib.sha256()
            with tar.extractfile(member) as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != digest(root / name):
                raise ValueError('Extracted JSONL mismatch: ' + name)
            matched.add(name)
    if len(matched) != 7 or len(list(root.glob('train_features_*.jsonl'))) != 6:
        raise ValueError('Expected exactly six train shards and one test file')
    return {'archive_sha256': SHA, 'archive_bytes': archive.stat().st_size, 'verified_feature_version': 2}


def matrix(root, output):
    provenance = verify(root)
    import numpy as np
    import ember
    import lief
    extractor = ember.PEFeatureExtractor(feature_version=2)
    if extractor.dim != 2381:
        raise ValueError('Expected 2381 features')
    report = audit(root)
    report.update(provenance)
    for info in report["splits"].values():
        if info["invalid_sha256"] or info["cross_split_overlap_rows"]:
            raise ValueError("Invalid hash or cross-split leakage; inspect audit")
    output.mkdir(parents=True, exist_ok=False)
    for split, info in report['splits'].items():
        if info['missing_feature_groups'] or any(k not in ('-1', '0', '1') for k in info['labels']):
            raise ValueError('Invalid/missing labels or feature groups; inspect audit')
        n = sum(info['labels'].get(k, 0) for k in ('0', '1'))
        if n == 0:
            raise ValueError('No labeled rows')
        X = np.lib.format.open_memmap(output / f'X_{split}.npy', mode='w+', dtype='float32', shape=(n, 2381))
        y = np.lib.format.open_memmap(output / f'y_{split}.npy', mode='w+', dtype='int8', shape=(n,))
        paths = sorted(root.glob('train_features_*.jsonl')) if split == 'train' else [root / 'test_features.jsonl']
        i = 0
        with (output / f'{split}_metadata.jsonl').open('w', encoding='utf-8') as metadata:
            for r in rows(paths):
                if r['label'] == -1:
                    continue
                vector = np.asarray(extractor.process_raw_features(r), dtype='float32')
                if vector.shape != (2381,) or not np.isfinite(vector).all():
                    raise ValueError('Invalid feature vector')
                X[i], y[i] = vector, r['label']
                metadata.write(json.dumps({k: r.get(k) for k in ('sha256', 'appeared', 'label')}) + '\n')
                i += 1
        if i != n:
            raise ValueError('Input changed during vectorization')
        X.flush(); y.flush()
    for info in report['splits'].values():
        for file in info['files']:
            if digest(root / file['name']) != file['sha256']:
                raise ValueError('Input changed during matrix creation')
    report['runtime'] = {'numpy': np.__version__, 'lief': lief.__version__, 'ember_module': ember.__file__}
    (output / 'COMPLETE.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['download', 'verify', 'audit', 'matrix'])
    p.add_argument('--data', required=True, type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.command == 'download':
        fetch(a.data)
    elif a.command == 'verify':
        print(json.dumps(verify(a.data), indent=2))
    elif a.command == 'audit':
        result = json.dumps(audit(a.data), indent=2)
        print(result)
        if a.output:
            a.output.write_text(result, encoding='utf-8')
    else:
        if not a.output:
            p.error('matrix requires --output (new directory)')
        matrix(a.data, a.output)


if __name__ == '__main__':
    main()
