"""Discover diverse benign Windows PE targets (read-only) and build a manifest.

Candidates are well-known Windows system binaries. Each is parsed statically (LIEF,
never executed), its SHA-256/size/format/machine/section/import counts recorded, and
its Authenticode signature status checked via PowerShell (read-only). A valid
signature is provenance evidence (the file is a genuine Microsoft-signed binary); it
does NOT by itself prove the file is harmless, and "lives in System32" is recorded as
provenance, not as proof of benignity.

Full user-specific paths are not emitted; only a source tag + filename are kept.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import lief

lief.logging.disable()

SYS32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
WINDIR = Path(os.environ.get("SystemRoot", r"C:\Windows"))
WOW64 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "SysWOW64"  # 32-bit (PE32) on x64

# Candidate benign system binaries (existence is verified; missing ones are skipped).
CANDIDATES = [
    SYS32 / "notepad.exe", WINDIR / "notepad.exe", SYS32 / "mspaint.exe",
    WINDIR / "regedit.exe", SYS32 / "cmd.exe", SYS32 / "ping.exe",
    SYS32 / "tasklist.exe", SYS32 / "where.exe", SYS32 / "hostname.exe",
    SYS32 / "xcopy.exe", SYS32 / "ipconfig.exe", SYS32 / "whoami.exe",
    SYS32 / "find.exe", SYS32 / "charmap.exe", SYS32 / "write.exe",
    SYS32 / "calc.exe", SYS32 / "certutil.exe", SYS32 / "net.exe",
    SYS32 / "attrib.exe", SYS32 / "chkdsk.exe",
    # DLLs for format/architecture diversity
    SYS32 / "kernel32.dll", SYS32 / "user32.dll", SYS32 / "gdi32.dll",
    SYS32 / "shell32.dll", SYS32 / "advapi32.dll", SYS32 / "ws2_32.dll",
    SYS32 / "ntdll.dll", SYS32 / "msvcrt.dll", SYS32 / "ole32.dll",
    SYS32 / "comctl32.dll",
    # 32-bit (PE32) binaries from SysWOW64 for format/architecture diversity
    WOW64 / "notepad.exe", WOW64 / "cmd.exe", WOW64 / "ping.exe",
    WOW64 / "kernel32.dll", WOW64 / "user32.dll", WOW64 / "msvcrt.dll",
    WOW64 / "xcopy.exe", WOW64 / "whoami.exe",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def signature_status(path: Path) -> Dict[str, str]:
    """Authenticode status via PowerShell Get-AuthenticodeSignature (read-only).

    Maps to VALID / INVALID / UNAVAILABLE / NOT_CHECKED. Never executes the file.
    """
    if os.name != "nt":
        return {"signature": "NOT_CHECKED", "detail": "non-Windows host"}
    try:
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
               f"(Get-AuthenticodeSignature -LiteralPath '{path}').Status"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        status = (out.stdout or "").strip()
    except Exception as exc:  # pragma: no cover
        return {"signature": "NOT_CHECKED", "detail": f"{type(exc).__name__}: {exc}"}
    mapping = {"Valid": "VALID", "NotSigned": "INVALID", "HashMismatch": "INVALID",
               "NotTrusted": "INVALID", "UnknownError": "UNAVAILABLE",
               "Incompatible": "UNAVAILABLE", "": "UNAVAILABLE"}
    return {"signature": mapping.get(status, "UNAVAILABLE"), "detail": status or "empty"}


def pe_metadata(path: Path) -> Optional[Dict[str, Any]]:
    """Static PE metadata via LIEF. Returns None if not a parseable PE."""
    try:
        binary = lief.PE.parse(str(path))
    except Exception:
        return None
    if binary is None:
        return None
    try:
        machine = str(binary.header.machine).split(".")[-1]
        magic = str(binary.optional_header.magic).split(".")[-1]
        chars = [str(c).split(".")[-1] for c in binary.header.characteristics_list]
        is_dll = "DLL" in chars
        n_imports = len(list(binary.imported_functions))
        return {
            "pe_format": "PE32+" if magic in ("PE32_PLUS", "PE32PLUS") else "PE32",
            "machine": machine,
            "kind": "DLL" if is_dll else "EXE",
            "section_count": len(binary.sections),
            "imported_function_count": n_imports,
            "has_signature_structure": bool(binary.has_signatures),
        }
    except Exception:
        return None


def discover(candidates: List[Path], target_min=15, target_max=30,
             check_signature=True) -> Dict[str, Any]:
    found: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    seen_sha = set()
    for path in candidates:
        if not path.exists():
            skipped.append({"filename": path.name, "reason": "not found"})
            continue
        meta = pe_metadata(path)
        if meta is None:
            skipped.append({"filename": path.name, "reason": "not a parseable PE"})
            continue
        try:
            sha = sha256_file(path)
            size = path.stat().st_size
        except Exception as exc:
            skipped.append({"filename": path.name, "reason": f"read error: {exc}"})
            continue
        if sha in seen_sha:
            skipped.append({"filename": path.name, "reason": "duplicate sha256"})
            continue
        seen_sha.add(sha)
        sig = signature_status(path) if check_signature else {"signature": "NOT_CHECKED",
                                                              "detail": "disabled"}
        found.append({
            "sample_id": f"RPE-{sha[:12]}",
            "filename": path.name,
            "source_tag": "%SystemRoot%\\System32" if "System32" in str(path) else "%SystemRoot%",
            "local_path": str(path),  # EVALUATOR-ONLY; not committed verbatim in reports
            "sha256": sha, "size_bytes": size,
            **meta,
            "signature_status": sig["signature"], "signature_detail": sig["detail"],
            "provenance": "Windows system binary (OS-provided, catalog/Authenticode signed)",
            "label": "benign",
            "label_source": "OS provenance (Microsoft-signed system binary)",
            "label_confidence": "MEDIUM-HIGH (provenance-based; not independently malware-analysed)",
            "track": "RAW_PE_E2E",
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        })
    manifest = {
        "schema_version": "task05d-sample-manifest-v1",
        "track": "RAW_PE_E2E",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(candidates),
        "n_selected": len(found),
        "n_skipped": len(skipped),
        "selection_met_min": len(found) >= target_min,
        "diversity": {
            "kinds": _count(found, "kind"),
            "pe_format": _count(found, "pe_format"),
            "machine": _count(found, "machine"),
            "signature_status": _count(found, "signature_status"),
            "size_bytes_min": min((s["size_bytes"] for s in found), default=None),
            "size_bytes_max": max((s["size_bytes"] for s in found), default=None),
        },
        "benign_label_caveat": (
            "Benign label is PROVENANCE-based (OS-provided, signed). A valid signature "
            "proves origin, not harmlessness. Do not generalise this set to real-world "
            "false-positive rates; it is a homogeneous Microsoft-signed corpus."),
        "samples": found,
        "skipped": skipped,
    }
    return manifest


def _count(rows, key):
    d = {}
    for r in rows:
        d[r.get(key)] = d.get(r.get(key), 0) + 1
    return d


def write_manifest(manifest, out_path: Path, public_path: Path):
    """Write the full (evaluator-only) manifest and a public copy without local paths."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    public = json.loads(json.dumps(manifest))
    for s in public["samples"]:
        s.pop("local_path", None)
    for s in public["skipped"]:
        s.pop("local_path", None)
    public["note"] = "Public manifest: local_path removed; see evaluator-only manifest for paths."
    public_path.write_text(json.dumps(public, indent=2), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Discover benign PE targets")
    ap.add_argument("--out", required=True, help="evaluator-only manifest (with paths)")
    ap.add_argument("--public-out", required=True, help="committable manifest (no paths)")
    ap.add_argument("--no-signature", action="store_true")
    args = ap.parse_args(argv)
    manifest = discover(CANDIDATES, check_signature=not args.no_signature)
    write_manifest(manifest, Path(args.out), Path(args.public_out))
    print(json.dumps({"selected": manifest["n_selected"], "skipped": manifest["n_skipped"],
                      "diversity": manifest["diversity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
