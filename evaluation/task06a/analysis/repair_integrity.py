"""06A-R read-only integrity audit; never repairs/rebases a historical freeze."""
import hashlib
import json
from pathlib import Path
import subprocess

from evaluation.task06a.experiment import ROOT, digest, read, snapshots, write_new

REVIEWED = "f913786822fb49608347013c884446000453fd79"


def main():
    out = ROOT / "evaluation/task06a/results/task06a_r"
    before = read(out / "integrity_before.json")["protected_sha256"]
    differences = [p for p, expected in before.items() if digest(ROOT / p) != expected]
    frozen = read(ROOT / "evaluation/task06a/results/dev_v2_1/freeze.json")
    unavailable = []
    # Git normalizes text line endings. Compare both LF and CRLF reconstructions
    # to the original byte hashes without changing ANY artifact or working file.
    for path, expected in frozen["source_sha256"].items():
        blob = subprocess.check_output(["git", "show", REVIEWED + ":" + path], cwd=ROOT)
        lf = blob.replace(b"\r\n", b"\n")
        variants = (blob, lf, lf.replace(b"\n", b"\r\n"))
        if expected not in {hashlib.sha256(v).hexdigest() for v in variants}:
            unavailable.append(path)
    current = snapshots()
    drift = sorted(p for p, expected in frozen["source_sha256"].items() if current.get(p) != expected)
    expected_drift = ["agent/planner.py", "evaluation/task06a/assessor_v2.py"]
    inputs = ROOT / "evaluation/task06a/results/dev_v2_1/inputs.json"
    manifest = inputs.with_name("manifest_EVALUATOR_ONLY.json")
    result = {
        "method": "READ_ONLY_INTEGRITY_AUDIT_NO_INFERENCE", "reviewed_commit": REVIEWED,
        "analysis_source_sha256": digest(Path(__file__)),
        "protected_path_count": len(before), "changed_protected_paths": differences,
        "historical_source_paths_checked": len(frozen["source_sha256"]),
        "historical_source_unrecoverable_from_reviewed_commit": unavailable,
        "expected_current_source_drift": drift,
        "historical_inputs_digest_matches": digest(inputs) == frozen["inputs_sha256"],
        "historical_manifest_digest_matches": digest(manifest) == frozen["manifest_sha256"],
        "model_digest_matches": digest(ROOT / "research/independent_static_ml/artifacts/model_lightgbm.txt") == frozen["model_sha256"],
        "freeze_policy": "Original freeze unchanged; current repaired source must NOT resume/relabel historical experiment",
    }
    if (differences or unavailable or drift != expected_drift
            or not all(result[k] for k in ("historical_inputs_digest_matches", "historical_manifest_digest_matches", "model_digest_matches"))):
        raise AssertionError(json.dumps(result, indent=2))
    write_new(out / "integrity_after.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
