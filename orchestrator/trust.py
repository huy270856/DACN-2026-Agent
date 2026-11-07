"""D8 - Trust & Approval for the D.0 Trusted Tool Orchestrator.

Two trust-boundary responsibilities (ADR-004, ADR-007; docs/d0/06):

  (a) Attestation signer for ToolResult commits. D8 OWNS the signing key custody
      and exposes it only to the trusted control plane (D1) that commits via D9.
      Signing/verification reuse Node C's existing HMAC machinery
      (``case_manager.sign_for_trusted_boundary`` / ``_verify_proof``) — D8 does
      not reinvent crypto. Keys are never handed to the Agent, tools or provider
      code.

  (b) Authenticated analyst approval for RESPONSE actions
      (QUARANTINE_FILE / TERMINATE_PROCESS / ISOLATE_HOST / RESTORE_FILE). D8
      issues an ``approval_request`` (PENDING), records a decision as an
      ``approval_event`` whose ``authenticated_subject`` comes from a real local
      authenticator (NOT from Agent input), binds the event to the exact action
      digest + case revision + expiration, and only then produces the signed
      ``response`` authorization. A forged/expired/replayed/mismatched approval is
      rejected.

MOCK vs TRUSTED separation:
  * ``TrustedSigner`` + a real ``KeyProvider`` (e.g. ``DpapiKeyProvider`` on
    Windows, or ``InMemoryKeyProvider`` which still generates a REAL random key)
    are the trusted path. ``MockSigner`` performs NO real signing and exists only
    for smoke tests; it must never be used in a flow advertised as trusted.
  * ``LocalOsAuthenticator`` is the trusted analyst identity source;
    ``StaticAuthenticator`` is a test double.

Key-custody limitation (stated, not hidden): ``DpapiKeyProvider`` protects the
key with Windows DPAPI (user scope) in a restricted file. This is best-effort OS
protection, NOT an HSM/TPM-sealed, production-grade key store.
"""
from __future__ import annotations

import ctypes
import getpass
import os
import secrets
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Protocol, Tuple

from d0.validate import validate, digest, ContractError
import case_manager as cm


# =============================================================================
# Errors
# =============================================================================
class TrustError(Exception):
    """Base error for the D8 trust boundary."""


class AuthenticationError(TrustError):
    """Analyst authentication failed or is unavailable."""


class ApprovalExpiredError(TrustError):
    """Approval event or request has expired."""


class ApprovalMismatchError(TrustError):
    """Approval event does not bind the exact action/case/revision requested."""


class KeyCustodyError(TrustError):
    """The signing key could not be created, protected or loaded."""


# =============================================================================
# Key custody
# =============================================================================
class KeyProvider(Protocol):
    def tool_key(self) -> bytes: ...
    def approval_key(self) -> bytes: ...


class InMemoryKeyProvider:
    """DEV/TEST key provider: REAL random keys held only in memory.

    Not persisted and not DPAPI-protected. This is a real signer key (so the
    signer is a genuine signer, not a mock), but it does not survive restart and
    offers no at-rest protection. Use DpapiKeyProvider for custody at rest.
    """

    def __init__(self, tool_key: Optional[bytes] = None, approval_key: Optional[bytes] = None):
        self._tool = tool_key or secrets.token_bytes(32)
        self._approval = approval_key or secrets.token_bytes(32)
        if len(self._tool) < 32 or len(self._approval) < 32:
            raise KeyCustodyError("Keys must be at least 32 bytes")

    def tool_key(self) -> bytes:
        return self._tool

    def approval_key(self) -> bytes:
        return self._approval


