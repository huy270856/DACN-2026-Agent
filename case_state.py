"""Node C: transform Context Collector v1 output into an evidence-aware CaseState.

No verdicts, tool execution, IOC lookup, or external API calls here.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import os
import uuid

SCHEMA_VERSION = 'casestate-v1'
VALID_STATUSES = {'SUCCESS', 'DEGRADED', 'FAILED', 'UNAVAILABLE'}


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _validate(ctx):
    if not isinstance(ctx, dict):
        raise ValueError('Collector result must be an object')
    for field in ('collection_id', 'target_type', 'target', 'status', 'facets'):
        if field not in ctx:
            raise ValueError(f'Missing collector field: {field}')
    if ctx.get('schema_version') != 'context-v1':
        raise ValueError('Unsupported collector schema_version')
    if ctx['target_type'] not in ('FILE', 'PROCESS') or ctx['status'] not in VALID_STATUSES:
        raise ValueError('Invalid target type or collection status')
    if not isinstance(ctx['facets'], dict) or not isinstance(ctx['target'], dict):
        raise ValueError('Malformed target or facets')
    if not isinstance(ctx['collection_id'], str) or not ctx['collection_id']:
        raise ValueError('Invalid collection_id')
    for name, entry in ctx['facets'].items():
        if not isinstance(entry, dict) or entry.get('status') not in VALID_STATUSES:
            raise ValueError(f'Invalid facet: {name}')
    if ctx['target_type'] == 'PROCESS' and not isinstance(ctx['target'].get('pid'), int):
        raise ValueError('PROCESS target requires integer pid')
    if ctx['target_type'] == 'FILE' and not isinstance(ctx['target'].get('path'), str):
        raise ValueError('FILE target requires path')


def _evidence(ctx, name, entry, parent=None):
    """Preserve provenance. A successful false value is still a valid observation."""
    return {
        'evidence_id': 'EV-' + uuid.uuid4().hex,
        'collection_id': ctx['collection_id'],
        'source_tool': 'context_collector',
        'target_type': ctx['target_type'],
        'target': ctx['target'],
        'facet': name,
        'status': entry['status'],
        'value': entry.get('value') if entry['status'] == 'SUCCESS' else None,
        'reason': entry.get('reason'),
        'observed_at': ctx.get('finished_at', ctx.get('started_at')),
        'coverage': 'limited',
        'parent_collection_id': parent,
        'artifact_ref': None,
    }


def build_case_state(ctx, *, source_path=None):
    _validate(ctx)
    nested = ctx.get('backing_file_context')
    if nested is not None:
        _validate(nested)
        if ctx['target_type'] != 'PROCESS' or nested['target_type'] != 'FILE':
            raise ValueError('Backing file must be FILE nested under PROCESS')
        if nested['collection_id'] == ctx['collection_id']:
            raise ValueError('Nested collection_id must be unique')
    evidence = []
    gaps = []
    collection_errors = []
    collections = [ctx] + ([nested] if nested else [])
    for item in collections:
        parent = ctx['collection_id'] if item is nested else None
        for name, facet in item['facets'].items():
            evidence.append(_evidence(item, name, facet, parent))
            if facet['status'] != 'SUCCESS':
                gaps.append({'collection_id': item['collection_id'], 'facet': name,
                             'reason': facet.get('reason', facet['status']), 'state': 'UNKNOWN'})
        for err in item.get('errors', []):
            collection_errors.append({'collection_id': item['collection_id'], **err})
    # Explicitly model intentionally uncollected facets; absence is NOT benign evidence.
    if ctx['target_type'] == 'PROCESS' and nested is None:
        gaps.append({'collection_id': ctx['collection_id'], 'facet': 'backing_file_sha256',
                     'reason': 'not_requested', 'state': 'NOT_COLLECTED'})
    if ctx['target_type'] == 'PROCESS':
        gaps.extend([
            {'collection_id': ctx['collection_id'], 'facet': 'runtime_modules', 'reason': 'outside_collector_scope', 'state': 'NOT_COLLECTED'},
            {'collection_id': ctx['collection_id'], 'facet': 'network_activity', 'reason': 'outside_collector_scope', 'state': 'NOT_COLLECTED'},
        ])
    gaps.append({'collection_id': ctx['collection_id'], 'facet': 'malware_assessment',
                 'reason': 'analysis_not_performed', 'state': 'NOT_COLLECTED'})
    return {
        'schema_version': SCHEMA_VERSION,
        'case_id': 'CASE-' + uuid.uuid4().hex,
        'created_at': _utc_now(),
        'lifecycle_status': 'NEEDS_CONTEXT' if ctx['status'] == 'FAILED' else 'READY_FOR_INVESTIGATION',
        'target_type': ctx['target_type'],
        'target': ctx['target'],
        'collection_status': ctx['status'],
        'collection_ids': [c['collection_id'] for c in collections],
        'source_context_path': str(Path(source_path).resolve()) if source_path else None,
        'evidence': evidence,
        'residual_unknowns': gaps,
        'collection_errors': collection_errors,
        'collection_limitations': [
            {'collection_id': c['collection_id'], 'message': limitation}
            for c in collections for limitation in c.get('limitations', [])
        ],
        'tool_runs': [{'tool': 'context_collector', 'collection_id': c['collection_id'], 'status': c['status']}
                      for c in collections],
        'evidence_conflicts': [],
        'used_authorization_nonces': [],
        'authorization_audit': [],
        'available_tools': {},  # populated later by Tool Registry, never fabricated here
        'action_history': [],
        'assessment': None,
        'response_history': [],
        'resolved_unknowns': [],
        'revision': 1,
        'updated_at': _utc_now(),
    }


def save_case_state(state, directory):
    dest = Path(directory) / state['case_id']
    dest.mkdir(parents=True, exist_ok=False)
    path = dest / 'case_state.json'
    fd, temp = tempfile.mkstemp(dir=dest, prefix='.case-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(state, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build Node C CaseState from Node B context.json')
    parser.add_argument('--context', required=True, type=Path)
    parser.add_argument('--output', default='cases', type=Path)
    args = parser.parse_args(argv)
    try:
        with args.context.open(encoding='utf-8-sig') as stream:
            ctx = json.load(stream)
        state = build_case_state(ctx, source_path=args.context)
        saved = save_case_state(state, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f'CaseState build failed: {exc}\n')
    print(json.dumps({'case_id': state['case_id'], 'case_state_path': str(saved.resolve()),
                      'evidence_count': len(state['evidence']),
                      'residual_unknown_count': len(state['residual_unknowns'])}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
