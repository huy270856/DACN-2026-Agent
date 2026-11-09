"""Checks for the held-out chronology and low-FPR decision rule."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from train_lightgbm import chronological_masks, metrics, threshold_for_fpr


class TrainLightgbmTests(unittest.TestCase):
    def test_threshold_uses_only_allowed_benign_false_positives(self):
        benign = np.array([0.1, 0.3, 0.5, 0.5, 0.9])
        threshold = threshold_for_fpr(benign, 0.2)
        self.assertEqual(int(np.count_nonzero(benign >= threshold)), 1)
        self.assertGreater(threshold, 0.5)

    def test_metrics_confusion_matrix(self):
        result = metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.8, 0.7, 0.9]), 0.75)
        self.assertEqual([result[key] for key in ('tp', 'tn', 'fp', 'fn')], [1, 1, 1, 1])

    def test_chronology_rejects_future_month_in_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'train_metadata.jsonl'
            with path.open('w', encoding='utf-8') as stream:
                for _ in range(3):
                    stream.write(json.dumps({'appeared': '2018-11', 'label': 0}) + '\n')
            with self.assertRaisesRegex(ValueError, 'Unexpected chronology'):
                chronological_masks(tmp, 3)


if __name__ == '__main__':
    unittest.main()
