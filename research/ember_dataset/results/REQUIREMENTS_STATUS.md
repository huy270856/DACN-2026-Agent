# Requirements re-audit — local Windows 2026-10-30

This supersedes the cloud-only 2026-10-29 report. The cloud ran seven synthetic tests but was blocked by proxy 403; this local run completed. See ../HANDOFF.md and local_windows/COMMANDS.md.

1. Sources/license/size/labels/split: PASS. Official EMBER2018 data MIT/code AGPL-v3 verified. EMBER2024 code and HF card Apache-2.0 verified; all 13 ZIP links HEAD 200, 24,332,624,240 bytes total by API/Content-Length. No 2024 corpus downloaded; publisher counts are not local measurements.
2. Compatibility: PASS. EMBER2018 v2 = 2381 dimensions selected. EMBER2024 full PE v3 = 2568, not interchangeable. Pinned official extractor installed and source hashes matched.
3. Download/verify/read: PASS. 1,696,539,273-byte archive and seven JSONL verified. One million JSON records read. No raw PE download/execution.
4. Real statistics/version: PASS. Train 800k (300k benign, 300k malicious, 200k unlabeled); test 200k (100k each class). Zero invalid/missing labels, missing required feature groups, invalid hashes, exact duplicates or cross-split overlap. Records omit feature_version; archive provenance establishes v2.
5. Matrix/script/load: PASS. Separate environment validated, 140-row preflight passed. Matrix train 600000x2381 and test 200000x2381, float32 X/int8 binary y. Independent checker validated every value finite and all 800k metadata/label rows against source; 34 vectors recomputed exactly. Read-only loader passed. Matrix artifacts total 7,712,003,111 bytes. No model training.

17 unit tests pass; pip check passes. Logs/manifests in local_windows. Dataset and matrices remain on D outside Git. No D1-D9 edits or main merge. No remaining blocker for preparation; near-duplicates, validation split, training/calibration/evaluation remain downstream work. Legacy Python/LIEF limitation and upstream LIEF warning are retained in the handoff.
