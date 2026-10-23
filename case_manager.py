"""Node C v1 CaseManager: persist investigation state; NEVER execute response actions.

Only accepts local JSON artifacts, explicit tool registrations, and human-approved
response *records*. The Agent and actual tools are separate components.
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import base64
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

from case_state import build_case_state, save_case_state
from bc_contracts import target_ref_from_context, validate_target_ref, same_target_ref, evidence_v2

MAX_JSON_BYTES = 8 * 1024 * 1024
CASE_RE = re.compile(r'^CASE-[a-f0-9]{32}$')
STATUSES = {'SUCCESS', 'DEGRADED', 'FAILED', 'UNAVAILABLE'}
LIFECYCLES = {'READY_FOR_INVESTIGATION', 'NEEDS_CONTEXT', 'INVESTIGATING', 'AWAITING_APPROVAL', 'CLOSED'}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError('JSON artifact exceeds 8 MiB limit')
    with path.open('r', encoding='utf-8-sig') as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError('JSON root must be an object')
    return obj


def write_atomic(path, obj):
    path = Path(path)
    data = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n'
    if len(data) > MAX_JSON_BYTES:
        raise ValueError('CaseState exceeds 8 MiB; move large evidence to artifacts')
    fd, temp = tempfile.mkstemp(prefix='.case-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def locked_case(path, wait_seconds=5):
    """Simple cross-platform lock; abandoned .lock requires manual inspection/removal."""
    path = Path(path)
    lock = path.with_suffix(path.suffix + '.lock')
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f'Case busy or stale lock: {lock}')
            time.sleep(0.05)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(f'pid={os.getpid()} created={now()}\n')
        yield
    finally:
        lock.unlink(missing_ok=True)


def case_path(root, case_id):
    if not CASE_RE.fullmatch(case_id):
        raise ValueError('Invalid case_id')
    return Path(root) / case_id / 'case_state.json'


def validate_case(state):
    if state.get('schema_version') != 'casestate-v1' or not CASE_RE.fullmatch(str(state.get('case_id', ''))):
        raise ValueError('Unsupported or invalid CaseState')
    if state.get('lifecycle_status') not in LIFECYCLES:
        raise ValueError('Invalid lifecycle')
    for key in ('evidence', 'residual_unknowns', 'collection_ids', 'tool_runs', 'action_history', 'response_history'):
        if not isinstance(state.get(key), list):
            raise ValueError(f'Invalid CaseState field: {key}')
    if not isinstance(state.get('evidence_conflicts', []), list):
        raise ValueError('Invalid conflict registry')
    if not isinstance(state.get('available_tools'), dict):
        raise ValueError('Invalid tool registry')
    # In-memory additive upgrade for old casestate-v1; persisted only on a valid update.
    if 'target_ref' not in state:
        state['target_ref'] = target_ref_from_context({
            'target_type': state['target_type'], 'target': state['target'], 'facets': {}})
    else:
        validate_target_ref(state['target_ref'])
    return state


def target_matches(case, typ, target):
    if typ != case['target_type'] or not isinstance(target, dict):
        return False
    old = case['target']
    if typ == 'PROCESS':
        # Never confuse reused PIDs; identity must include creation time when known.
        return (target.get('pid') == old.get('pid') and
                target.get('start_time_epoch') == old.get('start_time_epoch'))
    return os.path.normcase(os.path.normpath(str(target.get('path', '')))) == os.path.normcase(os.path.normpath(str(old.get('path', ''))))


def _resolve(state, facet, *, source, evidence_id=None, target_ref=None, scope='target'):
    """Resolve only gaps for the matching target/scope, never by facet alone.

    Legacy gaps lacking TargetRef use their originating collection's evidence to
    establish a matching target. Case-wide assessment is resolved separately.
    """
    for gap in list(state['residual_unknowns']):
        if gap.get('facet') != facet:
            continue
        if scope == 'case':
            if gap.get('scope', 'case' if facet == 'malware_assessment' else 'target') != 'case':
                continue
        elif scope == 'backing_file':
            if gap.get('scope') != 'backing_file':
                continue
        else:
            if gap.get('scope', 'target') != 'target':
                continue
            if target_ref is None:
                continue
            gap_ref = gap.get('target_ref')
            if gap_ref is None:
                origin = next((ev for ev in state['evidence'] if ev.get('collection_id') == gap.get('collection_id')
                               and ev.get('target_type') and ev.get('target')), None)
                if origin:
                    gap_ref = origin.get('target_ref') or target_ref_from_context({
                        'target_type': origin['target_type'], 'target': origin['target'], 'facets': {}})
            if gap_ref is None or not same_target_ref(gap_ref, target_ref):
                continue
        state['residual_unknowns'].remove(gap)
        state.setdefault('resolved_unknowns', []).append({**gap, 'resolved_at': now(),
            'resolved_by': source, 'evidence_id': evidence_id})


def _value_fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _record_conflicts(state, new_evidence):
    """Flag *potential* inconsistencies, not verdicts; preserve all observations.

    Compare only matching target identity + facet. Different observations can be
    legitimate across time (running, network, file mutation): analyst must review.
    """
    conflicts = state.setdefault('evidence_conflicts', [])
    seen = {tuple(sorted(x['evidence_ids'])) for x in conflicts}
    for ev in new_evidence:
        if ev['status'] != 'SUCCESS':
            continue
        for other in state['evidence']:
            if other['status'] != 'SUCCESS' or other['evidence_id'] == ev['evidence_id']:
                continue
            if other['facet'] != ev['facet'] or other['target_type'] != ev['target_type'] or other['target'] != ev['target']:
                continue
            if _value_fingerprint(other['value']) == _value_fingerprint(ev['value']):
                continue
            pair = tuple(sorted((other['evidence_id'], ev['evidence_id'])))
            if pair in seen:
                continue
            seen.add(pair)
            conflicts.append({'conflict_id': 'CONFLICT-' + uuid.uuid4().hex,
                'facet': ev['facet'], 'target_type': ev['target_type'],
                'target': ev['target'], 'evidence_ids': list(pair),
                'status': 'UNRESOLVED', 'detected_at': now(),
                'note': 'Potential conflicting observations; different collection times may explain changes.'})
            assessment = state.get('assessment')
            if assessment and any(x in assessment.get('evidence_ids', []) for x in pair):
                assessment['validity'] = 'STALE_CONFLICT'
                assessment['invalidated_at'] = now()
                assessment.setdefault('invalidating_conflict_ids', []).append(conflicts[-1]['conflict_id'])
                state.setdefault('residual_unknowns', []).append({'collection_id': None,
                    'facet': 'malware_assessment', 'scope': 'case', 'reason': 'evidence_conflict_after_assessment',
                    'state': 'UNKNOWN'})


def _canonical_bytes(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')


def _verify_proof(state, operation, data, proof, trusted_keys):
    """Verify a detached HMAC envelope. Signing is performed by a separate trusted boundary."""
    if not isinstance(proof, dict) or not isinstance(trusted_keys, dict):
        raise PermissionError('Verified external authorization required')
    role = 'tool' if operation == 'tool-result' else 'approval'
    key = trusted_keys.get(role)
    if not isinstance(key, bytes) or len(key) < 32:
        raise PermissionError('Missing/weak trusted verifier key')
    if proof.get('role') != role or not isinstance(proof.get('nonce'), str) or len(proof['nonce']) < 16:
        raise PermissionError('Invalid authorization envelope')
    if not isinstance(proof.get('issued_at'), (int, float)) or isinstance(proof['issued_at'], bool):
        raise PermissionError('Invalid authorization timestamp')
    if abs(time.time() - proof['issued_at']) > 300:
        raise PermissionError('Authorization expired or not yet valid')
    if not isinstance(proof.get('mac'), str):
        raise PermissionError('Missing authorization MAC')
    if role == 'approval' and (not isinstance(proof.get('subject'), str) or proof['subject'] != data.get('approver')):
        raise PermissionError('Verified approver does not match payload')
    signed = {'role': role, 'case_id': state['case_id'], 'nonce': proof['nonce'],
        'issued_at': proof['issued_at'], 'payload': data}
    if role == 'approval':
        signed['subject'] = proof['subject']
    expected = hmac.new(key, _canonical_bytes(signed), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(proof['mac'], expected):
        raise PermissionError('Invalid authorization MAC')
    if proof['nonce'] in state.setdefault('used_authorization_nonces', []):
        raise PermissionError('Authorization replay detected')
    state['used_authorization_nonces'].append(proof['nonce'])
    return {'role': role, 'nonce': proof['nonce'], 'verified_at': now()}


def sign_for_trusted_boundary(case_id, operation, payload, key, *, nonce=None, issued_at=None):
    """Helper for a separately trusted Orchestrator/approval service, not user input.

    Do not expose signing keys to the Agent, tools, web API, or untrusted callers.
    """
    if operation not in ('tool-result', 'response', 'resolve-conflict') or not isinstance(key, bytes) or len(key) < 32:
        raise ValueError('Invalid signer configuration')
    role = 'tool' if operation == 'tool-result' else 'approval'
    nonce = nonce or secrets.token_hex(16)
    issued_at = time.time() if issued_at is None else issued_at
    body = {'role': role, 'case_id': case_id, 'nonce': nonce,
        'issued_at': issued_at, 'payload': payload}
    if role == 'approval':
        if not isinstance(payload.get('approver'), str) or not payload['approver'].strip():
            raise ValueError('Verified approver required')
        body['subject'] = payload['approver']
    return {'role': role, 'nonce': nonce, 'issued_at': issued_at,
        **({'subject': payload['approver']} if role == 'approval' else {}),
        'mac': hmac.new(key, _canonical_bytes(body), hashlib.sha256).hexdigest()}


def _append_collection(state, context, source_path=None):
    incoming = build_case_state(context, source_path=source_path)
    if not target_matches(state, incoming['target_type'], incoming['target']):
        raise ValueError('Collector target identity does not match this case')
    # Stronger than path/PID matching: reject any known changed snapshot/digest.
    if state.get('target_ref') and incoming.get('target_ref') and not same_target_ref(state['target_ref'], incoming['target_ref']):
        raise ValueError('Collector target snapshot/digest differs from original case')
    incoming_ids = set(incoming['collection_ids'])
    if incoming_ids & set(state['collection_ids']):
        raise ValueError('Collection already present; duplicate/reused collection_id rejected')
    state['collection_ids'].extend(incoming['collection_ids'])
    _record_conflicts(state, incoming['evidence'])
    state['evidence'].extend(incoming['evidence'])
    state['collection_errors'].extend(incoming['collection_errors'])
    state['collection_limitations'].extend(incoming['collection_limitations'])
    state['tool_runs'].extend(incoming['tool_runs'])
    for ev in incoming['evidence']:
        if ev['status'] == 'SUCCESS':
            _resolve(state, ev['facet'], source=ev['collection_id'], evidence_id=ev['evidence_id'],
                    target_ref=ev.get('target_ref'))
            if ev['facet'] == 'sha256' and ev['parent_collection_id']:
                _resolve(state, 'backing_file_sha256', source=ev['collection_id'], evidence_id=ev['evidence_id'], scope='backing_file')
    existing = {(g['collection_id'], g['facet']) for g in state['residual_unknowns']}
    for gap in incoming['residual_unknowns']:
        key = (gap['collection_id'], gap['facet'])
        if key not in existing and not any(
                e['facet'] == gap['facet'] and e['status'] == 'SUCCESS'
                and gap.get('scope') == 'target'
                and same_target_ref(e['target_ref'], gap['target_ref'])
                for e in incoming['evidence']):
            state['residual_unknowns'].append(gap)
            existing.add(key)
    state['collection_status'] = incoming['collection_status']
    if state['lifecycle_status'] == 'NEEDS_CONTEXT' and incoming['collection_status'] != 'FAILED':
        state['lifecycle_status'] = 'READY_FOR_INVESTIGATION'
    return {'collection_ids': incoming['collection_ids'], 'added_evidence': len(incoming['evidence'])}


def _register_tool(state, data):
    name = data.get('name')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', name):
        raise ValueError('Tool name must be lowercase snake_case')
    if name == 'context_collector':
        raise ValueError('Collector is reserved for Node B')
    if not isinstance(data.get('description'), str) or not data['description'].strip():
        raise ValueError('Tool description required')
    if name in state['available_tools']:
        raise ValueError('Tool already registered')
    state['available_tools'][name] = {'description': data['description'],
        'registered_at': now(), 'enabled': True}
    return {'registered': name}


def _append_tool(state, data):
    run_id, tool = data.get('tool_run_id'), data.get('tool')
    if not isinstance(run_id, str) or not re.fullmatch(r'RUN-[A-Za-z0-9_-]{3,100}', run_id):
        raise ValueError('tool_run_id must begin RUN-')
    if any(r.get('tool_run_id') == run_id for r in state['tool_runs']):
        raise ValueError('Duplicate tool_run_id')
    if tool not in state['available_tools'] or not state['available_tools'][tool]['enabled']:
        raise ValueError('Tool not registered/enabled in this case')
    if data.get('status') not in STATUSES:
        raise ValueError('Invalid tool run status')
    if not target_matches(state, data.get('target_type'), data.get('target')):
        raise ValueError('Tool result target identity mismatch')
    if 'target_ref' in data:
        validate_target_ref(data['target_ref'])
        if not same_target_ref(state['target_ref'], data['target_ref']):
            raise ValueError('Tool result TargetRef mismatch')
        if data['target_ref']['kind'] != data['target_type'] or data['target_ref']['observed'] != state['target_ref']['observed']:
            raise ValueError('Tool result TargetRef disagrees with target')
    observations = data.get('observations')
    if not isinstance(observations, list):
        raise ValueError('observations must be a list')
    prepared = []
    for entry in observations:
        if not isinstance(entry, dict) or not isinstance(entry.get('facet'), str) or not entry['facet'] or entry.get('status') not in STATUSES:
            raise ValueError('Invalid tool observation')
        if entry['status'] != 'SUCCESS' and entry.get('value') is not None:
            raise ValueError('Non-successful observation must not contain a value')
        if entry['status'] == 'SUCCESS' and 'value' not in entry:
            raise ValueError('Successful observation requires value (can be false/null)')
        prepared.append(evidence_v2({'evidence_id': 'EV-' + uuid.uuid4().hex,
            'collection_id': None, 'tool_run_id': run_id, 'source_tool': tool,
            'target_type': state['target_type'], 'target': state['target'],
            'facet': entry['facet'], 'status': entry['status'],
            'value': entry.get('value') if entry['status'] == 'SUCCESS' else None,
            'reason': entry.get('reason'), 'observed_at': data.get('observed_at', now()),
            'coverage': entry.get('coverage', 'limited'), 'artifact_ref': entry.get('artifact_ref'),
            'parent_collection_id': None}, target_ref=data.get('target_ref') or state['target_ref'],
            source_kind='tool', source_id=tool, source_version=data.get('tool_version'),
            provider=data.get('provider'), limitations=entry.get('limitations', []),
            content_origin='provider_output'))
    state['tool_runs'].append({'tool_run_id': run_id, 'tool': tool, 'status': data['status'],
        'recorded_at': now(), 'error': data.get('error')})
    _record_conflicts(state, prepared)
    state['evidence'].extend(prepared)
    for ev in prepared:
        if ev['status'] == 'SUCCESS':
            _resolve(state, ev['facet'], source=run_id, evidence_id=ev['evidence_id'], target_ref=ev['target_ref'])
        else:
            if not any(g['facet'] == ev['facet'] and g.get('scope', 'target') == 'target'
                       and g.get('target_ref') and same_target_ref(g['target_ref'], ev['target_ref'])
                       for g in state['residual_unknowns']):
                state['residual_unknowns'].append({'collection_id': None, 'tool_run_id': run_id,
                    'target_type': state['target_type'], 'target': state['target'],
                    'target_ref': ev['target_ref'], 'scope': 'target',
                    'facet': ev['facet'], 'reason': ev['reason'] or ev['status'], 'state': 'UNKNOWN'})
    return {'tool_run_id': run_id, 'added_evidence': len(prepared)}


def _action(state, data):
    event_id = data.get('event_id')
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError('event_id required')
    if any(x.get('event_id') == event_id for x in state['action_history']):
        raise ValueError('Duplicate event_id')
    action = data.get('action')
    if action not in {'START_INVESTIGATION', 'REQUEST_MORE_CONTEXT', 'REQUEST_APPROVAL', 'CLOSE_CASE', 'NOTE'}:
        raise ValueError('Unsupported action')
    current = state['lifecycle_status']
    transitions = {
        'START_INVESTIGATION': ({'READY_FOR_INVESTIGATION', 'NEEDS_CONTEXT'}, 'INVESTIGATING'),
        'REQUEST_MORE_CONTEXT': ({'INVESTIGATING', 'READY_FOR_INVESTIGATION'}, 'NEEDS_CONTEXT'),
        'REQUEST_APPROVAL': ({'INVESTIGATING'}, 'AWAITING_APPROVAL'),
        'CLOSE_CASE': ({'INVESTIGATING', 'AWAITING_APPROVAL'}, 'CLOSED'),
    }
    if action in transitions:
        allowed, dest = transitions[action]
        if current not in allowed:
            raise ValueError(f'Invalid lifecycle transition: {current} -> {action}')
        if action == 'CLOSE_CASE' and (state.get('assessment') is None or state['assessment'].get('validity') == 'STALE_CONFLICT'):
            raise ValueError('Cannot close case without current assessment')
        state['lifecycle_status'] = dest
    elif current == 'CLOSED':
        raise ValueError('Cannot append notes to closed case')
    state['action_history'].append({'event_id': event_id, 'action': action,
        'actor': data.get('actor', 'unknown'), 'reason': data.get('reason'),
        'recorded_at': now(), 'lifecycle_before': current, 'lifecycle_after': state['lifecycle_status']})
    return {'event_id': event_id, 'lifecycle_status': state['lifecycle_status']}


def _resolve_conflict(state, data):
    cid = data.get('conflict_id')
    selected = data.get('selected_evidence_id')
    if not isinstance(data.get('reason'), str) or len(data['reason'].strip()) < 8:
        raise ValueError('Conflict resolution requires a meaningful reason')
    if not isinstance(data.get('approver'), str) or not data['approver'].strip():
        raise ValueError('Verified analyst required')
    conflict = next((x for x in state.get('evidence_conflicts', []) if x['conflict_id'] == cid), None)
    if not conflict or conflict['status'] != 'UNRESOLVED':
        raise ValueError('Unknown or already resolved conflict')
    if selected not in conflict['evidence_ids']:
        raise ValueError('Selected evidence is not part of conflict')
    conflict['status'] = 'RESOLVED'
    conflict['resolution'] = {'selected_evidence_id': selected,
        'reason': data['reason'], 'approver': data['approver'], 'recorded_at': now()}
    state.setdefault('conflict_resolution_history', []).append({'conflict_id': cid,
        **conflict['resolution']})
    return {'conflict_id': cid, 'status': 'RESOLVED'}


def _assessment(state, data):
    if state['lifecycle_status'] not in {'INVESTIGATING', 'AWAITING_APPROVAL'}:
        raise ValueError('Assessment requires investigation')
    prior = state.get('assessment')
    if prior is not None and prior.get('validity') != 'STALE_CONFLICT':
        raise ValueError('Current assessment already recorded; cannot overwrite')
    if prior is not None and prior.get('validity') == 'STALE_CONFLICT':
        if any(c['status'] == 'UNRESOLVED' for c in state.get('evidence_conflicts', [])):
            raise ValueError('Resolve outstanding conflicts before reassessment')
    if data.get('verdict') not in {'MALICIOUS', 'SUSPICIOUS', 'BENIGN', 'UNKNOWN'}:
        raise ValueError('Unsupported verdict')
    conf = data.get('confidence')
    if not isinstance(conf, (float, int)) or isinstance(conf, bool) or not 0 <= conf <= 1:
        raise ValueError('confidence must be between 0 and 1')
    ids = data.get('evidence_ids')
    if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
        raise ValueError('evidence_ids must be list of strings')
    conflicted = {eid for c in state.get('evidence_conflicts', []) if c['status'] == 'UNRESOLVED' for eid in c['evidence_ids']}
    if set(ids) & conflicted:
        raise ValueError('Assessment cites unresolved conflicting evidence')
    valid = {e['evidence_id'] for e in state['evidence'] if e['status'] == 'SUCCESS'}
    if not set(ids) <= valid or (data['verdict'] != 'UNKNOWN' and not ids):
        raise ValueError('Assessment must cite valid successful evidence')
    if not isinstance(data.get('rationale'), str) or not data['rationale'].strip():
        raise ValueError('rationale required')
    if prior is not None:
        state.setdefault('assessment_history', []).append(prior)
    state['assessment'] = {'verdict': data['verdict'], 'confidence': conf,
        'evidence_ids': ids, 'rationale': data['rationale'],
        'actor': data.get('actor', 'unknown'), 'recorded_at': now(), 'validity': 'CURRENT',
        'note': 'Recorded assessment; CaseManager did not independently verify verdict.'}
    _resolve(state, 'malware_assessment', source='assessment', scope='case')
    return {'verdict': data['verdict']}


def _response(state, data):
    if state['lifecycle_status'] not in {'AWAITING_APPROVAL', 'INVESTIGATING'}:
        raise ValueError('Response record requires investigation')
    if data.get('human_approved') is not True or not isinstance(data.get('approver'), str) or not data['approver'].strip():
        raise ValueError('Explicit human approval and approver required')
    if state.get('assessment') and state['assessment'].get('validity') == 'STALE_CONFLICT':
        raise ValueError('Cannot approve response while assessment is stale')
    if data.get('status') not in {'PROPOSED', 'APPROVED', 'REJECTED', 'EXECUTED_EXTERNALLY', 'FAILED_EXTERNALLY'}:
        raise ValueError('Unsupported response status')
    if not isinstance(data.get('description'), str) or not data['description'].strip():
        raise ValueError('description required')
    state['response_history'].append({'response_id': 'RESP-' + uuid.uuid4().hex,
        'status': data['status'], 'description': data['description'],
        'approver': data['approver'], 'recorded_at': now(),
        'note': 'Audit record only; no operating-system response was executed by Node C.'})
    return {'response_count': len(state['response_history'])}


OPERATIONS = {'collection': _append_collection, 'register-tool': _register_tool,
              'tool-result': _append_tool, 'resolve-conflict': _resolve_conflict, 'action': _action,
              'assessment': _assessment, 'response': _response}


def apply_update(path, operation, payload, *, source_path=None, authorization=None, trusted_keys=None):
    if operation not in OPERATIONS:
        raise ValueError('Unknown operation')
    with locked_case(path):
        state = validate_case(read_json(path))
        if state['lifecycle_status'] == 'CLOSED':
            raise ValueError('Case is closed and immutable')
        if operation in ('tool-result', 'response', 'resolve-conflict'):
            auth_record = _verify_proof(state, operation, payload, authorization, trusted_keys)
        else:
            auth_record = None
        if operation == 'collection':
            result = _append_collection(state, payload, source_path)
        else:
            result = OPERATIONS[operation](state, payload)
        if auth_record:
            state.setdefault('authorization_audit', []).append(auth_record)
        state['revision'] = state.get('revision', 1) + 1
        state['updated_at'] = now()
        write_atomic(path, state)
        return {'case_id': state['case_id'], 'revision': state['revision'], **result}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Node C CaseState + CaseManager (no tool execution)')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='Create case from Node B context')
    init.add_argument('--context', required=True)
    init.add_argument('--output', default='cases')
    for name in ('collection', 'register-tool', 'tool-result', 'resolve-conflict', 'action', 'assessment', 'response'):
        p = sub.add_parser(name)
        p.add_argument('--case', required=True, help='Existing case_state.json path')
        p.add_argument('--input', required=True, help='JSON payload path')
    show = sub.add_parser('show')
    show.add_argument('--case', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            ctx = read_json(args.context)
            state = build_case_state(ctx, source_path=args.context)
            path = save_case_state(state, args.output)
            result = {'case_id': state['case_id'], 'case_state_path': str(path.resolve()), 'revision': 1}
        elif args.command == 'show':
            state = validate_case(read_json(args.case))
            result = {'case_id': state['case_id'], 'revision': state.get('revision', 1),
                'lifecycle_status': state['lifecycle_status'], 'evidence_count': len(state['evidence']),
                'unknown_count': len(state['residual_unknowns']), 'tool_run_count': len(state['tool_runs']),
                'assessment': state['assessment']}
        else:
            if args.command in ('tool-result', 'response', 'resolve-conflict'):
                raise PermissionError('Protected operation: use trusted Orchestrator/approval adapter, not public CLI')
            result = apply_update(args.case, args.command, read_json(args.input), source_path=args.input)
    except (OSError, ValueError, PermissionError, TimeoutError, json.JSONDecodeError) as exc:
        parser.exit(1, f'Node C error: {exc}\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
