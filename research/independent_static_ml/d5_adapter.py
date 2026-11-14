"""D5 provider adapter: real EMBER v2 + LightGBM static PE prediction (read-only).

Invoked by the trusted D5 executor as a PINNED subprocess:

    <python.exe> -I <this script>
        --model <model.txt> --expected-model-sha256 <hex>
        --model-id <id> --threshold <float>
        --target <staged-file> --arguments-json <canonical-object>

Contract:
  * The target file is READ ONLY and never executed.
  * The model path, its expected digest, the model id and the threshold are
    TRUSTED values fixed by the installer (passed on the command line that D5
    pins), never taken from the untrusted target or from agent arguments.
  * On any extraction/parse failure the adapter exits NON-ZERO and prints a short
    reason to stderr; it NEVER emits a prediction or a zero-vector fallback.
  * On success it prints exactly one static-prediction-v1 JSON object to stdout.

This adapter contains no business logic of its own: it reuses the TASK 05A
feature extractor and model unchanged.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

# Make the TASK 05A package importable even under `python -I` (isolated mode):
# this file lives at <repo>/research/independent_static_ml/d5_adapter.py.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.independent_static_ml import (FEATURE_COUNT, FEATURE_VERSION,  # noqa: E402
                                            EXTRACTOR_NAME, EXTRACTOR_VERSION)
from research.independent_static_ml import pe_extractor  # noqa: E402


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _fail(msg, code=2):
    sys.stderr.write(f"d5_adapter: {msg}\n")
    sys.exit(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--expected-model-sha256", required=True)
    ap.add_argument("--model-id", required=True)
    ap.add_argument("--threshold", required=True, type=float)
    ap.add_argument("--target", required=True)
    ap.add_argument("--arguments-json", required=True)
    args = ap.parse_args()

    options = json.loads(args.arguments_json)
    if options.get("feature_version") != FEATURE_VERSION:
        _fail(f"unsupported feature_version: {options.get('feature_version')!r}")

    # 1. Trusted model integrity (defence in depth; D5 also pins/verifies the file).
    model_sha = _sha256_file(args.model)
    if model_sha != args.expected_model_sha256.lower():
        _fail("model digest mismatch; refusing to predict")

    # 2. Read-only feature extraction from the staged PE bytes.
    res = pe_extractor.extract_from_file(args.target)
    if res.vector is None:
        _fail(f"feature extraction failed (status={res.status}): {res.error}")
    if res.status != "OK":
        # A degraded/non-PE parse must not be scored as if it were a clean PE.
        _fail(f"parser status not OK ({res.status}); refusing to score a degraded extraction")

    # 3. Real LightGBM inference.
    try:
        import lightgbm as lgb
    except Exception as exc:  # pragma: no cover
        _fail(f"lightgbm unavailable: {exc!r}", code=3)
    booster = lgb.Booster(model_file=args.model)
    if booster.num_feature() != FEATURE_COUNT:
        _fail(f"model/feature-count mismatch: model={booster.num_feature()} expected={FEATURE_COUNT}")
    score = float(booster.predict(res.vector.reshape(1, -1))[0])
    predicted_class = int(score >= args.threshold)

    payload = {
        "schema_version": "static-prediction-v1",
        "feature_version": FEATURE_VERSION,
        "feature_count": FEATURE_COUNT,
        "extractor": {"name": EXTRACTOR_NAME, "version": EXTRACTOR_VERSION,
                      "lief_version": pe_extractor.lief_version()},
        "target_sha256": res.sha256,
        "model_id": args.model_id,
        "model_sha256": model_sha,
        "threshold": args.threshold,
        "raw_score": score,
        "score_is_calibrated_probability": False,
        "predicted_label": "malicious" if predicted_class == 1 else "benign",
        "predicted_class": predicted_class,
        "parser_status": res.status,
        "limitations": list(res.warnings) + [
            "Raw LightGBM score; NOT a calibrated probability.",
            "Static analysis only; no runtime/dynamic behaviour observed.",
            "Inference uses LIEF 0.15.1 while EMBER2018 training records used LIEF 0.9.0; "
            "feature parity for the raw-PE path is not asserted.",
        ],
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
