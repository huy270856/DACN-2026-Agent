"""TASK 05C — Controlled evaluation: Static-only vs Static + Qwen Agent.

This package evaluates whether the local Qwen agent adds value on top of the
TASK 05A LightGBM static detector, without changing the model, threshold, or the
D1-D9 security boundary.

Two evaluation tracks are kept strictly separate (never conflated):
  * FEATURE_RECORD_REPLAY - LightGBM is run on official EMBER2018 v2 *feature
    records* (not raw PE bytes). The agent reasons over a provenance-tagged
    projection of those records. This is NOT a raw-PE end-to-end run.
  * RAW_PE_E2E - the full TASK 05B pipeline on real PE bytes. Benign PEs only in
    this environment; malicious raw-PE E2E is BLOCKED (no malware is downloaded
    or executed here).

Ground truth is used ONLY by the evaluator (sampling strata + metrics) and is
never placed in anything the agent can read.
"""

SCHEMA_VERSION = "task05c-eval-v1"
