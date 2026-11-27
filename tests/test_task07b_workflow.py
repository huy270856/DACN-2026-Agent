"""TASK 07B S4: contract v4.0, verifier, D2 recommendation mapping, planner payload, and MOCK_LLM
end-to-end through the REAL D1-D9 path. MOCK_LLM is not evidence of autonomous behaviour."""
import copy
import io
import json
import urllib.request
from pathlib import Path

import pytest

import case_manager as cm
from agent.config import AgentConfig
from agent.planner import OllamaPlanner, PlannerError, PlanResult
from dacn import application as app, investigation as inv
from investigation_v3 import audit
from investigation_v4 import contract as C, projector as P, recommendation as R, verifier as V, workflow as W
from investigation_v4.config import V4Config
from tests.test_task07b_query_projector import _payload, _state

WHOAMI = Path("C:/Windows/System32/whoami.exe")
CFG = AgentConfig(max_iterations=8, max_tool_calls=1, max_context_chars=24000, num_predict=3072,
                  inference_timeout_s=90, wall_clock_s=300, max_tokens=160000)


# ----------------------------------------------------------------------------- contract
def test_analysis_first_in_every_branch_and_final():
    s = C.action_schema(["RUN_ANALYZER", "LIST_IMPORT_INDEX", "QUERY_IMPORTS", "READ_TABLE", "ANSWER"],
                        tool_ids=["static.pe_imports_table"])
    for br in s["oneOf"]:
        assert list(br["properties"])[0] == "analysis" and br["required"][0] == "analysis"
    f = C.final_schema()
    assert list(f["properties"])[0] == "analysis" and f["required"][0] == "analysis"
    for forbidden in ("recommendation", "alignment", "supporting_evidence_ids"):
        assert forbidden not in json.dumps(f)


def test_no_request_more_and_unknown_actions_rejected():
    assert "REQUEST_MORE_EVIDENCE" not in C.ACTIONS
    with pytest.raises(ValueError):
        C.action_schema(["REQUEST_MORE_EVIDENCE"])
    with pytest.raises(ValueError):
        C.action_schema(["RUN_ANALYZER"])  # no offered tool


def test_parse_valid_and_invalid():
    s = C.action_schema(["QUERY_IMPORTS", "ANSWER"])
    ok = json.dumps({"analysis": "a", "action": "QUERY_IMPORTS", "by": "DLL", "value": "KERNEL32.dll", "page": 0})
    assert C.parse(ok, s)["action"] == "QUERY_IMPORTS" and C.analysis_first(ok)
    assert not C.analysis_first(json.dumps({"action": "ANSWER", "analysis": "a"}))
    for bad in ('{"analysis":"a","action":"RUN_ANALYZER","tool_id":"x"}', "{bad", '{"action":"ANSWER"}'):
        with pytest.raises(ValueError):
            C.parse(bad, s)
    f = C.final_schema()
    good = _final(["I21"])
    C.parse(json.dumps(good), f)
    for mutate in (lambda o: o["findings"][0].update(sources=["EV-pred"]),
                   lambda o: o.update(findings=o["findings"] * 7),
                   lambda o: o.update(answer="x" * 901),
                   lambda o: o.update(recommendation="MONITOR")):
        o = copy.deepcopy(good)
        mutate(o)
        with pytest.raises(ValueError):
            C.parse(json.dumps(o), f)


def _final(sources, *, relation="NOT_INFORMATIVE", basis=(), kind="OBSERVED", text="Declares WS2_32 ordinal 115."):
    return {"analysis": "a", "answer_status": "PARTIALLY_ANSWERED", "answer": "Declared network imports seen.",
            "findings": [{"kind": kind, "text": text, "sources": list(sources)}],
            "evidence_needed": ["runtime trace"], "next_verification": ["dynamic analysis"],
            "detector_relation": {"value": relation, "basis_sources": list(basis)}}


# ----------------------------------------------------------------------------- verifier / recommendation
def _verify(obj, shown=("E1", "E2", "E3", "I21"), viewed=(21,), table=True):
    h = P.HandleMap()
    for eid in ("EV-hdr", "EV-fmt", "EV-tab"):
        h.e_handle(eid)
    return V.verify(obj, shown_handles=shown, handles=h, table_value=_payload() if table else None, viewed_indices=viewed)


def test_verifier_resolves_without_rewriting():
    obj = _final(["I21", "E1"])
    before = copy.deepcopy(obj)
    v = _verify(obj)
    assert obj == before and not v["has_flags"]
    lits = {r["handle"]: r for r in v["resolved_sources"]}
    assert lits["I21"]["literal"] == "WS2_32.dll!#115" and lits["I21"]["resolved_symbol"] == "WSAStartup"
    assert lits["E1"]["evidence_id"] == "EV-hdr"


