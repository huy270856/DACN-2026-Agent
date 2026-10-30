# Dataset selection and source checks

Checked on Windows, 2026-10-30 (Asia/Saigon). EMBER2018 numbers below are local measurements; EMBER2024 corpus counts are publisher-reported, not local measurements.

## EMBER2018 v2 selected

- Official code: https://github.com/elastic/ember/tree/d97a0b523de02f3fe5ea6089d080abacab6ee931
- Official download: https://ember.elastic.co/ember_dataset_2018_2.tar.bz2
- Release checksum: https://github.com/elastic/ember/blob/d97a0b523de02f3fe5ea6089d080abacab6ee931/README.md
- License declaration: https://github.com/elastic/ember/blob/d97a0b523de02f3fe5ea6089d080abacab6ee931/LICENSE.txt — data MIT; code AGPL-v3.
- Measured archive size: 1,696,539,273 bytes. Seven extracted JSONL total: 9,946,142,816 bytes.
- Official archive SHA256 and local Python/Get-FileHash results agree: `b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812`.
- Preserve official six train shards and one test shard. Local audit: train 800,000, test 200,000. Labels 0=benign, 1=malicious, -1=unlabeled. Do not convert -1 into benign.
- Keep test untouched for later evaluation. Observed labeled train metadata spans 2006-12 through 2018-10; labeled test has 100,000 records each in 2018-11 and 2018-12. See `results/local_windows/chronology.json`; this is not a newly randomized split.
- Official v2 extractor has 2,381 features. Python source installed locally matches the pinned upstream commit. The upstream README documents LIEF 0.10.1 v2 compatibility on Windows/Linux; its runtime warning relative to 0.9.0 is retained in logs. Only existing JSON features were vectorized; raw PE parsing equivalence was not tested.

## EMBER2024 comparison only

- Official code: https://github.com/FutureComputing4AI/EMBER2024/tree/0ef753e81d98bf209f71b03cd331dfc190b5b54d
- Official dataset: https://huggingface.co/datasets/joyce8/EMBER2024
- Dataset-card license: Apache-2.0, verified at HF revision `3d23efef7c0f0b702c5024400cfff4c3744a3832`. Code LICENSE also specifies Apache-2.0.
- All 13 ZIP download URLs returned HTTP 200 to HEAD on this machine. API sizes and Content-Length agree; total compressed size is 24,332,624,240 bytes. See `results/local_windows/ember2024_download_checks.json` for each link and exact byte count. Dataset bytes downloaded: zero. No local ZIP checksums or sample counts claimed.
- Publisher split: first 52 weeks train (2,626,000 records), last 12 weeks test (606,000), plus 6,315 malicious challenge records. Labels/tags cover binary, family, behavior, file_property, packer, exploit and group.
- This is feature v3 (thrember), not v2. The default complete PE extractor totals 2,568 dimensions from the feature-class dimensions in `src/thrember/features.py`; non-PE/subset configurations differ. Therefore it is not a drop-in input for the current 2,381-dimensional v2 pipeline.
- The README's per-subset feature/label sizes are publisher figures and differ from compressed ZIP transfer sizes. The HEAD/API results are remote metadata, not locally downloaded volume.

The referenced EMBER2024-capa supplemental corpus is outside scope and was not downloaded. Choosing EMBER2018 v2 satisfies the current extractor requirement; this does not claim it covers present-day threats. Near-duplicate checks, a validation split, training, calibration and model evaluation remain separate work.
