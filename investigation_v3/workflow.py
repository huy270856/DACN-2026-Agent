"""Opt-in multi-step investigation through the existing Controller/D1–D9."""
import copy
from dataclasses import asdict
import json
import time

import case_manager as cm
from agent.controller import Controller, ControllerReject
from agent.planner import OllamaPlanner, PlannerError
from . import context, schema
from .grounding import verify
from .imports_tool import TOOL_ID, FACET, ARGUMENTS


class SchemaPlanner:
    is_mock = False
    def __init__(self, cfg):
        self.transport = OllamaPlanner(cfg)
    def decide(self, ctx):
        return self.transport.decide_with_schema(ctx, schema.for_context(ctx))


class InvestigationController(Controller):
    def __init__(self, registry, orch, cfg, state, policy):
        super().__init__(registry, orch, cfg)
        self.policy = policy
        attempted = {r.get("tool") for r in state.get("tool_runs", [])}
        for spec in registry.list_tools(only_enabled=True):
            facet = FACET if spec["tool_id"] == TOOL_ID else "static.pe_malware_prediction"
            if (any(e.get("facet") == facet for e in state.get("evidence", []))
                    or spec["tool_id"].replace(".", "_") in attempted):
                args = ARGUMENTS if spec["tool_id"] == TOOL_ID else {"feature_version": 2}
                self._seen_toolcalls.add(self._toolcall_key(spec["tool_id"], spec["tool_version"],
                                                          spec["provider"]["id"], args, state["target_ref"]))

    def available_tools(self, state):
        available = []
        for spec in self._registry.list_tools(only_enabled=True):
            # Only the one supplemental analyzer is a follow-up for this version.
            if spec["tool_id"] != TOOL_ID or not self._registry.is_provider_available(spec["provider"]["id"]):
                continue
            identity = (spec["tool_id"], spec["tool_version"], spec["provider"]["id"])
            if identity in self._denied_tools:
                continue
            key = self._toolcall_key(*identity, ARGUMENTS, state["target_ref"])
            if key in self._seen_toolcalls:
                continue
            tool = dict(zip(("tool_id", "tool_version", "provider_id"), identity), arguments=ARGUMENTS)
            call = self._build_toolcall(tool, state)
            if self.policy.evaluate(call, spec, state)["outcome"] == "ALLOW":
                available.append(spec)
        return available


def _read(path):
    return cm.validate_case(cm.read_json(path))


def _controller_action(proposal):
    common = {k: proposal[k] for k in ("action", "case_id", "case_revision", "reason", "evidence_refs")}
    common["unknowns_targeted"] = []
    if proposal["action"] == "TOOL_CALL":
        common["tool"] = copy.deepcopy(proposal["tool"])
    else:
        a = proposal.get("assessment") or {}
        common.update(action="FINISH", finding={"verdict": "INSUFFICIENT_EVIDENCE", "confidence": 0.0,
                      "rationale": a.get("explanation") or proposal["reason"],
                      "limitations": a.get("uncertainty_notes", []),
                      **({"assessment": {k: a[k] for k in ("alignment", "review_required", "recommendation", "explanation")}} if a else {})})
    return common


def _check_visible(proposal, facts, initial_ids):
    visible = {e["evidence_id"] for e in facts["evidence"]}
    refs = list(proposal["evidence_refs"])
    if "assessment" in proposal:
        a = proposal["assessment"]
        refs += a["supporting_evidence_ids"] + a["contradicting_evidence_ids"]
        refs += [i for c in a["claims"] for i in c["evidence_ids"]]
        refs += proposal.get("old_evidence_ids", []) + proposal.get("new_evidence_ids", [])
        refs += [u["evidence_id"] for u in proposal.get("new_fact_uses", [])]
        if set(proposal.get("old_evidence_ids", [])) - initial_ids or set(proposal.get("new_evidence_ids", [])) & initial_ids:
            raise ControllerReject("EVIDENCE_PHASE_MISMATCH", "Old/new evidence groups are incorrect")
        if {u["evidence_id"] for u in proposal.get("new_fact_uses", [])} - set(proposal.get("new_evidence_ids", [])):
            raise ControllerReject("EVIDENCE_PHASE_MISMATCH", "New fact must cite a new evidence ID")
    if set(refs) - visible:
        raise ControllerReject("EVIDENCE_NOT_VISIBLE", "Citation was not present in model evidence projection")


