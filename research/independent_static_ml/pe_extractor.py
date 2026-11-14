"""Read-only raw-PE -> EMBER v2 raw features -> 2381 vector (inference path).

This mirrors the official EMBER v2 `raw_features` extraction but uses the modern
LIEF 0.15 API. It is INFERENCE ONLY and never executes the input binary: it reads
the bytes and parses the PE structure statically with LIEF.

Important honesty note (NOT claimed as parity):
    The EMBER2018 v2 *training* records were produced with LIEF 0.9.0. This path
    uses LIEF 0.15.1. The official EMBER code itself warns that different LIEF
    versions can cause slight feature inconsistencies. We therefore DO NOT claim
    that vectors from this path are byte-identical to the training vectors. We do
    guarantee: correct 2381 dimensionality, finite values, deterministic output,
    and a parser status that is never silently replaced by a zero vector.
"""
from __future__ import annotations

import hashlib

import numpy as np

try:
    import lief
    lief.logging.disable()
    _LIEF_VERSION = lief.__version__
except Exception as exc:  # pragma: no cover
    lief = None
    _LIEF_VERSION = f"unavailable: {exc!r}"

from . import ember_v2


def _props(section):
    return [str(c).split(".")[-1] for c in section.characteristics_lists]


def _raw_section(binary):
    if binary is None:
        return {"entry": "", "sections": []}
    entry_section = ""
    try:
        rva = binary.entrypoint - binary.imagebase
        sec = binary.section_from_rva(rva)
        if sec is not None:
            entry_section = sec.name
    except Exception:
        entry_section = ""
    if entry_section == "":
        for s in binary.sections:
            if "MEM_EXECUTE" in _props(s):
                entry_section = s.name
                break
    return {
        "entry": entry_section,
        "sections": [{
            "name": s.name,
            "size": s.size,
            "entropy": float(s.entropy),
            "vsize": s.virtual_size,
            "props": _props(s),
        } for s in binary.sections],
    }


def _raw_imports(binary):
    imports = {}
    if binary is None:
        return imports
    for lib in binary.imports:
        if lib.name not in imports:
            imports[lib.name] = []
        for entry in lib.entries:
            if entry.is_ordinal:
                imports[lib.name].append("ordinal" + str(entry.ordinal))
            else:
                name = entry.name or ""
                imports[lib.name].append(name[:10000])
    return imports


def _raw_exports(binary):
    if binary is None:
        return []
    out = []
    for export in binary.exported_functions:
        name = getattr(export, "name", export)
        out.append((name or "")[:10000])
    return out


def _raw_general(binary, size):
    if binary is None:
        return {"size": size, "vsize": 0, "has_debug": 0, "exports": 0, "imports": 0,
                "has_relocations": 0, "has_resources": 0, "has_signature": 0,
                "has_tls": 0, "symbols": 0}
    return {
        "size": size,
        "vsize": int(getattr(binary, "virtual_size", 0)),
        "has_debug": int(binary.has_debug),
        "exports": len(binary.exported_functions),
        "imports": len(binary.imported_functions),
        "has_relocations": int(binary.has_relocations),
        "has_resources": int(binary.has_resources),
        "has_signature": int(binary.has_signatures),
        "has_tls": int(binary.has_tls),
        "symbols": len(binary.symbols),
    }


def _raw_header(binary):
    raw = {"coff": {"timestamp": 0, "machine": "", "characteristics": []},
           "optional": {"subsystem": "", "dll_characteristics": [], "magic": "",
                        "major_image_version": 0, "minor_image_version": 0,
                        "major_linker_version": 0, "minor_linker_version": 0,
                        "major_operating_system_version": 0,
                        "minor_operating_system_version": 0,
                        "major_subsystem_version": 0, "minor_subsystem_version": 0,
                        "sizeof_code": 0, "sizeof_headers": 0, "sizeof_heap_commit": 0}}
    if binary is None:
        return raw
    h = binary.header
    oh = binary.optional_header
    raw["coff"]["timestamp"] = h.time_date_stamps
    raw["coff"]["machine"] = str(h.machine).split(".")[-1]
    raw["coff"]["characteristics"] = [str(c).split(".")[-1] for c in h.characteristics_list]
    raw["optional"]["subsystem"] = str(oh.subsystem).split(".")[-1]
    raw["optional"]["dll_characteristics"] = [str(c).split(".")[-1] for c in oh.dll_characteristics_lists]
    raw["optional"]["magic"] = str(oh.magic).split(".")[-1]
    for f in ("major_image_version", "minor_image_version", "major_linker_version",
              "minor_linker_version", "major_operating_system_version",
              "minor_operating_system_version", "major_subsystem_version",
              "minor_subsystem_version", "sizeof_code", "sizeof_headers",
              "sizeof_heap_commit"):
        raw["optional"][f] = getattr(oh, f)
    return raw


def _raw_datadirectories(binary):
    if binary is None:
        return []
    out = []
    for dd in binary.data_directories:
        out.append({
            "name": str(dd.type).split(".")[-1],
            "size": dd.size,
            "virtual_address": dd.rva,
        })
    return out


