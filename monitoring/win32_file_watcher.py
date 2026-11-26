"""Win32 ReadDirectoryChangesW file watcher (user-mode, zero external deps)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import struct
import threading
import time
from typing import Callable, Iterable, List, Optional

from monitoring.schemas import ObservationEvent, new_id, utc_now_iso

FILE_LIST_DIRECTORY = 0x0001
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010
FILE_NOTIFY_CHANGE_CREATION = 0x00000040

FILE_ACTION_ADDED = 0x00000001
FILE_ACTION_MODIFIED = 0x00000003
FILE_ACTION_RENAMED_NEW_NAME = 0x00000005

ERROR_OPERATION_ABORTED = 995
ERROR_NOTIFY_ENUM_DIR = 1022

_ACTION_MAP = {
    FILE_ACTION_ADDED: ("FILE_CREATED", "NEW_FILE"),
    FILE_ACTION_MODIFIED: ("FILE_MODIFIED", "MODIFIED_FILE"),
    FILE_ACTION_RENAMED_NEW_NAME: ("FILE_RENAMED", "RENAMED_FILE"),
}


def is_drive_root(path: str) -> bool:
    norm = os.path.normpath(os.path.abspath(path))
    drive, tail = os.path.splitdrive(norm)
    return tail in ("\\", "/", "")


def is_subpath(path: str, parent: str) -> bool:
    try:
        real_p = os.path.normcase(os.path.realpath(path))
        real_parent = os.path.normcase(os.path.realpath(parent))
        return os.path.commonpath([real_p, real_parent]) == real_parent
    except (ValueError, OSError):
        return False


def validate_watch_dirs(
    watch_dirs: Iterable[str],
    exclude_dirs: Iterable[str],
    allow_drive_root: bool = False,
) -> List[str]:
    """Validate configured watch directories; reject drive roots by default."""
    validated: List[str] = []
    excludes = [os.path.realpath(d) for d in exclude_dirs]
    for raw in watch_dirs:
        if not raw:
            continue
        abs_dir = os.path.abspath(raw)
        if not allow_drive_root and is_drive_root(abs_dir):
            raise ValueError(f"Refusing to watch drive root without explicit opt-in: {abs_dir}")
        if not os.path.isdir(abs_dir):
            raise FileNotFoundError(f"Watch directory does not exist: {abs_dir}")
        real_dir = os.path.realpath(abs_dir)
        if any(is_subpath(real_dir, ex) for ex in excludes):
            raise ValueError(f"Watch directory overlaps exclude_dirs: {real_dir}")
        validated.append(real_dir)
    if not validated:
        raise ValueError("At least one valid watch directory must be configured")
    return validated


class Win32FileWatcher:
    """Watches configured lab directories using Win32 ReadDirectoryChangesW."""

    def __init__(
        self,
        watch_dirs: List[str],
        exclude_dirs: List[str],
        on_event: Callable[[ObservationEvent], None],
        on_overflow: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        recursive: bool = True,
        buffer_bytes: int = 65536,
        allow_drive_root: bool = False,
    ) -> None:
        if os.name != "nt":
            raise RuntimeError("Win32FileWatcher is only supported on Windows")
        self._excludes = [os.path.realpath(d) for d in exclude_dirs]
        self._watch_dirs = validate_watch_dirs(
            watch_dirs, self._excludes, allow_drive_root=allow_drive_root
        )
        self._on_event = on_event
        self._on_overflow = on_overflow
        self._on_error = on_error
        self._recursive = recursive
        self._buffer_bytes = buffer_bytes
        self._stop_event = threading.Event()
        self._threads: List[threading.Thread] = []
        self._handles: List[int] = []
        self._handles_lock = threading.Lock()
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._setup_win32_sigs()

    def _setup_win32_sigs(self) -> None:
        k32 = self._kernel32
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        k32.ReadDirectoryChangesW.restype = wintypes.BOOL
        k32.ReadDirectoryChangesW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
            wintypes.LPVOID,
        ]
        k32.CancelIoEx.restype = wintypes.BOOL
        k32.CancelIoEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
        k32.CloseHandle.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

    def start(self) -> None:
        if self._threads:
            return
        self._stop_event.clear()
        for watch_dir in self._watch_dirs:
            t = threading.Thread(
                target=self._watch_loop,
                args=(watch_dir,),
                name=f"win32-file-watcher-{os.path.basename(watch_dir)}",
                daemon=True,
            )
            self._threads.append(t)
            t.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop_event.set()
        with self._handles_lock:
            for handle in self._handles:
                self._kernel32.CancelIoEx(handle, None)
                self._kernel32.CloseHandle(handle)
            self._handles.clear()
        for t in self._threads:
            t.join(timeout=timeout)
        self._threads.clear()

    def _is_excluded(self, full_path: str) -> bool:
        return any(is_subpath(full_path, ex) for ex in self._excludes)

    def _watch_loop(self, watch_dir: str) -> None:
        handle = self._kernel32.CreateFileW(
            watch_dir,
            FILE_LIST_DIRECTORY,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle == INVALID_HANDLE_VALUE or handle is None:
            err = ctypes.get_last_error()
            if self._on_error:
                self._on_error(f"CreateFileW failed for {watch_dir}: winerror={err}")
            return

        with self._handles_lock:
            self._handles.append(handle)

        buf = ctypes.create_string_buffer(self._buffer_bytes)
        bytes_returned = wintypes.DWORD(0)
        notify_filter = (
            FILE_NOTIFY_CHANGE_FILE_NAME
            | FILE_NOTIFY_CHANGE_LAST_WRITE
            | FILE_NOTIFY_CHANGE_CREATION
        )

        try:
            while not self._stop_event.is_set():
                ok = self._kernel32.ReadDirectoryChangesW(
                    handle,
                    buf,
                    self._buffer_bytes,
                    self._recursive,
                    notify_filter,
                    ctypes.byref(bytes_returned),
                    None,
                    None,
                )
                if not ok:
                    err = ctypes.get_last_error()
                    if self._stop_event.is_set() or err == ERROR_OPERATION_ABORTED:
                        break
                    if err == ERROR_NOTIFY_ENUM_DIR:
                        if self._on_overflow:
                            self._on_overflow(watch_dir)
                        continue
                    if self._on_error:
                        self._on_error(f"ReadDirectoryChangesW error={err} on {watch_dir}")
                    break

                nbytes = bytes_returned.value
                if nbytes == 0:
                    if self._on_overflow:
                        self._on_overflow(watch_dir)
                    continue

                self._parse_notifications(watch_dir, buf.raw[:nbytes])
        finally:
            with self._handles_lock:
                if handle in self._handles:
                    self._handles.remove(handle)
                    self._kernel32.CloseHandle(handle)

    def _parse_notifications(self, watch_dir: str, raw: bytes) -> None:
        offset = 0
        while offset + 12 <= len(raw):
            next_entry_offset, action, name_len = struct.unpack_from("<III", raw, offset)
            name_start = offset + 12
            name_end = name_start + name_len
            if name_end > len(raw):
                break
            rel_name = raw[name_start:name_end].decode("utf-16-le", errors="replace")
            if action in _ACTION_MAP:
                event_type, reason_code = _ACTION_MAP[action]
                full_path = os.path.join(watch_dir, rel_name)
                if not os.path.isdir(full_path) and not self._is_excluded(full_path):
                    evt = ObservationEvent(
                        event_id=new_id("EVT"),
                        source="file_watcher",
                        event_type=event_type,
                        timestamp_utc=utc_now_iso(),
                        target_kind="FILE",
                        target_path=full_path,
                        path_status="KNOWN",
                        reason_code=reason_code,
                        monotonic_ns=time.monotonic_ns(),
                    )
                    self._on_event(evt)
            if next_entry_offset == 0:
                break
            offset += next_entry_offset

