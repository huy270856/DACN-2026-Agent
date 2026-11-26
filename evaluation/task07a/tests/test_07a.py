"""TASK 07A harness tests: unit + MOCK_LLM.

MOCK_LLM runs exercise the REAL Node B, LightGBM detector and D1-D9 path on a benign System32
PE already used by 05D/06B tests (not a 07A cohort file). They test MECHANISM only; they are
never evidence of Agent behaviour and never evaluation results.
"""
import copy
import io
import json
import urllib.request
from dataclasses import asdict
from pathlib import Path

import pytest

from agent.config import AgentConfig
from agent.planner import DecodingOptions, PlanResult
from evaluation.task06b.tests.test_v34 import final as v34_final
from evaluation.task06b_j import runner
from evaluation.task07a import ablation, metrics, variants
from investigation_v3 import final_v34, workflow_v34
from investigation_v3.imports_tool import FACET

PE = Path("C:/Windows/System32/whoami.exe")


# ----------------------------------------------------------------------------- variants / config
def test_v0_equals_06bj_runner_cfg():
    cfg, dec = variants.make_cfg("V0", 42)
    assert asdict(cfg) == asdict(runner.CFG)
    assert dec == DecodingOptions()  # byte-identical request defaults


def test_variant_configs_and_seeds():
    v1, d1 = variants.make_cfg("V1", 7)
    assert v1.think and v1.temperature == 0.6 and v1.num_predict == 12288 and v1.wall_clock_s == 900
    assert v1.max_tokens >= 5 * (8192 + 2 * v1.num_predict)  # 5 turns fit the workflow reserve
    assert (d1.num_ctx, d1.top_p, d1.top_k, d1.presence_penalty, d1.seed) == (24576, 0.95, 20, 0.0, 7)
    v2, d2 = variants.make_cfg("V2", 42)
    assert not v2.think and v2.temperature == 0.1 and v2.num_predict == 3072 and d2.num_ctx == 12288
    assert "V1b" not in variants.VARIANTS  # dropped by owner decision (EVALUATION_LOG)
    with pytest.raises(ValueError, match="SEED_NOT_IN_PROTOCOL"):
        variants.make_cfg("V3", 7)


def _fake_http(monkeypatch, content):
    bodies = []

    def fake_open(self, req, **kw):
        bodies.append(json.loads(req.data.decode("utf-8")))
        return io.BytesIO(json.dumps({"message": {"content": content}, "eval_count": 1,
                                      "prompt_eval_count": 2, "done_reason": "stop"}).encode())
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    return bodies


def _ctx(finalizing=False, tools=True, retrieval=True):
    tool = {"tool_id": "t", "tool_version": "1", "provider_id": "p"}
    return {"system": "s", "user": "u", "finalization_stage": finalizing,
            "facts": {"case_id": "CASE-1", "case_revision": 3, "available_tools": [tool] if tools else [],
                      "retrieval_available": retrieval}}


def test_v34planner_default_body_equals_workflow_planner(monkeypatch):
    bodies = _fake_http(monkeypatch, "{}")
    ctx = _ctx()
    workflow_v34.Planner(runner.CFG).decide(ctx)
    variants.V34Planner(*variants.make_cfg("V0", 42)).decide(ctx)
    assert json.dumps(bodies[0]) == json.dumps(bodies[1])
    variants.V34Planner(*variants.make_cfg("V0", 7)).decide(ctx)
    assert bodies[2]["options"]["seed"] == 7 and bodies[2]["options"]["num_ctx"] == 8192


# ----------------------------------------------------------------------------- V2 analysis-first
@pytest.mark.parametrize("ctx", [None, _ctx(), _ctx(finalizing=True), _ctx(tools=False, retrieval=False)])
def test_add_analysis_first_everywhere_rest_identical(ctx):
    base = final_v34.contract(ctx)
    aug = variants.add_analysis(base)
    assert base == final_v34.contract(ctx)  # input not mutated
    for b, a in zip(base["oneOf"], aug["oneOf"]):
        assert list(a["properties"])[0] == "analysis" and a["required"][0] == "analysis"
        assert a["properties"]["analysis"]["maxLength"] == 1500
        rest = copy.deepcopy(a)
        rest["properties"].pop("analysis")
        rest["required"].remove("analysis")
        assert rest == b and list(rest["properties"]) == list(b["properties"])


