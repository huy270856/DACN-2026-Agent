"""Live Windows tests for ReadDirectoryChangesW and Toolhelp32 process monitoring."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest

from monitoring.cli import make_minimal_pe_bytes
from monitoring.pipeline import MockNodeBIntake, MonitoringPipeline
from monitoring.schemas import MonitorConfig


@unittest.skipUnless(os.name == "nt", "Windows-only live monitoring test")
class TestWindowsLiveMonitoring(unittest.TestCase):
    def test_live_file_create_and_rename_and_restart(self) -> None:
        with tempfile.TemporaryDirectory(prefix="task09c_live_file_") as tmp:
            sink = MockNodeBIntake()
            cfg = MonitorConfig(
                watch_dirs=[tmp],
                enable_file_watcher=True,
                enable_process_monitor=False,
                debounce_ms=20,
            )
            pipe = MonitoringPipeline(cfg, sink=sink)
            pipe.start()
            time.sleep(0.1)
            try:
                src = os.path.join(tmp, "staging.tmp")
                dst = os.path.join(tmp, "benign_renamed.exe")
                with open(src, "wb") as f:
                    f.write(make_minimal_pe_bytes(b"LIVE_FIXTURE"))
                time.sleep(0.1)
                os.replace(src, dst)

                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline and len(sink.snapshot()) < 2:
                    time.sleep(0.02)
                pipe.flush(timeout=1.0)
            finally:
                pipe.stop(timeout=3.0)

            cands = sink.snapshot()
            self.assertGreaterEqual(len(cands), 2)
            self.assertTrue(any(c.target_ref["observed"]["path"].endswith("benign_renamed.exe") for c in cands))

            # Verify restart does not hang or crash
            pipe.start()
            time.sleep(0.05)
            pipe.stop(timeout=3.0)

    def test_live_process_creation_in_lab(self) -> None:
        with tempfile.TemporaryDirectory(prefix="task09c_live_proc_") as tmp:
            sink = MockNodeBIntake()
            cfg = MonitorConfig(
                watch_dirs=[tmp],
                enable_file_watcher=False,
                enable_process_monitor=True,
                process_poll_interval_ms=30,
            )
            pipe = MonitoringPipeline(cfg, sink=sink)
            pipe.start()
            time.sleep(0.1)
            proc = None
            try:
                # Benign short sleep process so Toolhelp32 observes it cleanly
                proc = subprocess.Popen(
                    [sys.executable, "-c", "import time; time.sleep(0.4)"]
                )
                deadline = time.monotonic() + 3.0
                found = None
                while time.monotonic() < deadline:
                    for c in sink.snapshot():
                        if c.target_kind == "PROCESS" and c.target_ref["observed"]["pid"] == proc.pid:
                            found = c
                            break
                    if found is not None:
                        break
                    time.sleep(0.03)
            finally:
                if proc is not None:
                    proc.wait(timeout=3)
                pipe.stop(timeout=3.0)

            self.assertIsNotNone(found, "Expected live process creation event for child python.exe")
            assert found is not None
            self.assertIsNotNone(found.target_ref["observed"]["start_time_epoch"])
            self.assertTrue(
                found.target_ref["observed"]["path"].lower().endswith("python.exe")
            )


if __name__ == "__main__":
    unittest.main()

