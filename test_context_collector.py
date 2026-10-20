"""Tests use header fixtures only; no Windows sample is ever executed."""
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import context_collector as cc


def header_fixture(machine=0x8664, magic=0x20B, dll=False):
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, machine, 1, 0, 0, 0, 224, 0x2002 if dll else 2)
    struct.pack_into("<H", data, 152, magic)
    return bytes(data)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_pe32_pe32plus_and_dll_independent_of_extension(self):
        for machine, magic, dll in [(0x14C, 0x10B, False), (0x8664, 0x20B, False), (0x8664, 0x20B, True)]:
            payload = header_fixture(machine, magic, dll)
            path = self.write("sample.bin", payload)
            result = cc.collect_file_context(path)
            self.assertEqual(result["status"], "SUCCESS")
            fields = result["facets"]["pe_header"]["value"]
            self.assertTrue(fields["is_pe"])
            self.assertEqual(fields["is_dll"], dll)
            self.assertEqual(fields["architecture"], "x64" if magic == 0x20B else "x86")
            self.assertEqual(result["facets"]["sha256"]["value"], hashlib.sha256(payload).hexdigest())

    def test_non_pe_and_empty_are_observations_not_verdicts(self):
        for payload in [b"", b"plain text"]:
            result = cc.collect_file_context(self.write("test.exe", payload))
            self.assertEqual(result["status"], "SUCCESS")
            self.assertFalse(result["facets"]["pe_header"]["value"]["is_pe"])
            self.assertNotIn("verdict", result)

    def test_malformed_header_keeps_full_hash_and_marks_degraded(self):
        for payload in [b"MZ", header_fixture()[:160]]:
            result = cc.collect_file_context(self.write("broken.exe", payload))
            self.assertEqual(result["status"], "DEGRADED")
            self.assertEqual(result["facets"]["pe_header"]["status"], "FAILED")
            self.assertEqual(result["facets"]["sha256"]["value"], hashlib.sha256(payload).hexdigest())

    def test_missing_and_directory(self):
        for path in [self.root / "missing.exe", self.root]:
            result = cc.collect_file_context(path)
            self.assertEqual(result["status"], "FAILED")
            self.assertNotIn("sha256", result["facets"])

    @unittest.skipIf(os.name == "nt", "Symlink creation may require privileges on Windows")
    def test_does_not_follow_final_symlink(self):
        target = self.write("source", b"data")
        link = self.root / "link"
        link.symlink_to(target)
        result = cc.collect_file_context(link)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["facets"]["readable"]["reason"], "symlink_or_reparse_point_not_followed")

    def test_permission_denied_keeps_metadata(self):
        path = self.write("locked.exe", header_fixture())
        with patch.object(cc.os, "open", side_effect=PermissionError("denied")):
            result = cc.collect_file_context(path)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertEqual(result["facets"]["metadata"]["status"], "SUCCESS")
        self.assertEqual(result["facets"]["readable"]["status"], "UNAVAILABLE")

    def test_hash_reads_bounded_chunks(self):
        class BoundedReader(io.BytesIO):
            def read(self, size=-1):
                if size < 0 or size > cc.CHUNK_BYTES:
                    raise AssertionError("Unbounded read")
                return super().read(size)
        data = b"abc123" * 600_000
        self.assertEqual(cc.hash_stream(BoundedReader(data), len(data)), hashlib.sha256(data).hexdigest())

    def test_header_reader_does_not_read_entire_large_file(self):
        class BoundedReader(io.BytesIO):
            def read(self, size=-1):
                if size < 0 or size > 64:
                    raise AssertionError("PE header read too large")
                return super().read(size)
        data = header_fixture() + b"x" * (2 * cc.CHUNK_BYTES)
        self.assertTrue(cc.pe_header(BoundedReader(data), len(data))["value"]["is_pe"])

    def test_changed_file_discards_hash_and_header(self):
        path = self.write("changing.exe", header_fixture())
        original = cc.hash_stream
        def change(handle, total, progress):
            digest = original(handle, total, progress)
            with path.open("ab") as output:
                output.write(b"changed")
            return digest
        with patch.object(cc, "hash_stream", side_effect=change):
            result = cc.collect_file_context(path)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertIsNone(result["facets"]["sha256"]["value"])
        self.assertEqual(result["facets"]["pe_header"]["status"], "UNAVAILABLE")

    def test_windows_stat_and_fstat_ctime_difference_does_not_reject_file(self):
        # Windows stat(path) may expose birth time as ctime, while fstat(fd)
        # exposes change time. Same file, different ctime interpretation.
        path = self.write("stable.exe", header_fixture())
        real_fstat = os.fstat
        def windows_fstat(fd):
            info = real_fstat(fd)
            fields = {key: getattr(info, key) for key in [
                "st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"
            ]}
            fields["st_ctime_ns"] += 1_000_000_000
            return SimpleNamespace(**fields)
        with patch.object(cc, "STAT_CTIME_COMPARABLE", False, create=True), patch.object(cc.os, "fstat", side_effect=windows_fstat):
            result = cc.collect_file_context(path)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["facets"]["sha256"]["value"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_windows_policy_still_detects_same_size_modification(self):
        path = self.write("changing_same_size.exe", header_fixture())
        original = cc.hash_stream
        def change(handle, total, progress):
            digest = original(handle, total, progress)
            info = path.stat()
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
            return digest
        with patch.object(cc, "STAT_CTIME_COMPARABLE", False, create=True), patch.object(cc, "hash_stream", side_effect=change):
            result = cc.collect_file_context(path)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertIsNone(result["facets"]["sha256"]["value"])

    def test_windows_policy_keeps_file_identity_checks(self):
        base = dict(st_dev=1, st_ino=10, st_size=512, st_mtime_ns=100, st_ctime_ns=200)
        first = SimpleNamespace(**base)
        replacement = SimpleNamespace(**{**base, "st_ino": 11})
        with patch.object(cc, "STAT_CTIME_COMPARABLE", False, create=True):
            self.assertNotEqual(cc.identity(first), cc.identity(replacement))

    def test_windows_policy_still_checks_change_time_within_fd_stats(self):
        path = self.write("changed.exe", header_fixture())
        real_fstat = os.fstat
        observations = []
        def changing_fstat(fd):
            info = real_fstat(fd)
            fields = {key: getattr(info, key) for key in [
                "st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"
            ]}
            observations.append(fd)
            fields["st_ctime_ns"] += len(observations) * 1_000_000_000
            return SimpleNamespace(**fields)
        with patch.object(cc, "STAT_CTIME_COMPARABLE", False), patch.object(cc.os, "fstat", side_effect=changing_fstat):
            result = cc.collect_file_context(path)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertIsNone(result["facets"]["sha256"]["value"])

    def test_cancel_retains_context_without_partial_hash(self):
        path = self.write("sample.exe", header_fixture())
        with patch.object(cc, "hash_stream", side_effect=KeyboardInterrupt):
            result = cc.collect_file_context(path)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["status"], "DEGRADED")
        self.assertIsNone(result["facets"]["sha256"]["value"])
        output = cc.save_context(result, self.root / "output")
        self.assertTrue(json.loads(output.read_text())["cancelled"])

    def test_history_preserves_previous_runs_and_source(self):
        data = header_fixture()
        path = self.write("sample.exe", data)
        first = cc.save_context(cc.collect_file_context(path), self.root / "runs")
        before = first.read_bytes()
        second = cc.save_context(cc.collect_file_context(path), self.root / "runs")
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), before)
        self.assertEqual(path.read_bytes(), data)

    def test_cli_saved_output_and_exit_code(self):
        result = subprocess.run([sys.executable, str(Path(cc.__file__)), "--file", str(self.root / "missing"), "--output", str(self.root / "cli")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["status"], "FAILED")
        self.assertTrue(Path(summary["context_path"]).is_file())

    def test_current_pid_identity_and_backing_file(self):
        result = cc.collect_process_context(os.getpid())
        self.assertIn(result["status"], ["SUCCESS", "DEGRADED"])
        self.assertEqual(result["target"]["pid"], os.getpid())
        self.assertTrue(result["facets"]["process_identity_still_present"]["value"])
        self.assertIn("backing_file_context", result)

    def test_exited_pid(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        pid = child.pid
        child.wait()
        result = cc.collect_process_context(pid)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["errors"][0]["code"], "process_not_found")


if __name__ == "__main__":
    unittest.main()
