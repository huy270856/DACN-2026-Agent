"""06B-R2 v3.4 opt-in loop. Identical trusted engine to v3.3 (Controller/D1-D9,
one analyzer, two committed reads, one format repair, MANUAL_REVIEW fail-safe); the
only treatment change is the evidence-native final contract in final_v34. The v3.3
modules are left frozen and untouched.
"""
import copy
from dataclasses import asdict
import time
from agent.planner import OllamaPlanner, PlannerError
from agent.controller import ControllerReject
from . import repair_context, final_v34, retrieval
from .final_v34 import finalize, validate_refs
from .workflow import InvestigationController, _read, _controller_action
from .imports_tool import TOOL_ID, FACET


class Planner:
    is_mock = False
    def __init__(self, cfg): self.transport = OllamaPlanner(cfg)
    def decide(self, ctx): return self.transport.decide_with_schema(ctx, final_v34.contract(ctx))


def run(case_path, cfg, registry, orch, policy, *, planner=None, tool_enabled=True, events=None):
    started = time.monotonic()
    events = events if events is not None else []
    state = _read(case_path)
    initial = copy.deepcopy(state)
    initial_ids = {e['evidence_id'] for e in state['evidence']}
    prediction = next(e['value'] for e in reversed(state['evidence'])
                      if e['facet'] == 'static.pe_malware_prediction' and e['status'] == 'SUCCESS')

    class Dispatch:
        def run_tool_call(self, call, path):
            events.append({'stage': 'D1_TOOL_CALL', 'call': copy.deepcopy(call)})
            return orch.run_tool_call(call, path)

    ctl = InvestigationController(registry, Dispatch(), cfg, state, policy)
    turns, history, pages = [], [], {}
    result = {'schema_version': final_v34.VERSION, 'case_id': state['case_id'], 'initial_state': initial,
              'initial_revision': state['revision'], 'model_prediction': prediction, 'turns': turns,
              'history': history, 'agent_event_start': len(events), 'status': 'INVESTIGATION_INCOMPLETE',
              'final': None, 'tool_attempts': 0, 'retrieval_attempts': 0, 'repair_attempts': 0,
              'planner_kind': 'MOCK_LLM' if getattr(planner, 'is_mock', False) else 'LOCAL_QWEN'}
    feedback, charged, finalizing = None, 0, False
    try:
        planner = planner or Planner(cfg)
        for iteration in range(cfg.max_iterations if tool_enabled else min(3, cfg.max_iterations)):
            remaining = cfg.wall_clock_s - (time.monotonic() - started)
            reserve = 8192 + 2 * cfg.num_predict
            if remaining <= 0 or charged + reserve > cfg.max_tokens:
                result['failure'] = 'SHARED_BUDGET_EXHAUSTED'; break
            current = _read(case_path)
            if current['revision'] != state['revision'] or current['target_ref'] != state['target_ref']:
                result['failure'] = 'CONCURRENT_CASE_OR_TARGET_CHANGE'; break
            tools = ctl.available_tools(state) if tool_enabled and not feedback and not finalizing and result['tool_attempts'] == 0 else []
            ctx = repair_context.build(state, tools, cfg, initial_ids=initial_ids, history=history,
                    pages=pages, retrieval_available=tool_enabled and not feedback and not finalizing and result['retrieval_attempts'] < 2
                    and any(e['facet'] == FACET and e['status'] == 'SUCCESS' for e in state['evidence']),
                    repair_error=feedback)
            ctx['finalization_stage'] = finalizing
            # Evidence-native contract: replace the v3.3 binding prompt with final_v34's.
            ctx['system'] = final_v34.SYSTEM + (
                '\nFINAL AUTHORSHIP: write the complete FINISH assessment using only this evidence.' if finalizing
                else '\nACTION SELECTION ONLY: choose a listed tool/read for an unresolved question, FINISH to proceed to final authorship, or request more evidence. Do not write the assessment yet.')
            ctx['remaining_s'] = min(remaining, cfg.inference_timeout_s)
            from evaluation.task05c.agent_replay import _assert_no_ground_truth
            _assert_no_ground_truth(ctx['system'] + ctx['user'])
            turn = {'iteration': iteration + 1, 'context': copy.deepcopy(ctx),
                    'requested_decoding_schema': final_v34.contract(ctx), 'is_repair': bool(feedback)}
            turns.append(turn)
            response = planner.decide(ctx)
            turn.update(raw=response.raw, meta=response.meta, latency_s=response.latency_s)
            charged += max(reserve, sum(response.meta.get(k) or 0 for k in ('prompt_eval_count', 'eval_count')))
            if time.monotonic() - started >= cfg.wall_clock_s or charged > cfg.max_tokens:
                result['failure'] = 'SHARED_BUDGET_EXHAUSTED_AFTER_INFERENCE'; break
            try:
                obj = final_v34.parse(response.raw, ctx)
                turn['proposal'] = copy.deepcopy(obj)
                if response.meta.get('done_reason') == 'length':
                    raise ValueError('MODEL_OUTPUT_TRUNCATED')
                validate_refs(obj, ctx['facts'])
                current = _read(case_path)
                if current['revision'] != state['revision'] or current['target_ref'] != state['target_ref']:
                    raise ControllerReject('CASE_REVISION_STALE', 'Case changed during inference')
                if obj['action'] in {'FINISH', 'REQUEST_MORE_EVIDENCE', 'TOOL_CALL'}:
                    ctl.validate(_controller_action(obj), state)
                    turn['controller_validated'] = True
                if obj['action'] == 'FINISH' and finalizing:
                    verified = finalize(obj, ctx['facts'], initial_ids, prediction)
                    result.update(status='FINISHED_FLAGGED' if verified['has_suspected_or_consistency_flags'] else 'FINISHED',
                                  final=copy.deepcopy(obj), **verified)
                    break
            except ValueError as exc:
                turn['validation_error'] = str(exc)
                action = turn.get('proposal', {}).get('action')
                if result['repair_attempts'] == 0 and action not in {'TOOL_CALL', 'READ_EVIDENCE'}:
                    result['repair_attempts'] += 1
                    feedback = str(exc)[:800]
                    continue
                result['failure'] = 'VALIDATION_REPAIR_EXHAUSTED'; break
            feedback = None
            if obj['action'] == 'FINISH' and not finalizing:
                turn['finalization_selected'] = True
                finalizing = True
                continue
            if obj['action'] == 'REQUEST_MORE_EVIDENCE':
                result['failure'] = 'MODEL_REQUESTED_MORE_EVIDENCE'; break
            if obj['action'] == 'READ_EVIDENCE':
                if result['retrieval_attempts'] >= 2:
                    raise ValueError('RETRIEVAL_BUDGET')
                request = obj['retrieval']
                shown = next((e for e in ctx['facts']['evidence'] if e['evidence_id'] == request['evidence_id']), None)
                if shown is None or shown['facet'] != FACET:
                    raise ValueError('RETRIEVAL_SOURCE_NOT_VISIBLE')
                page = retrieval.fetch(state, case_id=obj['case_id'], revision=obj['case_revision'],
                          target_sha256=ctx['facts']['target_sha256'], **request)
                existing = pages.setdefault(request['evidence_id'], [(0, 16)])
                covered = {i for o, l in existing for i in range(o, o+l)}
                if not page['entries'] or all(e['entry_index'] in covered for e in page['entries']):
                    raise ValueError('RETRIEVAL_NO_INFORMATION_GAIN')
                existing.append((request['offset'], request['limit']))
                result['retrieval_attempts'] += 1
                turn['retrieved_page'] = page
                events.append({'stage': 'COMMITTED_EVIDENCE_READ', 'page': copy.deepcopy(page)})
                continue
            if obj['action'] != 'TOOL_CALL' or not tools or result['tool_attempts'] >= min(1, cfg.max_tool_calls):
                raise ValueError('TOOL_UNAVAILABLE_OR_REPEATED')
            if obj['tool']['tool_id'] != TOOL_ID:
                raise ValueError('UNKNOWN_TOOL')
            before = state['revision']; before_ids = {e['evidence_id'] for e in state['evidence']}
            result['tool_attempts'] += 1
            record = ctl.run_tool(_controller_action(obj), state, case_path,
                                  remaining_s=cfg.wall_clock_s - (time.monotonic() - started))
            events.append({'stage': 'ORCHESTRATOR_RETURN', 'record': asdict(record)})
            state = _read(case_path)
            history.append({'tool_id': TOOL_ID, 'outcome': record.outcome, 'reason_code': record.reason_code,
                'revision_before': before, 'revision_after': state['revision'], 'run_id': record.run_id,
                'new_evidence_ids': sorted({e['evidence_id'] for e in state['evidence']} - before_ids)})
            turn['post_execution'] = copy.deepcopy(history[-1])
            if record.outcome == 'DENY':
                result['failure'] = 'POLICY_DENY_NO_RETRY'; break
    except (ValueError, PlannerError, ControllerReject) as exc:
        result['failure'] = str(exc)
        if turns: turns[-1]['error'] = str(exc)
    checks = result.get('verification')
    effective = copy.deepcopy(checks['effective_recommendation']) if checks else {
        'action': 'MANUAL_REVIEW', 'review_required': True, 'requires_human_decision': True,
        'execution_status': 'NOT_EXECUTED', 'derivation': ['INVESTIGATION_INCOMPLETE; no accepted Agent final']}
    if result['status'] != 'FINISHED':
        effective.update(action='MANUAL_REVIEW', review_required=True, requires_human_decision=True)
    result.update(final_state=_read(case_path), final_revision=_read(case_path)['revision'],
                  latency_s=time.monotonic()-started, charged_tokens=charged, events=copy.deepcopy(events),
                  prompt_tokens=sum(t.get('meta', {}).get('prompt_eval_count') or 0 for t in turns),
                  output_tokens=sum(t.get('meta', {}).get('eval_count') or 0 for t in turns),
                  effective_recommendation=effective, execution_status='NOT_EXECUTED_CONTAINMENT')
    return result
