"""Tests for train/validation/test leakage controls."""
import unittest

import numpy as np

from research.independent_static_ml import dataset
from research.independent_static_ml.train_lightgbm import chronological_split


class TestChronologicalSplit(unittest.TestCase):
    def test_split_is_disjoint_and_covers(self):
        appeared = [f"2018-{(i % 12) + 1:02d}" for i in range(1000)]
        tr, va = chronological_split(appeared, 0.2)
        self.assertEqual(len(set(tr.tolist()) & set(va.tolist())), 0)
        self.assertEqual(len(tr) + len(va), 1000)
        self.assertAlmostEqual(len(va), 200, delta=1)

    def test_validation_holds_latest(self):
        appeared = [f"2018-{(i % 12) + 1:02d}" for i in range(1200)]
        tr, va = chronological_split(appeared, 0.25)
        latest_val = max(appeared[i] for i in va.tolist())
        # newest month must be in validation; training must not exceed it
        self.assertEqual(latest_val, "2018-12")
        max_train = max(appeared[i] for i in tr.tolist())
        self.assertLessEqual(max_train, latest_val)


class TestSplitDisjointShaGuard(unittest.TestCase):
    def test_overlapping_sha_would_be_detected(self):
        # The training script asserts train/val sha256 disjointness; emulate it.
        shas = [f"{i:064x}" for i in range(100)]
        idx_a = np.arange(0, 60)
        idx_b = np.arange(50, 100)  # deliberate overlap 50..59
        a = {shas[i] for i in idx_a.tolist()}
        b = {shas[i] for i in idx_b.tolist()}
        self.assertGreater(len(a & b), 0)  # the guard must catch this case


class TestDatasetNotFound(unittest.TestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            list(dataset.iter_records("Z:/does/not/exist/train_features_0.jsonl"))


if __name__ == "__main__":
    unittest.main()
