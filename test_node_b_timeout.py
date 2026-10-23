"""Deterministic timeout test: simulated monotonic clock, no huge file needed."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import context_collector as cc


class TimeoutTests(unittest.TestCase):
    def test_timeout_discards_partial_digest_and_retains_other_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'data.bin'
            target.write_bytes(b'hello' * 100)
            # Advance time by 0.1s per call; timeout must be deterministic.
            clock = iter(i * 0.1 for i in range(100))
            with patch.object(cc.time, 'monotonic', side_effect=lambda: next(clock)):
                result = cc.collect_file_context(target, hash_timeout=0.05)
            self.assertEqual(result['status'], 'DEGRADED')
            self.assertEqual(result['facets']['sha256']['status'], 'UNAVAILABLE')
            self.assertEqual(result['facets']['sha256']['reason'], 'hash_timeout')
            self.assertIsNone(result['facets']['sha256']['value'])
            self.assertEqual(result['facets']['metadata']['status'], 'SUCCESS')
            self.assertEqual(result['facets']['pe_header']['status'], 'SUCCESS')
            self.assertNotIn('file_unchanged_during_collection', result['facets'])

    def test_without_timeout_hash_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'data.bin'
            target.write_bytes(b'hello' * 100)
            result = cc.collect_file_context(target)
            self.assertEqual(result['facets']['sha256']['status'], 'SUCCESS')
            self.assertEqual(len(result['facets']['sha256']['value']), 64)

    def test_timeout_validation(self):
        with self.assertRaises(SystemExit) as cm:
            cc.main(['--file', 'irrelevant', '--hash-timeout', '0'])
        self.assertEqual(cm.exception.code, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
