"""TASK 07B investigation v4 (slice 1) loop. Opt-in; not wired into `python -m dacn`.

Trusted engine unchanged: every analyzer call goes Controller.validate -> D4 -> D5/D6 -> D7 ->
D8 -> D9 via `V4Controller`. Queries only read committed CaseState. Differences vs v3.4:
analysis-first decoding every turn; answer-centred final; no terminal REQUEST_MORE; the
analyzer is offered every turn until it ran; the last turn is always reserved for the final.
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import case_manager as cm
from agent.controller import ControllerReject
from agent.planner import DecodingOptions, OllamaPlanner, PlannerError

from . import contract, ledger, projector, query, recommendation, renderer, verifier
from .config import V4Config
from .controller import ToolBinding, V4Controller
from .imports_table_tool import ARGUMENTS as TABLE_ARGS, FACET as TABLE_FACET, TOOL_ID as TABLE_TOOL

DEFAULT_TOOLS = (ToolBinding(TABLE_TOOL, TABLE_FACET, TABLE_ARGS),)
WORKFLOW_VERSION = "investigation-v4.0-workflow-1"
# Fixed, case-independent feedback for typed query errors (facts, not suggestions of content).
QUERY_HINTS = {"QUERY_UNKNOWN_DLL": "value must equal a dll name exactly as listed in import_index (case-insensitive)",
               "QUERY_BAD_PREFIX": "prefix must be 3-64 characters of letters, digits, _ ? @ $",
               "QUERY_PAGE_OUT_OF_RANGE": "page is beyond the last page of this query",
               "READ_BAD_OFFSET": "offset must be a multiple of 16 inside the table"}


class V4Planner:
    """Live planner: schema-constrained local Ollama call with explicit DecodingOptions."""
    is_mock = False

    def __init__(self, cfg, decoding: Optional[DecodingOptions] = None):
        self.transport = OllamaPlanner(cfg, decoding)

    def decide(self, ctx):
        return self.transport.decide_with_schema(ctx, ctx["schema"])


def _read(path):
    return cm.validate_case(cm.read_json(path))


def _table_value(state):
    ok = [e for e in state.get("evidence", []) if e.get("facet") == TABLE_FACET and e.get("status") == "SUCCESS"]
    return ok[-1]["value"] if ok else None


def run(case_path, cfg, v4: V4Config, registry, orch, policy, *, question: str, planner=None,
        decoding: Optional[DecodingOptions] = None, events=None, tools=DEFAULT_TOOLS) -> Dict[str, Any]:
    started = time.monotonic()
    events = events if events is not None else []
    state = _read(case_path)
    initial = copy.deepcopy(state)

    class Dispatch:
        def run_tool_call(self, call, path):
            events.append({"stage": "D1_TOOL_CALL", "call": copy.deepcopy(call)})
            return orch.run_tool_call(call, path)

    ctl = V4Controller(registry, Dispatch(), cfg, state, policy, tools)
    handles = projector.HandleMap()
    viewed: Dict[int, Dict[str, Any]] = {}
    shown: set = set()
    turns: List[Dict[str, Any]] = []
    queries_run: List[Dict[str, Any]] = []
    query_keys: set = set()
    query_log: List[Dict[str, Any]] = []   # trusted record of executed QUERY_IMPORTS (for coverage)
    history: List[Dict[str, Any]] = []
    detector = projector.detector_context(state)
    result: Dict[str, Any] = {
        "schema_version": {"4.1": contract.VERSION_41, "4.2": contract.VERSION_42}.get(v4.contract_version, contract.VERSION), "workflow_version": WORKFLOW_VERSION, "case_id": state["case_id"],
        "initial_state": initial, "initial_revision": state["revision"], "detector_context": detector,
        "question": question, "turns": turns, "history": history, "agent_event_start": len(events),
        "status": "INVESTIGATION_INCOMPLETE", "final": None, "failure": None, "tool_attempts": 0,
        "query_attempts": 0, "repair_attempts": 0, "retrieval_mode": v4.retrieval_mode, "v4_config": asdict(v4),
        "planner_kind": "MOCK_LLM" if getattr(planner, "is_mock", False) else "LOCAL_QWEN"}
    feedback, finalizing, index_listed, last_result, charged = None, False, False, None, 0
    absence_repair_pending = False   # v4.1: one dedicated final-only repair for absence rejections
    result["absence_repair_used"] = False
    reserve = 8192 + 2 * cfg.num_predict
    try:
        planner = planner or V4Planner(cfg, decoding)
        for t in range(v4.max_turns + (1 if v4.contract_version in ("4.1", "4.2") else 0)):
            if t >= v4.max_turns and not absence_repair_pending:
                break  # the extra slot exists only for the dedicated absence repair
            turns_left = max(1, v4.max_turns - t)
            if absence_repair_pending:
                finalizing = True  # final-only: no tool / query is offered on the absence repair turn
            remaining = cfg.wall_clock_s - (time.monotonic() - started)
            if remaining <= 0 or charged + reserve > cfg.max_tokens:
                result["failure"] = "SHARED_BUDGET_EXHAUSTED"
                break
            current = _read(case_path)
            if current["revision"] != state["revision"] or current["target_ref"] != state["target_ref"]:
                result["failure"] = "CONCURRENT_CASE_OR_TARGET_CHANGE"
                break
            forced = turns_left == 1 and not finalizing
            final_stage = finalizing or forced
            table = _table_value(state)
            queries_left = v4.max_queries - result["query_attempts"]
            if final_stage:
                available, offered = [], []
            else:
                offered = ctl.available_tools(state)
                available = (["RUN_ANALYZER"] if offered else [])
                if table is not None:
                    if v4.retrieval_mode == "QUERY":
                        available += (["LIST_IMPORT_INDEX"] if not index_listed else [])
                        available += (["QUERY_IMPORTS"] if queries_left > 0 else [])
                    elif queries_left > 0:
                        available.append("READ_TABLE")
                available.append("ANSWER")
            v41 = v4.contract_version in ("4.1", "4.2")   # ledger-bound absence (4.2 = structured final)
            v42 = v4.contract_version == "4.2"
            led = ledger.build(query_log, index_listed, table)
            extra = ({"coverage_ledger": [{k: e[k] for k in ("id", "kind", "value", "total_matches", "returned", "exhausted")}
                                          for e in led], "coverage_summary": ledger.summary(led)}
                     if (v41 and final_stage) else None)
            schema = contract.final_schema(v4.contract_version) if final_stage else contract.action_schema(
                available, tool_ids=[s["tool_id"] for s in offered])
            proj = projector.build(state, question=question, handles=handles, viewed=viewed,
                                   index_listed=index_listed, queries_run=queries_run, queries_left=queries_left,
                                   turns_left=turns_left, available_actions=available or ["FINAL_ANSWER"],
                                   retrieval_mode=v4.retrieval_mode, max_context_chars=v4.max_context_chars,
                                   last_result=last_result, repair_error=feedback, extra=extra)
            shown |= {e["handle"] for e in proj["facts"]["evidence"]} | {x["handle"] for x in proj["facts"]["viewed_imports"]}
            system = contract.SYSTEM + (contract.SYSTEM_42 if v42 else contract.SYSTEM_41 if v41 else "") + (contract.STAGE_FORCED if forced else contract.STAGE_FINAL if finalizing
                                        else contract.STAGE_ACTION)
            ctx = {"system": system, "user": proj["user"], "facts": proj["facts"], "schema": schema,
                   "finalization_stage": final_stage, "remaining_s": min(remaining, cfg.inference_timeout_s)}
            from evaluation.task05c.agent_replay import _assert_no_ground_truth
            _assert_no_ground_truth(ctx["system"] + ctx["user"])
            turn = {"iteration": t + 1, "stage": "FORCED_FINAL" if forced else "FINAL" if finalizing else "ACTION",
                    "context": {"system": system, "user": proj["user"], "facts": copy.deepcopy(proj["facts"])},
                    "requested_decoding_schema": copy.deepcopy(schema), "is_repair": bool(feedback),
                    "case_revision": state["revision"]}
            turns.append(turn)
            try:
                response = planner.decide(ctx)
            except PlannerError as exc:
                turn["error"] = str(exc)
                turn["error_payload"] = copy.deepcopy(getattr(exc, "payload", None))
                result["failure"] = str(exc)
                break
            turn.update(raw=response.raw, meta=response.meta, latency_s=response.latency_s,
                        analysis_first=contract.analysis_first(response.raw))
            charged += max(reserve, sum(response.meta.get(k) or 0 for k in ("prompt_eval_count", "eval_count")))
            if time.monotonic() - started >= cfg.wall_clock_s or charged > cfg.max_tokens:
                result["failure"] = "SHARED_BUDGET_EXHAUSTED_AFTER_INFERENCE"
                break
            try:
                if response.meta.get("done_reason") == "length":
                    raise ValueError("MODEL_OUTPUT_TRUNCATED")
                obj = contract.parse(response.raw, schema)
                turn["proposal"] = copy.deepcopy(obj)
            except ValueError as exc:
                turn["validation_error"] = str(exc)[:800]
                if result["repair_attempts"] < v4.max_repairs and turns_left > 1:
                    result["repair_attempts"] += 1
                    feedback = str(exc)[:600]
                    if forced:
                        finalizing = True  # a repaired forced final stays a final
                    continue
                result["failure"] = "VALIDATION_REPAIR_EXHAUSTED"
                break
            feedback = None
            if final_stage:
                current = _read(case_path)
                if current["revision"] != state["revision"]:
                    raise ControllerReject("CASE_REVISION_STALE", "Case changed during inference")
                vobj = verifier.v42_view(obj) if v42 else obj
                ctl.validate(ctl.finish_proposal(state, obj["answer"] if not v42 else
                                                 " ".join(f["statement"] for f in obj["findings"])), state)
                checks = verifier.verify(vobj, shown_handles=shown, handles=handles, table_value=_table_value(state),
                                         viewed_indices=viewed.keys(), query_log=query_log)
                if v41:
                    ab = verifier.check_absence_claims(vobj, led, _table_value(state))
                    if v42:  # presence-only statements: any negated statement is rejected (stricter than 4.1)
                        ab["free_text_absence_rejected"] = verifier.statement_absence(obj)
                        ab["has_rejections"] = bool(ab["rejected"] or ab["free_text_absence_rejected"])
                    turn["absence_check"] = copy.deepcopy(ab)
                    if ab["has_rejections"] and not result["absence_repair_used"]:
                        result["absence_repair_used"] = True
                        absence_repair_pending = True
                        feedback = ("ABSENCE_REJECTED: rejected absence_claims "
                                    + json.dumps([{k: r[k] for k in ("api_or_prefix", "scope_ref", "reason")} for r in ab["rejected"]])
                                    + "; free-text absence sentences not allowed: "
                                    + json.dumps(ab["free_text_absence_rejected"][:4]))[:600]
                        finalizing = True
                        continue
                    checks["absence_claims"] = ab
                    if ab["rejected"]:
                        checks["flags"].append("absence_claims_rejected")
                    if ab["free_text_absence_rejected"]:
                        checks["flags"].append("free_text_absence_rejected")
                    checks["has_flags"] = bool(checks["flags"])
                result.update(status="FINISHED_FLAGGED" if checks["has_flags"] else "FINISHED",
                              final=copy.deepcopy(obj), verification=checks, forced_final=forced)
                if v42:
                    ab_ = checks.get("absence_claims") or {}
                    result["rendered_dropped_statements"] = list(ab_.get("free_text_absence_rejected", []))
                    result["rendered_report"] = renderer.render(obj, led, checks.get("absence_claims"),
                                                                checks.get("resolved_sources", []), detector, question)
                break
            action = obj["action"]
            turn["action"] = action
            if action == "ANSWER":
                finalizing = True
                last_result = {"action": "ANSWER", "outcome": "FINAL_ANSWER_NEXT"}
                continue
            if action == "RUN_ANALYZER":
                spec = next(s for s in offered if s["tool_id"] == obj["tool_id"])
                proposal = ctl.tool_proposal(spec, state, obj["analysis"][:600])
                ctl.validate(proposal, state)
                before, before_ids = state["revision"], {e["evidence_id"] for e in state["evidence"]}
                result["tool_attempts"] += 1
                record = ctl.run_tool(proposal, state, case_path,
                                      remaining_s=cfg.wall_clock_s - (time.monotonic() - started))
                events.append({"stage": "ORCHESTRATOR_RETURN", "record": asdict(record)})
                state = _read(case_path)
                history.append({"tool_id": spec["tool_id"], "outcome": record.outcome, "reason_code": record.reason_code,
                                "revision_before": before, "revision_after": state["revision"], "run_id": record.run_id,
                                "new_evidence_ids": sorted({e["evidence_id"] for e in state["evidence"]} - before_ids)})
                turn["post_execution"] = copy.deepcopy(history[-1])
                last_result = {"action": "RUN_ANALYZER", "outcome": record.outcome,
                               "note": "analyzer committed; use LIST_IMPORT_INDEX/QUERY_IMPORTS" if record.outcome == "SUCCESS"
                               else "analyzer did not produce evidence; answer with what is shown"}
                continue
            try:
                if action == "LIST_IMPORT_INDEX":
                    r = query.list_import_index(state)
                    index_listed = True
                    last_result = {"action": action, "outcome": "OK", "dll_count": len(r["dlls"])}
                elif action in ("QUERY_IMPORTS", "READ_TABLE"):
                    result["query_attempts"] += 1
                    key = (obj["by"], obj["value"].lower(), obj["page"]) if action == "QUERY_IMPORTS" else ("READ", obj["offset"])
                    if key in query_keys:
                        r = None
                        last_result = {"action": action, "outcome": "NO_INFORMATION_GAIN",
                                       "note": "identical to an earlier request; budget used"}
                    else:
                        query_keys.add(key)
                        b = query.binding(state, query.table_evidence(state))
                        r = (query.query_imports(state, obj["by"], obj["value"], obj["page"], expected_binding=b)
                             if action == "QUERY_IMPORTS" else query.read_table(state, obj["offset"], expected_binding=b))
                        new = [e["index"] for e in r["entries"] if e["index"] not in viewed]
                        for e in r["entries"]:
                            viewed.setdefault(e["index"], e)
                        rec = ({"by": obj["by"], "value": obj["value"], "page": obj["page"], "total_matches": r["total_matches"]}
                               if action == "QUERY_IMPORTS" else {"offset": obj["offset"]})
                        queries_run.append(rec)
                        if action == "QUERY_IMPORTS":
                            query_log.append(dict(rec, indices=[e["index"] for e in r["entries"]]))
                        last_result = {"action": action, "outcome": "OK", **rec, "returned": len(r["entries"]),
                                       "new_entries": len(new),
                                       "next_page" if action == "QUERY_IMPORTS" else "next_offset":
                                           r.get("next_page") if action == "QUERY_IMPORTS" else r.get("next_offset")}
                    turn["query_result"] = copy.deepcopy(r)
                    if r is not None:
                        events.append({"stage": "COMMITTED_EVIDENCE_QUERY", "result": copy.deepcopy(r)})
            except query.QueryError as exc:
                turn["query_error"] = exc.code
                last_result = {"action": action, "outcome": "ERROR", "error": exc.code,
                               "hint": QUERY_HINTS.get(exc.code, "request not executed; budget used")}
    except (ValueError, ControllerReject) as exc:
        result["failure"] = str(exc)
        if turns:
            turns[-1]["error"] = str(exc)
    final_state = _read(case_path)
    rec = recommendation.derive(result["final"], result.get("verification"), detector)
    if result["status"] != "FINISHED":
        rec.update(action="MANUAL_REVIEW", review_required=True)
    table_value = _table_value(final_state)
    result.update(
        trusted_metadata={"case_id": state["case_id"], "case_revision": final_state["revision"],
                          "target_sha256": final_state["target_ref"]["verified_digest"]["value"],
                          "handle_map": handles.to_trace(), "shown_handles": sorted(shown),
                          "viewed_indices": sorted(viewed),
                          "viewed_literals": {str(i): query.literal(v) for i, v in sorted(viewed.items())},
                          "resolved_sources": (result.get("verification") or {}).get("resolved_sources", []),
                          "table_evidence_present": table_value is not None,
                          "coverage_ledger": ledger.build(query_log, index_listed, table_value),
                          "semantic_grounding": "PENDING_INDEPENDENT_REVIEW"},
        final_state=final_state, final_revision=final_state["revision"], latency_s=time.monotonic() - started,
        charged_tokens=charged, events=copy.deepcopy(events),
        prompt_tokens=sum((t.get("meta") or {}).get("prompt_eval_count") or 0 for t in turns),
        output_tokens=sum((t.get("meta") or {}).get("eval_count") or 0 for t in turns),
        effective_recommendation=rec, execution_status="NOT_EXECUTED_CONTAINMENT")
    return result
