"""Tests for model IO, digest integrity, version mismatch, and determinism.

A tiny LightGBM model is trained in-memory on synthetic 2381-dim data. This is a
*mechanism* test (loading, digest checks, determinism) and makes no claim about
malware-detection accuracy.
"""
import json
import os
import tempfile
import unittest

import numpy as np

from research.independent_static_ml import FEATURE_COUNT, manifests, predict_cli


def _train_tiny_model(path, n_feat=FEATURE_COUNT, seed=0):
    import lightgbm as lgb
    rng = np.random.default_rng(seed)
    X = rng.random((400, n_feat), dtype=np.float64).astype(np.float32)
    # a learnable signal in feature 0
    y = (X[:, 0] > 0.5).astype(int)
    ds = lgb.Dataset(X, label=y)
    booster = lgb.train({"objective": "binary", "num_leaves": 7,
                         "verbosity": -1, "seed": seed},
                        ds, num_boost_round=15)
    booster.save_model(path)
    return booster


class TestModelMechanics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="dacn_model_test_")
        cls.model_path = os.path.join(cls.tmp, "model_lightgbm.txt")
        _train_tiny_model(cls.model_path)
        cls.model_sha = manifests.sha256_file(cls.model_path)
        cls.manifest_path = os.path.join(cls.tmp, "model_manifest.json")
        manifest = {
            "model_id": "tiny-test",
            "model_sha256": cls.model_sha,
            "threshold_selection": {"primary_threshold": 0.5},
        }
        with open(cls.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        # a real benign PE to feed
        cls.pe = r"C:\Windows\System32\notepad.exe"

    def test_predict_determinism_same_artifact(self):
        if not os.path.exists(self.pe):
            self.skipTest("benign PE not present")
        a = predict_cli.predict_file(self.pe, self.model_path, self.manifest_path)
        b = predict_cli.predict_file(self.pe, self.model_path, self.manifest_path)
        self.assertEqual(a["raw_score"], b["raw_score"])
        self.assertEqual(a["predicted_label"], b["predicted_label"])
        self.assertEqual(a["target_sha256"], b["target_sha256"])

    def test_wrong_model_digest_refused(self):
        # manifest claims a different digest -> must refuse to score
        bad_manifest = os.path.join(self.tmp, "bad_manifest.json")
        with open(bad_manifest, "w", encoding="utf-8") as f:
            json.dump({"model_id": "x", "model_sha256": "f" * 64,
                       "threshold_selection": {"primary_threshold": 0.5}}, f)
        out = predict_cli.predict_file(self.pe, self.model_path, bad_manifest)
        self.assertIsNone(out["raw_score"])
        self.assertIn("digest", out["error"].lower())

    def test_model_feature_version_mismatch(self):
        # model trained with the wrong number of features must be rejected
        wrong = os.path.join(self.tmp, "wrong_feat.txt")
        _train_tiny_model(wrong, n_feat=100)
        if not os.path.exists(self.pe):
            self.skipTest("benign PE not present")
        out = predict_cli.predict_file(self.pe, wrong, manifest_path=None)
        self.assertIsNone(out["raw_score"])
        self.assertIn("mismatch", out["error"].lower())

    def test_model_loading_failure(self):
        missing = os.path.join(self.tmp, "nope.txt")
        with self.assertRaises(Exception):
            predict_cli.predict_file(self.pe, missing, manifest_path=None)


if __name__ == "__main__":
    unittest.main()