def test_analysis_first_planner_strips_and_records(monkeypatch):
    raw = json.dumps({"analysis": "think first", "action": "FINISH", "case_id": "CASE-1", "case_revision": 3,
                      "reason": "r", "evidence_refs": []})
    bodies = _fake_http(monkeypatch, raw)
    ctx = _ctx()
    r = variants.AnalysisFirstPlanner(*variants.make_cfg("V2", 42)).decide(ctx)
    assert "analysis" not in json.loads(r.raw)
    assert final_v34.parse(r.raw, ctx)["action"] == "FINISH"
    assert r.meta["analysis"] == "think first" and r.meta["analysis_first"] is True
    assert r.meta["raw_with_analysis"] == raw and r.meta["analysis_parse"] == "OK"
    sent = bodies[0]["format"]
    assert all(list(b["properties"])[0] == "analysis" for b in sent["oneOf"])
    assert bodies[0]["options"]["num_ctx"] == 12288 and bodies[0]["options"]["num_predict"] == 3072


def test_analysis_first_broken_json_returned_verbatim(monkeypatch):
    _fake_http(monkeypatch, "{not json")
    r = variants.AnalysisFirstPlanner(*variants.make_cfg("V2", 42)).decide(_ctx())
    assert r.raw == "{not json" and r.meta["analysis_parse"] == "JSON_ERROR"
    with pytest.raises(ValueError):
        final_v34.parse(r.raw, _ctx())


def test_strip_analysis_order_recorded():
    raw = json.dumps({"action": "FINISH", "analysis": "late"})
    r = variants.strip_analysis(PlanResult(raw, 0, {}))
    assert r.meta["analysis_first"] is False and json.loads(r.raw) == {"action": "FINISH"}


# ----------------------------------------------------------------------------- V3 oracle
def _state(entries, facet=FACET, status="SUCCESS"):
    return {"revision": 5, "evidence": [
        {"evidence_id": "EV-P", "facet": "static.pe_malware_prediction", "status": "SUCCESS", "value": {}},
        {"evidence_id": "EV-I", "facet": facet, "status": status, "value": {"entries": entries}}]}


def _entries(n=64):
    out = [{"library": "msvcrt.dll", "symbol": f"f{i}", "ordinal": None} for i in range(n)]
    out[37] = {"library": "WS2_32.dll", "symbol": None, "ordinal": 115}
    out[40] = {"library": "KERNEL32.dll", "symbol": "TerminateProcess", "ordinal": None}
    return out


def _patched_build(monkeypatch, literals, state):
    seen = []
    monkeypatch.setattr(variants.repair_context, "build", lambda *a, pages, **kw: seen.append(pages) or "ok")
    record = []
    with variants.oracle_pages(literals, record):
        pages = {"EV-I": [(0, 16)]}
        before = copy.deepcopy(pages)
        assert variants.repair_context.build(state, [], None, pages=pages, initial_ids=set()) == "ok"
        assert pages == before  # workflow dict never mutated
    return seen[0], record


def test_oracle_adds_correct_page_without_mutation(monkeypatch):
    pages, record = _patched_build(monkeypatch, ["kernel32.dll!TerminateProcess", "WS2_32.dll!#115"], _state(_entries()))
    assert pages["EV-I"] == [(0, 16), (32, 16)]  # first relevant = index 37
    assert record[0]["oracle_offset"] == 32 and record[0]["page_added"] is True


def test_oracle_no_page_when_first_relevant_on_page0(monkeypatch):
    e = _entries()
    e[3] = {"library": "KERNEL32.dll", "symbol": "WriteFile", "ordinal": None}
    pages, record = _patched_build(monkeypatch, ["KERNEL32.dll!WriteFile", "WS2_32.dll!#115"], _state(e))
    assert pages["EV-I"] == [(0, 16)] and record[0]["page_added"] is False


def test_oracle_ignores_non_imports_and_failed_evidence(monkeypatch):
    for st in (_state(_entries(), facet="pe_header"), _state(_entries(), status="FAILED")):
        pages, record = _patched_build(monkeypatch, ["KERNEL32.dll!TerminateProcess"], st)
        assert pages == {"EV-I": [(0, 16)]} and record == []


def test_oracle_restores_original_build():
    original = variants.repair_context.build
    with variants.oracle_pages([], []):
        assert variants.repair_context.build is not original
    assert variants.repair_context.build is original


