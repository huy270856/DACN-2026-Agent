"""Independent EMBER2018 feature-version-2 vectorizer (2381 dimensions).

This is an INDEPENDENT reimplementation of the official EMBER v2 feature
*specification* (elastic/ember `features.py`, commit d97a0b5, feature_version=2).
It converts an already-extracted raw feature *record* (the JSON object stored in
each line of the EMBER `*_features.jsonl` files, or produced by `pe_extractor`
from raw PE bytes) into a fixed 2381-dim float32 vector.

Why a reimplementation and not the upstream package:
  * TASK 05A requires an independent pipeline whose results come from this run.
  * The record -> vector transform depends ONLY on numpy and
    sklearn.feature_extraction.FeatureHasher (a deterministic murmurhash3). It
    does not touch LIEF, so this reimplementation produces vectors that are
    numerically identical to the official extractor for the same input record.
    That parity is an empirically testable claim (see tests + the official-model
    cross-check), not an assumption.

Feature groups and the exact concatenation order (official v2):
    histogram        256
    byteentropy      256
    strings          104
    general           10
    header            62
    section          255
    imports         1280
    exports          128
    datadirectories   30   (appended for feature_version 2)
    ----------------------
    total           2381
"""
from __future__ import annotations

import numpy as np
from sklearn.feature_extraction import FeatureHasher

FEATURE_VERSION = 2
FEATURE_COUNT = 2381

# (name, dimension) in concatenation order. This ordering is part of the contract
# and is asserted by the unit tests.
GROUP_ORDER = (
    ("histogram", 256),
    ("byteentropy", 256),
    ("strings", 104),
    ("general", 10),
    ("header", 62),
    ("section", 255),
    ("imports", 1280),
    ("exports", 128),
    ("datadirectories", 30),
)

# Byte offset where each group begins in the 2381 vector (useful for diagnostics).
GROUP_OFFSETS = {}
_off = 0
for _name, _dim in GROUP_ORDER:
    GROUP_OFFSETS[_name] = (_off, _off + _dim)
    _off += _dim
assert _off == FEATURE_COUNT, _off


def _hasher(n, input_type):
    # alternate_sign defaults to True in sklearn, matching upstream EMBER.
    return FeatureHasher(n, input_type=input_type)


# --- per-group transforms (mirror official process_raw_features exactly) --------

def _histogram(raw):
    counts = np.array(raw, dtype=np.float32)
    total = counts.sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        return counts / total  # 0/0 -> nan is caught by the finite check downstream


def _byteentropy(raw):
    counts = np.array(raw, dtype=np.float32)
    total = counts.sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        return counts / total


def _strings(raw):
    hist_divisor = float(raw["printables"]) if raw["printables"] > 0 else 1.0
    return np.hstack([
        raw["numstrings"],
        raw["avlength"],
        raw["printables"],
        np.asarray(raw["printabledist"]) / hist_divisor,  # 96
        raw["entropy"],
        raw["paths"],
        raw["urls"],
        raw["registry"],
        raw["MZ"],
    ]).astype(np.float32)


def _general(raw):
    return np.asarray([
        raw["size"], raw["vsize"], raw["has_debug"], raw["exports"], raw["imports"],
        raw["has_relocations"], raw["has_resources"], raw["has_signature"],
        raw["has_tls"], raw["symbols"],
    ], dtype=np.float32)


def _header(raw):
    coff = raw["coff"]
    opt = raw["optional"]
    return np.hstack([
        coff["timestamp"],
        _hasher(10, "string").transform([[coff["machine"]]]).toarray()[0],
        _hasher(10, "string").transform([coff["characteristics"]]).toarray()[0],
        _hasher(10, "string").transform([[opt["subsystem"]]]).toarray()[0],
        _hasher(10, "string").transform([opt["dll_characteristics"]]).toarray()[0],
        _hasher(10, "string").transform([[opt["magic"]]]).toarray()[0],
        opt["major_image_version"],
        opt["minor_image_version"],
        opt["major_linker_version"],
        opt["minor_linker_version"],
        opt["major_operating_system_version"],
        opt["minor_operating_system_version"],
        opt["major_subsystem_version"],
        opt["minor_subsystem_version"],
        opt["sizeof_code"],
        opt["sizeof_headers"],
        opt["sizeof_heap_commit"],
    ]).astype(np.float32)


