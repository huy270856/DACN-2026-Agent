"""Identity-leakage audit for Agent-visible context (evaluation-only).

Identity tokens come from the ORIGINAL file, evaluator-side: filename stem, original path,
PE version resources (OriginalFilename, InternalName, FileDescription, ProductName,
CompanyName) and the Authenticode signer subject. A hit is classified by WHERE it appears:

  ACCIDENTAL_METADATA     - path/case metadata/question/unknowns (should be removed by staging)
  PE_DERIVED_STATIC       - inside legitimate static evidence values (imports, header, ...);
                            NOT removed (would destroy valid evidence) -> reported as residual

Absence of hits is NOT proof of anonymity: an Agent can still recognise a well-known program
from its import profile. Report residual leakage, never "complete anonymization".
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

VERSION_KEYS = ("OriginalFilename", "InternalName", "FileDescription", "ProductName", "CompanyName")
PROGRAM_KEYS = ("OriginalFilename", "InternalName", "FileDescription")
GENERIC_PROVENANCE = ("system32", "microsoft", "windows")
MIN_TOKEN = 4


def version_strings(path: Path) -> Dict[str, str]:
    import lief
    out: Dict[str, str] = {}
    try:
        b = lief.parse(str(path))
        if b is None or not b.has_resources or not b.resources_manager.has_version:
            return out
        v = b.resources_manager.version
        v = v[0] if isinstance(v, list) else v
        for lc in v.string_file_info.langcode_items:
            for k, val in dict(lc.items).items():
                # LIEF 0.15 returns UTF-8 encoded bytes for keys/values.
                k = k.decode("utf-8", "replace") if isinstance(k, bytes) else str(k)
                val = val.decode("utf-8", "replace") if isinstance(val, bytes) else str(val)
                if k in VERSION_KEYS and val.strip():
                    out.setdefault(k, val.replace("\x00", "").strip())
    except Exception as exc:  # recorded, not hidden
        out["_error"] = f"{type(exc).__name__}: {exc}"
    return out


def authenticode(paths: List[Path]) -> Dict[str, Dict[str, str]]:
    """Read-only signature check via PowerShell Get-AuthenticodeSignature (no execution of targets)."""
    if not paths:
        return {}
    # `-Command` does not populate $args, so paths are embedded as escaped single-quoted literals.
    plist = ",".join("'" + str(p).replace("'", "''") + "'" for p in paths)
    script = ("$r=@(); foreach($p in @(" + plist + ")){ $s=Get-AuthenticodeSignature -LiteralPath $p; "
              "$r+=[pscustomobject]@{path=$p;status=[string]$s.Status;type=[string]$s.SignatureType;"
              "subject=[string]$s.SignerCertificate.Subject} }; ConvertTo-Json -InputObject $r -Compress")
    try:
        raw = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=120).stdout
        rows = json.loads(raw) if raw.strip() else []
        rows = rows if isinstance(rows, list) else [rows]
        return {r["path"]: {"status": r["status"], "type": r["type"], "subject": r["subject"]} for r in rows}
    except Exception as exc:
        return {str(p): {"status": "UNKNOWN", "type": "UNKNOWN", "subject": f"check failed: {exc}"} for p in paths}


def identity_tokens(original: Path, version: Dict[str, str] | None = None, signer: str | None = None) -> List[Dict[str, str]]:
    version = version if version is not None else version_strings(original)
    toks = [{"token": original.stem, "source": "filename_stem", "kind": "PROGRAM_IDENTITY"},
            {"token": original.name, "source": "filename", "kind": "PROGRAM_IDENTITY"},
            {"token": str(original.parent), "source": "original_directory", "kind": "PROVENANCE"}]
    for k in VERSION_KEYS:
        if version.get(k):
            kind = "PROGRAM_IDENTITY" if k in PROGRAM_KEYS else "PROVENANCE"
            toks.append({"token": version[k], "source": f"version.{k}", "kind": kind})
            if k == "OriginalFilename":
                toks.append({"token": Path(version[k]).stem, "source": "version.OriginalFilename.stem", "kind": kind})
    if signer:
        toks.append({"token": signer, "source": "authenticode_subject", "kind": "PROVENANCE"})
    for g in GENERIC_PROVENANCE:
        toks.append({"token": g, "source": "generic_provenance_word", "kind": "PROVENANCE"})
    seen, out = set(), []
    for t in toks:
        key = t["token"].lower()
        if len(key) >= MIN_TOKEN and key not in seen:
            seen.add(key); out.append(t)
    return out


def _walk(obj: Any, path: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    elif obj is not None:
        yield path, str(obj)


def scan_facts(facts: Dict[str, Any], tokens: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    hits = []
    evidence_facets = {i: e.get("facet") for i, e in enumerate(facts.get("evidence", []))}
    for path, text in _walk(facts):
        low = text.lower()
        for t in tokens:
            tok = t["token"].lower()
            if not re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])", low):
                continue
            m = re.match(r"evidence\[(\d+)\]\.value", path)
            where = "PE_DERIVED_STATIC" if m else "ACCIDENTAL_METADATA"
            hits.append({"location": path, "classification": where,
                         "facet": evidence_facets.get(int(m.group(1))) if m else None, **t})
    return hits


def summarize(hits: List[Dict[str, Any]]) -> Dict[str, Any]:
    acc = [h for h in hits if h["classification"] == "ACCIDENTAL_METADATA"]
    res = [h for h in hits if h["classification"] == "PE_DERIVED_STATIC"]
    return {"accidental_metadata_hits": len(acc),
            "accidental_program_identity_hits": sum(h["kind"] == "PROGRAM_IDENTITY" for h in acc),
            "pe_derived_residual_hits": len(res),
            "status": "FAIL_ACCIDENTAL_IDENTITY_LEAK" if any(h["kind"] == "PROGRAM_IDENTITY" for h in acc)
                      else ("PASS_WITH_PROVENANCE_RESIDUAL" if hits else "PASS_NO_TOKEN_HITS_RESIDUAL_RECOGNITION_POSSIBLE"),
            "note": "No hits does not prove anonymity; a well-known program may be recognisable from its imports."}
