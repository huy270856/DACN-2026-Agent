"""Evidence projection for FEATURE_RECORD_REPLAY.

Turns an official EMBER2018 v2 feature *record* into a small set of provenance-
tagged, static-only evidence observations the agent may reason over. Hard rules:

  * Only metadata/feature groups that actually exist in the record are projected.
  * No raw 2381-float vector is exposed.
  * No runtime / network / process-behaviour observation is fabricated.
  * `has_signature` means a signature STRUCTURE is present, NOT that it is valid
    or trusted (no cryptographic verification is performed); labelled as such.
  * Each observation carries a deterministic evidence_id and FEATURE_RECORD_REPLAY
    provenance, so hallucinated / cross-case evidence IDs are detectable.

Ground truth label is NEVER part of a projection.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping

DATASET = "EMBER2018 feature version 2 (feature records)"
TRACK = "FEATURE_RECORD_REPLAY"

MAX_SECTIONS = 40
MAX_LIBRARIES = 30
MAX_IMPORT_FUNCS = 60


def evidence_id(record_sha: str, facet: str) -> str:
    return "EV-" + hashlib.sha256(f"{record_sha}:{facet}".encode()).hexdigest()[:24]


def _obs(record_sha: str, facet: str, value: Any, limitations=None) -> Dict[str, Any]:
    return {
        "evidence_id": evidence_id(record_sha, facet),
        "facet": facet,
        "status": "SUCCESS",
        "value": value,
        "trust_level": "UNTRUSTED_CONTENT",
        "content_origin": "provider_output",
        "limitations": limitations or [],
        "provenance": {"track": TRACK, "record_sha256": record_sha, "dataset": DATASET},
        "artifact_ref": None,
    }


def project_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Return {target_sha256, observations[]} derived ONLY from present fields."""
    sha = record.get("sha256") or ""
    obs: List[Dict[str, Any]] = []

    g = record.get("general") or {}
    if g:
        obs.append(_obs(sha, "static.general_file_info", {
            "size": g.get("size"), "virtual_size": g.get("vsize"),
            "has_debug": g.get("has_debug"),
            "exported_functions": g.get("exports"),
            "imported_functions": g.get("imports"),
            "has_relocations": g.get("has_relocations"),
            "has_resources": g.get("has_resources"),
            "has_signature_structure": g.get("has_signature"),
            "has_tls": g.get("has_tls"), "symbols": g.get("symbols"),
        }, limitations=[
            "has_signature_structure = a signature is PRESENT in the PE; it is NOT "
            "verified/validated. No cryptographic trust is established."]))

    h = record.get("header") or {}
    coff = h.get("coff") or {}
    opt = h.get("optional") or {}
    if coff or opt:
        obs.append(_obs(sha, "static.pe_header", {
            "machine": coff.get("machine"),
            "coff_characteristics": coff.get("characteristics"),
            "timestamp": coff.get("timestamp"),
            "subsystem": opt.get("subsystem"), "magic": opt.get("magic"),
            "dll_characteristics": opt.get("dll_characteristics"),
            "major_subsystem_version": opt.get("major_subsystem_version"),
        }, limitations=["timestamp is the declared COFF timestamp; it can be forged."]))

    sec = record.get("section") or {}
    sections = sec.get("sections") or []
    if sections:
        trimmed = [{"name": s.get("name"), "size": s.get("size"),
                    "entropy": round(float(s.get("entropy", 0.0)), 3),
                    "virtual_size": s.get("vsize")}
                   for s in sections[:MAX_SECTIONS]]
        high_entropy = sum(1 for s in sections if float(s.get("entropy", 0)) >= 7.0)
        wx = sum(1 for s in sections
                 if "MEM_WRITE" in (s.get("props") or []) and "MEM_EXECUTE" in (s.get("props") or []))
        obs.append(_obs(sha, "static.sections", {
            "entry_section": sec.get("entry"),
            "section_count": len(sections),
            "sections": trimmed,
            "sections_truncated": len(sections) > MAX_SECTIONS,
            "high_entropy_section_count_ge7": high_entropy,
            "writable_and_executable_section_count": wx,
        }, limitations=[
            "High entropy may indicate packing/compression/encryption but is NOT proof "
            "of maliciousness; benign packers exist."]))

    imp = record.get("imports") or {}
    if imp:
        libs = list(imp.keys())[:MAX_LIBRARIES]
        funcs: List[str] = []
        for lib in imp:
            for fn in imp[lib]:
                funcs.append(f"{lib}:{fn}")
                if len(funcs) >= MAX_IMPORT_FUNCS:
                    break
            if len(funcs) >= MAX_IMPORT_FUNCS:
                break
        total_funcs = sum(len(v) for v in imp.values())
        obs.append(_obs(sha, "static.imports_summary", {
            "library_count": len(imp), "libraries": libs,
            "total_imported_functions": total_funcs,
            "sampled_imports": funcs,
            "imports_truncated": total_funcs > len(funcs),
        }, limitations=[
            "Imports indicate capabilities the binary CAN use statically; they do NOT "
            "prove the behaviour was executed."]))

    exports = record.get("exports") or []
    if exports:
        obs.append(_obs(sha, "static.exports_summary", {
            "export_count": len(exports), "sampled_exports": exports[:30]}))

    st = record.get("strings") or {}
    if st:
        obs.append(_obs(sha, "static.strings_summary", {
            "num_strings": st.get("numstrings"),
            "avg_length": round(float(st.get("avlength", 0.0)), 2),
            "string_entropy": round(float(st.get("entropy", 0.0)), 3),
            "c_drive_path_occurrences": st.get("paths"),
            "url_occurrences": st.get("urls"),
            "registry_key_occurrences": st.get("registry"),
            "embedded_MZ_occurrences": st.get("MZ"),
        }, limitations=[
            "These are COUNTS of printable-string patterns, not observed behaviour. "
            "A URL/registry/MZ count is a static indicator only."]))

    dd = record.get("datadirectories") or []
    if dd:
        names = {"EXPORT_TABLE": 0, "IMPORT_TABLE": 1, "RESOURCE_TABLE": 2,
                 "CERTIFICATE_TABLE": 4, "BASE_RELOCATION_TABLE": 5, "DEBUG": 6,
                 "TLS_TABLE": 9, "IAT": 12}
        present = {name: (dd[i].get("size", 0) > 0) for name, i in names.items() if i < len(dd)}
        obs.append(_obs(sha, "static.data_directories", {
            "present_nonempty": present,
            "has_certificate_table": present.get("CERTIFICATE_TABLE", False),
        }, limitations=[
            "CERTIFICATE_TABLE presence = a signature blob exists; NOT a trust verdict."]))

    return {"target_sha256": sha, "observations": obs}


def prediction_observation(record_sha: str, prediction_payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Wrap the LightGBM static prediction as an evidence observation."""
    o = _obs(record_sha, "static.pe_malware_prediction", dict(prediction_payload),
             limitations=list(prediction_payload.get("limitations", [])))
    return o