@pytest.mark.parametrize("obj, flag", [
    (_final(["I22"]), "finding_flags_present"),                                     # not shown
    (_final([], kind="OBSERVED"), "finding_flags_present"),                         # OBSERVED without source
    (_final(["I21"], relation="AGREES"), "detector_relation_without_basis"),
    (_final(["I21"], text="The file does not import any file APIs."), "absence_beyond_coverage_suspected"),
    (_final(["I21"], text="Entropy is 7.9."), "numeric_or_entropy_claim_suspected_unverified"),
    (_final(["I21"], text="There is a 99% probability it is benign."), "numeric_or_entropy_claim_suspected_unverified"),
])
def test_verifier_flags(obj, flag):
    assert flag in _verify(obj)["flags"]


def test_absence_scoped_limitation_not_flagged_and_full_view_ok():
    lim = _final(["I21"], text="Static imports cannot prove the absence of dynamically resolved APIs.")
    assert "absence_beyond_coverage_suspected" not in _verify(lim)["flags"]
    absent = _final(["I21"], text="The file does not import CreateProcess.")
    assert "absence_beyond_coverage_suspected" in _verify(absent)["flags"]
    full = set(range(28))
    assert "absence_beyond_coverage_suspected" not in _verify(absent, viewed=full, shown=("I21",))["flags"]
    assert "absence_claim_without_imports_source_suspected" in _verify(absent, table=False, shown=())["flags"]


DET = {"predicted_label": "benign", "raw_score": 0.002, "threshold": 0.83}


@pytest.mark.parametrize("label, relation, flags, expected", [
    ("benign", "AGREES", [], "MONITOR"),
    ("benign", "NOT_INFORMATIVE", [], "MANUAL_REVIEW"),
    ("benign", "CONFLICTS", [], "MANUAL_REVIEW"),
    ("malicious", "AGREES", [], "CONSIDER_QUARANTINE"),
    ("malicious", "NOT_INFORMATIVE", [], "MANUAL_REVIEW"),
    ("benign", "AGREES", ["x"], "MANUAL_REVIEW"),
])
def test_recommendation_d2_mapping(label, relation, flags, expected):
    final = {"detector_relation": {"value": relation, "basis_sources": ["I1"]}}
    rec = R.derive(final, {"has_flags": bool(flags), "flags": flags}, dict(DET, predicted_label=label))
    assert rec["action"] == expected and rec["execution_status"] == "NOT_EXECUTED"
    assert rec["derivation"][0].startswith(f"detector_relation={relation}")


def test_recommendation_no_final_and_near_threshold():
    assert R.derive(None, None, DET)["action"] == "MANUAL_REVIEW"
    near = R.derive({"detector_relation": {"value": "AGREES", "basis_sources": ["I1"]}}, {"has_flags": False, "flags": []},
                    dict(DET, raw_score=0.80))
    assert near["action"] == "MANUAL_REVIEW"


def test_viewed_compact_fields_distinguish_ordinal_symbol_and_resolved():
    v = _payload()
    from investigation_v4 import query as Q
    f = P.build(_state(), question="q", handles=P.HandleMap(), viewed={i: Q.entry_view(v, i) for i in (20, 21, 23, 26)},
                index_listed=False, queries_run=[], queries_left=6, turns_left=8, available_actions=["ANSWER"],
                retrieval_mode="QUERY", max_context_chars=16000)["facts"]["viewed_imports"]
    by = {x["handle"]: x for x in f}
    assert by["I20"] == {"handle": "I20", "dll": "KERNEL32.dll", "symbol": "CreateFileW"}
    assert by["I21"] == {"handle": "I21", "dll": "WS2_32.dll", "ordinal": 115, "resolved_symbol": "WSAStartup"}
    assert by["I23"] == {"handle": "I23", "dll": "WS2_32.dll", "ordinal": 60000}  # unresolved ordinal
    assert by["I26"]["delay"] is True and "symbol" in by["I26"]
    assert "symbol" not in by["I21"] and "ordinal" not in by["I20"]
    assert 'if "symbol" is absent the import is by "ordinal"' in C.SYSTEM and "never means unknown" in C.SYSTEM


# ----------------------------------------------------------------------------- planner payload (fake HTTP)
def test_planner_error_carries_payload_message_unchanged(monkeypatch):
    def fake(self, req, **kw):
        return io.BytesIO(json.dumps({"message": {"content": "", "thinking": "t" * 9}, "done_reason": "length",
                                      "eval_count": 5, "prompt_eval_count": 7}).encode())
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake)
    with pytest.raises(PlannerError) as e:
        OllamaPlanner(AgentConfig(think=True)).decide({"system": "s", "user": "u"})
    assert str(e.value) == "Ollama returned empty content (thinking_chars=9, done_reason=length, eval_count=5)"
    assert e.value.payload == {"content": "", "thinking": "t" * 9, "done_reason": "length", "eval_count": 5,
                               "prompt_eval_count": 7}
    assert PlannerError("x").payload is None


