"""CLI demo and benchmark harness for TASK 09C monitoring module."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
import statistics
import struct
import tempfile
import time
from typing import Dict, List, Tuple

from monitoring.pipeline import MockNodeBIntake, MonitoringPipeline
from monitoring.schemas import MonitorConfig


def make_minimal_pe_bytes(payload: bytes = b"BENIGN_LAB_FIXTURE") -> bytes:
    """Create a minimal valid 64-byte DOS + PE32+ header in memory (benign fixture)."""
    dos = bytearray(64)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 64)  # e_lfanew = 64
    pe_header = bytearray(24)
    pe_header[0:4] = b"PE\x00\x00"
    struct.pack_into("<H", pe_header, 4, 0x8664)  # IMAGE_FILE_MACHINE_AMD64
    return bytes(dos) + bytes(pe_header) + payload


def _win32_process_memory_mb() -> Tuple[float, float]:
    """Return (current_rss_mb, peak_rss_mb) using Win32 psapi/kernel32."""
    if os.name != "nt":
        return 0.0, 0.0

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
    k32.K32GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        wintypes.DWORD,
    ]
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    handle = k32.GetCurrentProcess()
    if k32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        mib = 1024 * 1024
        return (
            round(counters.WorkingSetSize / mib, 2),
            round(counters.PeakWorkingSetSize / mib, 2),
        )
    return 0.0, 0.0


def run_benchmark(
    num_files: int = 100,
    queue_maxsize: int = 256,
    debounce_ms: int = 10,
) -> Dict[str, object]:
    """Run a controlled lab benchmark creating benign PE fixtures."""
    with tempfile.TemporaryDirectory(prefix="task09c_bench_") as tmpdir:
        watch_dir = os.path.join(tmpdir, "watch")
        exclude_dir = os.path.join(tmpdir, "quarantine_mock")
        os.makedirs(watch_dir, exist_ok=True)
        os.makedirs(exclude_dir, exist_ok=True)

        sink = MockNodeBIntake()
        cfg = MonitorConfig(
            watch_dirs=[watch_dir],
            exclude_dirs=[exclude_dir],
            enable_file_watcher=True,
            enable_process_monitor=False,
            debounce_ms=debounce_ms,
            queue_maxsize=queue_maxsize,
            dedup_ttl_seconds=5.0,
        )
        pipeline = MonitoringPipeline(cfg, sink=sink)
        pipeline.start()
        time.sleep(0.1)

        cpu_start = time.process_time()
        wall_start = time.perf_counter()

        for idx in range(num_files):
            fpath = os.path.join(watch_dir, f"benign_{idx:04d}.exe")
            with open(fpath, "wb") as handle:
                handle.write(make_minimal_pe_bytes(f"FIXTURE_{idx}".encode()))

        # Allow watcher + debounce + consumer to settle
        deadline = time.perf_counter() + 5.0
        while time.perf_counter() < deadline:
            if len(sink.snapshot()) >= num_files:
                break
            time.sleep(0.02)
        pipeline.flush(timeout=3.0)

        wall_ms = round((time.perf_counter() - wall_start) * 1000.0, 2)
        cpu_ms = round((time.process_time() - cpu_start) * 1000.0, 2)
        rss_mb, peak_rss_mb = _win32_process_memory_mb()

        pipeline.stop()
        delivered = sink.snapshot()
        latencies: List[float] = [
            c.latency_ms for c in delivered if c.latency_ms is not None
        ]
        latencies_sorted = sorted(latencies)
        median_ms = round(statistics.median(latencies_sorted), 3) if latencies_sorted else None
        p95_idx = int(0.95 * (len(latencies_sorted) - 1)) if latencies_sorted else 0
        p95_ms = round(latencies_sorted[p95_idx], 3) if latencies_sorted else None

        return {
            "workload": {
                "num_benign_pe_files": num_files,
                "queue_maxsize": queue_maxsize,
                "debounce_ms": debounce_ms,
            },
            "metrics": pipeline.metrics.to_dict(),
            "latency_ms": {
                "samples": len(latencies_sorted),
                "median": median_ms,
                "p95": p95_ms,
            },
            "resources": {
                "wall_time_ms": wall_ms,
                "cpu_time_ms": cpu_ms,
                "rss_mb": rss_mb,
                "peak_rss_mb": peak_rss_mb,
            },
        }


def run_watch_demo(
    watch_dir: str,
    exclude_dirs: List[str],
    duration_sec: float,
    enable_process: bool,
) -> Dict[str, object]:
    sink = MockNodeBIntake()
    cfg = MonitorConfig(
        watch_dirs=[watch_dir],
        exclude_dirs=exclude_dirs,
        enable_file_watcher=True,
        enable_process_monitor=enable_process,
    )
    pipeline = MonitoringPipeline(cfg, sink=sink)
    pipeline.start()
    try:
        time.sleep(max(0.1, duration_sec))
        pipeline.flush(timeout=1.0)
    finally:
        pipeline.stop()
    return {
        "metrics": pipeline.metrics.to_dict(),
        "candidates": [c.to_dict() for c in sink.snapshot()],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="TASK 09C File & Process Monitoring CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    bench_p = sub.add_parser("benchmark", help="Run lab PE creation benchmark")
    bench_p.add_argument("--num-files", type=int, default=100)
    bench_p.add_argument("--queue-maxsize", type=int, default=256)
    bench_p.add_argument("--debounce-ms", type=int, default=10)

    watch_p = sub.add_parser("watch", help="Watch a lab directory for a bounded duration")
    watch_p.add_argument("--dir", required=True, help="Lab directory to watch")
    watch_p.add_argument("--exclude", action="append", default=[], help="Excluded directories")
    watch_p.add_argument("--duration", type=float, default=3.0)
    watch_p.add_argument("--process", action="store_true", help="Enable process monitor")

    args = parser.parse_args()
    if args.command == "benchmark":
        result = run_benchmark(
            num_files=args.num_files,
            queue_maxsize=args.queue_maxsize,
            debounce_ms=args.debounce_ms,
        )
        print(json.dumps(result, indent=2))
        return 0

    result = run_watch_demo(
        watch_dir=args.dir,
        exclude_dirs=args.exclude,
        duration_sec=args.duration,
        enable_process=args.process,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
