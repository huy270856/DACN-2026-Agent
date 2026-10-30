# Huy — EMBER dataset preparation (29/10/2026)

## Completed local run 30/10/2026

See [HANDOFF.md](HANDOFF.md) for the current five-requirement handoff, [SOURCES.md](SOURCES.md) for the 2018/2024 comparison, and [dataset manifest](results/local_windows/dataset_manifest.json) for measured checksums/counts/paths. Local download, verification, audit, isolated legacy environment, full matrix and independent validation have completed. 17 unit tests pass. No LightGBM training or raw PE execution. The cloud blockers below are historical, not the current local status.

Use `load_dataset.py --matrix D:\datasets\ember2018-matrix` with `D:\datasets\envs\ember-v2\Scripts\python.exe` to load completed matrices read-only. `check_matrix.py` validates shapes/dtypes/all finite values/all metadata links and optionally recomputes sampled vectors using `--check-vectors`. `preflight.py` tests a small real sample before full vectorization. The pinned environment is recorded in `requirements-research.txt` and `results/local_windows/pip-freeze.txt`.

## Choice and compatibility
Select EMBER2018 feature v2 as technical baseline: 2381 dimensions. EMBER2024 uses v3 (2568 full PE dimensions) and is NOT a drop-in replacement. Self-collected recent PE remains necessary if the course requirement still applies. No D1–D9 changes.

Official sources:
- https://github.com/elastic/ember (reviewed d97a0b523de02f3fe5ea6089d080abacab6ee931)
- https://ember.elastic.co/ember_dataset_2018_2.tar.bz2
- Official SHA256: b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812
- https://github.com/FutureComputing4AI/EMBER2024 (reviewed 0ef753e81d98bf209f71b03cd331dfc190b5b54d)
- https://huggingface.co/datasets/joyce8/EMBER2024
- https://arxiv.org/abs/2506.05074

EMBER2018 data MIT, code AGPL-v3. EMBER2024 code and HF dataset-card license Apache-2.0, checked locally on 30/10/2026 (see SOURCES.md). LightGBM MIT.

EMBER2018: local audit measured 1M records: train 800k (300k benign, 300k malicious, 200k unlabeled), test 200k (100k each class). These agree with the expected release counts. Labels 0/1/-1; never interpret -1 as benign. Keep official test separate and derive temporal validation from train (appeared). See results/local_windows/audit.json for measured counts and zero missing/invalid labels/feature groups/hash overlap.

EMBER2024 official README: 2,626,000 train, 606,000 test, first 52 weeks vs last 12; 6315 additional malicious challenge records. Seven label/tag types: binary, family, behavior, file_property, packer, exploit, group. Challenge alone cannot measure FPR. Data is feature records, not a ready collection of raw executables.

Measured EMBER2018 archive: 1,696,539,273 bytes; extracted JSONL: 9,946,142,816 bytes. EMBER2024's 13 ZIP files total 24,332,624,240 bytes by HEAD/API metadata; no 2024 corpus was downloaded. README subset feature/label sizes are publisher figures, not local measurements or ZIP transfer sizes. See SOURCES.md and the manifest for the distinction.

## Run (PowerShell, from repo root)

Download/audit uses Python standard library only:

```powershell
python research/ember_dataset/prepare.py download --data D:\datasets\ember2018-v2
python research/ember_dataset/prepare.py audit --data D:\datasets\ember2018-v2 --output D:\datasets\ember2018-audit.json
```

Download reuses an existing archive only after checksum verification. Extracts only expected JSONL basenames, refuses overwrite. For failed extraction, inspect partial files before retrying in a fresh directory. Corpus is outside Git.

Matrix requires a SEPARATE research environment with official `ember` from the reviewed commit, NumPy, scikit-learn and compatible LIEF. Upstream v2 used LIEF 0.9.0; README also discusses 0.10.1 on Windows/Linux. The local Python 3.7.9/LIEF 0.10.1 environment passed real-data vectorization and matrix checks; its full versions and extractor source hashes are recorded under results/local_windows. Do not install these legacy dependencies into Orchestrator Python.

