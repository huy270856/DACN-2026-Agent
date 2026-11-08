"""Investigation loop: CaseState -> Qwen -> proposal -> Controller -> D1-D9 -> CaseState.

Closed loop with budgets, duplicate detection, DENY/stale/timeout handling and a
decision log. A model/parse/inference error is recorded as an error, never as a
benign conclusion.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

import case_manager as cm

from .config import AgentConfig
from .context import build_context
from .controller import Budget, Controller, ControllerReject
from .planner import Planner, PlannerError
from .report import build_report
from .schema import ActionError, parse_and_validate

MAX_INVALID_RETRIES = 3   # consecutive parse/validation failures before giving up


def _read_state(case_path: Path) -> Dict[str, Any]:
    return cm.validate_case(cm.read_json(case_path))


def run_investigation(case_path, cfg: AgentConfig, planner: Planner,
                      registry, orchestrator) -> Dict[str, Any]:
    case_path = Path(case_path)
    controller = Controller(registry, orchestrator, cfg)
    budget = Budget(cfg)
    history: List[Dict[str, Any]] = []
    decision_log: List[Dict[str, Any]] = []
    invalid_streak = 0

    state = _read_state(case_path)

    while True:
        stop = budget.exhausted()
        if stop:
            return build_report(state, outcome="BUDGET_EXHAUSTED", stop_reason=stop,
                                history=history, decision_log=decision_log)
        budget.tick_iteration()

        tools = registry.list_tools(only_enabled=True)
        context = build_context(state, tools, cfg, history)

        context["remaining_s"] = max(0.001, cfg.wall_clock_s - (__import__("time").monotonic() - budget.started))
        # Reserve a conservative upper bound including template and reasoning output.
        reserve = 8192 + cfg.num_predict * 2
        if budget.tokens + reserve > cfg.max_tokens:
            return build_report(state, outcome="BUDGET_EXHAUSTED", stop_reason="max_tokens_reservation",
                                history=history, decision_log=decision_log)
        # 1. Ask the model.
        try:
            result = planner.decide(context)
        except PlannerError as exc:
            decision_log.append({"iteration": budget.iterations, "error": f"planner:{exc}"})
            return build_report(state, outcome="ERROR", stop_reason=f"planner_error:{exc}",
                                history=history, decision_log=decision_log)

        counts = [result.meta.get(k) for k in ("prompt_eval_count", "eval_count")]
        actual = sum(counts) if all(type(n) is int and n >= 0 for n in counts) else None
        charged = max(reserve, actual or 0)  # runtime may omit internal thinking tokens
        budget.tokens += charged
        result.meta.update(usage_tokens=actual, charged_tokens=charged, cumulative_charged_tokens=budget.tokens,
                           accounting="conservative_reservation_or_higher_reported_usage")
        decision_log.append({"iteration": budget.iterations, "inference": result.meta, "latency_s": result.latency_s})
        # 2. Parse + shape-validate (model text is data, never executed).
        try:
            proposal = parse_and_validate(result.raw)
        except ActionError as exc:
            invalid_streak += 1
            decision_log.append({"iteration": budget.iterations, "raw": result.raw[:400],
                                 "parse_error": str(exc)})
            history.append({"action": "INVALID", "reason_code": "PARSE_ERROR"})
            if invalid_streak >= MAX_INVALID_RETRIES:
                return build_report(state, outcome="ERROR", stop_reason="repeated_invalid_output",
                                    history=history, decision_log=decision_log)
            continue

        if __import__("time").monotonic() - budget.started >= cfg.wall_clock_s:
            return build_report(state, outcome="BUDGET_EXHAUSTED", stop_reason="wall_clock",
                                history=history, decision_log=decision_log)
        state = _read_state(case_path)
        # 3. Deterministic validation against the live system.
        try:
            proposal = controller.validate(proposal, state)
        except ControllerReject as exc:
            invalid_streak += 1
            decision_log.append({"iteration": budget.iterations, "proposal": _redact(proposal),
                                 "rejected": f"{exc.code}: {exc.message}"})
            if exc.code == "CASE_REVISION_STALE":
                state = _read_state(case_path)      # reload, let the model re-propose
                invalid_streak = 0
            history.append({"action": proposal.get("action"), "reason_code": exc.code})
            if invalid_streak >= MAX_INVALID_RETRIES:
                return build_report(state, outcome="ERROR", stop_reason="repeated_rejection",
                                    history=history, decision_log=decision_log)
            continue

        invalid_streak = 0
        decision_log.append({"iteration": budget.iterations, "proposal": _redact(proposal),
                             "latency_s": result.latency_s, "meta": result.meta})

        # 4. Terminal actions.
        if proposal["action"] == "FINISH":
            return build_report(state, outcome="FINISHED", finding={**proposal["finding"], "evidence_refs": proposal["evidence_refs"]},
                                history=history, decision_log=decision_log)
        if proposal["action"] == "REQUEST_DYNAMIC_ANALYSIS":
            return build_report(state, outcome="DYNAMIC_REQUESTED",
                                stop_reason="agent_requested_human_sandbox_review",
                                finding={"evidence_refs": proposal["evidence_refs"], "rationale": proposal["reason"]},
                                history=history, decision_log=decision_log)

        # 5. TOOL_CALL -> D1-D9.
        budget.tool_calls += 1
        try:
            rec = controller.run_tool(proposal, state, case_path, remaining_s=cfg.wall_clock_s - (__import__("time").monotonic() - budget.started))
        except Exception as exc:
            decision_log.append({"iteration": budget.iterations, "error": type(exc).__name__})
            return build_report(state, outcome="ERROR", stop_reason="orchestrator_error:" + type(exc).__name__,
                                history=history, decision_log=decision_log)
        entry = {"action": "TOOL_CALL", "tool_id": proposal["tool"]["tool_id"],
                 "outcome": rec.outcome, "reason_code": rec.reason_code, "run_id": rec.run_id}
        history.append(entry)
        decision_log.append({"iteration": budget.iterations, "run_record": entry})

        # 6. Re-read Node C (new revision after D9 commit) and continue.
        state = _read_state(case_path)
        # DENY/REJECTED/FAILED are left for the model to reason about next turn;
        # the Controller already prevents re-submitting the identical call.


def _redact(proposal: Mapping[str, Any]) -> Dict[str, Any]:
    out = {k: proposal.get(k) for k in ("action", "case_id", "case_revision", "reason",
                                        "evidence_refs", "unknowns_targeted")}
    if proposal.get("action") == "TOOL_CALL":
        out["tool_id"] = proposal.get("tool", {}).get("tool_id")
    if proposal.get("action") == "FINISH":
        out["verdict"] = proposal.get("finding", {}).get("verdict")
    return out