def _section(raw):
    sections = raw["sections"]
    entry = raw["entry"]
    general = [
        len(sections),
        sum(1 for s in sections if s["size"] == 0),
        sum(1 for s in sections if s["name"] == ""),
        sum(1 for s in sections if "MEM_READ" in s["props"] and "MEM_EXECUTE" in s["props"]),
        sum(1 for s in sections if "MEM_WRITE" in s["props"]),
    ]
    section_sizes = [(s["name"], s["size"]) for s in sections]
    section_sizes_hashed = _hasher(50, "pair").transform([section_sizes]).toarray()[0]
    section_entropy = [(s["name"], s["entropy"]) for s in sections]
    section_entropy_hashed = _hasher(50, "pair").transform([section_entropy]).toarray()[0]
    section_vsize = [(s["name"], s["vsize"]) for s in sections]
    section_vsize_hashed = _hasher(50, "pair").transform([section_vsize]).toarray()[0]
    # NOTE: upstream passes the entry *string* directly to FeatureHasher, so old
    # sklearn iterated its individual characters as tokens. Modern sklearn rejects
    # a bare string, so we pass list(entry) to reproduce the exact same character
    # tokenisation -> bit-for-bit parity with the official v2 vectors.
    entry_name_hashed = _hasher(50, "string").transform([list(entry)]).toarray()[0]
    characteristics = [p for s in sections for p in s["props"] if s["name"] == entry]
    characteristics_hashed = _hasher(50, "string").transform([characteristics]).toarray()[0]
    return np.hstack([
        general, section_sizes_hashed, section_entropy_hashed, section_vsize_hashed,
        entry_name_hashed, characteristics_hashed,
    ]).astype(np.float32)


def _imports(raw):
    libraries = list(set(l.lower() for l in raw.keys()))
    libraries_hashed = _hasher(256, "string").transform([libraries]).toarray()[0]
    imports = [lib.lower() + ":" + e for lib, elist in raw.items() for e in elist]
    imports_hashed = _hasher(1024, "string").transform([imports]).toarray()[0]
    return np.hstack([libraries_hashed, imports_hashed]).astype(np.float32)


def _exports(raw):
    return _hasher(128, "string").transform([raw]).toarray()[0].astype(np.float32)


_DD_COUNT = 15


def _datadirectories(raw):
    features = np.zeros(2 * _DD_COUNT, dtype=np.float32)
    for i in range(_DD_COUNT):
        if i < len(raw):
            features[2 * i] = raw[i]["size"]
            features[2 * i + 1] = raw[i]["virtual_address"]
    return features


_GROUP_FUNCS = {
    "histogram": _histogram,
    "byteentropy": _byteentropy,
    "strings": _strings,
    "general": _general,
    "header": _header,
    "section": _section,
    "imports": _imports,
    "exports": _exports,
    "datadirectories": _datadirectories,
}


class FeatureExtractionError(ValueError):
    """Raised when a raw record cannot be turned into a valid 2381-dim vector."""


def process_raw_record(record, check_finite=True):
    """Transform one raw feature record into a 2381-dim float32 vector.

    Parameters
    ----------
    record : dict
        Must contain every key in GROUP_ORDER with the official v2 shape.
    check_finite : bool
        When True (default) a non-finite result raises FeatureExtractionError.
        We never silently emit a zero vector on failure (TASK 05A requirement).

    Raises
    ------
    FeatureExtractionError on missing groups, malformed groups, or non-finite
    output. The caller decides how to account for the failure; this function
    does not fabricate a default vector.
    """
    parts = []
    for name, dim in GROUP_ORDER:
        if name not in record:
            raise FeatureExtractionError(f"missing feature group: {name!r}")
        try:
            vec = _GROUP_FUNCS[name](record[name])
        except FeatureExtractionError:
            raise
        except Exception as exc:  # malformed group content
            raise FeatureExtractionError(f"group {name!r} failed: {exc!r}") from exc
        vec = np.asarray(vec, dtype=np.float32)
        if vec.shape[0] != dim:
            raise FeatureExtractionError(
                f"group {name!r} produced {vec.shape[0]} values, expected {dim}")
        parts.append(vec)

    out = np.hstack(parts).astype(np.float32)
    if out.shape[0] != FEATURE_COUNT:
        raise FeatureExtractionError(
            f"assembled {out.shape[0]} features, expected {FEATURE_COUNT}")
    if check_finite and not np.all(np.isfinite(out)):
        n_bad = int((~np.isfinite(out)).sum())
        raise FeatureExtractionError(
            f"{n_bad} non-finite feature value(s) in assembled vector")
    return out


def vectorize_many(records, check_finite=True):
    """Vectorize an iterable of records -> (n, 2381) float32 array."""
    rows = [process_raw_record(r, check_finite=check_finite) for r in records]
    if not rows:
        return np.empty((0, FEATURE_COUNT), dtype=np.float32)
    return np.vstack(rows).astype(np.float32)