```powershell
python research/ember_dataset/prepare.py matrix --data D:\datasets\ember2018-v2 --output D:\datasets\ember2018-matrix
```

Creates float32 X_train/X_test.npy, int8 y_train/y_test.npy, matching SHA256/appeared metadata JSONL. Drops only label -1, rejects unknown/invalid labels and missing feature groups. Delegates vectorization to official v2 extractor; checks 2381 finite values. Input JSON has already extracted raw features: this stage does not parse or run PE files. Successful completion requires COMPLETE.json. On failure discard incomplete matrix directory before retrying. Read with `numpy.load(path, mmap_mode='r')`.

Before training: inspect actual label counts; check duplicate SHA256/near duplicates and chronology; split validation; freeze dataset and feature manifest; never tune on test. Matrix preparation does NOT yet perform deduplication, calibration or model training.

## Historical cloud execution and blockers (29/10/2026)

- Official EMBER Git repo accessible; feature dimensions/license reviewed.
- HEAD and Python download attempt on official archive fail: proxy CONNECT tunnel 403 Forbidden. Dataset bytes downloaded: none. No archive checksum verified, no real sample count, missing-label statistics or feature matrix claimed.
- Hugging Face/arXiv access also blocked during source research. Dataset license remains unresolved for EMBER2024.
- Unit tests use tiny synthetic JSON records only. They verify accounting of unlabeled/null/invalid labels, malformed record location and digest. They DO NOT prove real EMBER extraction/vectorization compatibility.
- Matrix path needs real corpus and a validated legacy dependency environment before an end-to-end result can be reported.

```powershell
python -m unittest discover -s research/ember_dataset -p "test_*.py" -v
```

Handoff: run download/audit on an allowed machine and return archive bytes/SHA, audit JSON, environment versions, then validate matrix. No request to bypass proxy and no unverified mirror substituted.

## Second review: integrity hardening

The first draft did not connect expected feature version to verified extracted data and lacked duplicate detection. These gaps are now addressed:

- `audit` reports `expected_feature_version=2` and `verified_feature_version=null`. Presence of feature fields is not proof of version.
- New `verify` checks official archive SHA256 AND each of the seven extracted JSONL hashes against archive contents. It rejects extra train shards. This establishes release provenance, not equivalence of an arbitrary installed extractor.
- `matrix` requires verification before importing dependencies. After vectorization it rechecks source hashes before writing COMPLETE.json.
- Audit uses temporary SQLite to count duplicate hashes, train/test overlap, malformed hashes and declared feature versions. It does not silently deduplicate. Matrix rejects invalid hashes and cross-split overlap; within-split duplicates remain reported for review.
- Non-finite JSON constants are rejected; label booleans are invalid rather than class 1/0.

```powershell
python research/ember_dataset/prepare.py verify --data D:\datasets\ember2018-v2
```

Seven synthetic unit tests passed at the cloud handoff (results/unit_tests.txt); the local extended suite now passes 17 (results/local_windows/research_tests.log). Coverage includes checksum mismatch, tampered extracted JSON, duplicate leakage, non-finite values, safe resume, matrix validation/loading and rejection before dependencies for an unverified source. Mocking the archive checksum is ONLY a synthetic-test fixture, never the production verification path.

At the cloud handoff, real corpus reading, matrix end-to-end and a validated legacy runtime were still missing. These three items are completed by the local run above; model training remains out of scope. Near-duplicate similarity and a validation split remain downstream tasks. Download retries now resume a partial response only after validating HTTP Content-Range; ignored Range requests restart rather than append. Full archive SHA-256 is always required. Extraction refuses overwrites. Corpus immutable during processing is required; final hashes detect persistent modifications but are not a filesystem snapshot.
