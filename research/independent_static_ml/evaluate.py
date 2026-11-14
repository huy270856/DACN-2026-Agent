"""CLI: evaluate a trained model on the official EMBER2018 v2 LABELED TEST set.

The test set (test_features.jsonl, 100k benign + 100k malicious) is used ONLY
here, for measurement. The decision threshold is read from the model manifest
(selected on validation) and is NOT re-tuned on the test set.

Usage (from repo root):
    python -m research.independent_static_ml.evaluate \
        --data D:/datasets/ember2018-v2 \
        --cache D:/datasets/ember2018-cache \
        --model research/independent_static_ml/artifacts/model_lightgbm.txt \
        --manifest research/independent_static_ml/artifacts/model_manifest.json \
        --out research/independent_static_ml/artifacts/evaluation_results.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import FEATURE_COUNT, dataset, manifests, metrics


def main(argv=None):
    ap = argparse.ArgumentParser(description="Evaluate model on labeled EMBER test")
    ap.add_argument("--data", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args(argv)

    import lightgbm as lgb

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    # Integrity: verify the model file matches the manifest digest.
    model_sha = manifests.sha256_file(args.model)
    manifest_sha = manifest.get("model_sha256")
    if manifest_sha and model_sha != manifest_sha:
        raise SystemExit(
            f"MODEL DIGEST MISMATCH: file={model_sha} manifest={manifest_sha}")

    threshold = manifest["threshold_selection"]["primary_threshold"]
    print(f"Using frozen threshold from manifest: {threshold:.6f}", flush=True)

    print("Building/loading TEST feature matrix (labels 0/1)...", flush=True)
    X, y, shas, appeared, vec_stats = dataset.build_or_load_matrix(
        args.data, dataset.TEST_FILES, args.cache, tag="test",
        rebuild=args.rebuild_cache)
    X = np.asarray(X)
    assert X.shape[1] == FEATURE_COUNT, X.shape
    print(f"      test matrix: {X.shape} (vec_stats={vec_stats})", flush=True)

    booster = lgb.Booster(model_file=args.model)
    if booster.num_feature() != FEATURE_COUNT:
        raise SystemExit(f"model expects {booster.num_feature()} features, "
                         f"pipeline produces {FEATURE_COUNT}")

    t0 = time.perf_counter()
    scores = booster.predict(X)
    batch_sec = time.perf_counter() - t0

    # per-sample latency on a small sample (single-row predict)
    k = min(200, X.shape[0])
    t1 = time.perf_counter()
    for i in range(k):
        booster.predict(X[i:i + 1])
    per_sample_ms = (time.perf_counter() - t1) / k * 1000.0

    results = metrics.compute_metrics(y, scores, threshold)

    # error analysis: index samples of FP / FN
    y_pred = (scores >= threshold).astype(int)
    fp_idx = np.where((y == 0) & (y_pred == 1))[0]
    fn_idx = np.where((y == 1) & (y_pred == 0))[0]
    error_analysis = {
        "false_positives": int(fp_idx.size),
        "false_negatives": int(fn_idx.size),
        "fp_example_sha256": [shas[i] for i in fp_idx[:10].tolist()],
        "fn_example_sha256": [shas[i] for i in fn_idx[:10].tolist()],
    }

    report = {
        "model_id": manifest.get("model_id"),
        "model_sha256": model_sha,
        "model_sha256_matches_manifest": (model_sha == manifest_sha),
        "feature_version": manifest.get("feature_version"),
        "threshold_source": "model manifest (selected on validation, not test)",
        "threshold": threshold,
        "test_set": {
            "files": dataset.TEST_FILES,
            "n": results["n"],
            "n_benign": results["n_benign"],
            "n_malicious": results["n_malicious"],
        },
        "metrics": results,
        "error_analysis": error_analysis,
        "latency": {
            "batch_predict_total_sec": round(batch_sec, 3),
            "batch_predict_per_sample_ms": round(batch_sec / X.shape[0] * 1000.0, 4),
            "single_row_predict_per_sample_ms": round(per_sample_ms, 4),
        },
        "note": "Scores are raw LightGBM outputs (uncalibrated).",
        "environment": manifests.environment_manifest(),
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "roc_auc": results["roc_auc"],
        "average_precision": results["average_precision"],
        "precision": round(results["precision"], 5),
        "recall_tpr": round(results["recall_tpr"], 5),
        "f1": round(results["f1"], 5),
        "false_positive_rate": round(results["false_positive_rate"], 5),
        "confusion_matrix": results["confusion_matrix"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
