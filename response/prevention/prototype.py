"""Bounded lab identity checks and a MOCK policy lifecycle, Python 3.12 stdlib.

No commands, Windows policy mutations, execution endpoints or production auth.
Instances belong exclusively to a trusted single-threaded test harness.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class PrototypeError(ValueError):
    """Stable reason code; never interpreted as success."""


@dataclass(frozen=True)
class BlockRequest:
    request_id: str
    case_id: str
    case_revision: int
    target_ref: str  # relative to configured lab root, never an arbitrary shell path
    target_sha256: str
    action: str = "block_execution"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Prevention:
    """mode=dry-run by default; mock changes only a Python dictionary.

    authorize is an injected MOCK harness callback (request, operation)->bool.
    It must not come from request JSON/LLM. It is NOT a D4/D8 replacement.
    No persistent recovery, concurrency guarantees or live backend provided.
    """

    def __init__(self, lab_root, *, mode="dry-run",
                 authorize: Callable | None = None):
        if mode not in {"dry-run", "mock"}:
            raise PrototypeError("MODE_UNSUPPORTED")
        root = Path(lab_root).absolute()
        self._no_links(root)
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise PrototypeError("LAB_ROOT_INVALID")
        self.mode = mode
        self.authorize = authorize or (lambda request, operation: False)
        self.rules = {}  # MOCK state; not Windows policy
        self.plans = {}
        self.bindings = {}
        self.results = {}
        self.audit = []  # process-local, not durable/tamper-proof
        self.fail_next = None  # trusted harness failure injection, mock only

    @staticmethod
    def _no_links(path):
        for part in [path, *path.parents]:
            s = part.lstat()
            if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                raise PrototypeError("REPARSE_POINT_REJECTED")

    def _identity(self, request):
        for key in ("request_id", "case_id"):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", getattr(request, key)):
                raise PrototypeError("INVALID_REQUEST")
        if (type(request.case_revision) is not int or request.case_revision < 0
                or request.action != "block_execution"
                or not re.fullmatch(r"[0-9a-f]{64}", request.target_sha256)):
            raise PrototypeError("INVALID_REQUEST")
        relative = Path(request.target_ref)
        if (not request.target_ref or relative.is_absolute() or relative.anchor
                or relative.drive or ".." in relative.parts or ":" in request.target_ref
                or any(Path(part).is_reserved() for part in relative.parts)):
            raise PrototypeError("TARGET_OUTSIDE_LAB")
        candidate = self.root / relative
        self._no_links(candidate)
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(self.root) or resolved.suffix.lower() != ".exe":
            raise PrototypeError("TARGET_OUTSIDE_LAB")
        before = resolved.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > 16 * 1024 * 1024:
            raise PrototypeError("TARGET_SIZE_OR_TYPE_INVALID")
        with resolved.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            data = stream.read(16 * 1024 * 1024 + 1)
            after = os.fstat(stream.fileno())
        # Windows/Python 3.12 stat vs fstat st_ctime can have different semantics.
        # Digest + dev/inode/size/mtime checks reduce races, not a TOCTOU proof.
        fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if (fields(before) != fields(opened) or fields(opened) != fields(after)
                or fields(after) != fields(resolved.stat())):
            raise PrototypeError("TARGET_CHANGED_DURING_READ")
        if len(data) > 16 * 1024 * 1024:
            raise PrototypeError("TARGET_SIZE_OR_TYPE_INVALID")
        if hashlib.sha256(data).hexdigest() != request.target_sha256:
            raise PrototypeError("TARGET_HASH_MISMATCH")
        offset = int.from_bytes(data[60:64], "little") if len(data) >= 64 else -1
        if (data[:2] != b"MZ" or offset < 64
                or data[offset:offset + 4] != b"PE\0\0"):
            raise PrototypeError("NOT_PE_HEADER")
        # Header check is a filter, not a loader or validation of a runnable PE.
        return {"target_ref": request.target_ref, "sha256": request.target_sha256,
                "size": len(data), "pe_check": "HEADER_ONLY_NOT_EXECUTED"}

    def _state(self):
        return _digest(self.rules)

    def _result(self, request, operation, status, reason, **metadata):
        request_id = getattr(request, "request_id", None)
        result = {"request_id": request_id if isinstance(request_id, str) else "invalid-request", "status": status,
                  "reason_code": reason, "timestamp": datetime.now(timezone.utc).isoformat(),
                  "operation": operation, "evaluation_type": "MOCK" if self.mode == "mock" else "DRY_RUN",
                  "live_execution_verified": False, "policy_state": self._state(),
                  "rollback_reference": None, "audit_metadata": {"sequence": len(self.audit) + 1,
                  "durability": "PROCESS_LOCAL_ONLY"}, **metadata}
        # Result consumers must not be able to mutate stored rule identity/audit.
        result = json.loads(json.dumps(result))
        self.audit.append(json.loads(json.dumps(result)))
        return result

    def capabilities(self):
        from .capabilities import collect_capabilities
        return {**collect_capabilities(), "mode": self.mode, "live_supported": False,
                "reason_code": "PYTHON_MOCK_HAS_NO_LIVE_MODE",
                "policy_side_effects": "NONE" if self.mode == "dry-run" else "IN_MEMORY_MOCK_ONLY"}

    def _bind(self, request):
        if not isinstance(request, BlockRequest):
            raise PrototypeError("BLOCK_REQUEST_REQUIRED")
        if (any(not isinstance(getattr(request, key), str) for key in
                ("request_id", "case_id", "target_ref", "target_sha256", "action"))
                or type(request.case_revision) is not int or request.case_revision < 0):
            raise PrototypeError("INVALID_REQUEST")
        fingerprint = _digest(asdict(request))
        old = self.bindings.get(request.request_id)
        if old is not None and old != fingerprint:
            raise PrototypeError("DUPLICATE_REQUEST_CONFLICT")
        self.bindings[request.request_id] = fingerprint

    def plan_block(self, request):
        op = "plan_block"
        try:
            self._bind(request)
            identity = self._identity(request)
            previous = self.plans.get(request.request_id)
            if previous:
                return self._result(request, op, "PLANNED", "DUPLICATE_PLAN",
                                    plan=json.loads(json.dumps(previous)))
            plan = {"plan_id": _digest(asdict(request)), "identity": identity,
                    "backend": "IN_MEMORY_MOCK" if self.mode == "mock" else "APPLOCKER_RESEARCH_ONLY",
                    "base_policy_digest": self._state(), "operation": "ADD_OWNED_RULE_ONLY",
                    "scope": "MOCK exact relative path + byte SHA256; no Windows policy generated",
                    "windows_rule_hash": "UNKNOWN_AUTHENTICODE_HASH_REQUIRED",
                    "windows_policy_baseline": {"status": "UNKNOWN_NOT_BOUND", "deployable": False},
                    "policy_delta_proposal": {
                        "backend": "AppLocker", "collection": "Exe", "action": "Deny",
                        "subject_sid": None, "subject_status": "TEST_USER_NOT_SELECTED",
                        "condition": "FileHash_Authenticode", "authenticode_hash": None,
                        "target_byte_sha256": request.target_sha256,
                        "scope_warning": "Same Authenticode hash copies may match outside lab",
                        "replace_existing_policy": False, "change_collection_mode": False},
                    "live_gates": ["APPROVED_VM", "REHEARSED_RECOVERY", "TRUSTED_AUTHORIZATION",
                                   "EFFECTIVE_AND_LOCAL_POLICY_REVIEW", "EXACT_SUBJECT_AND_RULE_IDENTITY",
                                   "VALIDATED_OWNED_RULE_ROLLBACK"],
                    "rollback": "MOCK remove only owned rule; live recovery NOT_VALIDATED"}
            self.plans[request.request_id] = plan
            return self._result(request, op, "PLANNED", "DRY_RUN_NO_WINDOWS_CHANGES",
                                plan=json.loads(json.dumps(plan)))
        except (PrototypeError, OSError, TypeError, AttributeError) as exc:
            return self._failure(request, op, exc)

    def _failure(self, request, operation, exc):
        reason = str(exc) if isinstance(exc, PrototypeError) else type(exc).__name__
        return self._result(request, operation, "REJECTED", reason)

    def _gate(self, request, operation):
        self._bind(request)
        if self.mode != "mock":
            raise PrototypeError("LIVE_BLOCKED_DRY_RUN_ONLY")
        if self.authorize(request, operation) is not True:
            raise PrototypeError("MOCK_HARNESS_AUTHORIZATION_DENIED")
        if request.request_id not in self.plans:
            raise PrototypeError("PLAN_REQUIRED")

    def apply_block(self, request):
        op = "apply_block"
        try:
            self._gate(request, op)
            identity = self._identity(request)
            previous = self.results.get((request.request_id, op))
            if previous:
                raise PrototypeError("DUPLICATE_APPLY_USE_VERIFY")
            plan = self.plans[request.request_id]
            if self._state() != plan["base_policy_digest"]:
                raise PrototypeError("POLICY_STATE_CHANGED_REPLAN_REQUIRED")
            if self.fail_next == "apply":
                self.fail_next = None
                raise PrototypeError("INJECTED_APPLY_FAILURE_NO_CHANGE")
            self.rules[plan["plan_id"]] = identity
            result = self._result(request, op, "MOCK_APPLIED", "SIMULATED_RULE_ADDED",
                                  identity_before=identity, identity_after=identity,
                                  policy_before=plan["base_policy_digest"],
                                  rollback_reference=plan["plan_id"])
            self.results[(request.request_id, op)] = json.loads(json.dumps(result))
            return result
        except Exception as exc:
            return self._failure(request, op, exc)

    def verify_block(self, request):
        op = "verify_block"
        try:
            self._gate(request, op)
            identity = self._identity(request)
            plan = self.plans[request.request_id]
            if self.rules.get(plan["plan_id"]) != identity:
                raise PrototypeError("MOCK_RULE_NOT_PRESENT_OR_CHANGED")
            return self._result(request, op, "MOCK_VERIFIED", "SIMULATION_ONLY_NOT_EXECUTION_PROOF",
                                rollback_reference=plan["plan_id"])
        except Exception as exc:
            return self._failure(request, op, exc)

    def rollback_block(self, request):
        op = "rollback_block"
        try:
            self._gate(request, op)  # rollback needs separate operation authorization
            # Recovery uses saved owned policy identity, not a possibly deleted target.
            plan = self.plans[request.request_id]
            rule = self.rules.get(plan["plan_id"])
            if rule is None:
                if (request.request_id, op) in self.results:
                    return self._result(request, op, "MOCK_ROLLED_BACK", "DUPLICATE_ROLLBACK_NO_CHANGE")
                raise PrototypeError("MOCK_RULE_NOT_PRESENT")
            if rule != plan["identity"]:
                raise PrototypeError("OWNED_RULE_CHANGED_REQUIRES_REVIEW")
            before = self._state()
            if self.fail_next == "rollback":
                self.fail_next = None
                raise PrototypeError("INJECTED_ROLLBACK_FAILURE_RULE_RETAINED")
            del self.rules[plan["plan_id"]]
            result = self._result(request, op, "MOCK_ROLLED_BACK", "OWNED_SIMULATED_RULE_REMOVED",
                                  policy_before=before, rollback_reference=plan["plan_id"])
            self.results[(request.request_id, op)] = json.loads(json.dumps(result))
            return result
        except Exception as exc:
            return self._failure(request, op, exc)
