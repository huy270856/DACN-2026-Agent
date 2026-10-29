# Huy — EMBER dataset preparation (29/10/2026)

## Choice and compatibility
Select EMBER2018 feature v2 as technical baseline: 2381 dimensions. EMBER2024 uses v3 (2568 full PE dimensions) and is NOT a drop-in replacement. Self-collected recent PE remains necessary if the course requirement still applies. No D1–D9 changes.

Official sources:
- https://github.com/elastic/ember (reviewed d97a0b523de02f3fe5ea6089d080abacab6ee931)
- https://ember.elastic.co/ember_dataset_2018_2.tar.bz2
- Official SHA256: b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812
- https://github.com/FutureComputing4AI/EMBER2024 (reviewed 0ef753e81d98bf209f71b03cd331dfc190b5b54d)
- https://huggingface.co/datasets/joyce8/EMBER2024
- https://arxiv.org/abs/2506.05074

EMBER2018 data MIT, code AGPL-v3. EMBER2024 code Apache-2.0; HF dataset license NOT verified here (network blocked). LightGBM MIT.

EMBER2018: official total 1M records; expected train 800k (300k benign, 300k malicious, 200k unlabeled), test 200k (100k each class). These are expected counts, NOT measurements from this run. Labels 0/1/-1; never interpret -1 as benign. Keep official test separate and derive temporal validation from train (appeared). Audit reports actual counts when run.

EMBER2024 official README: 2,626,000 train, 606,000 test, first 52 weeks vs last 12; 6315 additional malicious challenge records. Seven label/tag types: binary, family, behavior, file_property, packer, exploit, group. Challenge alone cannot measure FPR. Data is feature records, not a ready collection of raw executables.

Size: EMBER2018 archive byte size NOT verified because HEAD/download blocked. Script reports exact downloaded bytes. EMBER2024 README reports feature/label sizes: Win32 train/test 23.7/4.9 GB, Win64 12.9/2.5 GB, .NET 1.8 GB/425 MB; these are author-reported sizes, not local measurements or guaranteed compressed transfer sizes. Keep extra disk space for extracted JSON and matrices.

## Run (PowerShell, from repo root)

Download/audit uses Python standard library only:

```powershell
python research/ember_dataset/prepare.py download --data D:\datasets\ember2018-v2
python research/ember_dataset/prepare.py audit --data D:\datasets\ember2018-v2 --output D:\datasets\ember2018-audit.json
```

Download reuses an existing archive only after checksum verification. Extracts only expected JSONL basenames, refuses overwrite. For failed extraction, inspect partial files before retrying in a fresh directory. Corpus is outside Git.

Matrix requires a SEPARATE research environment with official `ember` from the reviewed commit, NumPy, scikit-learn and compatible LIEF. Upstream v2 used LIEF 0.9.0; README also discusses 0.10.1 on Windows/Linux. Do not blindly install legacy LIEF into orchestrator Python. This environment has not been validated here; dependency setup is an explicit blocker. Record `pip freeze` and extractor commit once validated.

```powershell
python research/ember_dataset/prepare.py matrix --data D:\datasets\ember2018-v2 --output D:\datasets\ember2018-matrix
```

Creates float32 X_train/X_test.npy, int8 y_train/y_test.npy, matching SHA256/appeared metadata JSONL. Drops only label -1, rejects unknown/invalid labels and missing feature groups. Delegates vectorization to official v2 extractor; checks 2381 finite values. Input JSON has already extracted raw features: this stage does not parse or run PE files. Successful completion requires COMPLETE.json. On failure discard incomplete matrix directory before retrying. Read with `numpy.load(path, mmap_mode='r')`.

Before training: inspect actual label counts; check duplicate SHA256/near duplicates and chronology; split validation; freeze dataset and feature manifest; never tune on test. Matrix preparation does NOT yet perform deduplication, calibration or model training.

## Actual execution and blockers

- Official EMBER Git repo accessible; feature dimensions/license reviewed.
- HEAD and Python download attempt on official archive fail: proxy CONNECT tunnel 403 Forbidden. Dataset bytes downloaded: none. No archive checksum verified, no real sample count, missing-label statistics or feature matrix claimed.
- Hugging Face/arXiv access also blocked during source research. Dataset license remains unresolved for EMBER2024.
- Unit tests use tiny synthetic JSON records only. They verify accounting of unlabeled/null/invalid labels, malformed record location and digest. They DO NOT prove real EMBER extraction/vectorization compatibility.
- Matrix path needs real corpus and a validated legacy dependency environment before an end-to-end result can be reported.

```powershell
python -m unittest discover -s research/ember_dataset -p "test_*.py" -v
```

Handoff: run download/audit on an allowed machine and return archive bytes/SHA, audit JSON, environment versions, then validate matrix. No request to bypass proxy and no unverified mirror substituted.