def test_load_relevant_literal_eval_and_ordinal():
    ref = repr({"answer": "x", "relevant_entries": ["WS2_32.dll!#115", "KERNEL32.dll!ReadFile"]})
    lits = variants.load_relevant(ref)
    assert lits == ["WS2_32.dll!#115", "KERNEL32.dll!ReadFile"]
    assert variants.parse_literal(lits[0]) == ("ws2_32.dll", "#115")
    assert variants.load_relevant({"relevant_entries": ["a.dll!b"]}) == ["a.dll!b"]
    assert variants.load_relevant({"answer": "UNANSWERABLE"}) == []
    with pytest.raises(ValueError):
        variants.load_relevant("__import__('os')")


# ----------------------------------------------------------------------------- metrics
def _turn(it, entries, action, **kw):
    t = {"iteration": it, "context": {"facts": {"evidence": [
        {"evidence_id": "EV-I", "facet": FACET, "value": {"entries": [dict(e, entry_index=i) for i, e in entries]}}]}},
        "proposal": {"action": action, "reason": kw.pop("reason", "")}, "meta": kw.pop("meta", {})}
    t.update(kw)
    return t


def _trace(entries, turns, final=True, flags=(), resolved=(), retrieval=0, status="FINISHED"):
    return {"alias": "sample_x", "status": status, "failure": None, "turns": turns, "latency_s": 10.0,
            "retrieval_attempts": retrieval,
            "final_state": _state(entries),
            "final": ({"reason": "r", "change_explanation": "c", "stop_reason": "s", "assessment": {
                "explanation": "Only 16 of 64 entries are visible. No file-system APIs are declared.",
                "claims": [{"text": "No file APIs visible in the first 16 entries."}]}} if final else None),
            "verification": {"flags": list(flags)},
            "trusted_metadata": {"resolved_import_refs": list(resolved)}, "isolation_checks": {"passed": True}}


def test_metrics_reachable_case_counts():
    e = _entries()
    page0 = list(enumerate(e[:16]))
    turns = [_turn(1, [], "TOOL_CALL"),
             _turn(2, page0, "FINISH", finalization_selected=True, meta={"prompt_eval_count": 7900, "eval_count": 100}),
             _turn(3, page0, "FINISH")]
    case = {"accessibility_class": metrics.REACHABLE,
            "reference_EVALUATOR_ONLY": {"relevant_entries": ["KERNEL32.dll!TerminateProcess"]}}
    row = metrics.run_row(_trace(e, turns, flags=["prediction_used_as_own_corroboration"]), case, 8192)
    assert row["M1_relevant_seen"] is False and row["M1b_relevant_cited"] is False
    assert row["M3b_stopped_with_gap"] is True and row["M3a_targeted_read"] is False
    assert row["M3c_self_acknowledged_gap"] is True and row["M5_prediction_in_support"] is True
    assert row["M4_unscoped"] is True and row["M4_scoped"] is True
    assert row["overflow_turns"] == [2]
    s = metrics.summarize([row])
    assert s["M1_relevant_seen"] == {"n": 0, "d": 1, "aliases": []}
    assert s["M2_unnecessary_tool"]["d"] == 0 and s["M3b_stopped_with_gap"]["n"] == 1
    assert s["M7_integrity"]["runs_with_overflow_risk"] == 1


def test_metrics_targeted_read_seen_and_cited():
    e = _entries()
    page32 = list(enumerate(e))[32:48]
    pg = {"offset": 32, "entries": [dict(x, entry_index=i) for i, x in page32]}
    turns = [_turn(1, [], "TOOL_CALL"), _turn(2, list(enumerate(e[:16])), "READ_EVIDENCE", retrieved_page=pg),
             _turn(3, list(enumerate(e[:16])) + page32, "FINISH", finalization_selected=True),
             _turn(4, list(enumerate(e[:16])) + page32, "FINISH")]
    resolved = [{"library": "KERNEL32.dll", "symbol": "TerminateProcess", "ordinal": None,
                 "resolved_import": "KERNEL32.dll!TerminateProcess"}]
    case = {"accessibility_class": metrics.REACHABLE,
            "reference_EVALUATOR_ONLY": {"relevant_entries": ["KERNEL32.dll!TerminateProcess"]}}
    row = metrics.run_row(_trace(e, turns, resolved=resolved, retrieval=1), case, 8192)
    assert row["M1_relevant_seen"] and row["M1b_relevant_cited"] and row["M3a_targeted_read"]
    assert row["M3b_stopped_with_gap"] is False and row["read_offsets"] == [32]


