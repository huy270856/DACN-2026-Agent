"""06B-R2 v3.4 evidence-native claim contract: structural, resolution, grounding,
fail-safe, and explicit MOCK_LLM integration. The eliminated v3.3 association error
classes (over-binding, claim_index, literal-in-text) are asserted gone by design.
No live inference here; MOCK_LLM is never evidence of autonomous behaviour.
"""
import copy
import json
from pathlib import Path
import pytest
from agent.config import AgentConfig
from agent.planner import PlanResult, PlannerError
from investigation_v3 import repair_context as rc, final_v34 as fv, workflow_v34 as wv
from investigation_v3.final_v34 import finalize, validate_refs
from investigation_v3.imports_tool import FACET
from evaluation.task06b.tests.test_multistep import raw_case, with_detector
from evaluation.task06a.tests.test_task06a import _valid_v2

ROOT = Path(__file__).resolve().parents[3]
CFG = AgentConfig(max_iterations=5, max_context_chars=24000, num_predict=2048, wall_clock_s=180)


@pytest.fixture
def saved():
    return json.loads((ROOT / 'evaluation/task06b/results/dev_v2/01_C.json').read_text(encoding='utf8'))


def context(saved):
    ids = {e['evidence_id'] for e in saved['initial_state']['evidence']}
    return rc.build(saved['final_state'], [], CFG, initial_ids=ids, history=[], pages={}, retrieval_available=True), ids


def final(ctx):
    f = ctx['facts']
    a = _valid_v2()['assessment']
    a.update(supporting_evidence_ids=[], contradicting_evidence_ids=[], claims=[],
             review_required=True, recommendation='MANUAL_REVIEW')
    return {'action': 'FINISH', 'case_id': f['case_id'], 'case_revision': f['case_revision'],
            'reason': 'Static evidence remains limited', 'evidence_refs': [], 'assessment': a,
            'change_explanation': 'No unsupported conclusion', 'stop_reason': 'Static-only limits'}


def observed(ctx, *, with_ref=True, text=None, entry_index=0):
    p = final(ctx)
    ev = next(e for e in ctx['facts']['evidence'] if e['facet'] == FACET)
    claim = {'kind': 'OBSERVED',
             'text': text or 'The binary declares WS2_32.dll networking imports.',
             'evidence_ids': [ev['evidence_id']]}
    if with_ref:
        claim['import_refs'] = [{'evidence_id': ev['evidence_id'], 'entry_index': entry_index}]
    p['assessment']['claims'] = [claim]
    return p, ev


# ---------------------------------------------------------------- structural

@pytest.mark.parametrize('field', ['assessment', 'stop_reason', 'change_explanation'])
def test_finish_required_fields(saved, field):
    ctx, _ = context(saved)
    p = final(ctx); del p[field]
    assert field in fv.contract(ctx)['oneOf'][0]['required']
    with pytest.raises(ValueError):
        fv.parse(json.dumps(p), ctx)


def test_no_separate_import_bindings_array_accepted(saved):
    """RC1 by design: there is no top-level binding array to mis-populate."""
    ctx, _ = context(saved)
    assert 'import_bindings' not in fv.contract(ctx)['oneOf'][0]['properties']
    p = final(ctx); p['import_bindings'] = [{'claim_index': 0, 'evidence_id': 'x', 'entry_index': 0}]
    with pytest.raises(ValueError):
        fv.parse(json.dumps(p), ctx)


def test_claim_has_no_claim_index_field(saved):
    ctx, _ = context(saved)
    item = fv.contract(ctx)['oneOf'][0]['properties']['assessment']['properties']['claims']['items']
    assert 'claim_index' not in json.dumps(item)
    assert 'import_refs' in item['properties']
    assert 'import_refs' not in item['required']  # optional


@pytest.mark.parametrize('raw', ['{', '{"action":"FINISH"', 'null', '{"action":"DELETE"}'])
def test_malformed_truncated_wrong_enum(saved, raw):
    with pytest.raises(ValueError):
        fv.parse(raw, context(saved)[0])


def test_action_selection_is_not_final_authorship(saved):
    ctx, _ = context(saved); ctx['finalization_stage'] = False
    p = final(ctx)
    with pytest.raises(ValueError):
        fv.parse(json.dumps(p), ctx)
    select = {k: p[k] for k in ('action', 'case_id', 'case_revision', 'reason', 'evidence_refs')}
    assert fv.parse(json.dumps(select), ctx)['action'] == 'FINISH'
    ctx['finalization_stage'] = True
    with pytest.raises(ValueError):
        fv.parse(json.dumps(select), ctx)


