"""Metrics: detection (full labeled test) + investigation aggregation + paired stats.

Detection metrics are IDENTICAL for both branches (same model, score, threshold);
this is stated explicitly. Investigation metrics differ and are where any agent
value (or cost) shows up. Proportions get Wilson 95% CIs; paired binary outcomes
on the same samples use McNemar counts. No significance is claimed without the
evidence to support it.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Sequence

import numpy as np


def wilson_ci(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def proportion(k: int, n: int) -> Dict[str, Any]:
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None,
            "ci95": wilson_ci(k, n)}


def detection_metrics(cache_dir, model_path, threshold) -> Dict[str, Any]:
    """Full official test detection metrics (identical for both branches)."""
    import lightgbm as lgb
    from research.independent_static_ml import metrics as m05a
    from pathlib import Path
    cache_dir = Path(cache_dir)
    X = np.load(cache_dir / "test_X.npy", mmap_mode="r")
    y = np.load(cache_dir / "test_y.npy")
    booster = lgb.Booster(model_file=str(model_path))
    scores = booster.predict(np.asarray(X))
    res = m05a.compute_metrics(y, scores, threshold)
    res["note"] = ("Identical for STATIC_ONLY and STATIC_PLUS_AGENT: both use the same "
                   "model/score/threshold; the agent never changes the static label.")
    return res


def mcnemar_counts(static_flags: Sequence[bool], agent_flags: Sequence[bool]) -> Dict[str, Any]:
    """Paired discordance counts for a binary outcome on the same samples."""
    b = sum(1 for s, a in zip(static_flags, agent_flags) if s and not a)  # static yes, agent no
    c = sum(1 for s, a in zip(static_flags, agent_flags) if not s and a)  # static no, agent yes
    both = sum(1 for s, a in zip(static_flags, agent_flags) if s and a)
    neither = sum(1 for s, a in zip(static_flags, agent_flags) if not s and not a)
    n = len(static_flags)
    note = "insufficient discordant pairs for a significance claim" if (b + c) < 10 else \
           "report McNemar exact/continuity-corrected test externally if a claim is needed"
    return {"n_pairs": n, "static_only_yes_agent_no": b, "static_no_agent_yes": c,
            "both_yes": both, "neither": neither, "discordant": b + c, "note": note}


def aggregate_investigation(per_sample: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate auto-check investigation metrics by branch and stratum."""
    def agg(rows, branch):
        n = len(rows)
        checks = [r[branch]["auto"] for r in rows]
        cit = [c["citation_validity"] for c in checks]
        unsupported = sum(1 for c in checks if c["unsupported_claim"])
        unsafe = sum(1 for c in checks if c["safety_violations"])
        # review-required + alignment live on the branch report
        if branch == "agent":
            review = sum(1 for r in rows if (r["agent"]["report"].get("assessment") or {}).get("review_required"))
            schema_fail = sum(1 for r in rows if r["agent"]["report"].get("run_status") != "OK"
                              or not (r["agent"]["report"].get("assessment") or {}).get("structured_assessment"))
            errors = sum(1 for r in rows if r["agent"]["report"].get("run_status") not in ("OK",))
            lat = [r["agent"]["report"].get("latency_s") for r in rows
                   if isinstance(r["agent"]["report"].get("latency_s"), (int, float))]
            toks = [((r["agent"]["report"].get("meta") or {}) or {}).get("eval_count") for r in rows]
            toks = [t for t in toks if isinstance(t, int)]
        else:
            review = sum(1 for r in rows if r["static"]["report"]["recommendation"].get("action") == "MANUAL_REVIEW")
            schema_fail = errors = 0
            lat, toks = [], []
        out = {
            "n": n,
            "citation_validity_mean": round(sum(cit) / n, 4) if n else None,
            "unsupported_claim": proportion(unsupported, n),
            "safety_violation": proportion(unsafe, n),
            "review_required": proportion(review, n),
        }
        if branch == "agent":
            out["schema_or_assessment_failure"] = proportion(schema_fail, n)
            out["run_error_or_timeout"] = proportion(errors, n)
            out["latency_s_mean"] = round(sum(lat) / len(lat), 2) if lat else None
            out["eval_tokens_mean"] = round(sum(toks) / len(toks), 1) if toks else None
        return out

    strata = ("TP", "TN", "FP", "FN", "NEAR")
    by_stratum = {}
    for st in strata:
        rows = [r for r in per_sample if st in r["strata"]]
        if rows:
            by_stratum[st] = {"static": agg(rows, "static"), "agent": agg(rows, "agent")}

    overall = {"static": agg(per_sample, "static"), "agent": agg(per_sample, "agent")}

    # Paired (same samples) binary outcomes: unsupported-claim + safety-violation.
    s_unsupported = [bool(r["static"]["auto"]["unsupported_claim"]) for r in per_sample]
    a_unsupported = [bool(r["agent"]["auto"]["unsupported_claim"]) for r in per_sample]
    s_unsafe = [bool(r["static"]["auto"]["safety_violations"]) for r in per_sample]
    a_unsafe = [bool(r["agent"]["auto"]["safety_violations"]) for r in per_sample]
    paired = {
        "unsupported_claim": mcnemar_counts(s_unsupported, a_unsupported),
        "safety_violation": mcnemar_counts(s_unsafe, a_unsafe),
    }

    # Alignment distribution by stratum (agent only).
    alignment = defaultdict(lambda: defaultdict(int))
    for r in per_sample:
        a = (r["agent"]["report"].get("assessment") or {})
        al = a.get("evidence_alignment", "NONE")
        for st in r["strata"]:
            alignment[st][al] += 1
    return {"overall": overall, "by_stratum": by_stratum, "paired": paired,
            "agent_alignment_by_stratum": {k: dict(v) for k, v in alignment.items()}}
