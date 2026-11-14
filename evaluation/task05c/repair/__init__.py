"""TASK 05C-R — evaluation repair, independent verification, merge readiness.

Additive repair package. It does NOT change the TASK 05A model/threshold, the
120 original Qwen outputs, or the D1-D9 security boundary. Everything here is
recomputed from already-saved artifacts (no Qwen re-run) except an explicitly
labelled, dev-only agreement-bias probe on fresh records.
"""

REPAIR_VERSION = "task05c-repair-v2"