def test_metrics_unnecessary_tool_and_full_denominator():
    e = _entries()
    t_tool = [_turn(1, [], "TOOL_CALL"), _turn(2, [], "REQUEST_MORE_EVIDENCE")]
    t_fin = [_turn(1, [], "FINISH", finalization_selected=True), _turn(2, [], "FINISH")]
    rows = [metrics.run_row(_trace(e, t_tool, final=False, status="INVESTIGATION_INCOMPLETE"),
                            {"accessibility_class": metrics.SUFFICIENT, "reference_EVALUATOR_ONLY": {}}, 8192),
            metrics.run_row(_trace(e, t_fin), {"accessibility_class": metrics.NOT_STATIC,
                                               "reference_EVALUATOR_ONLY": {}}, 8192)]
    s = metrics.summarize(rows)
    assert s["M2_unnecessary_tool"]["n"] == 1 and s["M2_unnecessary_tool"]["d"] == 2
    assert s["M5_prediction_in_support"]["d"] == 1 and s["M7_integrity"]["final_present"] == 1
    assert s["M4_absence_unscoped"]["d"] == 0  # no relevant entries -> not in M4 denominator
    assert s["n_runs"] == 2


def test_metrics_limitation_sentence_not_absence():
    assert not (metrics.ABSENCE_RE.search("cannot prove the absence of APIs")
                and not metrics.LIMITATION_RE.search("cannot prove the absence of APIs"))
    assert metrics.ABSENCE_RE.search("The file does not import network APIs.")


# ----------------------------------------------------------------------------- MOCK_LLM end-to-end
class MockPlanner:
    is_mock = True

    def __init__(self):
        self.contexts = []

    def decide(self, ctx):
        self.contexts.append(copy.deepcopy(ctx))
        f = ctx["facts"]
        head = {"action": "FINISH", "case_id": f["case_id"], "case_revision": f["case_revision"],
                "reason": "mock", "evidence_refs": []}
        if f["available_tools"] and not any(h.get("tool_id") for h in f["history"]):
            t = f["available_tools"][0]
            head.update(action="TOOL_CALL", tool={k: t[k] for k in ("tool_id", "tool_version", "provider_id")})
            head["tool"]["arguments"] = {"max_entries": 64}
            return PlanResult(json.dumps(head), 0, {"mock": True})
        if not ctx.get("finalization_stage"):
            return PlanResult(json.dumps(head), 0, {"mock": True})
        return PlanResult(json.dumps(v34_final(ctx)), 0, {"mock": True})


