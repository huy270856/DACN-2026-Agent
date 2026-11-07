"""D3-01: validate d0-v1 calls; never authorize or execute them.

D2 supplies a trusted ToolSpec (None means unknown tool) and availability.
The caller supplies a trusted map of input_schema_id -> JSON Schema. Missing
schemas fail closed; this module does not invent EMBER's arguments contract.
The returned deep copy is only a validated candidate. D4 still owns policy;
D1/D9 must check revision atomically and D5 must revalidate the actual target.
ValidationError.code uses the proposed D.0 taxonomy for internal exceptions,
not the lowercase ToolResult.error wire format.
"""

from copy import deepcopy

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError as JsonSchemaError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from bc_contracts import same_target_ref
from d0.validate import SCHEMAS, ContractError, canonical_json_bytes, validate


class ValidationError(ValueError):
    """Typed internal rejection with stable code and safe diagnostic message."""

    def __init__(self, code, message, *, call_id=None):
        self.code = code
        self.message = message
        self.call_id = call_id
        super().__init__(f"{code}: {message}")


def validate_tool_call(call, spec, case, *, input_schemas=None,
                       provider_available=True):
    """Return a separate validated call or raise ValidationError.

    case is the B/C snapshot containing case_id, revision, target_ref.
    input_schemas defaults to installed D.0 schemas and must never come from Agent
    input. References resolve only in that local map; no network retrieval.
    No argument coercion, unknown-field removal, or provider fallback occurs.
    """
    call, spec, case = deepcopy((call, spec, case))
    input_schemas = SCHEMAS if input_schemas is None else input_schemas

    def reject(code, message):
        raise ValidationError(code, message, call_id=(
            call.get('call_id') if isinstance(call, dict) else None))

    def check_schema(name, value):
        try:
            validate(name, value)
            canonical_json_bytes(value)
        except (ContractError, TypeError, ValueError, OverflowError):
            reject('SCHEMA_INVALID', f'Invalid {name} document')

    check_schema('tool_call', call)
    if spec is None:
        reject('TOOL_UNKNOWN', 'Tool is not registered')
    check_schema('tool_spec', spec)
    check_schema('target_ref', call['target_ref'])
    if not isinstance(case, dict) or not isinstance(case.get('case_id'), str):
        reject('SCHEMA_INVALID', 'Case snapshot requires case_id')
    revision = case.get('revision')
    if type(revision) is not int or revision < 1:
        reject('SCHEMA_INVALID', 'Case snapshot requires a positive revision')
    check_schema('target_ref', case.get('target_ref'))

    if call['tool_id'] != spec['tool_id']:
        reject('TOOL_UNKNOWN', 'Requested tool differs from registered tool')
    if not spec['enabled']:
        reject('TOOL_DISABLED', 'Registered tool is disabled')
    if (call['tool_version'] != spec['tool_version'] or
            call['provider_id'] != spec['provider']['id']):
        reject('PROVIDER_MISMATCH', 'Tool version or provider binding differs')
    if provider_available is not True:
        reject('PROVIDER_UNAVAILABLE', 'Selected provider is unavailable')
    if call['target_ref']['kind'] not in spec['supported_targets']:
        reject('SCHEMA_INVALID', 'Tool does not support the requested target kind')
    if call['case_id'] != case['case_id']:
        reject('SCHEMA_INVALID', 'Requested case differs from snapshot')
    if call['expected_revision'] != revision:
        reject('CASE_REVISION_STALE', 'Case snapshot revision has changed')
    if call['target_ref']['identity_strength'] == 'UNAVAILABLE':
        reject('TARGET_IDENTITY_UNAVAILABLE', 'Target identity is unavailable')
    if not same_target_ref(case['target_ref'], call['target_ref']):
        reject('TARGET_CHANGED', 'Requested target differs from case target')
    for limit in ('timeout_ms', 'max_output_bytes'):
        if call['budget'][limit] > spec['limits'][limit]:
            reject('BUDGET_EXCEEDED', f'Requested {limit} exceeds tool limit')

    schema_id = spec['input_schema_id']
    if schema_id not in input_schemas:
        reject('SCHEMA_INVALID', 'Trusted tool input schema is unavailable')
    try:
        resources = []
        for identifier, schema in input_schemas.items():
            Draft202012Validator.check_schema(schema)
            resources.append((identifier, Resource.from_contents(
                schema, default_specification=DRAFT202012)))
        registry = Registry().with_resources(resources)
        Draft202012Validator(input_schemas[schema_id], registry=registry).validate(
            call['arguments'])
    except (SchemaError, JsonSchemaError, Unresolvable):
        reject('SCHEMA_INVALID', 'Arguments or trusted input schema are invalid')
    if (schema_id == 'ember-input-v1' and
            call['arguments'].get('include_feature_vector') is False):
        reject('SCHEMA_INVALID', 'EMBER vector omission is reserved, not supported')
    return call
