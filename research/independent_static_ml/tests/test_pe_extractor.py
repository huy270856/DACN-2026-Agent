"""Unit tests for the read-only PE inference extractor (error handling)."""
import os
import unittest

import numpy as np

from research.independent_static_ml import pe_extractor

# A real, benign Windows binary with a stable path. Skip if unavailable.
BENIGN_PE = r"C:\Windows\System32\notepad.exe"


class TestPEExtractorErrors(unittest.TestCase):
    def test_empty_input_malformed_no_zero_vector(self):
        res = pe_extractor.extract_from_bytes(b"")
        self.assertEqual(res.status, "MALFORMED")
        self.assertIsNone(res.vector)          # never fabricate a zero vector
        self.assertIsNotNone(res.error)

    def test_truncated_mz_is_flagged(self):
        res = pe_extractor.extract_from_bytes(b"MZ" + b"\x00" * 64)
        # Not a complete PE; status must flag it (not silently "OK").
        self.assertIn(res.status, ("PARSED_NULL", "MALFORMED"))

    def test_random_garbage(self):
        res = pe_extractor.extract_from_bytes(os.urandom(5000))
        self.assertIn(res.status, ("PARSED_NULL", "MALFORMED", "OK"))
        if res.vector is not None:
            self.assertEqual(res.vector.shape, (2381,))
            self.assertTrue(np.all(np.isfinite(res.vector)))

    def test_sha256_is_consistent(self):
        data = b"MZ" + b"\x00" * 100
        r1 = pe_extractor.extract_from_bytes(data)
        r2 = pe_extractor.extract_from_bytes(data)
        self.assertEqual(r1.sha256, r2.sha256)
        self.assertEqual(len(r1.sha256), 64)


@unittest.skipUnless(os.path.exists(BENIGN_PE), "benign Windows PE not present")
class TestPEExtractorRealBenign(unittest.TestCase):
    def test_real_benign_pe_vector(self):
        res = pe_extractor.extract_from_file(BENIGN_PE)
        self.assertEqual(res.status, "OK")
        self.assertEqual(res.vector.shape, (2381,))
        self.assertTrue(np.all(np.isfinite(res.vector)))

    def test_real_benign_pe_deterministic(self):
        a = pe_extractor.extract_from_file(BENIGN_PE)
        b = pe_extractor.extract_from_file(BENIGN_PE)
        self.assertTrue(np.array_equal(a.vector, b.vector))
        self.assertEqual(a.sha256, b.sha256)


if __name__ == "__main__":
    unittest.main()
