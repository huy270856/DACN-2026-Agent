"""Tests for Node B additive `format` facet (magic/header based detection).

No suspect binary is executed; all PE bytes are minimal synthetic headers built
in-memory, and non-PE cases use short magic prefixes. Benign only.
"""
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import context_collector as cc


def make_pe(*, machine=0x8664, characteristics=0x0002, magic=0x20B, sections=0):
    """Build a minimal structurally-valid PE that passes pe_header's minimum checks."""
    optional_size = 112 if magic == 0x20B else 96
    pe_offset = 64
    dos = bytearray(64)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 60, pe_offset)           # e_lfanew -> PE header
    coff = b"PE\0\0" + struct.pack(
        "<HHIIIHH", machine, sections, 0, 0, 0, optional_size, characteristics)
    optional = struct.pack("<H", magic) + b"\0" * (optional_size - 2)
    body = bytes(dos) + coff + optional
    # Ensure header_end + sections*40 <= file_size.
    pad = max(0, (pe_offset + 24 + optional_size + sections * 40) - len(body))
    return body + b"\0" * pad


class FormatFacetTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="nodeb-fmt-"))

    def _collect(self, name, data):
        p = self.dir / name
        p.write_bytes(data)
        ctx = cc.collect_file_context(str(p))
        return ctx, ctx["facets"].get("format", {})

    def _fmt(self, name, data):
        _, f = self._collect(name, data)
        self.assertEqual(f.get("status"), "SUCCESS")
        return f["value"]

    def test_pe32plus_exe(self):
        v = self._fmt("a.exe", make_pe(machine=0x8664, characteristics=0x0002, magic=0x20B))
        self.assertEqual(v["format"], "PE")
        self.assertTrue(v["analyzer_supported"])
        self.assertTrue(v["structural_valid"])
        self.assertEqual(v["architecture"], "x64")
        self.assertEqual(v["pe_kind"], "PE32+")
        self.assertFalse(v["is_dll"])

    def test_pe_dll(self):
        v = self._fmt("a.dll", make_pe(machine=0x8664, characteristics=0x2000, magic=0x20B))
        self.assertEqual(v["format"], "PE")
        self.assertTrue(v["is_dll"])

    def test_pe32_x86(self):
        v = self._fmt("x86.bin", make_pe(machine=0x14C, characteristics=0x0002, magic=0x10B))
        self.assertEqual(v["format"], "PE")
        self.assertEqual(v["architecture"], "x86")
        self.assertEqual(v["pe_kind"], "PE32")

    def test_detection_ignores_extension(self):
        # A valid PE named .txt is still PE; a text file named .exe is still UNKNOWN.
        self.assertEqual(self._fmt("looks_like_text.txt", make_pe())["format"], "PE")
        self.assertEqual(self._fmt("fake.exe", b"just text, not a binary")["format"], "UNKNOWN")

    def test_elf_is_unsupported_not_unknown(self):
        v = self._fmt("a.out", b"\x7fELF" + b"\x00" * 200)
        self.assertEqual(v["format"], "UNSUPPORTED")
        self.assertEqual(v["detected"], "ELF")
        self.assertFalse(v["analyzer_supported"])

    def test_zip_unsupported(self):
        self.assertEqual(self._fmt("a.zip", b"PK\x03\x04" + b"\x00" * 40)["detected"], "ZIP")

    def test_unknown_file(self):
        self.assertEqual(self._fmt("note", b"hello world")["format"], "UNKNOWN")

    def test_empty_file_unknown(self):
        self.assertEqual(self._fmt("empty", b"")["format"], "UNKNOWN")

    def test_mz_truncated_is_malformed(self):
        v = self._fmt("stub", b"MZ" + b"\x00" * 10)
        self.assertEqual(v["format"], "MALFORMED")
        self.assertEqual(v["detected"], "PE")
        self.assertFalse(v["analyzer_supported"])
        self.assertFalse(v["structural_valid"])

    def test_mz_bad_pe_signature_is_malformed(self):
        # MZ with a valid-looking e_lfanew but no "PE\0\0" at that offset.
        data = bytearray(make_pe())
        data[64:68] = b"XX\0\0"  # corrupt PE signature
        self.assertEqual(self._fmt("corrupt", bytes(data))["format"], "MALFORMED")

    def test_format_invalidated_when_file_changes_during_collection(self):
        # Force the unchanged check to fail -> format must become UNAVAILABLE,
        # never a stale SUCCESS value.
        p = self.dir / "changing.bin"
        p.write_bytes(make_pe())
        with mock.patch.object(cc, "same_observation", return_value=False):
            ctx = cc.collect_file_context(str(p))
        self.assertEqual(ctx["facets"]["format"]["status"], "UNAVAILABLE")
        self.assertEqual(ctx["facets"]["sha256"]["status"], "UNAVAILABLE")

    def test_pe_still_emits_legacy_pe_header_facet(self):
        # Backward compatibility: the pe_header facet is unchanged/present.
        ctx, _ = self._collect("legacy.bin", make_pe())
        pe = ctx["facets"]["pe_header"]
        self.assertEqual(pe["status"], "SUCCESS")
        self.assertTrue(pe["value"]["is_pe"])

    @unittest.skipUnless(os.name == "nt", "Backing-file PE detection uses the Windows python.exe")
    def test_process_backing_file_has_format_facet(self):
        ctx = cc.collect_process_context(os.getpid(), include_backing_file=True)
        backing = ctx.get("backing_file_context")
        self.assertIsNotNone(backing)
        fmt = backing["facets"].get("format", {})
        # python.exe on Windows is a PE image.
        self.assertEqual(fmt.get("status"), "SUCCESS")
        self.assertEqual(fmt["value"]["format"], "PE")


if __name__ == "__main__":
    unittest.main()
