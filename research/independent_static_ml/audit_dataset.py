"""CLI: verify the EMBER2018 v2 archive checksum and audit the extracted JSONL.

Usage (from repo root):
    python -m research.independent_static_ml.audit_dataset \
        --data D:/datasets/ember2018-v2 \
        --archive D:/datasets/ember2018-v2/ember_dataset_2018_2.tar.bz2 \
        --out research/independent_static_ml/artifacts/dataset_audit.json

The archive SHA-256 is checked against the value published in the official
elastic/ember README. The audit itself does not execute any binary; it only
parses JSON feature records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from . import dataset

OFFICIAL_ARCHIVE_NAME = "ember_dataset_2018_2.tar.bz2"
OFFICIAL_ARCHIVE_SHA256 = (
    "b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812"
)
OFFICIAL_ARCHIVE_URL = "https://ember.elastic.co/ember_dataset_2018_2.tar.bz2"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit EMBER2018 v2 dataset")
    ap.add_argument("--data", required=True, help="dir with extracted *.jsonl")
    ap.add_argument("--archive", default=None, help="path to .tar.bz2 to verify")
    ap.add_argument("--out", required=True, help="output audit JSON path")
    args = ap.parse_args(argv)

    report = {
        "official_source_url": OFFICIAL_ARCHIVE_URL,
        "official_archive_sha256": OFFICIAL_ARCHIVE_SHA256,
    }

    if args.archive:
        apath = Path(args.archive)
        if apath.exists():
            computed = sha256_file(apath)
            report["archive"] = {
                "path": str(apath),
                "size_bytes": apath.stat().st_size,
                "computed_sha256": computed,
                "sha256_verified": computed == OFFICIAL_ARCHIVE_SHA256,
            }
        else:
            report["archive"] = {"path": str(apath), "error": "not found"}

    print("Auditing dataset (streaming pass over all JSONL)...", flush=True)
    report.update(dataset.audit_dataset(args.data))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    # Short console summary
    print(json.dumps({
        "archive_verified": report.get("archive", {}).get("sha256_verified"),
        "train_labels": report["train"]["label_counts"],
        "test_labels": report["test"]["label_counts"],
        "train_test_overlap": report["train_test_sha256_overlap"],
        "train_dupes": report["train"]["duplicate_sha256_count"],
        "test_dupes": report["test"]["duplicate_sha256_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
