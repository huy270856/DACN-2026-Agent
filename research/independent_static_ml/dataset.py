"""EMBER2018 v2 JSONL ingest, label semantics, dataset audit, and vectorization.

Label semantics (fixed by the EMBER dataset, enforced here):
    0  = benign
    1  = malicious
   -1  = unlabeled    (NEVER treated as benign; excluded from supervised sets)

Train/test partition is defined by file provenance:
    train_features_0..5.jsonl  -> 'train'
    test_features.jsonl        -> 'test'
The official test split is held out and must never be used for tuning/threshold.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import ember_v2

TRAIN_FILES = [f"train_features_{i}.jsonl" for i in range(6)]
TEST_FILES = ["test_features.jsonl"]
REQUIRED_GROUPS = tuple(name for name, _ in ember_v2.GROUP_ORDER)


def iter_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield line


def iter_records(path):
    for line in iter_lines(path):
        yield json.loads(line)


# --- audit -----------------------------------------------------------------

def audit_split(data_dir, files):
    """One streaming pass: label counts, missing groups, appeared histogram,
    sha256 list (for duplicate / overlap detection)."""
    data_dir = Path(data_dir)
    label_counts = Counter()
    appeared_years = Counter()
    sha_counts = Counter()
    missing_group = Counter()
    invalid_label = 0
    missing_sha = 0
    total = 0
    for fname in files:
        path = data_dir / fname
        for rec in iter_records(path):
            total += 1
            label = rec.get("label", None)
            if label not in (0, 1, -1):
                invalid_label += 1
            else:
                label_counts[label] += 1
            sha = rec.get("sha256")
            if not sha:
                missing_sha += 1
            else:
                sha_counts[sha] += 1
            appeared = rec.get("appeared", "")
            if isinstance(appeared, str) and len(appeared) >= 4:
                appeared_years[appeared[:4]] += 1
            for g in REQUIRED_GROUPS:
                if g not in rec:
                    missing_group[g] += 1
    duplicate_sha = {s: c for s, c in sha_counts.items() if c > 1}
    return {
        "files": list(files),
        "total_records": total,
        "label_counts": {str(k): v for k, v in sorted(label_counts.items())},
        "invalid_label_records": invalid_label,
        "missing_sha256_records": missing_sha,
        "distinct_sha256": len(sha_counts),
        "duplicate_sha256_count": len(duplicate_sha),
        "appeared_year_histogram": dict(sorted(appeared_years.items())),
        "missing_feature_group_counts": dict(missing_group),
        "_sha_set": set(sha_counts.keys()),  # internal; stripped before JSON dump
    }


def audit_dataset(data_dir):
    train = audit_split(data_dir, TRAIN_FILES)
    test = audit_split(data_dir, TEST_FILES)
    overlap = train["_sha_set"] & test["_sha_set"]
    report = {
        "train": {k: v for k, v in train.items() if not k.startswith("_")},
        "test": {k: v for k, v in test.items() if not k.startswith("_")},
        "train_test_sha256_overlap": len(overlap),
        "train_test_overlap_examples": sorted(list(overlap))[:10],
    }
    return report


# --- vectorization ---------------------------------------------------------

def _vectorize_line(line):
    """Worker: parse one JSONL line -> (sha256, label, appeared, vector|None, err)."""
    try:
        rec = json.loads(line)
    except Exception as exc:  # malformed line
        return (None, None, None, None, f"json:{exc!r}")
    sha = rec.get("sha256")
    label = rec.get("label")
    appeared = rec.get("appeared", "")
    try:
        vec = ember_v2.process_raw_record(rec)
    except ember_v2.FeatureExtractionError as exc:
        return (sha, label, appeared, None, str(exc))
    return (sha, label, appeared, vec.astype(np.float32), None)


def _batched_lines(data_dir, files, batch_size, max_records):
    """Yield lists of <=batch_size raw lines, bounding memory for the pool."""
    data_dir = Path(data_dir)
    batch = []
    seen = 0
    for fname in files:
        for line in iter_lines(data_dir / fname):
            batch.append(line)
            seen += 1
            if len(batch) >= batch_size:
                yield batch
                batch = []
            if max_records is not None and seen >= max_records:
                if batch:
                    yield batch
                return
    if batch:
        yield batch


def vectorize_files(
    data_dir,
    files,
    keep_labels=(0, 1),
    max_records=None,
    workers=None,
    progress_every=50000,
    batch_size=20000,
):
    """Vectorize records from `files`, keeping only `keep_labels`.

    Returns (X float32 [n,2381], y int8 [n], shas list[str], appeared list[str],
             stats dict). Records whose label is not in keep_labels are skipped
             BEFORE vectorization. Extraction failures are counted and skipped
             (never replaced by a zero vector).

    Work is submitted to the process pool in bounded batches (batch_size lines)
    and each batch is vstacked immediately, so peak memory stays O(batch) for the
    task queue plus O(final matrix) for the accumulated result.
    """
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    X_chunks, ys, shas, appeared_list = [], [], [], []
    n_seen = n_kept = n_fail = n_skiplabel = 0
    keep_set = set(keep_labels)

    with ProcessPoolExecutor(max_workers=workers) as ex:
        for batch in _batched_lines(data_dir, files, batch_size, max_records):
            n_seen += len(batch)
            batch_rows = []
            for sha, label, appeared, vec, err in ex.map(
                _vectorize_line, batch, chunksize=max(1, len(batch) // (workers * 4) or 1)
            ):
                if label not in keep_set:
                    n_skiplabel += 1
                    continue
                if err is not None or vec is None:
                    n_fail += 1
                    continue
                batch_rows.append(vec)
                ys.append(label)
                shas.append(sha)
                appeared_list.append(appeared or "")
                n_kept += 1
            if batch_rows:
                X_chunks.append(np.vstack(batch_rows).astype(np.float32))
            if progress_every and n_seen % progress_every < batch_size:
                print(f"  vectorized {n_kept} kept / {n_seen} seen "
                      f"({n_fail} fail, {n_skiplabel} other-label)", flush=True)

    X = (np.concatenate(X_chunks, axis=0).astype(np.float32) if X_chunks
         else np.empty((0, ember_v2.FEATURE_COUNT), dtype=np.float32))
    y = np.asarray(ys, dtype=np.int8)
    stats = {
        "records_seen": n_seen,
        "records_kept": n_kept,
        "records_other_label_skipped": n_skiplabel,
        "records_extraction_failed": n_fail,
        "keep_labels": list(keep_labels),
    }
    return X, y, shas, appeared_list, stats


def build_or_load_matrix(data_dir, files, cache_dir, tag, max_records=None,
                         workers=None, rebuild=False):
    """Vectorize `files` (labels 0/1 only) once and cache X/y/sha/appeared on disk.

    Cache files: {cache_dir}/{tag}_X.npy, _y.npy, _sha.npy, _appeared.npy,
                 {cache_dir}/{tag}_stats.json
    Returns (X, y, shas, appeared, stats)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    xp = cache_dir / f"{tag}_X.npy"
    yp = cache_dir / f"{tag}_y.npy"
    sp = cache_dir / f"{tag}_sha.npy"
    apath = cache_dir / f"{tag}_appeared.npy"
    stp = cache_dir / f"{tag}_stats.json"
    if not rebuild and all(p.exists() for p in (xp, yp, sp, apath, stp)):
        X = np.load(xp, mmap_mode="r")
        y = np.load(yp)
        shas = np.load(sp, allow_pickle=False)
        appeared = np.load(apath, allow_pickle=False)
        stats = json.loads(stp.read_text(encoding="utf-8"))
        stats["loaded_from_cache"] = True
        return X, y, [str(s) for s in shas], [str(a) for a in appeared], stats

    X, y, shas, appeared, stats = vectorize_files(
        data_dir, files, keep_labels=(0, 1), max_records=max_records, workers=workers)
    np.save(xp, X)
    np.save(yp, y)
    np.save(sp, np.array(shas))
    np.save(apath, np.array(appeared))
    stp.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    stats["loaded_from_cache"] = False
    return X, y, shas, appeared, stats