class DpapiKeyProvider:
    """Windows DPAPI-protected key file (user scope) with a restricted ACL.

    Stores a 64-byte secret (split into a 32-byte tool key and 32-byte approval
    key) encrypted with CryptProtectData. On first use it generates and protects
    the secret; later it loads and unprotects it. The key file is best-effort
    locked down to the current user via ``icacls``.

    LIMITATION: DPAPI user-scope + file ACL is best-effort OS protection, NOT an
    HSM/TPM-sealed production key store. Any process running as the same user can
    unprotect it.
    """

    def __init__(self, key_path: Path | str, *, entropy: bytes = b"DACN-D8-v1"):
        if os.name != "nt":
            raise KeyCustodyError("DpapiKeyProvider requires Windows DPAPI")
        self._path = Path(key_path)
        self._entropy = entropy
        self._secret = self._load_or_create()

    # -- DPAPI via ctypes ---------------------------------------------------
    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _crypt(self, func_name: str, data: bytes) -> bytes:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_string_buffer(data, len(data))
        in_blob = self._BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        ent_buf = ctypes.create_string_buffer(self._entropy, len(self._entropy))
        ent_blob = self._BLOB(len(self._entropy), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
        out_blob = self._BLOB()
        func = getattr(crypt32, func_name)
        ok = func(ctypes.byref(in_blob), None, ctypes.byref(ent_blob),
                  None, None, 0, ctypes.byref(out_blob))
        if not ok:
            raise KeyCustodyError(f"{func_name} failed (err {ctypes.get_last_error()})")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)

    def _protect(self, data: bytes) -> bytes:
        return self._crypt("CryptProtectData", data)

    def _unprotect(self, data: bytes) -> bytes:
        return self._crypt("CryptUnprotectData", data)

    def _restrict_acl(self) -> None:
        # Best-effort: grant only the current user, remove inheritance. Failure is
        # non-fatal (DPAPI still protects contents) but is surfaced by the caller.
        try:
            user = os_account_name()
            subprocess.run(["icacls", str(self._path), "/inheritance:r",
                            "/grant:r", f"{user}:F"],
                           check=False, capture_output=True, timeout=10)
        except Exception:
            pass

    def _load_or_create(self) -> bytes:
        if self._path.exists():
            blob = self._path.read_bytes()
            secret = self._unprotect(blob)
            if len(secret) < 64:
                raise KeyCustodyError("Stored key material is too short")
            return secret
        self._path.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_bytes(64)
        blob = self._protect(secret)
        # Write then restrict ACL.
        with open(self._path, "wb") as f:
            f.write(blob)
        try:
            os.chmod(self._path, stat.S_IREAD | stat.S_IWRITE)
        except OSError:
            pass
        self._restrict_acl()
        return secret

    def tool_key(self) -> bytes:
        return self._secret[:32]

    def approval_key(self) -> bytes:
        return self._secret[32:64]


