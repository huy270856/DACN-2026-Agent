"""Node B/C v1.2 additive contracts; legacy context-v1/casestate-v1 remain readable.

A TargetRef describes an observation, not a guarantee that a mutable path remains safe.
Node D MUST revalidate the actual opened handle/process before execution.
"""
from __future__ import annotations
import hashlib
import copy
import json
import os
from pathlib import Path

TARGET_REF_VERSION = 'target-ref-v1'
EVIDENCE_VERSION = 'evidence-v2'


def _valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdefABCDEF' for c in value)


def target_ref_from_context(ctx):
    """Create a snapshot from observations, never invent unavailable identity fields."""
    typ = ctx['target_type']
    target = ctx['target']
    facets = ctx.get('facets', {})
    if typ == 'PROCESS':
        pid = target.get('pid')
        started = target.get('start_time_epoch')
        return {'schema_version': TARGET_REF_VERSION, 'kind': 'PROCESS',
                'observed': {'pid': pid, 'start_time_epoch': started},
                'identity_strength': 'PARTIAL' if isinstance(pid, int) and isinstance(started, (int, float)) else 'UNAVAILABLE',
                'verified_digest': None, 'snapshot': {}, 'revalidation_required': True}
    path = target.get('path')
    ident = facets.get('file_identity', {})
    snap = ident.get('value') if ident.get('status') == 'SUCCESS' and isinstance(ident.get('value'), dict) else {}
    hash_entry = facets.get('sha256', {})
    stable = facets.get('file_unchanged_during_collection', {})
    digest = hash_entry.get('value') if hash_entry.get('status') == 'SUCCESS' and _valid_sha(hash_entry.get('value')) and stable.get('status') == 'SUCCESS' and stable.get('value') is True else None
    has_file_id = isinstance(snap.get('device'), int) and isinstance(snap.get('inode'), int) and snap.get('inode') != 0
    strength = 'STRONG' if has_file_id and digest else 'PARTIAL' if has_file_id or digest or snap else 'UNAVAILABLE'
    return {'schema_version': TARGET_REF_VERSION, 'kind': 'FILE',
            'observed': {'path': path}, 'identity_strength': strength,
            'verified_digest': {'algorithm': 'sha256', 'value': digest} if digest else None,
            'snapshot': copy.deepcopy(snap), 'revalidation_required': True}


def validate_target_ref(ref):
    if not isinstance(ref, dict) or ref.get('schema_version') != TARGET_REF_VERSION or ref.get('kind') not in ('FILE', 'PROCESS'):
        raise ValueError('Invalid TargetRef contract')
    if ref.get('identity_strength') not in ('STRONG', 'PARTIAL', 'UNAVAILABLE') or not isinstance(ref.get('observed'), dict):
        raise ValueError('Invalid TargetRef identity')
    if ref['kind'] == 'FILE' and not isinstance(ref['observed'].get('path'), str):
        raise ValueError('FILE TargetRef requires path')
    if ref['kind'] == 'PROCESS' and not isinstance(ref['observed'].get('pid'), int):
        raise ValueError('PROCESS TargetRef requires pid')
    dig = ref.get('verified_digest')
    if dig is not None and (not isinstance(dig, dict) or dig.get('algorithm') != 'sha256' or not _valid_sha(dig.get('value'))):
        raise ValueError('Invalid verified digest')
    if not isinstance(ref.get('snapshot'), dict):
        raise ValueError('Invalid TargetRef snapshot')
    return ref


def same_target_ref(a, b):
    """Conservative cross-observation binding; returns False for known differences.

    UNAVAILABLE identity must not be accepted as a verified binding by Node D.
    """
    validate_target_ref(a)
    validate_target_ref(b)
    if a['kind'] != b['kind']:
        return False
    ao, bo = a['observed'], b['observed']
    if a['kind'] == 'PROCESS':
        return (ao.get('pid') == bo.get('pid') and ao.get('start_time_epoch') is not None
                and ao.get('start_time_epoch') == bo.get('start_time_epoch'))
    if os.path.normcase(os.path.normpath(ao.get('path', ''))) != os.path.normcase(os.path.normpath(bo.get('path', ''))):
        return False
    # Only compare facts known in both observations. Missing data is NOT a verified match.
    for key in ('device', 'inode', 'size_bytes', 'mtime_ns'):
        va, vb = a['snapshot'].get(key), b['snapshot'].get(key)
        if va is not None and vb is not None and va != vb:
            return False
    da, db = a.get('verified_digest'), b.get('verified_digest')
    if da and db and da['value'].lower() != db['value'].lower():
        return False
    return True


def evidence_v2(legacy, *, target_ref, source_kind, source_id, source_version=None,
                provider=None, limitations=None, content_origin='analysis_target'):
    """Add a versioned envelope without removing any v1 fields."""
    validate_target_ref(target_ref)
    result = dict(legacy)
    result.update({'evidence_schema_version': EVIDENCE_VERSION,
        'target_ref': target_ref, 'source': {'kind': source_kind, 'id': source_id, 'version': source_version},
        'provider': provider, 'limitations': list(limitations or []),
        'trust_level': 'UNTRUSTED_CONTENT', 'content_origin': content_origin,
        'parent_evidence_ids': [], 'analysis_profile': None})
    return result


def evidence_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
