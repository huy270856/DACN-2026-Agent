"""CLI: read-only static malware inference on a single PE file.

Path: PE bytes -> trusted feature extractor -> 2381 vector -> LightGBM -> raw
score -> predicted class. The input file is never executed; it is only read and
parsed statically.

Usage (from repo root):
    python -m research.independent_static_ml.predict_cli \
        --file C:/Windows/System32/notepad.exe \
        --model research/independent_static_ml/artifacts/model_lightgbm.txt \
        --manifest research/independent_static_ml/artifacts/model_manifest.json

Output is a JSON object (proposed ADDITIVE schema "static-prediction-v1";
NOT yet approved by the project owner; does not replace the D0 EMBER
feature-output contract).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import FEATURE_COUNT, FEATURE_VERSION, EXTRACTOR_NAME, EXTRACTOR_VERSION
from . import manifests, pe_extractor

SCHEMA_VERSION = "static-prediction-v1"


def predict_file(file_path, model_path, manifest_path=None, threshold=None):
    import lightgbm as lgb

    model_sha = manifests.sha256_file(model_path)
    model_id = None
    manifest_sha = None
    if manifest_path and Path(manifest_path).exists():
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        model_id = manifest.get("model_id")
        manifest_sha = manifest.get("model_sha256")
        if threshold is None:
            threshold = manifest["threshold_selection"]["primary_threshold"]
    if threshold is None:
        threshold = 0.5

    out = {
        "schema_version": SCHEMA_VERSION,
        "schema_status": "PROPOSED additive schema, not owner-approved; "
                         "does not modify the D0 ember-output-v1 contract",
        "target_file": str(file_path),
        "feature_version": FEATURE_VERSION,
        "feature_count": FEATURE_COUNT,
        "extractor": {"name": EXTRACTOR_NAME, "version": EXTRACTOR_VERSION,
                      "lief_version": pe_extractor.lief_version()},
        "model_id": model_id,
        "model_sha256": model_sha,
        "model_sha256_matches_manifest": (None if manifest_sha is None
                                          else model_sha == manifest_sha),
        "threshold": float(threshold),
        "score_is_calibrated_probability": False,
        "limitations": [],
    }

    # integrity: refuse to score with a model whose digest disagrees with manifest
    if manifest_sha is not None and model_sha != manifest_sha:
        out["target_sha256"] = None
        out["parser_status"] = "NOT_RUN"
        out["raw_score"] = None
        out["predicted_label"] = None
        out["error"] = "model digest does not match manifest; refusing to score"
        return out

    res = pe_extractor.extract_from_file(file_path)
    out["target_sha256"] = res.sha256
    out["parser_status"] = res.status
    if res.warnings:
        out["limitations"].extend(res.warnings)

    if res.vector is None:
        out["raw_score"] = None
        out["predicted_label"] = None
        out["error"] = res.error or "feature extraction failed"
        out["limitations"].append("no feature vector produced; no score emitted")
        return out

    booster = lgb.Booster(model_file=model_path)
    if booster.num_feature() != FEATURE_COUNT:
        out["raw_score"] = None
        out["predicted_label"] = None
        out["error"] = (f"model/feature-version mismatch: model expects "
                        f"{booster.num_feature()} features, pipeline produces {FEATURE_COUNT}")
        return out

    score = float(booster.predict(res.vector.reshape(1, -1))[0])
    out["raw_score"] = score
    out["predicted_label"] = "malicious" if score >= threshold else "benign"
    out["predicted_class"] = int(score >= threshold)
    if res.status != "OK":
        out["limitations"].append(
            f"parser_status={res.status}: features may be degraded; interpret with caution")
    out["limitations"].append(
        "inference uses LIEF 0.15.1 while EMBER2018 training records used LIEF 0.9.0; "
        "slight feature inconsistencies are possible and feature parity is not asserted")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only static PE malware inference")
    ap.add_argument("--file", required=True, help="path to a PE file (read-only)")
    ap.add_argument("--model", required=True, help="LightGBM model artifact (.txt)")
    ap.add_argument("--manifest", default=None, help="model manifest JSON (for id/threshold)")
    ap.add_argument("--threshold", type=float, default=None,
                    help="override threshold (default: manifest primary threshold)")
    args = ap.parse_args(argv)
    result = predict_file(args.file, args.model, args.manifest, args.threshold)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
