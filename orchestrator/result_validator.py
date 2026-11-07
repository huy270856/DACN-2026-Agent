"""D7-01: EMBER payload normalization and D.0 ToolResult validation.

Input: normalized adapter output (dict), D6 receipt, original ToolCall,
trusted ToolSpec and output-schema catalog. Output: separate validated result
or ResultValidationError. D8 signing and D9 commits remain outside D7.

normalize_ember_result is the EMBER integration entry point: validate the raw
provider payload first, then build and validate the D.0 envelope. The lower
level validate_tool_result checks only the envelope and artifact consistency;
it must not be used instead of provider-payload validation.
Artifact IO is injected: reader(ref)->bytes; writer(bytes)->artifact ref.
The trusted store must enforce case-owned paths, ACLs, symlink/reparse safety
and atomic writes. D7 checks relative-path syntax, sizes and actual hashes.
No disk IO, execution, signing, or approvals occur in this module itself.
"""
from copy import deepcopy
import hashlib
from pathlib import PureWindowsPath

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from d0.validate import (SCHEMAS, ContractError, canonical_json_bytes, digest,
                         validate, verify_receipt_result)


class ResultValidationError(ValueError):
    """Internal typed rejection; codes are not ToolResult wire error codes."""

    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f'{code}: {message}')


def validate_tool_result(raw_output, receipt, call, spec, *,
                         artifact_reader=None, artifact_writer=None):
    """Validate normalized output; externalize large inline observation values.

    This validates the D.0 envelope, NOT the provider's raw-output schema.
    IO callbacks must be supplied by trusted integration code.
    Receipt facts/digests are verified, never repaired to make a result pass.
    Large SUCCESS values retain coverage/provenance and move to artifact_ref.
    Exceeding artifact or total inline budget is a typed rejection.
    """
    result, receipt, call, spec = deepcopy((raw_output, receipt, call, spec))

    def reject(code, message):
        raise ResultValidationError(code, message)

    def check(name, value):
        try:
            validate(name, value)
            canonical_json_bytes(value)
        except (ContractError, TypeError, ValueError, OverflowError):
            reject('RESULT_INVALID', f'Invalid {name} document')

    for name, value in (('tool_result', result), ('execution_receipt', receipt),
                        ('tool_call', call), ('tool_spec', spec)):
        check(name, value)
    check('target_ref', result['target_ref'])
    check('target_ref', receipt['target_binding']['observed_ref'])
    if (result['tool_id'], result['tool_version'], result['provider']) != (
            spec['tool_id'], spec['tool_version'], spec['provider']):
        reject('PROVIDER_MISMATCH', 'Result does not match registered tool/provider')
    if (call['tool_id'], call['tool_version'], call['provider_id']) != (
            spec['tool_id'], spec['tool_version'], spec['provider']['id']):
        reject('PROVIDER_MISMATCH', 'Call does not match registered tool/provider')
    for key in ('timeout_ms', 'max_output_bytes'):
        if call['budget'][key] > spec['limits'][key]:
            reject('BUDGET_EXCEEDED', 'Call exceeds registered limits')
    if receipt['resources']['output_bytes'] > call['budget']['max_output_bytes']:
        reject('BUDGET_EXCEEDED', 'Recorded output exceeds call budget')
    try:
        verify_receipt_result(receipt, result, call)
    except (ContractError, ValueError, TypeError):
        reject('RESULT_INVALID', 'Call, receipt and result are inconsistent')

    def verify_artifact(ref, expected=None):
        check('artifact', ref)
        path = PureWindowsPath(ref['relative_path'])
        if (not path.parts or path.drive or path.root or
                any(part in ('.', '..') or ':' in part for part in path.parts)):
            reject('ARTIFACT_INTEGRITY_FAILED', 'Unsafe artifact path')
        if ref['size_bytes'] > spec['limits']['max_artifact_bytes']:
            reject('BUDGET_EXCEEDED', 'Artifact exceeds registered limit')
        if artifact_reader is None:
            reject('ARTIFACT_INTEGRITY_FAILED', 'Artifact reader is required')
        try:
            data = artifact_reader(deepcopy(ref))
        except Exception:
            reject('ARTIFACT_INTEGRITY_FAILED', 'Artifact could not be read')
        if (not isinstance(data, bytes) or len(data) != ref['size_bytes'] or
                hashlib.sha256(data).hexdigest() != ref['sha256'] or
                (expected is not None and data != expected)):
            reject('ARTIFACT_INTEGRITY_FAILED', 'Artifact size or digest mismatch')

    for ref in result['raw_artifacts']:
        verify_artifact(ref)
    inline_limit = min(call['budget']['max_output_bytes'],
                       spec['limits']['max_output_bytes'])
    for observation in result['observations']:
        # Provider output cannot promote itself to trusted system metadata by
        # changing BOTH fields; trusted metadata belongs to the control plane.
        if (observation['content_origin'] == 'trusted_system' or
                observation['trust_level'] != 'UNTRUSTED_CONTENT'):
            reject('RESULT_INVALID', 'Provider observations must remain untrusted')
        if observation['artifact_ref'] is not None:
            verify_artifact(observation['artifact_ref'])

    # Consider the whole envelope, not only individual values: several modest
    # observations can together exceed the inline budget.
    candidates = sorted(result['observations'],
                        key=lambda ob: len(canonical_json_bytes(ob['value'])),
                        reverse=True)
    for observation in candidates:
        if len(canonical_json_bytes(result)) <= inline_limit:
            break
        data = canonical_json_bytes(observation['value'])
        if len(data) > 512 and observation['artifact_ref'] is None:
            if len(data) > spec['limits']['max_artifact_bytes']:
                reject('BUDGET_EXCEEDED', 'Observation exceeds artifact limit')
            if artifact_writer is None:
                reject('BUDGET_EXCEEDED', 'Large value requires artifact storage')
            try:
                ref = artifact_writer(data)
            except Exception:
                reject('ARTIFACT_INTEGRITY_FAILED', 'Artifact write failed')
            verify_artifact(ref, expected=data)
            observation['value'] = None
            observation['artifact_ref'] = deepcopy(ref)
    if len(canonical_json_bytes(result)) > inline_limit:
        reject('BUDGET_EXCEEDED', 'Normalized result exceeds inline budget')
    check('tool_result', result)
    return result


