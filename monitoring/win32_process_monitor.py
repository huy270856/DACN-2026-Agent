"""Win32 Toolhelp32 process creation monitor (user-mode, zero external deps).

Notes:
- Post-execution observation only (not pre-execution prevention).
- Uses (pid, start_time_epoch) to mitigate PID reuse.
- Does NOT collect command line, username, or sensitive environment data.
- Represents inaccessible image paths explicitly as path_status='UNKNOWN'.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import threading
import time
from typing import Callable, Dict, Optional, Set, Tuple

from monitoring.schemas import ObservationEvent, new_id, utc_now_iso

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_PATH = 260
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
WINDOWS_TO_UNIX_EPOCH_100NS = 116444736000000000


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


def _filetime_to_epoch(ft: FILETIME) -> float:
    ticks = (ft.dwHighDateTime << 32) | ft.dwLowDateTime
    return (ticks - WINDOWS_TO_UNIX_EPOCH_100NS) / 10_000_000.0


class Win32ProcessMonitor:
    """Polls Toolhelp32 process snapshots and emits PROCESS_CREATED events."""

    def __init__(
        self,
        on_event: Callable[[ObservationEvent], None],
        poll_interval_ms: int = 100,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        if os.name != "nt":
            raise RuntimeError("Win32ProcessMonitor is only supported on Windows")
        self._on_event = on_event
        self._poll_interval = max(0.02, poll_interval_ms / 1000.0)
        self._on_error = on_error
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Track (pid, start_time_epoch_rounded) to mitigate PID reuse.
        self._seen: Set[Tuple[int, Optional[int]]] = set()
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._setup_win32_sigs()

    def _setup_win32_sigs(self) -> None:
        k32 = self._kernel32
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.restype = wintypes.BOOL
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.Process32NextW.restype = wintypes.BOOL
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.GetProcessTimes.restype = wintypes.BOOL
        k32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
        ]
        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        k32.CloseHandle.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

    def _snapshot_pids(self) -> Dict[int, Optional[str]]:
        snap = self._kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == INVALID_HANDLE_VALUE or snap is None:
            raise OSError(f"CreateToolhelp32Snapshot failed: {ctypes.get_last_error()}")
        pids: Dict[int, Optional[str]] = {}
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if self._kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                while True:
                    pids[int(entry.th32ProcessID)] = None
                    if not self._kernel32.Process32NextW(snap, ctypes.byref(entry)):
                        break
        finally:
            self._kernel32.CloseHandle(snap)
        return pids

    def _query_process_identity(
        self, pid: int
    ) -> Tuple[Optional[float], Optional[str], str, str]:
        """Return (start_time_epoch, full_path, path_status, reason_code)."""
        if pid in (0, 4):
            return None, None, "UNKNOWN", "SYSTEM_PSEUDO_PID"
        handle = self._kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            reason = "ACCESS_DENIED" if err == 5 else "PROCESS_EXITED_OR_UNAVAILABLE"
            return None, None, "UNKNOWN", reason

        try:
            c_ft, e_ft, k_ft, u_ft = FILETIME(), FILETIME(), FILETIME(), FILETIME()
            start_epoch: Optional[float] = None
            if self._kernel32.GetProcessTimes(
                handle,
                ctypes.byref(c_ft),
                ctypes.byref(e_ft),
                ctypes.byref(k_ft),
                ctypes.byref(u_ft),
            ):
                start_epoch = round(_filetime_to_epoch(c_ft), 6)

            buf_len = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(buf_len.value)
            if self._kernel32.QueryFullProcessImageNameW(
                handle, 0, buf, ctypes.byref(buf_len)
            ):
                return start_epoch, buf.value, "KNOWN", "NEW_PROCESS"
            return start_epoch, None, "UNKNOWN", "IMAGE_PATH_UNAVAILABLE"
        finally:
            self._kernel32.CloseHandle(handle)

    def baseline(self) -> None:
        """Record currently running processes so only new creations are emitted."""
        current: Set[Tuple[int, Optional[int]]] = set()
        for pid in self._snapshot_pids():
            start_epoch, _, _, _ = self._query_process_identity(pid)
            key = (pid, int(start_epoch * 1000) if start_epoch is not None else None)
            current.add(key)
        self._seen = current

    def poll_once(self) -> int:
        """Run one snapshot diff cycle; returns number of new process events emitted."""
        emitted = 0
        current_seen: Set[Tuple[int, Optional[int]]] = set()
        for pid in self._snapshot_pids():
            start_epoch, full_path, path_status, reason_code = self._query_process_identity(pid)
            key = (pid, int(start_epoch * 1000) if start_epoch is not None else None)
            current_seen.add(key)
            if key not in self._seen:
                notes = []
                if path_status != "KNOWN":
                    notes.append(f"process_path_unknown:{reason_code}")
                if start_epoch is None:
                    notes.append("process_start_time_unavailable")
                evt = ObservationEvent(
                    event_id=new_id("EVT"),
                    source="process_monitor",
                    event_type="PROCESS_CREATED",
                    timestamp_utc=utc_now_iso(),
                    target_kind="PROCESS",
                    target_path=full_path,
                    pid=pid,
                    process_start_time_epoch=start_epoch,
                    path_status=path_status,
                    reason_code=reason_code,
                    uncertainty_notes=notes,
                    monotonic_ns=time.monotonic_ns(),
                )
                self._on_event(evt)
                emitted += 1
        self._seen = current_seen
        return emitted

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self.baseline()
        self._thread = threading.Thread(
            target=self._loop, name="win32-process-monitor", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # pragma: no cover
                if self._on_error:
                    self._on_error(f"process_poll_error:{exc}")
            self._stop_event.wait(self._poll_interval)

