"""Unit tests for bounded PE header probe."""
from __future__ import annotations

import os
import struct
import tempfile
import unittest
from unittest import mock

from monitoring.cli import make_minimal_pe_bytes
from monitoring.pe_probe import probe_pe_file


class TestPEProbe(unittest.TestCase):
    def test_valid_pe_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "benign.exe")
            with open(path, "wb") as f:
                f.write(make_minimal_pe_bytes())
            res = probe_pe_file(path)
            self.assertTrue(res.is_pe)
            self.assertEqual(res.status, "VALID_PE")
            self.assertEqual(res.machine, "0x8664")

    def test_non_pe_text_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "notes.txt")
            with open(path, "wb") as f:
                f.write(b"hello world " * 20)
            res = probe_pe_file(path)
            self.assertFalse(res.is_pe)
            self.assertEqual(res.status, "NON_PE")

    def test_empty_or_short_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_path = os.path.join(tmp, "empty.exe")
            with open(empty_path, "wb"):
                pass
            res_empty = probe_pe_file(empty_path)
            self.assertFalse(res_empty.is_pe)
            self.assertEqual(res_empty.status, "PARTIAL_OR_EMPTY")

            short_path = os.path.join(tmp, "short.exe")
            with open(short_path, "wb") as f:
                f.write(b"MZ")
            res_short = probe_pe_file(short_path)
            self.assertFalse(res_short.is_pe)
            self.assertEqual(res_short.status, "NON_PE")

    def test_malformed_pe_bad_e_lfanew_and_bad_sig(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_off = os.path.join(tmp, "bad_offset.exe")
            dos = bytearray(64)
            dos[0:2] = b"MZ"
            struct.pack_into("<I", dos, 0x3C, 999999)
            with open(bad_off, "wb") as f:
                f.write(dos)
            res1 = probe_pe_file(bad_off)
            self.assertFalse(res1.is_pe)
            self.assertEqual(res1.status, "MALFORMED_PE")

            bad_sig = os.path.join(tmp, "bad_sig.exe")
            data = bytearray(make_minimal_pe_bytes())
            data[64:68] = b"NOPE"
            with open(bad_sig, "wb") as f:
                f.write(data)
            res2 = probe_pe_file(bad_sig)
            self.assertFalse(res2.is_pe)
            self.assertEqual(res2.status, "MALFORMED_PE")

    def test_missing_and_permission_denied(self) -> None:
        res_missing = probe_pe_file(r"C:\nonexistent_task09c_dir\missing.exe")
        self.assertFalse(res_missing.is_pe)
        self.assertEqual(res_missing.status, "FILE_MISSING")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "locked.exe")
            with open(path, "wb") as f:
                f.write(make_minimal_pe_bytes())
            with mock.patch("builtins.open", side_effect=PermissionError("denied")):
                res_perm = probe_pe_file(path)
                self.assertFalse(res_perm.is_pe)
                self.assertEqual(res_perm.status, "PERMISSION_DENIED")


if __name__ == "__main__":
    unittest.main()

