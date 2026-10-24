"""D6: bounded trusted-adapter execution on Windows, with Job Object ownership.

This is NOT a malware sandbox. The gated worker runs only trusted adapter argv.
It waits for admission into the job before creating any adapter descendants.
All provider output remains untrusted bytes for D7; no parsing into observations.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


@dataclass(frozen=True)
class ControlResult:
    outcome: str
    error_code: str | None
    exit_code: int | None
    output_bytes: int
    duration_ms: int
    cleanup_status: str
    remaining_owned_resources: tuple[str, ...]
    stream_sha256: tuple[tuple[str, str], ...] = ()


class WindowsJob:
    """Unnamed, non-inheritable job; no breakaway permission is granted."""

    def __init__(self):
        if os.name != 'nt':
            raise OSError('Windows Job Objects required; no weaker fallback')
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
            'SetInformationJobObject': ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
            'AssignProcessToJobObject': ([w.HANDLE, w.HANDLE], w.BOOL),
            'TerminateJobObject': ([w.HANDLE, w.UINT], w.BOOL),
            'QueryInformationJobObject': ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
            'CloseHandle': ([w.HANDLE], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result

        class BasicLimits(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                        ('flags', w.DWORD), ('min_ws', ctypes.c_size_t),
                        ('max_ws', ctypes.c_size_t), ('active_limit', w.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('basic', BasicLimits), ('io', IO), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]

        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def active_count(self):
        class Accounting(ctypes.Structure):
            _fields_ = [('user', ctypes.c_longlong), ('kernel', ctypes.c_longlong),
                        ('period_user', ctypes.c_longlong), ('period_kernel', ctypes.c_longlong),
                        ('faults', w.DWORD), ('total', w.DWORD), ('active', w.DWORD), ('terminated', w.DWORD)]
        info = Accounting()
        if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return info.active

    def cleanup(self, grace_seconds=3.0):
        # Terminate even on normal parent exit: descendants may still be running.
        if self.active_count() and not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())
        end = time.monotonic() + grace_seconds
        while self.active_count():
            if time.monotonic() >= end:
                return False
            time.sleep(0.01)
        return True

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def clean_environment(workdir: Path):
    """Do not pass parent tokens, PYTHONPATH, PATH or signing secrets to adapters."""
    env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR') if k in os.environ}
    env.update(TEMP=str(workdir), TMP=str(workdir), PYTHONIOENCODING='utf-8')
    return env


class ExecutionControl:
    """One controlled run. Caller supplies absolute trusted argv and private cwd.

    Captured stdout+stderr share one cap (also limited by artifact budget).
    Direct adapter filesystem writes are not sandboxed; only trusted read-only
    adapters belong here. A VM backend must implement its own isolation gate.
    """

    def run(self, argv: list[str], workdir: Path, *, timeout_ms: int,
            max_output_bytes: int, max_artifact_bytes: int,
            cancel: threading.Event | None = None) -> ControlResult:
        if any(type(n) is not int or n <= 0 for n in (timeout_ms, max_output_bytes, max_artifact_bytes)):
            raise ValueError('Positive integer limits required')
        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError('Absolute trusted executable required')
        if os.name != 'nt':
            raise OSError('Windows-only execution backend')
        workdir = Path(workdir)
        cap = min(max_output_bytes, max_artifact_bytes)
        started = time.monotonic()
        cancel = cancel if cancel is not None else threading.Event()
        outcome, error, exit_code = 'FAILED', None, None
        count = 0
        lock = threading.Lock()
        overflow, reader_error = threading.Event(), threading.Event()
        process, job = None, None
        readers = []
        remaining = []
        stream_hashes = {}
        cleanup = 'NOT_REQUIRED'

        def drain(pipe, path):
            nonlocal count
            checksum = hashlib.sha256()
            try:
                with path.open('xb', buffering=0) as output:
                    while block := pipe.read(4096):
                        with lock:
                            keep = block[:max(0, cap - count)]
                            output.write(keep)
                            checksum.update(keep)
                            count += len(keep)
                            if len(keep) != len(block):
                                overflow.set()
            except OSError:
                reader_error.set()
            finally:
                with lock:
                    stream_hashes[path.name] = checksum.hexdigest()
                pipe.close()

        try:
            if cancel.is_set():
                return ControlResult('CANCELLED', 'CANCELLED', None, 0, 0, 'NOT_REQUIRED', ())
            job = WindowsJob()
            # Use the real interpreter, not a venv launcher that could fork before assignment.
            worker_python = getattr(sys, '_base_executable', sys.executable)
            process = subprocess.Popen(
                [worker_python, '-I', str(Path(__file__).resolve()), '--gated-worker'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=workdir, env=clean_environment(workdir), shell=False, close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW, bufsize=0)
            job.assign(process)
            for name, pipe in [('stdout.bin', process.stdout), ('stderr.bin', process.stderr)]:
                thread = threading.Thread(target=drain, args=(pipe, workdir / name), daemon=True)
                thread.start()
                readers.append(thread)
            payload = json.dumps(argv, ensure_ascii=True).encode('ascii')
            if len(payload) > 24000:
                raise ValueError('Adapter argv exceeds control-message limit')
            process.stdin.write(payload)
            process.stdin.close()  # Release the worker ONLY after successful job assignment.
            while True:
                if cancel.is_set():
                    outcome, error = 'CANCELLED', 'CANCELLED'
                    break
                if overflow.is_set():
                    outcome, error = 'FAILED', 'BUDGET_EXCEEDED'
                    break
                if reader_error.is_set():
                    outcome, error = 'FAILED', 'INTERNAL_ERROR'
                    break
                exit_code = process.poll()
                if exit_code is not None:
                    outcome = 'SUCCESS' if exit_code == 0 else 'FAILED'
                    error = None if exit_code == 0 else 'PROVIDER_FAILED'
                    break
                if (time.monotonic() - started) * 1000 >= timeout_ms:
                    outcome, error = 'TIMEOUT', 'TIMEOUT'
                    break
                time.sleep(0.01)
        except (OSError, ValueError):
            outcome, error = 'FAILED', 'PROVIDER_UNAVAILABLE'
        except BaseException:
            # Cleanup must happen for KeyboardInterrupt and other caller interruptions too.
            outcome, error = 'CANCELLED', 'CANCELLED'
            raise
        finally:
            if process is not None:
                cleanup = 'COMPLETE'
                try:
                    if job is not None and not job.cleanup():
                        remaining.append('job_processes')
                except OSError:
                    remaining.append('job_cleanup_unverified')
                if job is not None:
                    job.close()
                    job = None
                try:
                    if process.poll() is None:
                        process.kill()  # Also handles assignment failure; gate was never released.
                    process.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    remaining.append('worker_process')
                for thread in readers:
                    thread.join(timeout=3)
                    if thread.is_alive():
                        remaining.append('output_reader')
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe and not pipe.closed and 'output_reader' not in remaining:
                        pipe.close()
                if remaining:
                    cleanup = 'INCOMPLETE'
            if job is not None:
                job.close()
        if overflow.is_set() and outcome not in ('CANCELLED', 'TIMEOUT'):
            outcome, error = 'FAILED', 'BUDGET_EXCEEDED'
        if reader_error.is_set():
            outcome, error = 'FAILED', 'INTERNAL_ERROR'
        if cleanup == 'INCOMPLETE' and outcome == 'SUCCESS':
            outcome, error = 'FAILED', 'CLEANUP_INCOMPLETE'
        return ControlResult(outcome, error, exit_code, count,
                             round((time.monotonic() - started) * 1000), cleanup, tuple(remaining),
                             tuple(sorted(stream_hashes.items())))


class VMResetGate:
    """Interface state only, NOT a VM adapter or evidence of real isolation.

    A failed reset blocks reuse until the trusted owner verifies a new reset.
    No host fallback exists; booleans are trusted-backend inputs, not proof.
    """
    def __init__(self):
        self._ready = False

    @property
    def ready(self):
        return self._ready

    def begin(self, *, isolation_verified: bool, snapshot_verified: bool):
        if not self._ready or not isolation_verified or not snapshot_verified:
            raise RuntimeError('VM unavailable or reset/isolation not verified')
        self._ready = False

    def record_reset(self, *, verified: bool):
        self._ready = verified is True


def _gated_worker():
    # Trusted bootstrap: no descendants or provider imports before parent closes stdin.
    payload = sys.stdin.buffer.read(24001)
    if not payload or len(payload) > 24000:
        return 125
    argv = json.loads(payload)
    if not isinstance(argv, list) or not argv or not all(isinstance(s, str) for s in argv):
        return 125
    try:
        return subprocess.call(argv, stdin=subprocess.DEVNULL, shell=False, close_fds=True)
    except OSError:
        return 126


if __name__ == '__main__':
    if sys.argv[1:] != ['--gated-worker']:
        raise SystemExit('Internal worker only')
    raise SystemExit(_gated_worker())
