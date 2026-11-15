"""Validation never edits LLM semantics. Phase enrichment is trusted metadata only."""
import copy
import re
from .grounding import verify
from .imports_tool import FACET


def validate_refs(obj, facts):
    visible = {e['evidence_id']: e for e in facts['evidence']}
    refs = list(obj['evidence_refs'])
    if 'assessment' in obj:
        a = obj['assessment']
        refs += a['supporting_evidence_ids'] + a['contradicting_evidence_ids']
        refs += [i for c in a['claims'] for i in c['evidence_ids']]
        refs += [b['evidence_id'] for b in obj['import_bindings']]
    if set(refs) - visible.keys():
        raise ValueError('EVIDENCE_NOT_VISIBLE: cited ID not present in this prompt')
    return visible, set(refs)


def finalize(obj, facts, initial_ids, prediction):
    visible, refs = validate_refs(obj, facts)
    claims = obj['assessment']['claims']
    uses, bindings = [], []
    for b in obj['import_bindings']:
        if b['claim_index'] >= len(claims):
            raise ValueError('CLAIM_INDEX_UNKNOWN')
        claim = claims[b['claim_index']]
        ev = visible[b['evidence_id']]
        entry = next((e for e in (ev.get('value') or {}).get('entries', [])
                      if e.get('entry_index') == b['entry_index']), None)
        if ev['facet'] != FACET or entry is None or b['evidence_id'] not in claim['evidence_ids']:
            raise ValueError('CLAIM_SOURCE_BINDING: no matching visible entry/source')
        literal = entry['symbol'] if entry['symbol'] is not None else '#' + str(entry['ordinal'])
        if entry['library'] not in claim['text'] or literal not in claim['text']:
            raise ValueError('CLAIM_LITERAL_MISMATCH: selected entry is not stated in claim')
        bindings.append({**copy.deepcopy(b), 'literal': copy.deepcopy(entry),
                         'phase': ev['phase'], 'value_sha256': ev['full_detail_ref']['value_sha256']})
        if b['evidence_id'] not in initial_ids and entry['symbol'] is not None:
            uses.append({'evidence_id': b['evidence_id'], 'library': entry['library'],
                         'symbol': entry['symbol'], 'why_relevant': claim['text']})
    for i, c in enumerate(claims):
        imported = [visible[e] for e in c['evidence_ids'] if visible[e]['facet'] == FACET]
        if c['kind'] == 'OBSERVED' and re.search(r'\.dll\b|\bnull\b', c['text'], re.I):
            if not imported or not any(b['claim_index'] == i for b in bindings):
                raise ValueError('IMPORT_CLAIM_REQUIRES_LITERAL_BINDING')
        if c['kind'] == 'OBSERVED' and not c['evidence_ids']:
            raise ValueError('OBSERVED_WITHOUT_SOURCE')
    checks = verify({'assessment': obj['assessment'], 'new_fact_uses': uses}, facts, initial_ids, prediction)
    text = ' '.join([obj['assessment']['explanation']] + [c['text'] for c in claims])
    if (not any(e['facet'] == FACET and e['status'] == 'SUCCESS' for e in visible.values())
            and re.search(r'no (?:declared )?imports (?:are )?declared|no declared imports|no imports exist', text, re.I)):
        checks['flags'].append('absence_claim_without_imports_source_suspected_unverified')
    if any(re.search(r'\bentropy\b|\b\d+(?:\.\d+)?\s*%\s*(?:probability|chance)', c['text'], re.I)
           for c in claims):
        checks['flags'].append('numeric_or_entropy_claim_suspected_unverified')
    flagged = bool(checks['flags'] or checks['claim_flags'] or checks['consistency']['flags']
                   or not checks['grounding_screen']['grounded'])
    if flagged:
        checks['effective_recommendation'].update(action='MANUAL_REVIEW', review_required=True,
                                                 requires_human_decision=True)
    return {'llm_assessment': copy.deepcopy(obj),
            'trusted_metadata': {'case_id': facts['case_id'], 'case_revision': facts['case_revision'],
                'target_sha256': facts['target_sha256'], 'cited_initial_ids': sorted(refs & initial_ids),
                'cited_committed_during_run_ids': sorted(refs - initial_ids),
                'claim_literal_bindings': bindings, 'semantic_grounding': 'PENDING_INDEPENDENT_REVIEW'},
            'verification': checks, 'has_suspected_or_consistency_flags': flagged}
