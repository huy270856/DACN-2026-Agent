"""Tests for label semantics, unlabeled handling, and dataset audit."""
import json
import os
import tempfile
import unittest

from research.independent_static_ml import dataset
from research.independent_static_ml.tests.fixtures import minimal_raw_record


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class TestLabelSemantics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dacn_ds_test_")
        recs = []
        for i, label in enumerate([0, 1, -1, 0, 1, -1, 99]):
            r = minimal_raw_record()
            r["sha256"] = f"{i:064x}"
            r["label"] = label
            r["appeared"] = "2018-01"
            recs.append(r)
        self.path = os.path.join(self.tmp, "train_features_0.jsonl")
        _write_jsonl(self.path, recs)

    def test_audit_counts_labels_and_excludes_invalid(self):
        rep = dataset.audit_split(self.tmp, ["train_features_0.jsonl"])
        self.assertEqual(rep["total_records"], 7)
        self.assertEqual(rep["label_counts"], {"-1": 2, "0": 2, "1": 2})
        self.assertEqual(rep["invalid_label_records"], 1)  # the label=99 record

    def test_vectorize_keeps_only_0_and_1(self):
        X, y, shas, appeared, stats = dataset.vectorize_files(
            self.tmp, ["train_features_0.jsonl"], keep_labels=(0, 1), workers=1)
        # -1 and 99 excluded -> 4 kept (two 0, two 1)
        self.assertEqual(X.shape[0], 4)
        self.assertEqual(sorted(y.tolist()), [0, 0, 1, 1])
        self.assertEqual(stats["records_other_label_skipped"], 3)
        self.assertNotIn(-1, y.tolist())  # unlabeled NEVER treated as benign

    def test_dataset_not_found(self):
        with self.assertRaises(FileNotFoundError):
            dataset.audit_split("Z:/nonexistent", ["train_features_0.jsonl"])


if __name__ == "__main__":
    unittest.main()
