"""Minimum context only. Never executes the target; no file-size cap."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import time
import uuid

VERSION = "1.0.1"
SCHEMA = "context-v1"
CHUNK_BYTES = 1024 * 1024
# Windows path stat may expose birth time as ctime while fd stat exposes
# change time. Compare ctime only between observations from the same API.
STAT_CTIME_COMPARABLE = os.name != "nt"


def now():
    return datetime.now(timezone.utc).isoformat()


def facet(value=None, status="SUCCESS", reason=None):
    result = {"status": status, "value": value}
    if reason:
        result["reason"] = reason
    return result


def new_context(target_type, target):
    return {
        "schema_version": SCHEMA,
        "collector_version": VERSION,
        "collection_id": "COL-" + uuid.uuid4().hex,
        "started_at": now(),
        "target_type": target_type,
        "target": target,
        "status": "FAILED",
        "facets": {},
        "errors": [],
        "limitations": [],
        "cancelled": False,
    }


def finish(context, started):
    values = list(context["facets"].values())
    successes = sum(f["status"] == "SUCCESS" for f in values)
    problems = any(f["status"] in {"FAILED", "UNAVAILABLE", "DEGRADED"} for f in values)
    context["status"] = "FAILED" if not successes else "DEGRADED" if problems or context["errors"] else "SUCCESS"
    context["finished_at"] = now()
    context["runtime_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return context


def identity(info):
    fields = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return fields + (info.st_ctime_ns,) if STAT_CTIME_COMPARABLE else fields


def same_observation(before, after):
    """Compare two path stats OR two fd stats, including their change time."""
    return identity(before) == identity(after) and before.st_ctime_ns == after.st_ctime_ns


def iso_time(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def metadata(path, info):
    created = getattr(info, "st_birthtime", None)
    if created is None and os.name == "nt":
        created = info.st_ctime
    return {
        "path": str(path), "name": path.name, "extension": path.suffix,
        "size_bytes": info.st_size, "modified_at": iso_time(info.st_mtime),
        "created_at": iso_time(created) if created is not None else None,
        "created_at_status": "SUCCESS" if created is not None else "UNAVAILABLE",
    }


def pe_header(handle, file_size):
    """Bounded reads of DOS/COFF/optional header, not full PE validation."""
    handle.seek(0)
    dos = handle.read(64)
    if dos[:2] != b"MZ":
        return facet({"is_pe": False})
    if len(dos) != 64:
        return facet(status="FAILED", reason="truncated_dos_header")
    pe_offset = struct.unpack_from("<I", dos, 60)[0]
    if pe_offset < 64 or pe_offset + 24 > file_size:
        return facet(status="FAILED", reason="invalid_pe_header_offset")
    handle.seek(pe_offset)
    coff = handle.read(24)
    if len(coff) != 24 or coff[:4] != b"PE\0\0":
        return facet(status="FAILED", reason="invalid_pe_signature")
    machine, sections, _, _, _, optional_size, characteristics = struct.unpack_from("<HHIIIHH", coff, 4)
    header_end = pe_offset + 24 + optional_size
    if header_end + sections * 40 > file_size or optional_size < 2:
        return facet(status="FAILED", reason="truncated_pe_headers")
    optional_magic_bytes = handle.read(2)
    if len(optional_magic_bytes) != 2:
        return facet(status="FAILED", reason="truncated_optional_header")
    magic = struct.unpack("<H", optional_magic_bytes)[0]
    minimum = {0x10B: 96, 0x20B: 112}.get(magic)
    if minimum is None or optional_size < minimum:
        return facet(status="FAILED", reason="unsupported_or_truncated_optional_header")
    architecture = {0x14C: "x86", 0x8664: "x64", 0xAA64: "ARM64", 0x1C4: "ARMNT"}.get(machine)
    return facet({
        "is_pe": True, "pe_kind": "PE32+" if magic == 0x20B else "PE32",
        "architecture": architecture, "machine_code": machine,
        "is_dll": bool(characteristics & 0x2000),
        "executable_image_flag": bool(characteristics & 0x0002),
        "classification": "DLL" if characteristics & 0x2000 else "PE_IMAGE",
        "coverage_scope": "DOS_COFF_optional_header_minimum",
    })


def hash_stream(handle, total, progress=False):
    handle.seek(0)
    digest = hashlib.sha256()
    read_count = 0
    last_update = 0.0
    while True:
        block = handle.read(CHUNK_BYTES)
        if not block:
            break
        digest.update(block)
        read_count += len(block)
        current = time.monotonic()
        if progress and current - last_update >= 0.5:
            print(f"Hash: {read_count:,} / {total:,} bytes (Ctrl+C to cancel)", file=sys.stderr)
            last_update = current
    if progress:
        print(f"Hash complete: {read_count:,} bytes", file=sys.stderr)
    return digest.hexdigest()


def collect_file_context(file_path, progress=False):
    started = time.perf_counter()
    path = Path(os.path.abspath(os.path.expanduser(os.fspath(file_path))))
    context = new_context("FILE", {"path": str(path)})
    context["limitations"] = [
        "PE detection checks minimum headers only; it is not full validation or a Win10/11 compatibility test.",
        "Target is not executed; no signature trust, imports, entropy, malware score or verdict is collected.",
        "Change checks are best effort, not an immutable filesystem snapshot.",
    ]
    try:
        initial = path.lstat()
        is_reparse = bool(getattr(initial, "st_file_attributes", 0) & 0x400)
        if stat.S_ISLNK(initial.st_mode) or is_reparse:
            context["facets"]["readable"] = facet(status="UNAVAILABLE", reason="symlink_or_reparse_point_not_followed")
            return finish(context, started)
        if not stat.S_ISREG(initial.st_mode):
            context["facets"]["readable"] = facet(status="UNAVAILABLE", reason="not_a_regular_file")
            return finish(context, started)
        context["facets"]["metadata"] = facet(metadata(path, initial))
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or identity(before) != identity(initial):
                context["facets"]["readable"] = facet(status="UNAVAILABLE", reason="file_changed_before_open")
                return finish(context, started)
            context["facets"]["readable"] = facet(True)
            try:
                context["facets"]["pe_header"] = pe_header(handle, before.st_size)
            except OSError as exc:
                context["facets"]["pe_header"] = facet(status="FAILED", reason=str(exc))
            try:
                digest = hash_stream(handle, before.st_size, progress)
                after = os.fstat(handle.fileno())
                current_path = path.lstat()
                unchanged = (
                    same_observation(before, after)
                    and same_observation(initial, current_path)
                    and identity(after) == identity(current_path)
                )
                context["facets"]["file_unchanged_during_collection"] = facet(unchanged)
                if unchanged:
                    context["facets"]["sha256"] = facet(digest)
                else:
                    context["facets"]["sha256"] = facet(status="UNAVAILABLE", reason="file_changed_during_collection")
                    context["facets"]["pe_header"] = facet(status="UNAVAILABLE", reason="file_changed_during_collection")
                    context["limitations"].append("Metadata describes the initial observation; target changed during collection.")
            except KeyboardInterrupt:
                context["cancelled"] = True
                context["facets"]["sha256"] = facet(status="FAILED", reason="cancelled_by_user_no_complete_hash")
            except OSError as exc:
                context["facets"]["sha256"] = facet(status="UNAVAILABLE", reason=str(exc))
    except OSError as exc:
        context["facets"]["readable"] = facet(status="UNAVAILABLE", reason=type(exc).__name__)
        context["errors"].append({"code": type(exc).__name__, "message": str(exc)})
    except KeyboardInterrupt:
        context["cancelled"] = True
        context["errors"].append({"code": "cancelled", "message": "Collection interrupted; only completed observations retained."})
    return finish(context, started)


def collect_process_context(pid, progress=False):
    started = time.perf_counter()
    context = new_context("PROCESS", {"pid": pid})
    try:
        import psutil
    except ImportError:
        context["errors"].append({"code": "missing_dependency", "message": "Install requirements.txt for PID support."})
        return finish(context, started)
    context["limitations"] = [
        "Process metadata only; no memory, modules, network or registry inspection.",
        "Executable backing file hash does not identify process memory or prove the loaded bytes match disk.",
    ]
    try:
        process = psutil.Process(pid)
        start_time = process.create_time()
        context["target"]["start_time_epoch"] = start_time
        context["facets"]["start_time"] = facet(iso_time(start_time))
        for key, method in [("name", process.name), ("executable_path", process.exe), ("parent_pid", process.ppid), ("user", process.username), ("running", process.is_running)]:
            try:
                value = method()
                context["facets"][key] = facet(value) if value is not None and value != "" else facet(status="UNAVAILABLE", reason="not_provided")
            except psutil.AccessDenied:
                context["facets"][key] = facet(status="UNAVAILABLE", reason="access_denied")
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                context["facets"][key] = facet(status="UNAVAILABLE", reason="process_exited")
        try:
            if os.name == "nt":
                import ctypes
                session = ctypes.c_ulong()
                if not ctypes.windll.kernel32.ProcessIdToSessionId(pid, ctypes.byref(session)):
                    raise OSError("ProcessIdToSessionId failed")
                session_id = session.value
            else:
                session_id = os.getsid(pid)
            context["facets"]["session_id"] = facet(session_id)
        except OSError as exc:
            context["facets"]["session_id"] = facet(status="UNAVAILABLE", reason=str(exc))
        executable = context["facets"].get("executable_path", {})
        if executable.get("status") == "SUCCESS":
            backing_file = collect_file_context(executable["value"], progress)
            context["backing_file_context"] = backing_file
            if backing_file["status"] != "SUCCESS":
                context["facets"]["backing_file_collection"] = facet(status="DEGRADED", reason="see_backing_file_context")
            else:
                context["facets"]["backing_file_collection"] = facet(backing_file["collection_id"])
            context["cancelled"] = backing_file["cancelled"]
        try:
            stable = process.is_running() and psutil.Process(pid).create_time() == start_time
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            stable = False
        context["facets"]["process_identity_still_present"] = facet(stable) if stable else facet(status="UNAVAILABLE", reason="process_exited_or_pid_reused")
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        context["errors"].append({"code": "process_not_found", "message": "PID no longer exists; no process identity established."})
    except psutil.AccessDenied:
        context["errors"].append({"code": "access_denied", "message": "Cannot establish process identity/start time."})
    except KeyboardInterrupt:
        context["cancelled"] = True
        context["errors"].append({"code": "cancelled", "message": "Collection interrupted."})
    except OSError as exc:
        context["errors"].append({"code": type(exc).__name__, "message": str(exc)})
    return finish(context, started)


def save_context(context, output):
    """Each run gets a unique directory; no silent history overwrite."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    run_directory = output / context["collection_id"]
    run_directory.mkdir(exist_ok=False)
    path = run_directory / "context.json"
    fd, temporary = tempfile.mkstemp(prefix=".context-", suffix=".tmp", dir=run_directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(context, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--file", type=Path)
    target.add_argument("--pid", type=int)
    parser.add_argument("--output", type=Path, default=Path("collections"), help="Output directory; unique subdirectory per collection")
    parser.add_argument("--progress", action="store_true", help="Hash progress on stderr; Ctrl+C cancels with best-effort result saving")
    args = parser.parse_args(argv)
    if args.pid is not None and args.pid <= 0:
        parser.error("PID must be positive")
    context = collect_file_context(args.file, args.progress) if args.file is not None else collect_process_context(args.pid, args.progress)
    try:
        saved = save_context(context, args.output)
    except OSError as exc:
        print(f"Cannot save context: {exc}", file=sys.stderr)
        return 3
    print(json.dumps({"status": context["status"], "collection_id": context["collection_id"], "context_path": str(saved.resolve())}, ensure_ascii=False, indent=2))
    return 130 if context["cancelled"] else 1 if context["status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
