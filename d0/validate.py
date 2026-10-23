"""Strict D.0 schema + cross-field validators. No process execution, signing or approvals.

Requires jsonschema>=4.20. Does not trust JSON Schema alone for cross-field rules.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).parent / 'schemas'
SCHEMAS = {p.name.removesuffix('.schema.json'): json.loads(p.read_text(encoding='utf8'))
           for p in SCHEMA_DIR.glob('*.schema.json')}
REGISTRY = Registry().with_resources([(s['$id'], Resource.from_contents(s)) for s in SCHEMAS.values()])

class ContractError(ValueError):
    pass

def canonical_json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf8')

def digest(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

def validate(name, value):
    if name not in SCHEMAS:
        raise ContractError(f'Unknown schema: {name}')
    errors = sorted(Draft202012Validator(SCHEMAS[name], registry=REGISTRY).iter_errors(value),
                    key=lambda e: str(list(e.path)))
    if errors:
        e = errors[0]
        raise ContractError(f'{name} at {list(e.path)}: {e.message}')
    if name == 'target_ref':
        if value['kind'] == 'FILE' and not isinstance(value['observed'].get('path'), str):
            raise ContractError('FILE requires observed.path')
        if value['kind'] == 'PROCESS' and (not isinstance(value['observed'].get('pid'), int)
                                         or isinstance(value['observed'].get('pid'), bool)):
            raise ContractError('PROCESS requires observed.pid')
    if name == 'observation':
        if value['status'] == 'SUCCESS' and value['coverage'] == 'NONE':
            raise ContractError('SUCCESS cannot have NONE coverage')
        if value['status'] != 'SUCCESS' and value['value'] is not None:
            raise ContractError('Non-SUCCESS value must be null (retain partial data as artifact)')
        if value['content_origin'] != 'trusted_system' and value['trust_level'] != 'UNTRUSTED_CONTENT':
            raise ContractError('Target/provider content cannot be marked trusted')
    if name == 'tool_result':
        for ob in value['observations']:
            validate('observation', ob)
        if value['status'] != 'SUCCESS' and value['error'] is None and value['status'] not in ('PARTIAL',):
            raise ContractError('Failed/cancelled/denied result needs error')
    if name == 'execution_receipt':
        if value['outcome'] == 'SUCCESS' and value['target_binding']['status'] != 'VERIFIED':
            raise ContractError('Success requires VERIFIED target binding')
        if value['cleanup']['status'] == 'COMPLETE' and value['cleanup']['remaining_owned_resources']:
            raise ContractError('COMPLETE cleanup cannot have remaining resources')
        if datetime.fromisoformat(value['finished_at'].replace('Z','+00:00')) < datetime.fromisoformat(value['started_at'].replace('Z','+00:00')):
            raise ContractError('finish before start')
    if name == 'approval_request':
        if datetime.fromisoformat(value['expires_at'].replace('Z','+00:00')) <= datetime.fromisoformat(value['requested_at'].replace('Z','+00:00')):
            raise ContractError('Approval expires before request')
    return value

def verify_tool_call(spec, call, case, *, provider_available=True):
    """Pre-dispatch checks, not a substitute for locked transactional admission."""
    validate('tool_spec', spec); validate('tool_call', call)
    if not spec['enabled'] or not provider_available:
        raise ContractError('Tool/provider unavailable; never silently fallback')
    if (call['tool_id'], call['tool_version'], call['provider_id']) != (spec['tool_id'], spec['tool_version'], spec['provider']['id']):
        raise ContractError('Tool/provider binding mismatch')
    if call['target_ref']['kind'] not in spec['supported_targets']:
        raise ContractError('Unsupported target kind')
    if call['case_id'] != case['case_id'] or call['expected_revision'] != case['revision']:
        raise ContractError('Stale case revision or wrong case')
    if call['budget']['timeout_ms'] > spec['limits']['timeout_ms'] or call['budget']['max_output_bytes'] > spec['limits']['max_output_bytes']:
        raise ContractError('Requested budget exceeds tool limits')
    # bc_contracts is in project root when patch installed; do not reimplement identity rules.
    try:
        from bc_contracts import same_target_ref
    except ImportError as exc:
        raise ContractError('Node B/C v1.2 bc_contracts.py required') from exc
    if not same_target_ref(case['target_ref'], call['target_ref']):
        raise ContractError('TargetRef mismatch')
    if call['target_ref']['identity_strength'] == 'UNAVAILABLE':
        raise ContractError('Unverified identity cannot be dispatched')
    return True

def verify_receipt_result(receipt, result, call):
    validate('execution_receipt', receipt); validate('tool_result', result); validate('tool_call', call)
    for key in ('run_id','call_id','case_id','tool_id','tool_version'):
        if receipt[key] != result[key]:
            raise ContractError(f'{key} mismatch')
    if result['call_id'] != call['call_id'] or result['case_id'] != call['case_id']:
        raise ContractError('Result/call mismatch')
    if receipt['provider'] != result['provider'] or receipt['provider']['id'] != call['provider_id']:
        raise ContractError('Provider swapped')
    if receipt['arguments_sha256'] != digest(call['arguments']):
        raise ContractError('Arguments tampered')
    if result['receipt_sha256'] != digest(receipt):
        raise ContractError('Receipt hash mismatch')
    if result['status'] != receipt['outcome']:
        raise ContractError('Outcome mismatch')
    if result['target_ref'] != call['target_ref']:
        raise ContractError('Result target differs from requested target')
    if receipt['target_binding']['observed_ref'] != call['target_ref']:
        raise ContractError('Receipt target differs from requested target')
    if receipt['resources']['output_bytes'] > call['budget']['max_output_bytes']:
        raise ContractError('Output exceeds call budget')
    if receipt['target_binding']['status'] != 'VERIFIED' and result['status'] == 'SUCCESS':
        raise ContractError('Unverified target')
    return True
