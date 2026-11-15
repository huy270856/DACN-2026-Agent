"""D2 installer + tool-specific D7 validator for ONE imports analyzer."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

from d0.validate import canonical_json_bytes, digest, validate
from orchestrator.execution_adapter import make_artifact_reader, _read_stdout_payload, wire_error
from orchestrator.result_validator import ResultValidationError, validate_tool_result

TOOL_ID = "static.pe_imports_detail"
FACET = "static.pe_imports_detail"
VERSION = "0.1.0"
PROVIDER = "dacn_pe_imports"
ARGUMENTS = {"max_entries": 64}


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def install(registry, installation):
    import lief
    from orchestrator.executor import PinnedAdapter
    script = Path(__file__).with_name("import_adapter.py").resolve()
    interpreter = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    # Imported native parser and its Python entrypoint are installer-owned pins.
    paths = (interpreter, script, Path(lief.__file__).resolve(), Path(lief._lief.__file__).resolve())
    adapter = PinnedAdapter(PROVIDER, VERSION, "pe_imports_adapter", (str(interpreter), "-I", str(script)),
                            tuple((str(p), file_sha(p)) for p in paths))
    spec = {"schema_version": "d0-v1", "tool_id": TOOL_ID, "tool_version": VERSION,
            "capability": FACET, "description": "Read declared DLL/API/ordinal imports from staged PE; static capabilities only",
            "input_schema_id": "pe-imports-input-v1", "output_schema_id": "pe-imports-output-v1",
            "provider": adapter.provider(),
            "effects": {"reads_target": True, "executes_foreign_code": False, "writes_filesystem": False,
                        "mutates_target": False, "requires_human_approval": False, "cleanup_required": False},
            "limits": {"timeout_ms": 10000, "max_output_bytes": 65536,
                       "max_artifact_bytes": 131072, "max_concurrency": 1},
            "supported_targets": ["FILE"], "enabled": True}
    registry.register_tool(spec)
    installation.install(provider_id=PROVIDER, version=VERSION, adapter_id="pe_imports_adapter",
                         command=adapter.command, pins=list(adapter.pins))
    return spec


def normalize(payload, receipt, call, spec, *, error=None, artifact_reader=None):
    payload, receipt, call, spec = deepcopy((payload, receipt, call, spec))
    def reject(code, message):
        raise ResultValidationError(code, message)
    try:
        for name, value in (("execution_receipt", receipt), ("tool_call", call), ("tool_spec", spec)):
            validate(name, value)
        if (spec["tool_id"], spec["input_schema_id"], spec["output_schema_id"]) != (
                TOOL_ID, "pe-imports-input-v1", "pe-imports-output-v1"):
            raise ValueError("Wrong imports contracts")
        validate("pe-imports-input-v1", call["arguments"])
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
            validate("pe-imports-output-v1", payload)
            encoded = canonical_json_bytes(payload)
        except ValueError as exc:
            reject("RESULT_INVALID", str(exc))
        if len(encoded) > min(call["budget"]["max_output_bytes"], spec["limits"]["max_output_bytes"]):
            reject("BUDGET_EXCEEDED", "Imports payload exceeds output budget")
        binding = receipt["target_binding"]
        requested, observed = call["target_ref"], binding["observed_ref"]
        if binding["status"] != "VERIFIED" or requested["kind"] != "FILE" or observed["kind"] != "FILE":
            reject("TARGET_CHANGED", "Imports requires verified file binding")
        if not requested.get("verified_digest") or not observed.get("verified_digest"):
            reject("TARGET_CHANGED", "Missing file digests")
        if not payload["target_sha256"] == requested["verified_digest"]["value"] == observed["verified_digest"]["value"]:
            reject("TARGET_CHANGED", "Imports hash differs from admitted target")
        count = len(payload["entries"])
        if (payload["returned_entries"] != count or payload["total_entries"] < count
                or payload["truncated"] != (payload["total_entries"] > count)
                or count != min(payload["total_entries"], 64)):
            reject("RESULT_INVALID", "Inconsistent imports counts/coverage")
        if any((e["symbol"] is None) == (e["ordinal"] is None) for e in payload["entries"]):
            reject("RESULT_INVALID", "Import requires exactly one symbol or ordinal")
        observations.append({"facet": FACET, "status": "SUCCESS",
                             "coverage": "PARTIAL" if payload["truncated"] else "COMPLETE",
                             "value": payload, "limitations": payload["limitations"],
                             "content_origin": "provider_output", "trust_level": "UNTRUSTED_CONTENT", "artifact_ref": None})
    result = {"schema_version": "d0-v1", **{k: receipt[k] for k in ("run_id", "call_id", "case_id", "tool_id", "tool_version", "provider")},
              "target_ref": call["target_ref"], "status": status, "observations": observations,
              "receipt_sha256": digest(receipt), "raw_artifacts": [], "error": error}
    return validate_tool_result(result, receipt, call, spec, artifact_reader=artifact_reader)


def from_execution(output, call, spec, *, artifact_root):
    reader = make_artifact_reader(artifact_root)
    payload = _read_stdout_payload(output, reader) if output.receipt["outcome"] == "SUCCESS" else None
    return normalize(payload, output.receipt, call, spec, error=wire_error(output.error), artifact_reader=reader)
