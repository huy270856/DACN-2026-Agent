"""D5: trusted-backend-only, read-only FILE adapter executor (d0-v1).

No public CLI accepts ALLOW from an Agent. D1 owns authenticated/atomic admission,
D2 owns installed provider configuration, D7 normalizes bytes, D8 signs, D9 commits.
This API checks supplied snapshots but cannot implement those trust boundaries.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import copy
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import time
import uuid

from d0.validate import ContractError, canonical_json_bytes, digest, validate, verify_tool_call
from .execution_control import ExecutionControl


class ExecutionRejected(ValueError):
    """Pre-execution rejection; codes are internal, not ToolResult.error.code."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PinnedAdapter:
    """Installed by trusted D2/backend, NEVER constructed from ToolCall arguments.

    command is fixed executable + adapter prefix, pins are (absolute path, sha256).
    All code-bearing files must be pinned by the installer. Adapter protocol is:
    <command> --target <locked-staged-file> --arguments-json <canonical-object>.
    """
    provider_id: str
    version: str
    adapter_id: str
    command: tuple[str, ...]
    pins: tuple[tuple[str, str], ...]

    def provider(self):
        return {'id': self.provider_id, 'version': self.version,
                'adapter': self.adapter_id, 'runtime': 'subprocess'}


@dataclass(frozen=True)
class ExecutionOutput:
    receipt: dict
    raw_artifacts: tuple[dict, ...]
    error: dict | None
    exit_code: int | None
    run_directory: Path


def now():
    return datetime.now(timezone.utc).isoformat()


def checked_path(value):
    """Reject relative/device/UNC/ADS paths and existing reparse components.

    Artifact/provider directories must additionally be owned/protected by the
    trusted backend. This check does not create Windows ACL isolation.
    """
    path = Path(value)
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')):
        raise ExecutionRejected('TARGET_IDENTITY_UNAVAILABLE', 'Local absolute path required')
    if '..' in path.parts or any(':' in part for part in path.parts[1:]):
        raise ExecutionRejected('TARGET_IDENTITY_UNAVAILABLE', 'Traversal or alternate stream rejected')
    for part in reversed([path, *path.parents]):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ExecutionRejected('TARGET_IDENTITY_UNAVAILABLE', 'Reparse points are not supported')
    return path


@contextmanager
def locked_reader(path):
    """Hold Windows read access WITHOUT write/delete sharing until exit."""
    if os.name != 'nt':
        raise ExecutionRejected('PROVIDER_UNAVAILABLE', 'Windows-only locked-file backend')
    import msvcrt
    path = checked_path(path)
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes, api.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
    handle = api.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        api.CloseHandle(handle)
        raise
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        current = path.lstat()
        if (not stat.S_ISREG(opened.st_mode) or getattr(current, 'st_file_attributes', 0) & 0x400
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)):
            raise ExecutionRejected('TARGET_CHANGED', 'Opened file does not match path identity')
        yield stream


def check_deadline(deadline, cancel):
    if cancel is not None and cancel.is_set():
        raise ExecutionRejected('CANCELLED', 'Cancelled before adapter dispatch')
    if time.monotonic() >= deadline:
        raise ExecutionRejected('TIMEOUT', 'Preparation exceeded the run deadline')


def stream_digest(stream, deadline, cancel, destination=None):
    stream.seek(0)
    checksum = hashlib.sha256()
    while True:
        check_deadline(deadline, cancel)
        block = stream.read(1024 * 1024)
        if not block:
            break
        checksum.update(block)
        if destination is not None:
            destination.write(block)
    return checksum.hexdigest()