def test_controller_evidence_ref_limit_preserved(saved):
    ctx, _ = context(saved); p = final(ctx)
    p['evidence_refs'] = ['EV-a', 'EV-b', 'EV-c', 'EV-d']
    with pytest.raises(ValueError):
        fv.parse(json.dumps(p), ctx)


# ---------------------------------------------- evidence-native resolution (RC2/RC3)

def test_general_claim_without_literal_is_accepted_and_resolved(saved):
    """RC2/RC3 fix: the model points at the entry; the exact DLL/symbol is NOT
    required in the prose. The trusted layer resolves it for display."""
    ctx, ids = context(saved)
    p, ev = observed(ctx, with_ref=True, entry_index=0)
    r = finalize(p, ctx['facts'], ids, saved['model_prediction'])
    rr = r['trusted_metadata']['resolved_import_refs']
    assert len(rr) == 1 and rr[0]['claim_index'] == 0
    assert rr[0]['library'] == 'WS2_32.dll' and rr[0]['symbol'] == 'WSAEnumNetworkEvents'
    assert rr[0]['resolved_import'] == 'WS2_32.dll!WSAEnumNetworkEvents'
    assert rr[0]['phase'] == 'COMMITTED_DURING_RUN'
    # The literal was NOT in the claim text, yet the final is accepted.
    assert 'WSAEnumNetworkEvents' not in p['assessment']['claims'][0]['text']


def test_observed_claim_needs_no_import_ref(saved):
    ctx, ids = context(saved)
    p, _ = observed(ctx, with_ref=False, text='Standard C runtime behaviour is declared.')
    r = finalize(p, ctx['facts'], ids, saved['model_prediction'])
    assert r['trusted_metadata']['resolved_import_refs'] == []


@pytest.mark.parametrize('bad', ['wrong_source_facet', 'ref_not_claim_source', 'invisible_entry'])
def test_import_ref_structural_rejections(saved, bad):
    ctx, ids = context(saved)
    p, ev = observed(ctx, with_ref=True)
    fmt = next(e['evidence_id'] for e in ctx['facts']['evidence'] if e['facet'] == 'format')
    if bad == 'wrong_source_facet':
        p['assessment']['claims'][0]['evidence_ids'].append(fmt)
        p['assessment']['claims'][0]['import_refs'][0]['evidence_id'] = fmt
    if bad == 'ref_not_claim_source':
        p['assessment']['claims'][0]['import_refs'][0]['evidence_id'] = fmt  # not in evidence_ids
    if bad == 'invisible_entry':
        p['assessment']['claims'][0]['import_refs'][0]['entry_index'] = 63
    with pytest.raises(ValueError):
        finalize(p, ctx['facts'], ids, saved['model_prediction'])


def test_prediction_claim_carries_no_import_ref_and_validates(saved):
    """The v3.3 over-binding shape (a prediction claim bound to an import entry) is
    structurally absent: a prediction claim simply has no import_refs."""
    ctx, ids = context(saved)
    pred = next(e['evidence_id'] for e in ctx['facts']['evidence'] if e['facet'] == 'static.pe_malware_prediction')
    p = final(ctx)
    p['assessment']['claims'] = [{'kind': 'OBSERVED',
        'text': 'The detector raw score is uncalibrated and is not a probability.',
        'evidence_ids': [pred]}]
    r = finalize(p, ctx['facts'], ids, saved['model_prediction'])
    assert r['trusted_metadata']['resolved_import_refs'] == []
    # If the model DID try to point a prediction claim at an import, it is rejected, not silently mis-paired.
    p['assessment']['claims'][0]['import_refs'] = [{'evidence_id': pred, 'entry_index': 0}]
    with pytest.raises(ValueError):
        finalize(p, ctx['facts'], ids, saved['model_prediction'])


def test_unknown_or_invisible_evidence_rejected(saved):
    ctx, ids = context(saved)
    p, _ = observed(ctx, with_ref=False)
    p['assessment']['claims'][0]['evidence_ids'] = ['EV-unknown']
    with pytest.raises(ValueError):
        validate_refs(p, ctx['facts'])


def test_observed_without_source_rejected(saved):
    ctx, ids = context(saved)
    p, _ = observed(ctx, with_ref=False)
    p['assessment']['claims'][0]['evidence_ids'] = []
    with pytest.raises(ValueError):
        finalize(p, ctx['facts'], ids, saved['model_prediction'])


# -------------------------------------------------------- grounding / honesty

