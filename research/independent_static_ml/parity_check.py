"""Feature-parity verification (independent check, NOT a deliverable result).

This script empirically verifies that the INDEPENDENT vectorizer in this package
reproduces the official EMBER v2 feature space. It vectorizes real test records
with our own code and scores them with the *official* EMBER2018 model
(ember_model_2018.txt, shipped in the dataset archive). If our feature ordering
or arithmetic were wrong, a model trained on the true feature space would score
near chance (AUC ~0.5). A high AUC therefore demonstrates feature parity.

The official model is used here ONLY as an oracle for this parity test. It is
NOT the TASK 05A deliverable model and its scores are not reported as our result.

Usage (from repo root):
    python -m research.independent_static_ml.parity_check \
        --data D:/datasets/ember2018-v2 \
        --official-model D:/datasets/ember2018-v2/ember_model_2018.txt \
        --n 20000 \
        --out research/independent_static_ml/artifacts/parity_check.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from . import dataset, manifests


def main(argv=None):
    ap = argparse.ArgumentParser(description="EMBER v2 feature-parity check")
    ap.add_argument("--data", required=True)
    ap.add_argument("--official-model", required=True)
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    import lightgbm as lgb

    X, y, shas, appeared, stats = dataset.vectorize_files(
        args.data, dataset.TEST_FILES, keep_labels=(0, 1), max_records=args.n)
    booster = lgb.Booster(model_file=args.official_model)
    scores = booster.predict(np.asarray(X))
    auc = float(roc_auc_score(y, scores))

    report = {
        "purpose": "feature-parity verification only; official model is an oracle, "
                   "NOT the TASK 05A deliverable",
        "official_model_file": args.official_model,
        "official_model_sha256": manifests.sha256_file(args.official_model),
        "n_samples": int(X.shape[0]),
        "n_benign": int((y == 0).sum()),
        "n_malicious": int((y == 1).sum()),
        "independent_features_vs_official_model_auc": auc,
        "interpretation": ("AUC near 1.0 confirms the independent vectorizer "
                           "reproduces the official EMBER v2 feature space; a wrong "
                           "feature order/value would collapse this toward 0.5."),
        "model_num_feature": int(booster.num_feature()),
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"parity_auc": round(auc, 6),
                      "n": int(X.shape[0])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
