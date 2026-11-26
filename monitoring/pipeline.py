"""Core monitoring pipeline: debounce, bounded retry, PE filter, dedup, bounded queue."""
from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from monitoring.pe_probe import observation_sha256, probe_pe_file
from monitoring.schemas import (
    MonitorConfig,
    MonitorMetrics,
    ObservationEvent,
    ScanCandidate,
    build_target_ref,
    new_id,
    utc_now_iso,
)
from monitoring.win32_file_watcher import Win32FileWatcher, is_subpath
from monitoring.win32_process_monitor import Win32ProcessMonitor

RETRYABLE_PE_STATUSES = {"LOCKED_OR_PARTIAL", "PARTIAL_OR_EMPTY"}


class NodeBSink(Protocol):
    """Mock boundary protocol representing Node B intake."""

    def submit_candidate(self, candidate: ScanCandidate) -> None:
        ...


class MockNodeBIntake:
    """In-memory mock Node B receiver for testing and handoff demonstration."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._candidates: List[ScanCandidate] = []

    def submit_candidate(self, candidate: ScanCandidate) -> None:
        with self._lock:
            self._candidates.append(candidate)

    def snapshot(self) -> List[ScanCandidate]:
        with self._lock:
            return list(self._candidates)

    def clear(self) -> None:
        with self._lock:
            self._candidates.clear()


class MonitoringPipeline:
    """Orchestrates file/process observation into bounded ScanCandidate delivery."""

    def __init__(
        self,
        config: MonitorConfig,
        sink: Optional[NodeBSink] = None,
        file_watcher_factory: Optional[Callable[..., Any]] = None,
        process_monitor_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config
        self.sink: NodeBSink = sink or MockNodeBIntake()
        self.metrics = MonitorMetrics()
        self._metrics_lock = threading.Lock()

        self._queue: queue.Queue[Optional[ScanCandidate]] = queue.Queue(
            maxsize=max(1, config.queue_maxsize)
        )
        self._stop_event = threading.Event()
        self._consumer_thread: Optional[threading.Thread] = None

        # Debounce state: key -> (Timer, ObservationEvent)
        self._debounce_lock = threading.Lock()
        self._pending_debounce: Dict[str, Tuple[threading.Timer, ObservationEvent]] = {}

        # Dedup cache: dedup_key -> monotonic_expiry
        self._dedup_lock = threading.Lock()
        self._dedup_cache: Dict[str, float] = {}

        self._excludes = [os.path.realpath(d) for d in config.exclude_dirs]
        self._watch_roots = [os.path.realpath(d) for d in config.watch_dirs]

        self._file_watcher: Optional[Any] = None
        if config.enable_file_watcher:
            factory = file_watcher_factory or self._default_file_watcher
            self._file_watcher = factory()

        self._process_monitor: Optional[Any] = None
        if config.enable_process_monitor:
            pfactory = process_monitor_factory or self._default_process_monitor
            self._process_monitor = pfactory()

    def _default_file_watcher(self) -> Win32FileWatcher:
        return Win32FileWatcher(
            watch_dirs=self.config.watch_dirs,
            exclude_dirs=self.config.exclude_dirs,
            on_event=self.submit_event,
            on_overflow=self._on_watcher_overflow,
            on_error=self._on_component_error,
            allow_drive_root=self.config.allow_drive_root,
        )

    def _default_process_monitor(self) -> Win32ProcessMonitor:
        return Win32ProcessMonitor(
            on_event=self.submit_event,
            poll_interval_ms=self.config.process_poll_interval_ms,
            on_error=self._on_component_error,
        )

    def _on_watcher_overflow(self, _watch_dir: str) -> None:
        with self._metrics_lock:
            self.metrics.watcher_overflows += 1

    def _on_component_error(self, _msg: str) -> None:
        with self._metrics_lock:
            self.metrics.errors += 1

    def start(self) -> None:
        if self._consumer_thread is not None:
            return
        self._stop_event.clear()
        self._consumer_thread = threading.Thread(
            target=self._consume_loop, name="monitoring-consumer", daemon=True
        )
        self._consumer_thread.start()
        if self._file_watcher is not None:
            self._file_watcher.start()
        if self._process_monitor is not None:
            self._process_monitor.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._file_watcher is not None:
            self._file_watcher.stop(timeout=timeout)
        if self._process_monitor is not None:
            self._process_monitor.stop(timeout=timeout)

        # Cancel pending debounce timers cleanly
        with self._debounce_lock:
            for timer, _ in self._pending_debounce.values():
                timer.cancel()
            self._pending_debounce.clear()

        if self._consumer_thread is not None:
            # Put sentinel; if queue is full, drain one slot or wait briefly
            try:
                self._queue.put(None, timeout=0.5)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    pass
                self._queue.put_nowait(None)
            self._consumer_thread.join(timeout=timeout)
            self._consumer_thread = None

    def flush(self, timeout: float = 5.0) -> None:
        """Wait until pending debounce timers and queued items are processed (for tests)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._debounce_lock:
                pending = len(self._pending_debounce)
            if pending == 0 and self._queue.unfinished_tasks == 0:
                return
            time.sleep(0.01)

    def submit_event(self, event: ObservationEvent) -> None:
        """Ingest an ObservationEvent (from watcher, process monitor, or test)."""
        if self._stop_event.is_set():
            return
        with self._metrics_lock:
            self.metrics.events_emitted += 1

        if event.target_kind == "PROCESS" or self.config.debounce_ms <= 0:
            self._process_event(event)
            return

        key = os.path.normcase(os.path.normpath(event.target_path or event.event_id))
        delay = self.config.debounce_ms / 1000.0
        with self._debounce_lock:
            existing = self._pending_debounce.pop(key, None)
            if existing is not None:
                existing[0].cancel()
                with self._metrics_lock:
                    self.metrics.events_coalesced += 1
            timer = threading.Timer(delay, self._on_debounce_fired, args=(key,))
            timer.daemon = True
            self._pending_debounce[key] = (timer, event)
            timer.start()

    def _on_debounce_fired(self, key: str) -> None:
        with self._debounce_lock:
            entry = self._pending_debounce.pop(key, None)
        if entry is None or self._stop_event.is_set():
            return
        self._process_event(entry[1])

    def _is_in_scope_file(self, path: Optional[str]) -> Tuple[bool, str]:
        if not path:
            return False, "missing_path"
        try:
            real_p = os.path.realpath(path)
        except OSError:
            return False, "realpath_failed"
        if any(is_subpath(real_p, ex) for ex in self._excludes):
            return False, "excluded_dir"
        if self._watch_roots and not any(is_subpath(real_p, root) for root in self._watch_roots):
            return False, "outside_watch_dirs"
        return True, "in_scope"

    def _is_duplicate(self, dedup_key: str) -> bool:
        now_m = time.monotonic()
        with self._dedup_lock:
            if len(self._dedup_cache) >= self.config.dedup_max_entries:
                # Evict expired entries first; if still full, clear oldest
                expired = [k for k, exp in self._dedup_cache.items() if exp <= now_m]
                for k in expired:
                    del self._dedup_cache[k]
                if len(self._dedup_cache) >= self.config.dedup_max_entries:
                    self._dedup_cache.clear()

            expiry = self._dedup_cache.get(dedup_key)
            if expiry is not None and expiry > now_m:
                return True
            self._dedup_cache[dedup_key] = now_m + self.config.dedup_ttl_seconds
            return False

    def _process_event(self, event: ObservationEvent) -> None:
        if event.target_kind == "PROCESS":
            self._handle_process_event(event)
            return
        self._handle_file_event(event)

    def _handle_process_event(self, event: ObservationEvent) -> None:
        if event.path_status != "KNOWN" and not self.config.emit_unknown_process_paths:
            return

        pe_info: Dict[str, Any] = {
            "status": "SKIPPED_UNKNOWN_PATH",
            "is_pe": None,
            "reason": event.reason_code,
        }
        obs_hash: Optional[str] = None
        if event.target_path and os.path.isfile(event.target_path):
            probe = probe_pe_file(event.target_path)
            pe_info = probe.to_dict()
            if probe.is_pe and self.config.compute_observation_hash_for_dedup:
                obs_hash = observation_sha256(event.target_path)

        dedup_key = f"PROC:{event.pid}:{event.process_start_time_epoch}"
        if self._is_duplicate(dedup_key):
            with self._metrics_lock:
                self.metrics.events_deduped += 1
            return

        candidate = ScanCandidate(
            candidate_id=new_id("CAND"),
            source_event_id=event.event_id,
            source=event.source,
            created_at_utc=utc_now_iso(),
            target_kind="PROCESS",
            target_ref=build_target_ref(
                "PROCESS",
                target_path=event.target_path,
                pid=event.pid,
                start_time_epoch=event.process_start_time_epoch,
            ),
            pe_probe=pe_info,
            observation_sha256=obs_hash,
            reason=f"{event.event_type}:{event.reason_code}",
            path_status=event.path_status,
            uncertainty_notes=list(event.uncertainty_notes),
            latency_ms=self._calc_latency_ms(event),
        )
        self._enqueue_candidate(candidate)

    def _handle_file_event(self, event: ObservationEvent) -> None:
        in_scope, scope_reason = self._is_in_scope_file(event.target_path)
        if not in_scope:
            with self._metrics_lock:
                self.metrics.filtered_out_of_scope += 1
            return

        path = event.target_path or ""
        probe = probe_pe_file(path)
        attempts = 0
        while (
            probe.status in RETRYABLE_PE_STATUSES
            and attempts < self.config.max_retries
            and not self._stop_event.is_set()
        ):
            attempts += 1
            with self._metrics_lock:
                self.metrics.retry_attempts += 1
            time.sleep(self.config.retry_delay_ms / 1000.0)
            probe = probe_pe_file(path)

        if probe.status in RETRYABLE_PE_STATUSES:
            with self._metrics_lock:
                self.metrics.retry_exhausted += 1

        if not probe.is_pe:
            with self._metrics_lock:
                self.metrics.filtered_non_pe += 1
            return

        obs_hash = (
            observation_sha256(path)
            if self.config.compute_observation_hash_for_dedup
            else None
        )
        dedup_key = f"FILE:{os.path.normcase(os.path.realpath(path))}:{obs_hash or ''}"
        if self._is_duplicate(dedup_key):
            with self._metrics_lock:
                self.metrics.events_deduped += 1
            return

        candidate = ScanCandidate(
            candidate_id=new_id("CAND"),
            source_event_id=event.event_id,
            source=event.source,
            created_at_utc=utc_now_iso(),
            target_kind="FILE",
            target_ref=build_target_ref("FILE", target_path=path),
            pe_probe=probe.to_dict(),
            observation_sha256=obs_hash,
            reason=f"{event.event_type}:{probe.status}",
            path_status="KNOWN",
            uncertainty_notes=list(event.uncertainty_notes),
            latency_ms=self._calc_latency_ms(event),
        )
        self._enqueue_candidate(candidate)

    @staticmethod
    def _calc_latency_ms(event: ObservationEvent) -> Optional[float]:
        if event.monotonic_ns <= 0:
            return None
        return round((time.monotonic_ns() - event.monotonic_ns) / 1_000_000.0, 3)

    def _enqueue_candidate(self, candidate: ScanCandidate) -> None:
        try:
            self._queue.put_nowait(candidate)
        except queue.Full:
            with self._metrics_lock:
                self.metrics.dropped_queue_full += 1
            return

        qsize = self._queue.qsize()
        with self._metrics_lock:
            self.metrics.candidates_enqueued += 1
            if qsize > self.metrics.queue_peak:
                self.metrics.queue_peak = qsize

    def _consume_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                self.sink.submit_candidate(item)
                with self._metrics_lock:
                    self.metrics.candidates_delivered += 1
            except Exception:
                with self._metrics_lock:
                    self.metrics.errors += 1
            finally:
                self._queue.task_done()

