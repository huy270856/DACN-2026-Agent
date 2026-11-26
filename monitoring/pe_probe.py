"""Bounded PE header probe for filtering scan candidates without full reads."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import struct
from typing import Optional

# Cap header offset to avoid unbounded seeks on malformed files.
MAX_E_LFANEW = 16 * 1024 * 1024  # 16 MiB
HASH_CHUNK_BYTES = 1024 * 1024
MAX_OBS_HASH_BYTES = 32 * 1024 * 1024  # Bound dedup hash read to 32 MiB


@dataclass(frozen=True)
class PEProbeResult:
    status: str
    is_pe: bool
    machine: Optional[str] = None
    reason: str = ""
    size_bytes: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "is_pe": self.is_pe,
            "machine": self.machine,
            "reason": self.reason,
            "size_bytes": self.size_bytes,
        }


def probe_pe_file(path: str) -> PEProbeResult:
    """Inspect only DOS + PE signature + COFF machine header (bounded read).

    Never executes the file and never reads the entire file just to detect PE.
    """
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return PEProbeResult("FILE_MISSING", False, reason="file_not_found")
    except PermissionError:
        return PEProbeResult("PERMISSION_DENIED", False, reason="permission_denied")
    except OSError as exc:
        return PEProbeResult("IO_ERROR", False, reason=f"stat_error:{exc.errno}")

    if st.st_size < 64:
        return PEProbeResult(
            "PARTIAL_OR_EMPTY" if st.st_size == 0 else "NON_PE",
            False,
            reason="file_smaller_than_dos_header",
            size_bytes=st.st_size,
        )

    try:
        with open(path, "rb") as handle:
            dos = handle.read(64)
            if len(dos) < 64:
                return PEProbeResult(
                    "PARTIAL_OR_EMPTY",
                    False,
                    reason="short_dos_read",
                    size_bytes=st.st_size,
                )
            if dos[:2] != b"MZ":
                return PEProbeResult(
                    "NON_PE",
                    False,
                    reason="missing_mz_magic",
                    size_bytes=st.st_size,
                )

            (e_lfanew,) = struct.unpack_from("<I", dos, 0x3C)
            if e_lfanew < 64 or e_lfanew > MAX_E_LFANEW or e_lfanew + 24 > st.st_size:
                return PEProbeResult(
                    "MALFORMED_PE",
                    False,
                    reason="invalid_e_lfanew",
                    size_bytes=st.st_size,
                )

            handle.seek(e_lfanew)
            pe_hdr = handle.read(24)
            if len(pe_hdr) < 24:
                return PEProbeResult(
                    "MALFORMED_PE",
                    False,
                    reason="truncated_pe_header",
                    size_bytes=st.st_size,
                )
            if pe_hdr[:4] != b"PE\x00\x00":
                return PEProbeResult(
                    "MALFORMED_PE",
                    False,
                    reason="missing_pe_signature",
                    size_bytes=st.st_size,
                )

            (machine,) = struct.unpack_from("<H", pe_hdr, 4)
            return PEProbeResult(
                "VALID_PE",
                True,
                machine=f"0x{machine:04x}",
                reason="pe_signature_verified",
                size_bytes=st.st_size,
            )
    except FileNotFoundError:
        return PEProbeResult("FILE_MISSING", False, reason="file_disappeared")
    except PermissionError:
        return PEProbeResult("PERMISSION_DENIED", False, reason="open_permission_denied")
    except OSError as exc:
        # Windows sharing violation (winerror 32) or lock violation (winerror 33)
        if getattr(exc, "winerror", None) in (32, 33):
            return PEProbeResult("LOCKED_OR_PARTIAL", False, reason=f"sharing_violation:{exc.winerror}")
        return PEProbeResult("IO_ERROR", False, reason=f"io_error:{exc.errno}")


def observation_sha256(path: str, max_bytes: int = MAX_OBS_HASH_BYTES) -> Optional[str]:
    """Compute bounded SHA-256 purely for local event deduplication.

    Does NOT replace Node B/D trusted identity verification.
    """
    try:
        size = os.path.getsize(path)
        if size > max_bytes:
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None

