"""06B-R v3.3: branch-required decoding and LLM-authored claims, no phase lists."""
import copy
import json
from jsonschema import Draft202012Validator
from .schema import FORMAT

VERSION = 'investigation-v3.3'


def contract(ctx=None):
    common = {k: copy.deepcopy(FORMAT['properties'][k]) for k in
              ('action', 'case_id', 'case_revision', 'reason', 'evidence_refs')}
    common['reason']['maxLength'] = 600
    common['evidence_refs']['maxItems'] = 3  # existing trusted Controller contract
    if ctx:
        for key in ('case_id', 'case_revision'):
            common[key] = {'const': ctx['facts'][key]}
    assessment = copy.deepcopy(FORMAT['properties']['assessment'])
    for key in ('explanation',):
        assessment['properties'][key]['maxLength'] = 900
    assessment['properties']['claims']['maxItems'] = 3
    assessment['properties']['claims']['items']['properties']['text']['maxLength'] = 500
    binding = {'type': 'object', 'additionalProperties': False,
               'required': ['claim_index', 'evidence_id', 'entry_index'], 'properties': {
                   'claim_index': {'type': 'integer', 'minimum': 0, 'maximum': 2},
                   'evidence_id': {'type': 'string'},
                   'entry_index': {'type': 'integer', 'minimum': 0, 'maximum': 63}}}
    def branch(action, extras):
        props = dict(copy.deepcopy(common), action={'const': action}, **extras)
        return {'type': 'object', 'additionalProperties': False, 'required': list(props), 'properties': props}
    final_branch = branch('FINISH', {'assessment': assessment,
                     'import_bindings': {'type': 'array', 'maxItems': 3, 'items': binding},
                     'change_explanation': {'type': 'string', 'minLength': 1, 'maxLength': 600},
                     'stop_reason': {'type': 'string', 'minLength': 1, 'maxLength': 400}})
    # Action selection and final authorship have separate decoding contracts.
    # FINISH selection is not a final report and adds no semantic claims.
    if ctx is None or ctx.get('finalization_stage', True):
        return {'oneOf': [final_branch, branch('REQUEST_MORE_EVIDENCE', {})]}
    branches = []
    if ctx is None or ctx['facts']['available_tools']:
        tool = copy.deepcopy(FORMAT['properties']['tool'])
        if ctx and len(ctx['facts']['available_tools']) == 1:
            for k in ('tool_id', 'tool_version', 'provider_id'):
                tool['properties'][k] = {'const': ctx['facts']['available_tools'][0][k]}
        branches.append(branch('TOOL_CALL', {'tool': tool}))
    if ctx is None or ctx['facts'].get('retrieval_available'):
        branches.append(branch('READ_EVIDENCE', {'retrieval': {
            'type': 'object', 'additionalProperties': False,
            'required': ['evidence_id', 'value_sha256', 'offset', 'limit'],
            'properties': {'evidence_id': {'type': 'string'}, 'value_sha256': {'type': 'string'},
                           'offset': {'type': 'integer', 'minimum': 0, 'maximum': 64},
                           'limit': {'type': 'integer', 'minimum': 1, 'maximum': 16}}}}))
    branches += [branch('FINISH', {}), branch('REQUEST_MORE_EVIDENCE', {})]
    return {'oneOf': branches}


def parse(raw, ctx):
    obj = json.loads(raw)
    errors = sorted(Draft202012Validator(contract(ctx)).iter_errors(obj), key=lambda e: str(e.path))
    if errors:
        # Keep branch-specific diagnostics, not the full untrusted model object.
        details = [e.message[:220] for e in errors[0].context
                   if e.validator in {'required', 'enum', 'const', 'additionalProperties'}]
        raise ValueError('STRUCTURAL_SCHEMA: ' + '; '.join(details[:10]))
    return obj