def _raw_histogram(bytez):
    counts = np.bincount(np.frombuffer(bytez, dtype=np.uint8), minlength=256)
    return counts.tolist()


def _raw_byteentropy(bytez, step=1024, window=2048):
    output = np.zeros((16, 16), dtype=np.int32)
    a = np.frombuffer(bytez, dtype=np.uint8)

    def bin_counts(block):
        c = np.bincount(block >> 4, minlength=16)
        p = c.astype(np.float32) / window
        wh = np.where(c)[0]
        H = np.sum(-p[wh] * np.log2(p[wh])) * 2
        Hbin = int(H * 2)
        if Hbin == 16:
            Hbin = 15
        return Hbin, c

    if a.shape[0] < window:
        Hbin, c = bin_counts(a)
        output[Hbin, :] += c
    else:
        shape = a.shape[:-1] + (a.shape[-1] - window + 1, window)
        strides = a.strides + (a.strides[-1],)
        blocks = np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)[::step, :]
        for block in blocks:
            Hbin, c = bin_counts(block)
            output[Hbin, :] += c
    return output.flatten().tolist()


import re as _re
_ALLSTRINGS = _re.compile(b"[\x20-\x7f]{5,}")
_PATHS = _re.compile(b"c:\\\\", _re.IGNORECASE)
_URLS = _re.compile(b"https?://", _re.IGNORECASE)
_REGISTRY = _re.compile(b"HKEY_")
_MZ = _re.compile(b"MZ")


def _raw_strings(bytez):
    allstrings = _ALLSTRINGS.findall(bytez)
    if allstrings:
        string_lengths = [len(s) for s in allstrings]
        avlength = sum(string_lengths) / len(string_lengths)
        as_shifted = [b - 0x20 for b in b"".join(allstrings)]
        c = np.bincount(as_shifted, minlength=96)
        csum = c.sum()
        p = c.astype(np.float32) / csum
        wh = np.where(c)[0]
        H = float(np.sum(-p[wh] * np.log2(p[wh])))
    else:
        avlength = 0
        c = np.zeros((96,), dtype=np.float32)
        H = 0
        csum = 0
    return {
        "numstrings": len(allstrings), "avlength": avlength,
        "printabledist": c.tolist(), "printables": int(csum), "entropy": float(H),
        "paths": len(_PATHS.findall(bytez)), "urls": len(_URLS.findall(bytez)),
        "registry": len(_REGISTRY.findall(bytez)), "MZ": len(_MZ.findall(bytez)),
    }


class PEExtractResult:
    def __init__(self, sha256, status, vector=None, raw=None, error=None, warnings=None):
        self.sha256 = sha256
        self.status = status          # "OK" | "PARSED_NULL" | "MALFORMED" | "ERROR"
        self.vector = vector          # np.ndarray[2381] or None
        self.raw = raw
        self.error = error
        self.warnings = warnings or []


def extract_from_bytes(bytez):
    """Static read-only extraction. Returns PEExtractResult.

    Never executes the input. On parse failure the status reflects it and the
    vector is None (we never fabricate a zero vector)."""
    sha256 = hashlib.sha256(bytez).hexdigest()
    if lief is None:
        return PEExtractResult(sha256, "ERROR", error=f"LIEF unavailable: {_LIEF_VERSION}")
    warnings = []
    binary = None
    status = "OK"
    try:
        binary = lief.PE.parse(list(bytez))
    except Exception as exc:
        return PEExtractResult(sha256, "MALFORMED", error=f"lief parse error: {exc!r}")
    if binary is None:
        # Not a parseable PE (truncated / not a PE). EMBER still defines a vector
        # for the "lief_binary is None" case, but for inference we surface it.
        status = "PARSED_NULL"
        warnings.append("LIEF returned no binary (not a valid/complete PE)")

    try:
        raw = {
            "sha256": sha256,
            "histogram": _raw_histogram(bytez),
            "byteentropy": _raw_byteentropy(bytez),
            "strings": _raw_strings(bytez),
            "general": _raw_general(binary, len(bytez)),
            "header": _raw_header(binary),
            "section": _raw_section(binary),
            "imports": _raw_imports(binary),
            "exports": _raw_exports(binary),
            "datadirectories": _raw_datadirectories(binary),
        }
        vec = ember_v2.process_raw_record(raw)
    except ember_v2.FeatureExtractionError as exc:
        return PEExtractResult(sha256, "MALFORMED", raw=None,
                               error=f"feature extraction failed: {exc}")
    except Exception as exc:
        return PEExtractResult(sha256, "ERROR", error=f"unexpected: {exc!r}")
    return PEExtractResult(sha256, status, vector=vec, raw=raw, warnings=warnings)


def extract_from_file(path):
    with open(path, "rb") as f:
        bytez = f.read()
    return extract_from_bytes(bytez)


def lief_version():
    return _LIEF_VERSION