def test_self_corroboration_and_numeric_are_suspected(saved):
    ctx, ids = context(saved)
    pred = next(e['evidence_id'] for e in ctx['facts']['evidence'] if e['facet'] == 'static.pe_malware_prediction')
    p = final(ctx)
    p['assessment'].update(supporting_evidence_ids=[pred], review_required=False, recommendation='MONITOR')
    p['assessment']['claims'] = [{'kind': 'OBSERVED', 'text': 'Entropy is 7.99', 'evidence_ids': [pred]}]
    r = finalize(p, ctx['facts'], ids, saved['model_prediction'])
    assert 'prediction_used_as_own_corroboration' in r['verification']['flags']
    assert 'numeric_or_entropy_claim_suspected_unverified' in r['verification']['flags']
    assert r['has_suspected_or_consistency_flags']
    assert r['verification']['effective_recommendation']['action'] == 'MANUAL_REVIEW'
    assert r['llm_assessment']['assessment']['review_required'] is False  # model text preserved verbatim


def test_fabricated_api_is_flagged_not_silently_accepted(saved):
    ctx, ids = context(saved)
    ev = next(e for e in ctx['facts']['evidence'] if e['facet'] == FACET)
    p = final(ctx)
    p['assessment']['claims'] = [{'kind': 'OBSERVED',
        'text': 'The binary imports VirtualAllocEx and WriteProcessMemory for injection.',
        'evidence_ids': [ev['evidence_id']]}]
    r = finalize(p, ctx['facts'], ids, saved['model_prediction'])
    assert r['has_suspected_or_consistency_flags']


# ------------------------------------------------------- MOCK_LLM integration

class Mock:
    is_mock = True
    def __init__(self, mode='normal'): self.mode = mode; self.contexts = []
    def decide(self, ctx):
        self.contexts.append(copy.deepcopy(ctx)); f = ctx['facts']; n = len(self.contexts)
        if self.mode == 'unavailable':
            raise PlannerError('offline test')
        if self.mode == 'bad' or (self.mode == 'repair' and n == 1):
            return PlanResult('{', 0, {'mock': True})
        p = final(ctx)
        if self.mode == 'tool' and n == 1:
            t = f['available_tools'][0]
            p = {k: p[k] for k in ('action', 'case_id', 'case_revision', 'reason', 'evidence_refs')}
            p.update(action='TOOL_CALL', tool={k: t[k] for k in ('tool_id', 'tool_version', 'provider_id')})
            p['tool']['arguments'] = {'max_entries': 64}
        elif self.mode == 'tool':
            ev = next(e for e in f['evidence'] if e['facet'] == FACET)
            entry = ev['value']['entries'][0]
            p['assessment']['claims'] = [{'kind': 'OBSERVED',
                'text': 'A committed declared import was observed after analysis.',
                'evidence_ids': [ev['evidence_id']],
                'import_refs': [{'evidence_id': ev['evidence_id'], 'entry_index': entry['entry_index']}]}]
        if p['action'] == 'FINISH' and not ctx.get('finalization_stage', True):
            p = {k: p[k] for k in ('action', 'case_id', 'case_revision', 'reason', 'evidence_refs')}
        return PlanResult(json.dumps(p), 0, {'mock': True})


@pytest.mark.parametrize('mode,repairs,accepted', [('normal', 0, True), ('repair', 1, True),
                                                   ('bad', 1, False), ('unavailable', 0, False)])
def test_bounded_repair_and_failure_fallback(raw_case, mode, repairs, accepted):
    path, reg, orch, policy = with_detector(raw_case)
    report = wv.run(path, CFG, reg, orch, policy, planner=Mock(mode), tool_enabled=False)
    assert report['repair_attempts'] == repairs
    assert (report['final'] is not None) == accepted
    assert report['tool_attempts'] == 0
    if not accepted:
        assert report['status'] == 'INVESTIGATION_INCOMPLETE'
        assert report['effective_recommendation']['action'] == 'MANUAL_REVIEW'
        assert report['effective_recommendation']['requires_human_decision']
    if mode == 'repair':
        assert report['turns'][0]['raw'] == '{' and report['turns'][0]['validation_error']


def test_real_d1_d9_then_evidence_native_final_mock_llm(raw_case):
    path, reg, orch, policy = with_detector(raw_case)
    report = wv.run(path, CFG, reg, orch, policy, planner=Mock('tool'), events=raw_case[4])
    assert report['final'] is not None, report.get('failure')
    assert report['tool_attempts'] == 1
    assert report['final_revision'] > report['initial_revision']
    assert sum(e['stage'] == 'D9_COMMITTED' for e in report['events'][report['agent_event_start']:]) == 1
    rr = report['trusted_metadata']['resolved_import_refs']
    assert rr and rr[0]['phase'] == 'COMMITTED_DURING_RUN'
    assert report['execution_status'] == 'NOT_EXECUTED_CONTAINMENT'