# ----------------------------------------------------------------------------- MOCK_LLM E2E
class Mock:
    is_mock = True

    def __init__(self, script=None):
        self.script = script
        self.ctxs = []

    def decide(self, ctx):
        self.ctxs.append(copy.deepcopy(ctx))
        f, avail = ctx["facts"], ctx["facts"]["available_actions"]
        if ctx["finalization_stage"]:
            src = [x["handle"] for x in f["viewed_imports"][:2]] or [f["evidence"][0]["handle"]]
            obj = _final(src, relation="AGREES", basis=src[:1], text="Declared imports are listed.")
        elif self.script:
            obj = self.script.pop(0)(f, avail)
        elif "RUN_ANALYZER" in avail:
            obj = {"analysis": "need imports", "action": "RUN_ANALYZER", "tool_id": "static.pe_imports_table"}
        elif "LIST_IMPORT_INDEX" in avail:
            obj = {"analysis": "list", "action": "LIST_IMPORT_INDEX"}
        elif "QUERY_IMPORTS" in avail and not f["viewed_imports"]:
            obj = {"analysis": "q", "action": "QUERY_IMPORTS", "by": "DLL", "value": f["import_index"][0]["dll"], "page": 0}
        else:
            obj = {"analysis": "done", "action": "ANSWER"}
        return PlanResult(json.dumps(obj), 0.0, {"mock": True})


@pytest.fixture
def case(tmp_path):
    if not WHOAMI.exists():
        pytest.skip("Windows benign PE required")
    from dacn.config import AppConfig
    cfg = AppConfig.from_home(tmp_path / "home")
    intake = app.intake_file(str(WHOAMI), cfg)
    path = cm.case_path(cfg.cases_dir, intake["case_id"])
    from dacn.investigation import run_static_prediction
    reg, orch = inv.build_detector_backend(cfg, include_imports_table=True)
    run_static_prediction(cfg, orch, path, cm.read_json(path))
    events = []
    policy = audit.attach(orch, events)
    return path, reg, orch, policy, events


def _run(case, planner, v4=V4Config(), **kw):
    path, reg, orch, policy, events = case
    return W.run(path, CFG, v4, reg, orch, policy, question="Which declared imports indicate process control?",
                 planner=planner, events=events, **kw)


def test_e2e_run_list_query_answer_final(case):
    m = Mock()
    r = _run(case, m)
    acts = [t.get("action") for t in r["turns"]]
    assert acts[:4] == ["RUN_ANALYZER", "LIST_IMPORT_INDEX", "QUERY_IMPORTS", "ANSWER"]
    assert r["status"] in ("FINISHED", "FINISHED_FLAGGED") and r["final"] is not None
    assert r["final_revision"] > r["initial_revision"] and r["tool_attempts"] == 1
    stages = [e["stage"] for e in r["events"][r["agent_event_start"]:]]
    assert stages[:5] == ["D1_TOOL_CALL", "D4", "D5_D6_RECEIPT", "D7_VALIDATED", "D9_COMMITTED"]
    assert "COMMITTED_EVIDENCE_QUERY" in stages
    ev = next(e for e in r["final_state"]["evidence"] if e["facet"] == "static.pe_imports_table")
    assert ev["trust_level"] == "UNTRUSTED_CONTENT"
    q = next(t for t in r["turns"] if t.get("action") == "QUERY_IMPORTS")["query_result"]
    assert q["case_revision"] == r["final_revision"] and q["trust_level"] == "UNTRUSTED_CONTENT"
    assert all(t["analysis_first"] for t in r["turns"])
    assert r["trusted_metadata"]["resolved_sources"] and r["planner_kind"] == "MOCK_LLM"
    assert r["effective_recommendation"]["execution_status"] == "NOT_EXECUTED"
    # detector context is never citable and never an evidence handle
    for c in m.ctxs:
        assert all(e["kind"] != "static.pe_malware_prediction" for e in c["facts"]["evidence"])
        assert "EVALUATOR_ONLY" not in c["user"]