class ToolExecutor:
    """Single-flight per instance; D1/D2 enforce cross-instance/global concurrency.

    Only trusted, read-only subprocess adapters on FILE targets are supported.
    All foreign-code, mutation, approval-required and PROCESS calls fail closed.
    """
    def __init__(self, artifact_root: Path, *, control: ExecutionControl | None = None):
        self.root = Path(artifact_root)
        self.root.mkdir(exist_ok=True)
        checked_path(self.root)
        self.control = control if control is not None else ExecutionControl()
        self._slot = threading.Lock()
        self._quarantined = False

    def execute(self, call: dict, spec: dict, policy: dict, case_snapshot: dict,
                adapter: PinnedAdapter, *, cancel: threading.Event | None = None) -> ExecutionOutput:
        if not self._slot.acquire(blocking=False):
            raise ExecutionRejected('BUDGET_EXCEEDED', 'Executor already owns an active run')
        try:
            if self._quarantined:
                raise ExecutionRejected('CLEANUP_INCOMPLETE', 'Executor quarantined after incomplete cleanup')
            return self._execute(copy.deepcopy(call), copy.deepcopy(spec), copy.deepcopy(policy),
                                 copy.deepcopy(case_snapshot), adapter, cancel)
        finally:
            self._slot.release()

    def _execute(self, call, spec, policy, case, adapter, cancel):
        try:
            validate('tool_call', call)
            validate('tool_spec', spec)
            validate('policy_decision', policy)
            validate('target_ref', call['target_ref'])
        except (ContractError, KeyError, TypeError, ValueError) as exc:
            raise ExecutionRejected('SCHEMA_INVALID', 'Invalid D.0 input') from exc
        if call['case_id'] != case.get('case_id') or call['expected_revision'] != case.get('revision'):
            raise ExecutionRejected('CASE_REVISION_STALE', 'Case snapshot mismatch; D1 must re-admit')
        if any(policy[k] != call[k] for k in ('call_id', 'case_id', 'expected_revision')):
            raise ExecutionRejected('POLICY_DENIED', 'Policy is bound to a different call/case revision')
        if policy['outcome'] != 'ALLOW':
            code = 'APPROVAL_REQUIRED' if policy['outcome'] == 'REQUIRE_APPROVAL' else 'POLICY_DENIED'
            raise ExecutionRejected(code, 'No admitted execution')
        effects = spec['effects']
        if any(effects[k] for k in ('executes_foreign_code', 'mutates_target', 'writes_filesystem', 'requires_human_approval')):
            raise ExecutionRejected('POLICY_DENIED', 'Only read-only host analysis supported; VM/approval backend absent')
        if spec['provider'] != adapter.provider() or call['provider_id'] != adapter.provider_id:
            raise ExecutionRejected('PROVIDER_MISMATCH', 'Exact installed provider binding required')
        if not spec['enabled']:
            raise ExecutionRejected('TOOL_DISABLED', 'Installed tool is disabled')
        if (call['tool_id'], call['tool_version']) != (spec['tool_id'], spec['tool_version']):
            raise ExecutionRejected('PROVIDER_MISMATCH', 'Tool identity/version mismatch')
        if call['target_ref']['kind'] != 'FILE':
            raise ExecutionRejected('TARGET_IDENTITY_UNAVAILABLE', 'PROCESS adapter not implemented')
        try:
            verify_tool_call(spec, call, case)
        except (ContractError, ValueError, KeyError) as exc:
            raise ExecutionRejected('SCHEMA_INVALID', 'Tool/case/target/limit validation failed') from exc
        ref = call['target_ref']
        if not ref['verified_digest']:
            raise ExecutionRejected('TARGET_IDENTITY_UNAVAILABLE', 'Verified SHA-256 required for FILE execution')
        limits = {k: min(spec['limits'][k], policy['effective_limits'][k]) for k in spec['limits']}
        for key in call['budget']:
            limits[key] = min(limits[key], call['budget'][key])
        started_at, started = now(), time.monotonic()
        deadline = started + limits['timeout_ms'] / 1000
        check_deadline(deadline, cancel)
        if not adapter.command or not Path(adapter.command[0]).is_absolute():
            raise ExecutionRejected('PROVIDER_MISMATCH', 'Absolute installed command required')
        if Path(adapter.command[0]).suffix.lower() != '.exe':
            raise ExecutionRejected('PROVIDER_MISMATCH', 'Native EXE required; batch/shell launchers unsupported')
        pins = dict(adapter.pins)
        if adapter.command[0] not in pins or not pins:
            raise ExecutionRejected('PROVIDER_MISMATCH', 'Provider executable must be pinned')
        # Absolute code arguments (e.g. Python script) also require declared pins.
        if any(Path(arg).is_absolute() and arg not in pins for arg in adapter.command):
            raise ExecutionRejected('PROVIDER_MISMATCH', 'Unpinned provider code path')
        run_id = 'RUN-' + uuid.uuid4().hex
        run_dir = self.root / run_id
        staged = run_dir / 'target.bin'
        binding = None
        control_result = None
        try:
            with ExitStack() as stack:
                for path, expected in adapter.pins:
                    try:
                        provider_stream = stack.enter_context(locked_reader(path))
                    except OSError as exc:
                        raise ExecutionRejected('PROVIDER_UNAVAILABLE', 'Pinned provider cannot be opened') from exc
                    if stream_digest(provider_stream, deadline, cancel) != expected:
                        raise ExecutionRejected('PROVIDER_MISMATCH', 'Installed provider digest changed')
                source = stack.enter_context(locked_reader(ref['observed']['path']))
                info = os.fstat(source.fileno())
                observed = {'device': info.st_dev, 'inode': info.st_ino,
                            'size_bytes': info.st_size, 'mtime_ns': info.st_mtime_ns}
                if any(value is not None and observed.get(k) != value
                       for k, value in ref['snapshot'].items() if k in observed):
                    raise ExecutionRejected('TARGET_CHANGED', 'Opened file differs from collected snapshot')
                checked_path(self.root)
                run_dir.mkdir(exist_ok=False)
                with staged.open('xb') as destination:
                    actual = stream_digest(source, deadline, cancel, destination)
                if actual != ref['verified_digest']['value']:
                    raise ExecutionRejected('TARGET_CHANGED', 'Opened file hash differs from admitted target')
                staged_reader = stack.enter_context(locked_reader(staged))
                if stream_digest(staged_reader, deadline, cancel) != actual:
                    raise ExecutionRejected('ARTIFACT_INTEGRITY_FAILED', 'Staged bytes failed verification')
                binding = {'status': 'VERIFIED', 'method': 'windows_locked_handle_and_locked_staged_sha256',
                           'observed_ref': copy.deepcopy(ref), 'verified_at': now()}
                arguments = canonical_json_bytes(call['arguments']).decode('utf-8')
                argv = [*adapter.command, '--target', str(staged), '--arguments-json', arguments]
                if len(json.dumps(argv, ensure_ascii=True).encode('ascii')) > 24000:
                    raise ExecutionRejected('BUDGET_EXCEEDED', 'Arguments exceed adapter control-message budget')
                check_deadline(deadline, cancel)
                control_result = self.control.run(argv, run_dir,
                    timeout_ms=max(1, int((deadline - time.monotonic()) * 1000)),
                    max_output_bytes=limits['max_output_bytes'],
                    max_artifact_bytes=limits['max_artifact_bytes'], cancel=cancel)
        except OSError as exc:
            raise ExecutionRejected('TARGET_IDENTITY_UNAVAILABLE', 'File/provider access unavailable; no unsafe fallback') from exc
        finally:
            # Never remove arbitrary directories. Only the exact generated staging file.
            if staged.exists() and (control_result is None or control_result.cleanup_status != 'INCOMPLETE'):
                try:
                    staged.unlink()
                except OSError:
                    self._quarantined = True
            if control_result is not None and control_result.cleanup_status == 'INCOMPLETE':
                self._quarantined = True
        remaining = list(control_result.remaining_owned_resources)
        if staged.exists():
            remaining.append('staged_target')
            self._quarantined = True
        cleanup = 'INCOMPLETE' if remaining else control_result.cleanup_status
        outcome = control_result.outcome
        error_code = control_result.error_code
        if cleanup == 'INCOMPLETE' and outcome == 'SUCCESS':
            outcome, error_code = 'FAILED', 'CLEANUP_INCOMPLETE'
        receipt = {'schema_version': 'd0-v1', 'run_id': run_id, 'call_id': call['call_id'],
                   'case_id': call['case_id'], 'tool_id': call['tool_id'], 'tool_version': call['tool_version'],
                   'provider': adapter.provider(), 'arguments_sha256': digest(call['arguments']),
                   'target_binding': binding, 'started_at': started_at, 'finished_at': now(),
                   'outcome': outcome, 'cleanup': {'status': cleanup, 'remaining_owned_resources': remaining},
                   'resources': {'duration_ms': round((time.monotonic() - started) * 1000),
                                 'output_bytes': control_result.output_bytes}}
        validate('execution_receipt', receipt)
        artifacts = []
        artifact_size = 0
        for name in ('stdout.bin', 'stderr.bin'):
            path = run_dir / name
            if path.exists():
                with locked_reader(path) as stream:
                    size = os.fstat(stream.fileno()).st_size
                    artifact_size += size
                    if artifact_size > min(limits['max_output_bytes'], limits['max_artifact_bytes']):
                        receipt['outcome'], error_code = 'FAILED', 'ARTIFACT_INTEGRITY_FAILED'
                        continue  # Never hash an unexpectedly oversized provider-created artifact.
                    checksum = hashlib.sha256()
                    while chunk := stream.read(1024 * 1024):
                        checksum.update(chunk)
                if checksum.hexdigest() != dict(control_result.stream_sha256).get(name):
                    receipt['outcome'], error_code = 'FAILED', 'ARTIFACT_INTEGRITY_FAILED'
                artifacts.append({'artifact_id': 'ART-' + uuid.uuid4().hex,
                                  'sha256': checksum.hexdigest(), 'size_bytes': size,
                                  'media_type': 'application/octet-stream',
                                  'relative_path': f'{run_id}/{name}'})
        if artifact_size != control_result.output_bytes:
            receipt['outcome'], error_code = 'FAILED', 'ARTIFACT_INTEGRITY_FAILED'
        for artifact in artifacts:
            validate('artifact', artifact)
        error = None if error_code is None else {'code': error_code, 'message': {
            'TIMEOUT': 'Adapter deadline exceeded', 'CANCELLED': 'Cancellation requested',
            'BUDGET_EXCEEDED': 'Combined stdout/stderr artifact cap exceeded',
            'CLEANUP_INCOMPLETE': 'Owned resources remain; executor quarantined',
            'PROVIDER_FAILED': 'Adapter exited with a nonzero status',
            'ARTIFACT_INTEGRITY_FAILED': 'Captured artifact size or digest disagrees with the execution record',
        }.get(error_code, 'Adapter execution unavailable or failed')}
        (run_dir / 'execution_receipt.json').write_bytes(canonical_json_bytes(receipt))
        return ExecutionOutput(receipt, tuple(artifacts), error, control_result.exit_code, run_dir)
