"""D7 normalizer for the real static PE prediction tool (static.pe_malware_predict).

Mirrors ``normalize_ember_result`` but validates a ``static-prediction-v1``
provider payload and binds it to:
  * the verified target SHA-256 (payload must match the admitted file), and
  * the TRUSTED installed model identity/digest (payload must match what the
    backend installed, not an arbitrary model the provider claims).

Provider bytes remain UNTRUSTED_CONTENT. No malware verdict is invented here; the
LightGBM label is carried through verbatim as an untrusted provider observation.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from d0.validate import (SCHEMAS, ContractError, canonical_json_bytes, digest,
                         validate)
from orchestrator.result_validator import ResultValidationError, validate_tool_result
from orchestrator.execution_adapter import make_artifact_reader, wire_error

PREDICTION_FACET = "static.pe_malware_prediction"


def normalize_pe_prediction_result(payload, receipt, call, spec, *, error=None,
                                   expected_model_id=None, expected_model_sha256=None,
                                   output_schemas=None, artifact_reader=None,
                                   artifact_writer=None):
    """Validate static-prediction-v1 payload and construct a D.0 ToolResult."""
    payload, receipt, call, spec, error = deepcopy((payload, receipt, call, spec, error))

    def reject(code, message):
        raise ResultValidationError(code, message)

    for name, value in (('execution_receipt', receipt), ('tool_call', call),
                        ('tool_spec', spec)):
        try:
            validate(name, value)
            canonical_json_bytes(value)
        except (ContractError, ValueError, TypeError, OverflowError):
            reject('RESULT_INVALID', f'Invalid {name} document')

    if (spec['tool_id'] != 'static.pe_malware_predict' or
            spec['input_schema_id'] != 'pe-predict-input-v1' or
            spec['output_schema_id'] != 'static-prediction-v1'):
        reject('RESULT_INVALID', 'Expected the registered static prediction contracts')
    try:
        validate('pe-predict-input-v1', call['arguments'])
    except (ContractError, ValueError, TypeError):
        reject('RESULT_INVALID', 'Invalid prediction call arguments')

    status = receipt['outcome']
    if status == 'SUCCESS' and (payload is None or error is not None):
        reject('RESULT_INVALID', 'Successful prediction requires payload and no error')
    if payload is not None and status not in ('SUCCESS', 'PARTIAL'):
        reject('RESULT_INVALID', 'Failed prediction cannot carry a success payload')

    observations = []
    if payload is not None:
        schemas = SCHEMAS if output_schemas is None else output_schemas
        schema_id = spec['output_schema_id']
        if schema_id not in schemas:
            reject('RESULT_INVALID', 'Trusted prediction output schema is unavailable')
        try:
            resources = []
            for identifier, schema in schemas.items():
                Draft202012Validator.check_schema(schema)
                resources.append((identifier, Resource.from_contents(
                    schema, default_specification=DRAFT202012)))
            Draft202012Validator(schemas[schema_id],
                                 registry=Registry().with_resources(resources)).validate(payload)
            validate('static-prediction-v1', payload)
            encoded = canonical_json_bytes(payload)
        except (SchemaError, ValidationError, ContractError, ValueError, TypeError, OverflowError):
            reject('RESULT_INVALID', 'Invalid static prediction payload')
        if len(encoded) > min(call['budget']['max_output_bytes'],
                              spec['limits']['max_output_bytes']):
            reject('BUDGET_EXCEEDED', 'Prediction payload exceeds output budget')

        # --- target binding: prediction must be about the admitted file --------
        requested = call['target_ref']
        observed = receipt['target_binding']['observed_ref']
        if (requested['kind'] != 'FILE' or observed['kind'] != 'FILE' or
                requested['identity_strength'] == 'UNAVAILABLE' or
                observed['identity_strength'] == 'UNAVAILABLE' or
                receipt['target_binding']['status'] != 'VERIFIED' or
                requested['verified_digest'] is None or observed['verified_digest'] is None):
            reject('TARGET_IDENTITY_UNAVAILABLE', 'Prediction requires verified file digests')
        if not (payload['target_sha256'] == requested['verified_digest']['value'] ==
                observed['verified_digest']['value']):
            reject('TARGET_CHANGED', 'Prediction payload hash differs from verified file')

        # --- model binding: prediction must be from the trusted installed model -
        if expected_model_sha256 is not None and payload['model_sha256'] != expected_model_sha256.lower():
            reject('RESULT_INVALID', 'Prediction model digest differs from the installed model')
        if expected_model_id is not None and payload['model_id'] != expected_model_id:
            reject('RESULT_INVALID', 'Prediction model id differs from the installed model')

        observations.append({
            'facet': PREDICTION_FACET, 'status': 'SUCCESS', 'coverage': 'COMPLETE',
            'value': payload,
            'limitations': [w for w in payload.get('limitations', []) if w],
            'content_origin': 'provider_output', 'trust_level': 'UNTRUSTED_CONTENT',
            'artifact_ref': None,
        })

    result = {
        'schema_version': 'd0-v1',
        **{key: receipt[key] for key in (
            'run_id', 'call_id', 'case_id', 'tool_id', 'tool_version', 'provider')},
        'target_ref': deepcopy(call['target_ref']), 'status': status,
        'observations': observations, 'receipt_sha256': digest(receipt),
        'raw_artifacts': [], 'error': error,
    }
    return validate_tool_result(result, receipt, call, spec,
                               artifact_reader=artifact_reader,
                               artifact_writer=artifact_writer)


def pe_prediction_result_from_execution(output, call: Mapping[str, Any], spec: Mapping[str, Any], *,
                                        artifact_root: Path | str,
                                        expected_model_id=None, expected_model_sha256=None,
                                        output_schemas: Optional[Mapping[str, Any]] = None,
                                        artifact_writer=None) -> dict:
    """D5 ExecutionOutput -> D7-validated static prediction ToolResult."""
    import json

    receipt = output.receipt
    outcome = receipt.get("outcome")
    reader = make_artifact_reader(artifact_root)

    payload = None
    if outcome in ("SUCCESS", "PARTIAL"):
        stdout_refs = [a for a in output.raw_artifacts
                       if Path(a["relative_path"]).name == "stdout.bin"]
        if not stdout_refs:
            raise ResultValidationError("RESULT_INVALID", "Successful prediction has no stdout payload")
        try:
            data = reader(stdout_refs[0])
        except Exception as exc:
            raise ResultValidationError("ARTIFACT_INTEGRITY_FAILED",
                                        "Provider stdout artifact failed verification") from exc
        try:
            payload = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ResultValidationError("RESULT_INVALID", "Prediction payload is not valid UTF-8 JSON") from exc

    return normalize_pe_prediction_result(
        payload, receipt, call, spec,
        error=wire_error(output.error),
        expected_model_id=expected_model_id, expected_model_sha256=expected_model_sha256,
        output_schemas=output_schemas, artifact_reader=reader, artifact_writer=artifact_writer)