def test_tool_offered_every_turn_until_run_and_last_turn_final_only(case):
    script = [lambda f, a: {"analysis": "wait", "action": "ANSWER"}]
    r = _run(case, Mock(script))  # answers without the tool
    assert r["turns"][0]["context"]["facts"]["available_actions"] == ["RUN_ANALYZER", "ANSWER"]
    assert r["final"] is not None and r["tool_attempts"] == 0
    # A planner that never answers is forced into the final on the last turn.
    never = [lambda f, a: ({"analysis": "x", "action": "RUN_ANALYZER", "tool_id": "static.pe_imports_table"}
                           if "RUN_ANALYZER" in a else {"analysis": "x", "action": "QUERY_IMPORTS", "by": "SYMBOL_PREFIX",
                                                        "value": "Get", "page": 0})] * 7
    r2 = _run(case, Mock(list(never)), V4Config(max_turns=4))
    assert [t["stage"] for t in r2["turns"]][-1] == "FORCED_FINAL" and r2["forced_final"] is True
    assert "RUN_ANALYZER" not in r2["turns"][1]["context"]["facts"]["available_actions"]
    assert r2["turns"][-1]["requested_decoding_schema"] == C.final_schema()


def test_duplicate_query_no_gain_and_query_budget(case):
    q = lambda f, a: {"analysis": "q", "action": "QUERY_IMPORTS", "by": "SYMBOL_PREFIX", "value": "Get", "page": 0}
    script = [lambda f, a: {"analysis": "r", "action": "RUN_ANALYZER", "tool_id": "static.pe_imports_table"}, q, q]
    r = _run(case, Mock(script), V4Config(max_queries=2))
    outcomes = [t["context"]["facts"]["last_result"] for t in r["turns"]]
    assert any(o and o.get("outcome") == "NO_INFORMATION_GAIN" for o in outcomes)
    assert r["query_attempts"] == 2
    after = r["turns"][3]["context"]["facts"]["available_actions"]
    assert "QUERY_IMPORTS" not in after


def test_bad_query_is_recorded_not_fatal(case):
    script = [lambda f, a: {"analysis": "r", "action": "RUN_ANALYZER", "tool_id": "static.pe_imports_table"},
              lambda f, a: {"analysis": "q", "action": "QUERY_IMPORTS", "by": "DLL", "value": "NOPE.dll", "page": 0}]
    r = _run(case, Mock(script))
    assert any(t.get("query_error") == "QUERY_UNKNOWN_DLL" for t in r["turns"]) and r["final"] is not None


def test_noq_mode_read_table_only(case):
    script = [lambda f, a: {"analysis": "r", "action": "RUN_ANALYZER", "tool_id": "static.pe_imports_table"},
              lambda f, a: {"analysis": "read", "action": "READ_TABLE", "offset": 16}]
    r = _run(case, Mock(script), V4Config(retrieval_mode="READ_TABLE"))
    avail = r["turns"][1]["context"]["facts"]["available_actions"]
    assert "READ_TABLE" in avail and "QUERY_IMPORTS" not in avail and "LIST_IMPORT_INDEX" not in avail
    assert r["trusted_metadata"]["viewed_indices"][0] == 16


def test_d4_deny_is_not_retried(case):
    path, reg, orch, policy, events = case
    from orchestrator.policy_engine import PolicyConfig, PolicyEngine
    deny = PolicyEngine(PolicyConfig(tool_allowlist=frozenset(), budget_caps={
        "timeout_ms": 120000, "max_output_bytes": 262144, "max_artifact_bytes": 1048576, "max_concurrency": 1}))
    r = W.run(path, CFG, V4Config(), reg, orch, deny, question="q", planner=Mock(), events=events)
    assert r["tool_attempts"] == 0 and "RUN_ANALYZER" not in r["turns"][0]["context"]["facts"]["available_actions"]
    assert not any(e["facet"] == "static.pe_imports_table" for e in r["final_state"]["evidence"])


def test_planner_error_payload_recorded_and_incomplete(case):
    class Boom:
        is_mock = True

        def decide(self, ctx):
            raise PlannerError("Ollama returned empty content", payload={"thinking": "lost?", "content": ""})
    r = _run(case, Boom())
    assert r["status"] == "INVESTIGATION_INCOMPLETE" and r["turns"][0]["error_payload"]["thinking"] == "lost?"
    assert r["effective_recommendation"]["action"] == "MANUAL_REVIEW"


def test_format_repair_once_then_exhausted(case):
    class Bad:
        is_mock = True

        def __init__(self): self.n = 0

        def decide(self, ctx):
            self.n += 1
            return PlanResult('{"analysis": "x", "action": "NOPE"}', 0.0, {"mock": True})
    r = _run(case, Bad())
    assert r["repair_attempts"] == 1 and r["failure"] == "VALIDATION_REPAIR_EXHAUSTED" and len(r["turns"]) == 2
    assert r["turns"][1]["is_repair"] and r["turns"][1]["context"]["facts"]["repair_feedback"]
