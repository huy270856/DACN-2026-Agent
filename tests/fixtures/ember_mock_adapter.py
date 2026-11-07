"""BENIGN MOCK EMBER feature provider for integration tests only.

THIS IS NOT A REAL EMBER v2 EXTRACTOR AND NOT LIGHTGBM. It never executes the
target. It reads the already-staged, verified file bytes, computes their SHA-256
and emits a schema-valid ``ember-output-v1`` payload whose feature vector is a
deterministic all-zeros placeholder of the correct length (2381). It exists only
to exercise the D5 -> D7 -> D9 wiring end to end with harmless data; no result it
produces is evidence of real feature extraction or any malware verdict.

Adapter protocol (fixed by D5): invoked as
    <interpreter> -I <this script> --target <staged-file> --arguments-json <json>
"""
import argparse
import hashlib
import json
from pathlib import Path

FEATURE_COUNT = 2381  # EMBER2018 v2 dimensionality (shape only; values are placeholders)

parser = argparse.ArgumentParser()
parser.add_argument("--target", required=True)
parser.add_argument("--arguments-json", required=True)
args = parser.parse_args()

options = json.loads(args.arguments_json)
assert options.get("feature_version") == 2, "mock only supports feature_version 2"

data = Path(args.target).read_bytes()
sha = hashlib.sha256(data).hexdigest()

payload = {
    "schema_version": "ember-output-v1",
    "feature_version": 2,
    "extractor": {"name": "MOCK-ember-placeholder", "version": "0.0.0-mock"},
    "target_sha256": sha,
    "feature_count": FEATURE_COUNT,
    "features": [0.0] * FEATURE_COUNT,
    "warnings": ["MOCK adapter: placeholder zero vector, NOT real EMBER extraction"],
}
print(json.dumps(payload, ensure_ascii=True), flush=True)
