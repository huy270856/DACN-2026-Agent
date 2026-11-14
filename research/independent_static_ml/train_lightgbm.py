"""CLI: train an INDEPENDENT LightGBM PE malware classifier from EMBER2018 v2.

No prior-work weights are loaded. The model is trained from scratch on features
produced by this package's own vectorizer. A chronological validation split is
carved out of the labeled training data (latest `appeared` held out), and the
decision threshold is selected on that validation split only. The official test
set is NEVER touched here.

Usage (from repo root):
    python -m research.independent_static_ml.train_lightgbm \
        --data D:/datasets/ember2018-v2 \
        --cache D:/datasets/ember2018-cache \
        --out research/independent_static_ml/artifacts \
        [--max-train N] [--val-frac 0.15] [--rounds 1500] [--seed 42]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from . import FEATURE_COUNT, FEATURE_VERSION, EXTRACTOR_NAME, EXTRACTOR_VERSION
from . import dataset, manifests, metrics
from .audit_dataset import OFFICIAL_ARCHIVE_SHA256, OFFICIAL_ARCHIVE_URL


def chronological_split(appeared, val_frac):
    """Return (train_idx, val_idx). The most-recent `val_frac` by `appeared`
    (YYYY-MM string) becomes validation; ties broken deterministically by order.
    """
    appeared = list(appeared)
    n = len(appeared)
    order = sorted(range(n), key=lambda i: (appeared[i], i))  # oldest -> newest
    n_val = int(round(n * val_frac))
    val_idx = np.array(sorted(order[n - n_val:]), dtype=np.int64)
    train_idx = np.array(sorted(order[: n - n_val]), dtype=np.int64)
    return train_idx, val_idx


def main(argv=None):
    ap = argparse.ArgumentParser(description="Train independent LightGBM on EMBER2018 v2")
    ap.add_argument("--data", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-train", type=int, default=None,
                    help="cap labeled training records (for a smaller run)")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--rounds", type=int, default=1500)
    ap.add_argument("--num-leaves", type=int, default=512)
    ap.add_argument("--learning-rate", type=float, default=0.05)
    ap.add_argument("--early-stopping", type=int, default=75)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args(argv)

    import lightgbm as lgb

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("[1/5] Building/loading TRAIN feature matrix (labels 0/1 only)...", flush=True)
    X, y, shas, appeared, vec_stats = dataset.build_or_load_matrix(
        args.data, dataset.TRAIN_FILES, args.cache, tag="train",
        max_records=args.max_train, rebuild=args.rebuild_cache)
    X = np.asarray(X)
    print(f"      train matrix: X={X.shape} y+={int(y.sum())} y0={int((y==0).sum())} "
          f"(vec_stats={vec_stats})", flush=True)
    assert X.shape[1] == FEATURE_COUNT, X.shape

    print("[2/5] Chronological train/validation split...", flush=True)
    tr_idx, va_idx = chronological_split(appeared, args.val_frac)
    Xtr, ytr = X[tr_idx], y[tr_idx]
    Xva, yva = X[va_idx], y[va_idx]
    # leakage guard: training and validation sha256 sets must be disjoint
    tr_sha = {shas[i] for i in tr_idx.tolist()}
    va_sha = {shas[i] for i in va_idx.tolist()}
    split_overlap = len(tr_sha & va_sha)
    assert split_overlap == 0, f"train/val sha overlap {split_overlap}"
    print(f"      train={Xtr.shape[0]} val={Xva.shape[0]} overlap={split_overlap} "
          f"val_appeared=[{min(appeared[i] for i in va_idx.tolist())}.."
          f"{max(appeared[i] for i in va_idx.tolist())}]", flush=True)

    print("[3/5] Training LightGBM from scratch...", flush=True)
    params = {
        "objective": "binary",
        "metric": ["auc", "binary_logloss"],
        "num_leaves": args.num_leaves,
        "learning_rate": args.learning_rate,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "min_child_samples": 50,
        "num_threads": 0,
        "seed": args.seed,
        "deterministic": True,
        "force_row_wise": True,
        "verbosity": -1,
    }
    dtr = lgb.Dataset(Xtr, label=ytr, free_raw_data=False)
    dva = lgb.Dataset(Xva, label=yva, reference=dtr, free_raw_data=False)
    booster = lgb.train(
        params, dtr, num_boost_round=args.rounds, valid_sets=[dtr, dva],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(args.early_stopping),
                   lgb.log_evaluation(period=50)],
    )

    print("[4/5] Selecting threshold on VALIDATION only...", flush=True)
    va_scores = booster.predict(Xva, num_iteration=booster.best_iteration)
    thr_1pct = metrics.threshold_at_fpr(yva, va_scores, 0.01)
    thr_01pct = metrics.threshold_at_fpr(yva, va_scores, 0.001)
    primary_threshold = thr_1pct
    val_metrics = metrics.compute_metrics(yva, va_scores, primary_threshold)
    val_metrics_01 = metrics.compute_metrics(yva, va_scores, thr_01pct)

    print("[5/5] Saving model + manifest...", flush=True)
    model_path = out / "model_lightgbm.txt"
    booster.save_model(str(model_path), num_iteration=booster.best_iteration)
    model_sha = manifests.sha256_file(model_path)

    model_id = f"dacn-lgbm-ember2018v2-{model_sha[:12]}"
    manifest = {
        "task": "TASK 05A independent static ML",
        "model_id": model_id,
        "model_file": model_path.name,
        "model_sha256": model_sha,
        "feature_version": FEATURE_VERSION,
        "feature_count": FEATURE_COUNT,
        "extractor": {"name": EXTRACTOR_NAME, "version": EXTRACTOR_VERSION},
        "dataset": {
            "name": "EMBER2018 feature version 2",
            "source_url": OFFICIAL_ARCHIVE_URL,
            "archive_sha256": OFFICIAL_ARCHIVE_SHA256,
            "label_semantics": {"0": "benign", "1": "malicious", "-1": "unlabeled (excluded)"},
        },
        "split": {
            "method": "chronological by 'appeared'; latest val_frac held out as validation",
            "val_frac": args.val_frac,
            "n_train": int(Xtr.shape[0]),
            "n_val": int(Xva.shape[0]),
            "train_val_sha256_overlap": split_overlap,
            "max_train_cap": args.max_train,
        },
        "training": {
            "library": "lightgbm",
            "params": params,
            "num_boost_round_requested": args.rounds,
            "best_iteration": int(booster.best_iteration),
            "early_stopping_rounds": args.early_stopping,
            "seed": args.seed,
        },
        "threshold_selection": {
            "selected_on": "validation split (never on official test)",
            "primary_threshold": primary_threshold,
            "threshold_at_val_fpr_1pct": thr_1pct,
            "threshold_at_val_fpr_0.1pct": thr_01pct,
        },
        "validation_metrics_at_1pct_fpr": val_metrics,
        "validation_metrics_at_0.1pct_fpr": val_metrics_01,
        "calibration": "NONE — model outputs are raw LightGBM scores, not calibrated probabilities",
        "environment": manifests.environment_manifest(),
        "vectorization_stats": vec_stats,
    }
    (out / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "model_id": model_id,
        "model_sha256": model_sha,
        "best_iteration": int(booster.best_iteration),
        "primary_threshold": primary_threshold,
        "val_auc": val_metrics["roc_auc"],
        "val_recall_at_1pct_fpr": val_metrics["recall_tpr"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
