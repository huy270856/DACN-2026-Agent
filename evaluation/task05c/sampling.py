"""Build a reproducible, stratified audit manifest from the EMBER2018 v2 test set.

Runs the FROZEN TASK 05A model over the cached test feature vectors, classifies
each record as TP/TN/FP/FN at the frozen threshold, and draws a seeded stratified
sample (balanced across TP/TN/FP/FN, plus near-threshold hard cases). The manifest
records ground truth for the EVALUATOR only; it is never shown to the agent.

No retraining, no threshold tuning. Detection metrics over the FULL labeled test
are computed separately (metrics.py) and are identical for both branches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def _load_cache(cache_dir: Path):
    X = np.load(cache_dir / "test_X.npy", mmap_mode="r")
    y = np.load(cache_dir / "test_y.npy")
    sha = np.load(cache_dir / "test_sha.npy")
    appeared = np.load(cache_dir / "test_appeared.npy")
    return X, y, [str(s) for s in sha], [str(a) for a in appeared]


def classify(y_true: int, score: float, threshold: float) -> str:
    pred = 1 if score >= threshold else 0
    if y_true == 1 and pred == 1:
        return "TP"
    if y_true == 0 and pred == 0:
        return "TN"
    if y_true == 0 and pred == 1:
        return "FP"
    return "FN"


def build_manifest(cache_dir, model_path, manifest_json_path, *, threshold,
                   model_id, model_sha256, seed=20261114, per_stratum=25,
                   near_per=20, near_margin=0.10):
    import lightgbm as lgb

    cache_dir = Path(cache_dir)
    X, y, sha, appeared = _load_cache(cache_dir)
    booster = lgb.Booster(model_file=str(model_path))
    scores = booster.predict(np.asarray(X))

    n = len(sha)
    # Deduplicate by sha256 (keep first occurrence); EMBER test is already unique.
    seen, dup = set(), 0
    rows = []
    for i in range(n):
        if sha[i] in seen:
            dup += 1
            continue
        seen.add(sha[i])
        s = float(scores[i])
        rows.append({"sha256": sha[i], "score": s, "appeared": appeared[i],
                     "true_label": int(y[i]), "predicted_label": int(s >= threshold),
                     "correctness": classify(int(y[i]), s, threshold),
                     "near_threshold": abs(s - threshold) < near_margin})

    rng = np.random.default_rng(seed)

    def sample(pool, k):
        idx = [r["sha256"] for r in pool]
        if len(idx) <= k:
            return list(idx)
        chosen = rng.choice(len(idx), size=k, replace=False)
        return [idx[j] for j in sorted(chosen.tolist())]

    by = {c: [r for r in rows if r["correctness"] == c] for c in ("TP", "TN", "FP", "FN")}
    near_pool = [r for r in rows if r["near_threshold"]]
    picks = {}
    for c in ("TP", "TN", "FP", "FN"):
        picks[c] = sample(by[c], per_stratum)
    picks["NEAR"] = sample(near_pool, near_per)

    # Union of selected shas (dedup across strata); keep evaluator metadata per sha.
    selected = {}
    meta_by_sha = {r["sha256"]: r for r in rows}
    strata_membership = {}
    for stratum, shas in picks.items():
        for s in shas:
            strata_membership.setdefault(s, []).append(stratum)
    for s in strata_membership:
        r = meta_by_sha[s]
        selected[s] = {**r, "strata": strata_membership[s]}

    audit = sorted(selected.values(), key=lambda r: r["sha256"])
    manifest = {
        "schema_version": "task05c-audit-manifest-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "EMBER2018 feature version 2 (official test split)",
        "track": "FEATURE_RECORD_REPLAY",
        "model_id": model_id, "model_sha256": model_sha256,
        "threshold": threshold, "near_threshold_margin": near_margin,
        "seed": seed, "per_stratum": per_stratum, "near_per": near_per,
        "full_test_n": n, "distinct_sha256": len(seen), "duplicate_sha256": dup,
        "stratum_pool_sizes": {c: len(by[c]) for c in by} | {"NEAR": len(near_pool)},
        "audit_set_size": len(audit),
        "audit_strata_counts": {
            c: sum(1 for r in audit if c in r["strata"])
            for c in ("TP", "TN", "FP", "FN", "NEAR")},
        "ground_truth_note": "true_label is EVALUATOR-ONLY and is never sent to the agent",
        "audit_samples": audit,
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "manifest_sha256"},
                   sort_keys=True).encode()).hexdigest()
    Path(manifest_json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_json_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build TASK 05C audit manifest")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--model-manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-stratum", type=int, default=25)
    ap.add_argument("--near-per", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261114)
    args = ap.parse_args(argv)
    mm = json.loads(Path(args.model_manifest).read_text(encoding="utf-8"))
    manifest = build_manifest(
        args.cache, args.model, args.out,
        threshold=mm["threshold_selection"]["primary_threshold"],
        model_id=mm["model_id"], model_sha256=mm["model_sha256"],
        seed=args.seed, per_stratum=args.per_stratum, near_per=args.near_per)
    print(json.dumps({"audit_set_size": manifest["audit_set_size"],
                      "strata_counts": manifest["audit_strata_counts"],
                      "pool_sizes": manifest["stratum_pool_sizes"],
                      "duplicate_sha256": manifest["duplicate_sha256"],
                      "manifest_sha256": manifest["manifest_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
