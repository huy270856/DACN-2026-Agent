"""TASK 05D — Real-PE validation (RAW_PE_E2E) + human grading workflow.

Part A: run the REAL TASK 05B pipeline (Node B -> D1-D9 -> EMBER v2 + LightGBM ->
        Node C -> Qwen3.5-4B -> report) on a diverse set of benign Windows PEs.
Part B: malicious raw-PE E2E is BLOCKED (no malware is downloaded or executed).
Part C: an offline human-grading workflow (UI + validated multi-reviewer import).

This package never executes a target PE; it only reads/parses bytes statically. It
reuses the existing pipeline (dacn.application.investigate_real) unchanged; it does
not change the model, threshold, or any 05A-05C result.
"""

TRACK = "RAW_PE_E2E"
