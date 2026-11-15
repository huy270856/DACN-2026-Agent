"""Bounded views of committed CaseState data; never a target-file analyzer."""
import copy
from d0.validate import digest
from .imports_tool import FACET

PAGE_SIZE = 16


def fetch(state, *, case_id, revision, target_sha256, evidence_id, value_sha256,
          offset=0, limit=PAGE_SIZE):
    if state['case_id'] != case_id or state['revision'] != revision:
        raise ValueError('RETRIEVAL_CASE_OR_REVISION_MISMATCH')
    if state['target_ref']['verified_digest']['value'] != target_sha256:
        raise ValueError('RETRIEVAL_TARGET_MISMATCH')
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= PAGE_SIZE:
        raise ValueError('RETRIEVAL_BOUNDS')
    ev = next((e for e in state['evidence'] if e['evidence_id'] == evidence_id), None)
    if ev is None or ev['facet'] != FACET or ev['status'] != 'SUCCESS' or not ev.get('tool_run_id'):
        raise ValueError('RETRIEVAL_NO_COMMITTED_IMPORTS')
    value = ev['value']
    if value['target_sha256'] != target_sha256 or digest(value) != value_sha256:
        raise ValueError('RETRIEVAL_SOURCE_BINDING_MISMATCH')
    entries = value['entries']
    if value['returned_entries'] != len(entries) or offset > len(entries):
        raise ValueError('RETRIEVAL_BOUNDS_OR_COUNT')
    return {'evidence_id': evidence_id, 'case_id': case_id, 'case_revision': revision,
            'target_sha256': target_sha256, 'value_sha256': value_sha256,
            'tool_run_id': ev['tool_run_id'], 'source': copy.deepcopy(ev.get('source')),
            'provider_total_entries': value['total_entries'], 'committed_entries': len(entries),
            'offset': offset, 'limit': limit, 'visible_entries': len(entries[offset:offset + limit]),
            'entries': [dict(entry_index=i, **copy.deepcopy(e))
                        for i, e in enumerate(entries[offset:offset + limit], offset)],
            'next_offset': offset + limit if offset + limit < len(entries) else None,
            'trust_level': 'UNTRUSTED_CONTENT', 'new_evidence_created': False}
