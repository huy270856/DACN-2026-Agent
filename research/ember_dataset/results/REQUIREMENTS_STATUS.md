# Requirements re-audit — 29/10/2026

1. Sources/license/size/labels/split: official Git repos reviewed (pinned commits in README). EMBER2018 source checksum and code/data licenses confirmed. Size of downloaded archive unknown. EMBER2024 README sizes and temporal split recorded; HF dataset license still unverified.
2. Compatibility: v2=2381 vs v3 full PE=2568 confirmed from source dimensions. D.0 fixture v2 observed; no claim that an extractor/model has already been installed or validated.
3. Download/verify/read: BLOCKED. Repeated HEAD to https://ember.elastic.co/ember_dataset_2018_2.tar.bz2 and https://huggingface.co/datasets/joyce8/EMBER2024/raw/main/README.md both returned proxy CONNECT 403 at 2026-10-29 16:19 UTC. This is an environment access failure, not proof the upstream download link is dead. Earlier Python download also failed before dataset bytes were received. No bypass or alternate unverified mirror used.
4. Real counts/labels/missing/version: NOT RUN on real data. Audit implementation tested on synthetic records only. Expected release counts are not measured results.
5. Matrix script: IMPLEMENTED, not validated end-to-end with official data. Requires archive/JSONL integrity, official v2 extractor and compatible dependencies. Rejects nonfinite vectors, malformed labels and cross-split overlap; preserves metadata and excludes -1. COMPLETE.json only appears after checks.

Actual local execution: 7 tests pass, compile passes, diff whitespace check passes. No D1-D9 edits. Next needed evidence: run download/verify/audit on a permitted machine; share audit JSON and exact environment versions, then validate matrix on official corpus. Do not claim task fully completed until steps 3–5 have real outputs.
