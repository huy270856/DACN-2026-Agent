"""Windows-only integration tests for DACN Context Collector v1.
Run: .\.venv\Scripts\python.exe test_windows_advanced.py
Optional: .\.venv\Scripts\python.exe test_windows_advanced.py --large
Does not execute untrusted files or alter system files.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import context_collector as cc

if os.name != 'nt':
    raise SystemExit('Windows only')

class AdvancedWindowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='dacn-win-advanced-')
        cls.base = Path(cls.temp.name)
        cls.output = cls.base / 'results'
        cls.output.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_01_exclusive_windows_file_lock(self):
        path = self.base / 'exclusive-lock.bin'
        path.write_bytes(b'DACN lock test' * 1024)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        create = kernel32.CreateFileW
        create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        create.restype = ctypes.c_void_p
        close = kernel32.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        GENERIC_READ = 0x80000000
        OPEN_EXISTING = 3
        handle = create(str(path), GENERIC_READ, 0, None, OPEN_EXISTING, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value, f'CreateFileW error {ctypes.get_last_error()}')
        try:
            result = cc.collect_file_context(path)
            self.assertIn(result['status'], ('DEGRADED', 'FAILED'))
            self.assertNotEqual(result['facets'].get('sha256', {}).get('status'), 'SUCCESS')
            print('  lock:', result['status'], result['errors'])
        finally:
            close(handle)
        result = cc.collect_file_context(path)
        self.assertEqual(result['facets']['sha256']['status'], 'SUCCESS')

    def test_02_file_symlink_reparse(self):
        real = self.base / 'real-file.bin'
        link = self.base / 'linked-file.bin'
        real.write_bytes(b'DACN real file')
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'Symlink requires Developer Mode or privileges: {exc}')
        result = cc.collect_file_context(link)
        self.assertEqual(result['facets']['readable']['reason'], 'symlink_or_reparse_point_not_followed')
        self.assertNotIn('sha256', result['facets'])

    def test_03_directory_as_file(self):
        result = cc.collect_file_context(self.base)
        self.assertEqual(result['facets']['readable']['reason'], 'not_a_regular_file')
        self.assertNotIn('sha256', result['facets'])

    def test_04_mutation_during_hash_deterministic(self):
        path = self.base / 'mutation.bin'
        path.write_bytes(b'X' * (8 * 1024 * 1024))
        original_hash = cc.hash_stream
        def mutate_after_hash(handle, total, progress=False):
            digest = original_hash(handle, total, progress)
            # Deterministically change the same file after reading, before post-hash stat.
            with open(path, 'r+b') as writer:
                writer.seek(0)
                writer.write(b'CHANGED')
                writer.flush()
                os.fsync(writer.fileno())
            return digest
        with mock.patch.object(cc, 'hash_stream', side_effect=mutate_after_hash):
            result = cc.collect_file_context(path)
        self.assertEqual(result['facets']['sha256']['status'], 'UNAVAILABLE')
        self.assertEqual(result['facets']['sha256']['reason'], 'file_changed_during_collection')
        self.assertFalse(result['facets']['file_unchanged_during_collection']['value'])
        print('  mutation:', result['status'], result['facets']['sha256']['reason'])

    def test_05_empty_file_and_hash(self):
        path = self.base / 'empty.bin'
        path.write_bytes(b'')
        result = cc.collect_file_context(path)
        self.assertEqual(result['facets']['sha256']['value'], hashlib.sha256(b'').hexdigest())
        self.assertFalse(result['facets']['pe_header']['value']['is_pe'])

    def test_06_malformed_pe_header(self):
        path = self.base / 'bad-pe.exe'
        data = bytearray(128)
        data[:2] = b'MZ'
        data[60:64] = (999999).to_bytes(4, 'little')
        path.write_bytes(data)
        result = cc.collect_file_context(path)
        self.assertEqual(result['facets']['pe_header']['status'], 'FAILED')
        self.assertEqual(result['facets']['pe_header']['reason'], 'invalid_pe_header_offset')
        self.assertEqual(result['facets']['sha256']['status'], 'SUCCESS')

    def test_07_saved_json_integrity(self):
        path = self.base / 'saved.bin'
        path.write_bytes(b'persisted')
        result = cc.collect_file_context(path)
        saved = cc.save_context(result, self.output)
        self.assertEqual(json.loads(saved.read_text(encoding='utf-8'))['collection_id'], result['collection_id'])
        self.assertTrue(saved.parent.name.startswith('COL-'))
        self.assertEqual(saved.name, 'context.json')

    def test_08_process_exits_while_collecting(self):
        proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.4)'], creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            time.sleep(0.7)
            result = cc.collect_process_context(proc.pid)
            self.assertEqual(result['status'], 'FAILED')
            self.assertTrue(any(e['code'] == 'process_not_found' for e in result['errors']))
        finally:
            proc.wait(timeout=5)

    @unittest.skipUnless('--large' in sys.argv, 'Use --large for 512 MiB streaming test')
    def test_09_large_file_streaming(self):
        path = self.base / 'large-512MiB.bin'
        with open(path, 'wb') as f:
            f.truncate(512 * 1024 * 1024)
        start = time.perf_counter()
        result = cc.collect_file_context(path)
        elapsed = time.perf_counter() - start
        self.assertEqual(result['facets']['sha256']['status'], 'SUCCESS')
        print(f'  512 MiB hashed in {elapsed:.2f}s')

if __name__ == '__main__':
    large = '--large' in sys.argv
    sys.argv = [arg for arg in sys.argv if arg != '--large']
    unittest.main(verbosity=2)