def normalize_ember_result(payload, receipt, call, spec, *, error=None,
                           output_schemas=None, artifact_reader=None,
                           artifact_writer=None):
    """Check ember-output-v1 payload, bind its hash and construct ToolResult.

    payload is the provider JSON object, not a ToolResult. None represents no
    completed extraction. Non-success errors use D.0 lowercase wire codes.
    A PARTIAL run may retain a completed extraction; failed/cancelled/timed-out
    extraction never fabricates a vector. Receipts come from trusted D5/D6.
    No model prediction or malware verdict is derived here.

    The complete payload (including extractor version, hash and warnings) is
    preserved in one observation with facet static.ember_features, inline or
    in a digest-verified artifact. Payload and envelope have separate budgets:
    artifact storage may reduce the envelope, never bypass provider output cap.
    """
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
    if (spec['tool_id'] != 'static.ember_features' or
            spec['input_schema_id'] != 'ember-input-v1' or
            spec['output_schema_id'] != 'ember-output-v1'):
        reject('RESULT_INVALID', 'Expected the registered EMBER v1 contracts')
    try:
        validate('ember-input-v1', call['arguments'])
    except (ContractError, ValueError, TypeError):
        reject('RESULT_INVALID', 'Invalid EMBER call arguments')
    if call['arguments'].get('include_feature_vector') is False:
        reject('RESULT_INVALID', 'EMBER vector omission is not supported')

    status = receipt['outcome']
    if status == 'SUCCESS' and (payload is None or error is not None):
        reject('RESULT_INVALID', 'Successful extraction requires payload and no error')
    if payload is not None and status not in ('SUCCESS', 'PARTIAL'):
        reject('RESULT_INVALID', 'Failed extraction cannot carry a success payload')

    observations = []
    if payload is not None:
        schemas = SCHEMAS if output_schemas is None else output_schemas
        schema_id = spec['output_schema_id']
        if schema_id not in schemas:
            reject('RESULT_INVALID', 'Trusted EMBER output schema is unavailable')
        try:
            resources = []
            for identifier, schema in schemas.items():
                Draft202012Validator.check_schema(schema)
                resources.append((identifier, Resource.from_contents(
                    schema, default_specification=DRAFT202012)))
            Draft202012Validator(schemas[schema_id],
                                registry=Registry().with_resources(resources)).validate(payload)
            # Preserve the shipped semantic finite-number rule as well as shape.
            validate('ember-output-v1', payload)
            encoded = canonical_json_bytes(payload)
        except (SchemaError, ValidationError, Unresolvable, ContractError,
                ValueError, TypeError, OverflowError):
            reject('RESULT_INVALID', 'Invalid EMBER feature extraction payload')
        if len(encoded) > min(call['budget']['max_output_bytes'],
                              spec['limits']['max_output_bytes']):
            reject('BUDGET_EXCEEDED', 'EMBER provider payload exceeds output budget')
        requested = call['target_ref']
        observed = receipt['target_binding']['observed_ref']
        if (requested['kind'] != 'FILE' or observed['kind'] != 'FILE' or
                requested['identity_strength'] == 'UNAVAILABLE' or
                observed['identity_strength'] == 'UNAVAILABLE' or
                receipt['target_binding']['status'] != 'VERIFIED' or
                requested['verified_digest'] is None or
                observed['verified_digest'] is None):
            reject('TARGET_IDENTITY_UNAVAILABLE', 'EMBER requires verified file digests')
        if not (payload['target_sha256'] == requested['verified_digest']['value'] ==
                observed['verified_digest']['value']):
            reject('TARGET_CHANGED', 'EMBER payload hash differs from verified file')
        observations.append({
            'facet': 'static.ember_features', 'status': 'SUCCESS',
            'coverage': 'COMPLETE', 'value': payload,
            'limitations': [warning for warning in payload.get('warnings', []) if warning],
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