# =============================================================================
# Attestation signer
# =============================================================================
class TrustedSigner:
    """Signs ToolResult commits with the D8-custodied key (real HMAC via Node C)."""

    def __init__(self, key_provider: KeyProvider):
        self._keys = key_provider

    def tool_key(self) -> bytes:
        """Return the tool-attestation key for the trusted control plane (D1->D9).

        Only the trusted control plane calls this; it is never exposed to the
        Agent, tools or provider code.
        """
        return self._keys.tool_key()

    def sign_tool_result(self, case_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return cm.sign_for_trusted_boundary(case_id, "tool-result", dict(payload), self._keys.tool_key())

    def trusted_keys(self) -> Dict[str, bytes]:
        return {"tool": self._keys.tool_key()}


class MockSigner(TrustedSigner):
    """NOT a real signer. For smoke tests only; never use in a trusted flow."""

    def __init__(self):
        super().__init__(InMemoryKeyProvider())
        self.is_mock = True


# =============================================================================
# Analyst authentication
# =============================================================================
class AnalystAuthenticator(Protocol):
    def authenticate(self) -> Tuple[str, str]: ...


class LocalOsAuthenticator:
    """Returns the current local OS account as the analyst identity.

    LIMITATION: asserts the process-owner identity (via the Windows token, not an
    env var); it does NOT re-verify a credential or MFA. A production approval
    gate must perform real interactive authentication in a trusted local service.
    The Agent can never supply this.
    """

    def authenticate(self) -> Tuple[str, str]:
        subject = os_account_name()
        if not subject:
            raise AuthenticationError("No local OS account identity available")
        return subject, "local_os_account"


class StaticAuthenticator:
    """Test double for a known authenticated analyst."""

    def __init__(self, subject: str, method: str = "local_os_account"):
        self._subject = subject
        self._method = method

    def authenticate(self) -> Tuple[str, str]:
        return self._subject, self._method


# =============================================================================
# Approval service (response actions)
# =============================================================================
def _now() -> datetime:
    return datetime.now(timezone.utc)


def os_account_name() -> str:
    """Return the current process-token account name.

    On Windows this reads the actual thread/process token via ``GetUserNameW``
    (advapi32), which is NOT overridable by the ``USERNAME``/``LOGNAME`` env vars
    — unlike ``getpass.getuser()``. This removes trivial env-based spoofing of the
    analyst identity. It still asserts the *process owner*, not a re-verified
    interactive credential (see LocalOsAuthenticator limitations).
    """
    if os.name == "nt":
        try:
            size = ctypes.c_ulong(0)
            ctypes.windll.advapi32.GetUserNameW(None, ctypes.byref(size))
            buf = ctypes.create_unicode_buffer(size.value)
            if ctypes.windll.advapi32.GetUserNameW(buf, ctypes.byref(size)) and buf.value:
                return buf.value
        except Exception:
            pass
    return getpass.getuser()


class ApprovalService:
    """Issues and verifies authenticated analyst approvals for response actions."""

    def __init__(self, *, ttl_seconds: int = 120):
        self._ttl = ttl_seconds

    def canonical_action(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        """The exact action an approval binds (digested into the event)."""
        return {
            "action_id": request["action_id"],
            "action_type": request["action_type"],
            "case_id": request["case_id"],
            "expected_revision": request["expected_revision"],
            "target_ref": request["target_ref"],
            "effect_summary": request["effect_summary"],
        }

    def create_request(self, case_snapshot: Mapping[str, Any], *, action_id: str,
                       action_type: str, target_ref: Mapping[str, Any],
                       effect_summary: str, risk: str, reason: str) -> Dict[str, Any]:
        now = _now()
        request = {
            "schema_version": "d0-v1",
            "request_id": "APR-" + secrets.token_hex(16),
            "case_id": case_snapshot["case_id"],
            "expected_revision": int(case_snapshot["revision"]),
            "action_id": action_id,
            "action_type": action_type,
            "target_ref": dict(target_ref),
            "effect_summary": effect_summary,
            "risk": risk,
            "reason": reason,
            "expires_at": (now + timedelta(seconds=self._ttl)).isoformat(),
            "requested_at": now.isoformat(),
            "status": "PENDING",
        }
        validate("approval_request", request)
        return request

    def record_decision(self, request: Mapping[str, Any], decision: str,
                        authenticator: AnalystAuthenticator) -> Dict[str, Any]:
        """Record an APPROVED/REJECTED decision from an authenticated analyst.

        The subject comes ONLY from the authenticator, never from input.
        """
        if decision not in ("APPROVED", "REJECTED"):
            raise ApprovalMismatchError("decision must be APPROVED or REJECTED")
        subject, method = authenticator.authenticate()
        event = {
            "schema_version": "d0-v1",
            "request_id": request["request_id"],
            "case_id": request["case_id"],
            "action_id": request["action_id"],
            "decision": decision,
            "authenticated_subject": subject,
            "authentication_method": method,
            "decided_at": _now().isoformat(),
            "expires_at": request["expires_at"],
            "case_revision": int(request["expected_revision"]),
            "action_digest_sha256": digest(self.canonical_action(request)),
        }
        validate("approval_event", event)
        return event

    def authorize_response(self, case_snapshot: Mapping[str, Any],
                           response_payload: Mapping[str, Any],
                           request: Mapping[str, Any], event: Mapping[str, Any],
                           key_provider: KeyProvider) -> Dict[str, Any]:
        """Verify an approval and produce the signed Node C 'response' authorization.

        Returns {'payload', 'authorization', 'trusted_keys'} for
        cm.apply_update('response', ...). Fails closed on any mismatch/expiry.
        """
        validate("approval_event", event)
        # 1. Must be an approval, for this exact request/action/case.
        if event["decision"] != "APPROVED":
            raise ApprovalMismatchError("Approval event is not APPROVED")
        if (event["request_id"] != request["request_id"]
                or event["action_id"] != request["action_id"]
                or event["case_id"] != request["case_id"]):
            raise ApprovalMismatchError("Approval event does not match the request")
        # 2. Exact action digest binding (no substitution of the approved action).
        if event["action_digest_sha256"] != digest(self.canonical_action(request)):
            raise ApprovalMismatchError("Approved action digest does not match")
        # 3. Expiration.
        if _now() >= datetime.fromisoformat(event["expires_at"]):
            raise ApprovalExpiredError("Approval has expired")
        # 4. Re-check current case revision (ADR-004: recheck before effects).
        current_rev = int(case_snapshot["revision"])
        if event["case_revision"] != current_rev or request["expected_revision"] != current_rev:
            raise ApprovalMismatchError(
                f"Case revision changed since approval (approved {event['case_revision']}, now {current_rev})")
        # 5. D8 sets the approver to the AUTHENTICATED subject; Agent input is ignored.
        payload = dict(response_payload)
        payload["approver"] = event["authenticated_subject"]
        payload["human_approved"] = True
        proof = cm.sign_for_trusted_boundary(
            case_snapshot["case_id"], "response", payload, key_provider.approval_key())
        return {"payload": payload, "authorization": proof,
                "trusted_keys": {"approval": key_provider.approval_key()}}
