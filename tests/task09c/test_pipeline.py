"""Unit & integration tests for MonitoringPipeline, queue, dedup, retries, and scope."""
from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from monitoring.cli import make_minimal_pe_bytes
from monitoring.pe_probe import PEProbeResult
from monitoring.pipeline import MockNodeBIntake, MonitoringPipeline
from monitoring.schemas import MonitorConfig, ObservationEvent, new_id, utc_now_iso
from monitoring.win32_file_watcher import validate_watch_dirs


def _file_event(path: str, event_type: str = "FILE_CREATED") -> ObservationEvent:
    return ObservationEvent(
        event_id=new_id("EVT"),
        source="file_watcher",
        event_type=event_type,
        timestamp_utc=utc_now_iso(),
        target_kind="FILE",
        target_path=path,
        path_status="KNOWN",
        reason_code="TEST",
        monotonic_ns=time.monotonic_ns(),
    )


class TestMonitoringPipeline(unittest.TestCase):
    def test_reject_drive_root_and_excluded_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                validate_watch_dirs(["C:\\"], [])
            with self.assertRaises(ValueError):
                validate_watch_dirs([tmp], [tmp])

    def test_valid_pe_and_non_pe_and_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pe_path = os.path.join(tmp, "ok.exe")
            txt_path = os.path.join(tmp, "readme.txt")
            gone_path = os.path.join(tmp, "deleted.exe")
            with open(pe_path, "wb") as f:
                f.write(make_minimal_pe_bytes())
            with open(txt_path, "wb") as f:
                f.write(b"not a pe" * 20)

            sink = MockNodeBIntake()
            cfg = MonitorConfig(
                watch_dirs=[tmp],
                enable_file_watcher=False,
                enable_process_monitor=False,
                debounce_ms=10,
            )
            pipe = MonitoringPipeline(cfg, sink=sink)
            pipe.start()
            try:
                pipe.submit_event(_file_event(pe_path, "FILE_CREATED"))
                pipe.submit_event(_file_event(txt_path, "FILE_CREATED"))
                pipe.submit_event(_file_event(gone_path, "FILE_RENAMED"))
                pipe.flush(timeout=2.0)
            finally:
                pipe.stop()

            cands = sink.snapshot()
            self.assertEqual(len(cands), 1)
            self.assertEqual(cands[0].target_kind, "FILE")
            self.assertTrue(cands[0].target_ref["revalidation_required"])
            self.assertEqual(cands[0].pe_probe["status"], "VALID_PE")
            self.assertEqual(pipe.metrics.filtered_non_pe, 2)

    def test_partial_write_bounded_retry_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "partial.exe")
            with open(path, "wb") as f:
                f.write(make_minimal_pe_bytes())

            calls = {"n": 0}

            def flaky_probe(_p: str) -> PEProbeResult:
                calls["n"] += 1
                if calls["n"] < 3:
                    return PEProbeResult("LOCKED_OR_PARTIAL", False, reason="sharing_violation")
                return PEProbeResult("VALID_PE", True, machine="0x8664", reason="ok")

            sink = MockNodeBIntake()
            cfg = MonitorConfig(
                watch_dirs=[tmp],
                enable_file_watcher=False,
                enable_process_monitor=False,
                debounce_ms=0,
                max_retries=3,
                retry_delay_ms=5,
            )
            pipe = MonitoringPipeline(cfg, sink=sink)
            pipe.start()
            try:
                with mock.patch("monitoring.pipeline.probe_pe_file", side_effect=flaky_probe):
                    pipe.submit_event(_file_event(path))
                    pipe.flush(timeout=2.0)
            finally:
                pipe.stop()

            self.assertEqual(len(sink.snapshot()), 1)
            self.assertEqual(pipe.metrics.retry_attempts, 2)
            self.assertEqual(pipe.metrics.retry_exhausted, 0)

    def test_debounce_coalesce_and_dedup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dup.exe")
            with open(path, "wb") as f:
                f.write(make_minimal_pe_bytes())

            sink = MockNodeBIntake()
            cfg = MonitorConfig(
                watch_dirs=[tmp],
                enable_file_watcher=False,
                enable_process_monitor=False,
                debounce_ms=40,
                dedup_ttl_seconds=5.0,
            )
            pipe = MonitoringPipeline(cfg, sink=sink)
            pipe.start()
            try:
                # Rapid burst -> coalesced into 1
                pipe.submit_event(_file_event(path, "FILE_CREATED"))
                pipe.submit_event(_file_event(path, "FILE_MODIFIED"))
                pipe.flush(timeout=2.0)
                # Second event after debounce -> deduped
                pipe.submit_event(_file_event(path, "FILE_MODIFIED"))
                pipe.flush(timeout=2.0)
            finally:
                pipe.stop()

            self.assertEqual(len(sink.snapshot()), 1)
            self.assertEqual(pipe.metrics.events_coalesced, 1)
            self.assertEqual(pipe.metrics.events_deduped, 1)

    def test_exclude_dir_filtered_and_queue_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            watch_dir = os.path.join(tmp, "lab")
            excl_dir = os.path.join(watch_dir, "quarantine")
            os.makedirs(excl_dir, exist_ok=True)

            excl_file = os.path.join(excl_dir, "ignored.exe")
            with open(excl_file, "wb") as f:
                f.write(make_minimal_pe_bytes())

            # Test exclude_dirs filtering
            sink = MockNodeBIntake()
            cfg = MonitorConfig(
                watch_dirs=[watch_dir],
                exclude_dirs=[excl_dir],
                enable_file_watcher=False,
                enable_process_monitor=False,
                debounce_ms=0,
            )
            pipe = MonitoringPipeline(cfg, sink=sink)
            pipe.start()
            try:
                pipe.submit_event(_file_event(excl_file))
                pipe.flush(timeout=1.0)
            finally:
                pipe.stop()

            self.assertEqual(len(sink.snapshot()), 0)
            self.assertEqual(pipe.metrics.filtered_out_of_scope, 1)

            # Test bounded queue overflow with blocked sink
            gate = threading.Event()

            class SlowSink:
                def __init__(self) -> None:
                    self.items = []

                def submit_candidate(self, c) -> None:
                    gate.wait(timeout=2.0)
                    self.items.append(c)

            slow_sink = SlowSink()
            cfg2 = MonitorConfig(
                watch_dirs=[watch_dir],
                enable_file_watcher=False,
                enable_process_monitor=False,
                debounce_ms=0,
                queue_maxsize=2,
            )
            pipe2 = MonitoringPipeline(cfg2, sink=slow_sink)
            pipe2.start()
            try:
                for i in range(6):
                    p = os.path.join(watch_dir, f"f{i}.exe")
                    with open(p, "wb") as f:
                        f.write(make_minimal_pe_bytes(f"P{i}".encode()))
                    pipe2.submit_event(_file_event(p))
                time.sleep(0.05)
                gate.set()
                pipe2.flush(timeout=2.0)
            finally:
                gate.set()
                pipe2.stop()

            self.assertGreater(pipe2.metrics.dropped_queue_full, 0)
            self.assertLessEqual(pipe2.metrics.queue_peak, 2)

    def test_process_unknown_path_represented_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = MockNodeBIntake()
            cfg = MonitorConfig(
                watch_dirs=[tmp],
                enable_file_watcher=False,
                enable_process_monitor=False,
                debounce_ms=0,
            )
            pipe = MonitoringPipeline(cfg, sink=sink)
            pipe.start()
            try:
                evt = ObservationEvent(
                    event_id=new_id("EVT"),
                    source="process_monitor",
                    event_type="PROCESS_CREATED",
                    timestamp_utc=utc_now_iso(),
                    target_kind="PROCESS",
                    target_path=None,
                    pid=4242,
                    process_start_time_epoch=1795684500.5,
                    path_status="UNKNOWN",
                    reason_code="ACCESS_DENIED",
                    uncertainty_notes=["process_path_unknown:ACCESS_DENIED"],
                    monotonic_ns=time.monotonic_ns(),
                )
                pipe.submit_event(evt)
                pipe.flush(timeout=1.0)
            finally:
                pipe.stop()

            cands = sink.snapshot()
            self.assertEqual(len(cands), 1)
            self.assertEqual(cands[0].path_status, "UNKNOWN")
            self.assertEqual(cands[0].pe_probe["status"], "SKIPPED_UNKNOWN_PATH")
            self.assertEqual(cands[0].target_ref["observed"]["pid"], 4242)
            self.assertIsNone(cands[0].target_ref["observed"]["path"])


if __name__ == "__main__":
    unittest.main()