def run(case_path, cfg, registry, orch, policy, *, planner=None, tool_enabled=True, events=None):
    events = events if events is not None else []
    planner = planner or SchemaPlanner(cfg)
    state = _read(case_path)
    initial = copy.deepcopy(state)
    initial_ids = {e["evidence_id"] for e in initial["evidence"]}
    class Dispatch:
        def run_tool_call(self, call, path):
            events.append({"stage": "D1_TOOL_CALL", "call": copy.deepcopy(call)})
            return orch.run_tool_call(call, path)
    controller = InvestigationController(registry, Dispatch(), cfg, state, policy)
    prediction = next(e["value"] for e in reversed(state["evidence"])
                      if e["facet"] == "static.pe_malware_prediction" and e["status"] == "SUCCESS")
    history, turns = [], []
    started, tokens, attempted = time.monotonic(), 0, 0
    result = {"schema_version": "investigation-v3", "planner_kind": "MOCK_LLM" if getattr(planner, "is_mock", False) else "LOCAL_QWEN",
              "case_id": state["case_id"], "initial_revision": state["revision"], "initial_state": initial,
              "model_prediction": prediction, "turns": turns, "events": events, "history": history,
              "agent_event_start": len(events),
              "status": "BUDGET_EXHAUSTED", "final": None}
    for iteration in range(cfg.max_iterations if tool_enabled else 1):
        remaining = cfg.wall_clock_s - (time.monotonic() - started)
        if remaining <= 0 or tokens + 8192 + cfg.num_predict * 2 > cfg.max_tokens:
            break
        available = controller.available_tools(state) if tool_enabled else []
        try:
            ctx = context.build_context(state, available, cfg, initial_ids=initial_ids, history=history)
        except ValueError as exc:
            turns.append({"iteration": iteration + 1, "error": str(exc), "inference_attempted": False})
            result["status"] = "CONTEXT_ERROR"
            break
        ctx["remaining_s"] = min(remaining, cfg.inference_timeout_s)
        # The collector/projector never reads evaluator labels.
        from evaluation.task05c.agent_replay import _assert_no_ground_truth
        _assert_no_ground_truth(ctx["system"] + ctx["user"])
        turn = {"iteration": iteration + 1, "context": copy.deepcopy(ctx),
                "requested_decoding_schema": schema.for_context(ctx)}
        turns.append(turn)
        try:
            response = planner.decide(ctx)
            turn.update(raw=response.raw, meta=response.meta, latency_s=response.latency_s)
            usage = sum(response.meta.get(k) or 0 for k in ("prompt_eval_count", "eval_count"))
            tokens += max(usage, 8192 + cfg.num_predict * 2)
            proposal = schema.parse(response.raw)
            turn["proposal"] = copy.deepcopy(proposal)
            remaining = cfg.wall_clock_s - (time.monotonic() - started)
            if remaining <= 0 or tokens > cfg.max_tokens:
                turn["error"] = "Investigation budget expired after inference; no tool dispatch"
                result["status"] = "BUDGET_EXHAUSTED"
                break
            _check_visible(proposal, ctx["facts"], initial_ids)
            state = _read(case_path)
            normalized = _controller_action(proposal)
            controller.validate(normalized, state)
            turn["controller_validated"] = True
        except (ValueError, PlannerError, ControllerReject) as exc:
            turn["error"] = str(exc)
            result["status"] = "REJECTED_OR_MODEL_ERROR"
            break
        if proposal["action"] == "REQUEST_MORE_EVIDENCE":
            result.update(status="MORE_EVIDENCE_REQUIRED", final=copy.deepcopy(proposal))
            if "assessment" in proposal:
                verification_input = {**proposal, "new_fact_uses": proposal.get("new_fact_uses", [])}
                result["verification"] = verify(verification_input, ctx["facts"], initial_ids, prediction)
            break
        if proposal["action"] == "FINISH":
            checks = verify(proposal, ctx["facts"], initial_ids, prediction)
            result.update(status="FINISHED", final=copy.deepcopy(proposal), verification=checks)
            break
        if (not tool_enabled or proposal["tool"]["tool_id"] != TOOL_ID
                or attempted >= 1 or attempted >= cfg.max_tool_calls):
            turn["error"] = "TOOL_NOT_AVAILABLE_OR_NO_ADDITIONAL_GAIN"
            result["status"] = "REJECTED_TOOL"
            break
        attempted += 1
        before_rev = state["revision"]
        before_ids = {e["evidence_id"] for e in state["evidence"]}
        try:
            record = controller.run_tool(normalized, state, case_path, remaining_s=max(.001, remaining))
            event = {"stage": "ORCHESTRATOR_RETURN", "record": asdict(record)}
            events.append(event)
        except Exception as exc:
            turn["error"] = str(exc)
            result["status"] = "EXECUTION_ERROR"
            break
        state = _read(case_path)
        ids = [e["evidence_id"] for e in state["evidence"] if e["evidence_id"] not in before_ids]
        history.append({"tool_id": proposal["tool"]["tool_id"], "outcome": record.outcome,
                        "reason_code": record.reason_code, "revision_before": before_rev,
                        "revision_after": state["revision"], "new_evidence_ids": ids,
                        "run_id": record.run_id})
        turn["post_execution"] = copy.deepcopy(history[-1])
    result.update(final_revision=state["revision"], final_state=_read(case_path),
                  latency_s=time.monotonic() - started, charged_tokens=tokens,
                  prompt_tokens=sum(t.get("meta", {}).get("prompt_eval_count") or 0 for t in turns),
                  output_tokens=sum(t.get("meta", {}).get("eval_count") or 0 for t in turns),
                  tool_attempts=attempted, execution_status="NOT_EXECUTED_CONTAINMENT")
    result["events"] = copy.deepcopy(events)
    if "verification" in result:
        effective = copy.deepcopy(result["verification"]["effective_recommendation"])
    else:
        effective = {"action": "MANUAL_REVIEW", "priority": "HIGH", "review_required": True,
                     "requires_human_decision": True, "execution_status": "NOT_EXECUTED",
                     "derivation": ["No validated final assessment; do not turn failure/unknown into MONITOR"]}
    if result["status"] != "FINISHED":
        effective.update(action="MANUAL_REVIEW", review_required=True, requires_human_decision=True)
    result["effective_recommendation"] = effective
    return result