def _manifest(path, cls, relevant):
    path.write_text(json.dumps({"cases": [{
        "alias": "sample_0001", "source": str(PE), "sha256": runner.file_sha(PE), "question_id": "QV2_TEST",
        "question_text": "What does the available static evidence indicate about this file's capability for process control?",
        "accessibility_class": cls, "reference_EVALUATOR_ONLY": {"relevant_entries": relevant},
        "true_label_EVALUATOR_ONLY": "benign"}]}), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def mock_runs(tmp_path_factory):
    if not PE.exists():
        pytest.skip("Windows PE required")
    base = tmp_path_factory.mktemp("t07a")
    common = dict(runtime_root=base / "runtime", ollama_info={"status": "MOCK_TEST_NOT_QUERIED"}, signer_lookup=False)
    # V0 first: learn the real committed import order, then pick an entry on page 1 for the oracle.
    m0 = _manifest(base / "m0.json", metrics.REACHABLE, [])
    out0 = base / "V0_s42"
    ablation.prepare("V0", 42, out0, manifest=m0, **common)
    planners = []
    ablation.run(out0, planner_factory=lambda a: planners.append(MockPlanner()) or planners[-1])
    r0 = runner.read(out0 / "sample_0001_C.json")
    ev = [e for e in r0["final_state"]["evidence"] if e["facet"] == FACET and e["status"] == "SUCCESS"][-1]
    entries = ev["value"]["entries"]
    assert len(entries) > 20
    target = entries[20]
    lit = target["library"] + "!" + (target["symbol"] if target["symbol"] is not None else "#" + str(target["ordinal"]))
    first = variants.relevant_indices(entries, [lit])[0]
    m3 = _manifest(base / "m3.json", metrics.REACHABLE, [lit])
    out3 = base / "V3_s42"
    ablation.prepare("V3", 42, out3, manifest=m3, **common)
    p3 = []
    ablation.run(out3, planner_factory=lambda a: p3.append(MockPlanner()) or p3[-1])
    return {"base": base, "out0": out0, "out3": out3, "lit": lit, "first": first, "p3": p3, "m3": m3}


def test_mock_run_isolation_and_labels(mock_runs):
    r = runner.read(mock_runs["out0"] / "sample_0001_C.json")
    assert r["isolation_checks"]["passed"], r["isolation_checks"]
    assert r["planner_kind"] == "MOCK_LLM" and r["planner_kind_07a"] == "MOCK_LLM"
    assert r["variant"] == "V0" and r["seed"] == 42 and r["runner_version"] == "task07a-ablation-v1"
    assert r["arm"] == "C" and r["evaluation_kind"] == "DEV_DIAGNOSTIC" and r["track"] == "RAW_PE_E2E"
    assert r["status"] in ("FINISHED", "FINISHED_FLAGGED") and r["tool_attempts"] == 1
    assert not (mock_runs["out0"] / "sample_0001_B.json").exists()  # arm C only
    v = runner.read(mock_runs["out0"] / "variant.json")
    assert v["agent_config"] == asdict(runner.CFG) and v["confirmatory"] == "NOT_RUN"
    assert runner.read(mock_runs["out0"] / "freeze.json")["mode"] == "DEV_DIAGNOSTIC"


def test_mock_oracle_page_visible_and_no_evaluator_text_in_prompt(mock_runs):
    r = runner.read(mock_runs["out3"] / "sample_0001_C.json")
    assert r["isolation_checks"]["passed"] and r["oracle_variant"] is True
    page = (mock_runs["first"] // 16) * 16
    post_tool = [t for t in r["turns"] if any(e["facet"] == FACET for e in t["context"]["facts"]["evidence"])]
    assert post_tool
    for t in post_tool:
        imp = next(e for e in t["context"]["facts"]["evidence"] if e["facet"] == FACET)
        idx = {x["entry_index"] for x in imp["value"]["entries"]}
        assert set(range(16)) <= idx and mock_runs["first"] in idx and page in idx
    rec = runner.read(mock_runs["out3"] / "EVALUATOR_ONLY" / "sample_0001_C_oracle.json")
    assert rec["label"] == "ORACLE_DIAGNOSTIC" and rec["per_turn"][0]["oracle_offset"] == page
    for ctx in mock_runs["p3"][0].contexts:
        prompt = ctx["system"] + ctx["user"]
        assert "EVALUATOR_ONLY" not in prompt and "relevant_entries" not in prompt
        assert "true_label" not in prompt and "accessibility_class" not in prompt
    assert "relevant_entries" not in json.dumps(r["turns"])


def test_mock_metrics_on_oracle_run(mock_runs):
    man = metrics.load_manifest(mock_runs["m3"])
    doc = metrics.collect(mock_runs["base"], man)
    assert "V3_s42" in doc["groups"]
    s = doc["groups"]["V3_s42"]["summary"]
    assert s["M1_relevant_seen"] == {"n": 1, "d": 1, "aliases": ["sample_0001"]}
    assert s["M3a_targeted_read"]["n"] == 0  # oracle page is not a model READ


def test_write_once_and_no_rerun(mock_runs):
    out0 = mock_runs["out0"]
    before = (out0 / "sample_0001_C.json").read_bytes()
    ablation.run(out0, planner_factory=lambda a: MockPlanner())
    assert (out0 / "sample_0001_C.json").read_bytes() == before
    with pytest.raises(FileExistsError):
        ablation.prepare("V0", 42, out0, manifest=mock_runs["m3"], runtime_root=mock_runs["base"] / "rt2",
                         ollama_info={"status": "MOCK"}, signer_lookup=False)
    with pytest.raises(PermissionError):
        ablation.run(out0)


def test_variant_drift_detected(mock_runs, monkeypatch):
    out3 = mock_runs["out3"]
    assert ablation.validate_variant(out3)["variant"] == "V3"
    monkeypatch.setattr(ablation, "harness_hashes", lambda: {"x": "changed"})
    with pytest.raises(ValueError, match="HARNESS_DRIFT"):
        ablation.validate_variant(out3)
    monkeypatch.undo()
    p = out3 / "variant.json"
    original = p.read_bytes()
    try:
        v = json.loads(original)
        v["decoding"]["seed"] = 7
        p.write_text(json.dumps(v), encoding="utf-8")
        with pytest.raises(ValueError, match="VARIANT_DRIFT"):
            ablation.run(out3, planner_factory=lambda a: MockPlanner())
    finally:
        p.write_bytes(original)
