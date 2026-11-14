"""Unit tests for the independent EMBER v2 vectorizer (feature contract)."""
import unittest

import numpy as np

from research.independent_static_ml import ember_v2
from research.independent_static_ml.tests.fixtures import minimal_raw_record


class TestVectorContract(unittest.TestCase):
    def test_group_dims_sum_to_2381(self):
        self.assertEqual(sum(d for _, d in ember_v2.GROUP_ORDER), 2381)
        self.assertEqual(ember_v2.FEATURE_COUNT, 2381)

    def test_group_order_and_offsets(self):
        names = [n for n, _ in ember_v2.GROUP_ORDER]
        self.assertEqual(names, ["histogram", "byteentropy", "strings", "general",
                                 "header", "section", "imports", "exports",
                                 "datadirectories"])
        # offsets are contiguous and cover [0, 2381)
        last = 0
        for name, dim in ember_v2.GROUP_ORDER:
            start, end = ember_v2.GROUP_OFFSETS[name]
            self.assertEqual(start, last)
            self.assertEqual(end - start, dim)
            last = end
        self.assertEqual(last, 2381)

    def test_vector_shape_dtype_finite(self):
        v = ember_v2.process_raw_record(minimal_raw_record())
        self.assertEqual(v.shape, (2381,))
        self.assertEqual(v.dtype, np.float32)
        self.assertTrue(np.all(np.isfinite(v)))

    def test_determinism(self):
        r = minimal_raw_record()
        v1 = ember_v2.process_raw_record(r)
        v2 = ember_v2.process_raw_record(r)
        self.assertTrue(np.array_equal(v1, v2))

    def test_missing_feature_group_raises(self):
        r = minimal_raw_record()
        del r["imports"]
        with self.assertRaises(ember_v2.FeatureExtractionError):
            ember_v2.process_raw_record(r)

    def test_malformed_group_raises_not_zero_vector(self):
        r = minimal_raw_record()
        r["general"] = {"size": 1}  # missing required keys
        with self.assertRaises(ember_v2.FeatureExtractionError):
            ember_v2.process_raw_record(r)

    def test_non_finite_input_rejected(self):
        r = minimal_raw_record()
        r["histogram"] = [0] * 256  # sum == 0 -> 0/0 -> nan
        with self.assertRaises(ember_v2.FeatureExtractionError):
            ember_v2.process_raw_record(r)

    def test_group_boundaries_place_values(self):
        # general group is 10 raw values at a known offset; verify placement.
        r = minimal_raw_record()
        v = ember_v2.process_raw_record(r)
        s, e = ember_v2.GROUP_OFFSETS["general"]
        self.assertEqual(e - s, 10)
        self.assertEqual(v[s], np.float32(r["general"]["size"]))


if __name__ == "__main__":
    unittest.main()
