"""TASK 07B: D2 installer + tool-specific D7 validator for `static.pe_imports_table` 0.1.0.

Separate tool/provider from v3's `static.pe_imports_detail` (unchanged). Read-only effects; the
D4 allowlist entry is added explicitly by the v4 backend (dacn.investigation, opt-in flag).
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

from d0.validate import canonical_json_bytes, digest, validate
from orchestrator.execution_adapter import make_artifact_reader, _read_stdout_payload, wire_error
from orchestrator.result_validator import ResultValidationError, validate_tool_result

from . import imports_table_adapter as adapter_mod

TOOL_ID = "static.pe_imports_table"
FACET = "static.pe_imports_table"
VERSION = "0.1.0"
PROVIDER = "dacn_pe_imports_table"
ADAPTER_ID = "pe_imports_table_adapter"
ARGUMENTS = {"max_entries": 1024}
INPUT_SCHEMA, OUTPUT_SCHEMA = "pe-imports-table-input-v1", "pe-imports-table-output-v1"
LIMITS = {"timeout_ms": 15000, "max_output_bytes": 131072, "max_artifact_bytes": 262144, "max_concurrency": 1}


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pinned_table():
    """(table dict, lowercase lookup, canonical digest) of the pinned ordinal table."""
    table, lookup = adapter_mod.load_ordinal_table()
    return table, lookup, digest(table)


def install(registry, installation):
    import lief
    from orchestrator.executor import PinnedAdapter
    script = Path(adapter_mod.__file__).resolve()
    interpreter = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    paths = (interpreter, script, Path(lief.__file__).resolve(), Path(lief._lief.__file__).resolve(),
             adapter_mod.TABLE_PATH.resolve())
    adapter = PinnedAdapter(PROVIDER, VERSION, ADAPTER_ID, (str(interpreter), "-I", str(script)),
                            tuple((str(p), file_sha(p)) for p in paths))
    spec = {"schema_version": "d0-v1", "tool_id": TOOL_ID, "tool_version": VERSION, "capability": FACET,
            "description": "Read the full declared DLL/API/ordinal import table (compact, with library index) from staged PE; static capabilities only",
            "input_schema_id": INPUT_SCHEMA, "output_schema_id": OUTPUT_SCHEMA, "provider": adapter.provider(),
            "effects": {"reads_target": True, "executes_foreign_code": False, "writes_filesystem": False,
                        "mutates_target": False, "requires_human_approval": False, "cleanup_required": False},
            "limits": dict(LIMITS), "supported_targets": ["FILE"], "enabled": True}
    registry.register_tool(spec)
    installation.install(provider_id=PROVIDER, version=VERSION, adapter_id=ADAPTER_ID,
                         command=adapter.command, pins=list(adapter.pins))
    return spec


def check_payload(payload):
    """Cross-field D7 rules beyond JSON Schema. Raises ValueError(message)."""
    entries, libs = payload["entries"], payload["libraries"]
    n = len(entries)
    if payload["returned_entries"] != n or payload["total_entries"] < n:
        raise ValueError("Inconsistent returned/total counts")
    if payload["truncated"] != (payload["total_entries"] > n):
        raise ValueError("truncated flag inconsistent with counts")
    reason = payload["truncation_reason"]
    if not payload["truncated"] and reason is not None:
        raise ValueError("truncation_reason without truncation")
    if payload["truncated"]:
        if reason == "MAX_ENTRIES" and n != adapter_mod.MAX_ENTRIES:
            raise ValueError("MAX_ENTRIES truncation must return exactly the entry cap")
        if reason not in ("MAX_ENTRIES", "OUTPUT_BYTES"):
            raise ValueError("Truncated table requires a truncation_reason")
    if sum(l["declared_count"] for l in libs) != payload["total_entries"]:
        raise ValueError("Library index declared counts do not sum to total_entries")
    # Library blocks must tile [0, n) contiguously, in order, and match each entry's block index.
    cursor = 0
    for li, lib in enumerate(libs):
        rc = lib["returned_count"]
        if rc > lib["declared_count"]:
            raise ValueError("Library returned_count exceeds declared_count")
        if rc == 0:
            if lib["first_index"] is not None or lib["last_index"] is not None:
                raise ValueError("Empty library block must have null indices")
            continue
        if lib["first_index"] != cursor or lib["last_index"] != cursor + rc - 1:
            raise ValueError("Library index does not tile entries contiguously")
        for e in entries[cursor:cursor + rc]:
            if e[0] != li or e[3] != lib["delay"]:
                raise ValueError("Entry library/delay does not match library index")
        cursor += rc
    if cursor != n:
        raise ValueError("Library index does not cover every returned entry")
    table, lookup, table_digest = pinned_table()
    if payload["ordinal_table_sha256"] != table_digest or payload["ordinal_table_version"] != table["table_version"]:
        raise ValueError("Ordinal table digest/version differs from the pinned table")
    any_resolved = False
    for e in entries:
        lib_idx, symbol, ordinal, _delay, resolved = e
        if (symbol is None) == (ordinal is None):
            raise ValueError("Import requires exactly one symbol or ordinal")
        lname = libs[lib_idx]["name"].lower()
        expected = lookup.get(lname, {}).get(ordinal) if symbol is None else None
        if resolved != expected:
            raise ValueError("resolved_symbol differs from the pinned ordinal table")
        any_resolved |= resolved is not None
    if any_resolved != (payload["resolution_source"] is not None):
        raise ValueError("resolution_source must be present exactly when an ordinal was resolved")


def normalize(payload, receipt, call, spec, *, error=None, artifact_reader=None):
    payload, receipt, call, spec = deepcopy((payload, receipt, call, spec))

    def reject(code, message):
        raise ResultValidationError(code, message)
    try:
        for name, value in (("execution_receipt", receipt), ("tool_call", call), ("tool_spec", spec)):
            validate(name, value)
        if (spec["tool_id"], spec["input_schema_id"], spec["output_schema_id"]) != (TOOL_ID, INPUT_SCHEMA, OUTPUT_SCHEMA):
            raise ValueError("Wrong imports table contracts")
        validate(INPUT_SCHEMA, call["arguments"])
    except ValueError as exc:
        reject("RESULT_INVALID", str(exc))
    status = receipt["outcome"]
    if status == "SUCCESS" and (payload is None or error is not None):
        reject("RESULT_INVALID", "Successful analyzer requires payload without error")
    if status != "SUCCESS" and payload is not None:
        reject("RESULT_INVALID", "Failed analyzer cannot carry successful observations")
    observations = []
    if payload is not None:
        try:
            validate(OUTPUT_SCHEMA, payload)
            encoded = canonical_json_bytes(payload)
        except ValueError as exc:
            reject("RESULT_INVALID", str(exc))
        if len(encoded) > min(call["budget"]["max_output_bytes"], spec["limits"]["max_output_bytes"]):
            reject("BUDGET_EXCEEDED", "Imports table payload exceeds output budget")
        binding = receipt["target_binding"]
        requested, observed = call["target_ref"], binding["observed_ref"]
        if binding["status"] != "VERIFIED" or requested["kind"] != "FILE" or observed["kind"] != "FILE":
            reject("TARGET_CHANGED", "Imports table requires verified file binding")
        if not requested.get("verified_digest") or not observed.get("verified_digest"):
            reject("TARGET_CHANGED", "Missing file digests")
        if not payload["target_sha256"] == requested["verified_digest"]["value"] == observed["verified_digest"]["value"]:
            reject("TARGET_CHANGED", "Imports table hash differs from admitted target")
        try:
            check_payload(payload)
        except ValueError as exc:
            reject("RESULT_INVALID", str(exc))
        observations.append({"facet": FACET, "status": "SUCCESS",
                             "coverage": "PARTIAL" if payload["truncated"] else "COMPLETE",
                             "value": payload, "limitations": payload["limitations"],
                             "content_origin": "provider_output", "trust_level": "UNTRUSTED_CONTENT",
                             "artifact_ref": None})
    result = {"schema_version": "d0-v1",
              **{k: receipt[k] for k in ("run_id", "call_id", "case_id", "tool_id", "tool_version", "provider")},
              "target_ref": call["target_ref"], "status": status, "observations": observations,
              "receipt_sha256": digest(receipt), "raw_artifacts": [], "error": error}
    return validate_tool_result(result, receipt, call, spec, artifact_reader=artifact_reader)


def from_execution(output, call, spec, *, artifact_root):
    reader = make_artifact_reader(artifact_root)
    payload = _read_stdout_payload(output, reader) if output.receipt["outcome"] == "SUCCESS" else None
    return normalize(payload, output.receipt, call, spec, error=wire_error(output.error), artifact_reader=reader)
