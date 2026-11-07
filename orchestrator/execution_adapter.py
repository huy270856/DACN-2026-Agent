"""D5/D6 ExecutionOutput -> D7 ToolResult adapter.

The D5 executor (``orchestrator.executor.ToolExecutor.execute``) returns an
``ExecutionOutput(receipt, raw_artifacts, error, exit_code, run_directory)``.
D7 (``orchestrator.result_validator``) does NOT accept that shape: for EMBER it
needs the parsed provider payload plus the receipt; for other tools it needs a
fully-built ToolResult. This module is the missing read-and-normalize bridge.

Responsibilities (and only these):
  * read the raw provider artifacts (stdout.bin) written by D5 under the
    artifact root, verifying each against the SHA-256 recorded in the receipt's
    artifact ref before using it (fail closed on any mismatch);
  * parse the untrusted provider payload (JSON) WITHOUT trusting it — it stays
    ``UNTRUSTED_CONTENT`` all the way through D7;
  * translate the executor's internal UPPERCASE error codes into the lowercase
    ``tool_result.error.code`` wire format required by the frozen schema;
  * hand everything to the correct D7 normalizer and return its validated result.

It performs NO execution, NO policy/approval decision, NO signing and NO
CaseState mutation (those are D4/D8/D9). Provider bytes are untrusted data, not
instructions.

Only the EMBER tool (``static.ember_features``) has a concrete D7 normalizer
(``normalize_ember_result``); a generic ToolResult builder is intentionally NOT
invented here. Other tools must ship their own normalizer, mirroring EMBER.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from orchestrator.result_validator import (
    ResultValidationError,
    normalize_ember_result,
)


def wire_error(error: Optional[Mapping[str, Any]]) -> Optional[dict]:
    """Map an executor ExecutionOutput.error to the ToolResult wire error.

    Executor codes are internal UPPER_SNAKE (e.g. ``PROVIDER_FAILED``); the
    frozen tool_result schema requires ``^[a-z][a-z0-9_.-]{1,80}$``. Lower-casing
    is faithful and lossless (same token), so no information is fabricated.
    """
    if error is None:
        return None
    if not isinstance(error, Mapping):
        raise ResultValidationError("RESULT_INVALID", "Execution error is not a mapping")
    code = str(error.get("code") or "").lower() or "internal_error"
    message = error.get("message")
    if not isinstance(message, str) or not message:
        message = "Adapter execution error"
    return {"code": code, "message": message}


def make_artifact_reader(artifact_root: Path | str):
    """Build a trusted artifact reader for D7 over the executor's run root.

    The returned callable resolves ``ref['relative_path']`` under the root,
    rejects path escapes, and verifies size + SHA-256 before returning bytes.
    """
    root = Path(artifact_root).resolve()

    def reader(ref: Mapping[str, Any]) -> bytes:
        rel = Path(ref["relative_path"])
        if rel.is_absolute() or ".." in rel.parts or any(":" in part for part in rel.parts):
            raise ValueError("Unsafe artifact relative_path")
        path = (root / rel).resolve()
        if root not in path.parents and path != root:
            raise ValueError("Artifact path escapes the artifact root")
        data = path.read_bytes()
        if len(data) != ref["size_bytes"] or hashlib.sha256(data).hexdigest() != ref["sha256"]:
            raise ValueError("Artifact size or digest mismatch")
        return data

    return reader


def _read_stdout_payload(output, reader) -> Any:
    """Locate, integrity-check and JSON-parse the provider stdout artifact."""
    stdout_refs = [a for a in output.raw_artifacts
                   if Path(a["relative_path"]).name == "stdout.bin"]
    if not stdout_refs:
        raise ResultValidationError(
            "RESULT_INVALID", "Successful extraction has no stdout provider payload")
    try:
        data = reader(stdout_refs[0])
    except Exception as exc:  # integrity failure, missing file, etc.
        raise ResultValidationError(
            "ARTIFACT_INTEGRITY_FAILED", "Provider stdout artifact failed verification") from exc
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ResultValidationError(
            "RESULT_INVALID", "Provider payload is not valid UTF-8 JSON") from exc


def ember_result_from_execution(output, call: Mapping[str, Any], spec: Mapping[str, Any], *,
                                artifact_root: Path | str,
                                output_schemas: Optional[Mapping[str, Any]] = None,
                                artifact_writer=None) -> dict:
    """Turn a D5 ExecutionOutput for EMBER into a D7-validated ToolResult.

    On SUCCESS/PARTIAL the stdout payload is read, integrity-checked and parsed,
    then normalized by D7. On FAILED/TIMEOUT/CANCELLED no payload is read and the
    translated error is carried through; D7 forbids a success payload there.
    """
    receipt = output.receipt
    outcome = receipt.get("outcome")
    reader = make_artifact_reader(artifact_root)

    payload = None
    if outcome in ("SUCCESS", "PARTIAL"):
        payload = _read_stdout_payload(output, reader)

    return normalize_ember_result(
        payload, receipt, call, spec,
        error=wire_error(output.error),
        output_schemas=output_schemas,
        artifact_reader=reader,
        artifact_writer=artifact_writer,
    )
