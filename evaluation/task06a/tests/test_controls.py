"""Regression controls; synthetic tests are never DEV evidence of generalization."""
import copy
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from agent.config import AgentConfig
from agent.controller import Controller, ControllerReject
from agent.planner import MockPlanner, OllamaPlanner, PlannerError
from evaluation.task06a.assessor_v2 import assess_once_v2, build_context_v2
from evaluation.task06a.consistency import check_consistency
from evaluation.task06a.verification import screen, visible_projection
from .test_task06a import _state_for_pipeline, _valid_v2

ROOT = Path(__file__).resolve().parents[3]


def check(assessment, state=None, cfg=None):
    state = state or _state_for_pipeline()
    facts = build_context_v2(state, cfg or AgentConfig())["facts"]
    prediction = next(e["value"] for e in state["evidence"] if e["facet"] == "static.pe_malware_prediction")
    return screen(assessment, facts, prediction)


def test_visible_citation_does_not_prove_claim():
    state = _state_for_pipeline()
    imp = next(e["evidence_id"] for e in state["evidence"] if e["facet"] == "static.imports_summary")
    a = _valid_v2()["assessment"]
    a["claims"] = [{"kind": "OBSERVED", "text": "Imports VirtualAlloc", "evidence_ids": [imp]}]
    r = check(a, state)
    assert not r["invalid_ids"]
    assert r["claim_flags"]


def test_import_observation_supported_only_by_matching_source():
    state = _state_for_pipeline()
    by_facet = {e["facet"]: e["evidence_id"] for e in state["evidence"]}
    a = _valid_v2()["assessment"]
    a["claims"] = [{"kind": "OBSERVED", "text": "Imports ReadFile", "evidence_ids": [by_facet["static.imports_summary"]]}]
    assert not check(a, state)["claim_flags"]
    a["claims"][0]["evidence_ids"] = [by_facet["static.sections"]]
    assert check(a, state)["claim_flags"]


def test_entropy_observation_contradicted_by_zero_count():
    state = _state_for_pipeline()
    ev = next(e for e in state["evidence"] if e["facet"] == "static.sections")
    a = _valid_v2()["assessment"]
    a["claims"] = [{"kind": "OBSERVED", "text": "High entropy sections", "evidence_ids": [ev["evidence_id"]]}]
    assert check(a, state)["claim_flags"]


def test_truncated_evidence_is_not_negative_observation():
    state = _state_for_pipeline()
    ctx = build_context_v2(state, AgentConfig(max_value_chars=20))
    projection, incomplete = visible_projection(ctx["facts"])
    assert incomplete
    from evaluation.task06a.grounding import build_evidence_index
    assert build_evidence_index(projection)["high_entropy_count"] is None


def test_dropped_id_rejected_against_visible_projection():
    state = _state_for_pipeline()
    facts = build_context_v2(state, AgentConfig())["facts"]
    gone = facts["evidence"].pop()["evidence_id"]
    a = _valid_v2()["assessment"]
    a["supporting_evidence_ids"] = [gone]
    r = screen(a, facts, {"predicted_label": "benign", "raw_score": .1, "threshold": .83})
    assert gone in r["invalid_ids"]
    assert r["effective_recommendation"]["action"] == "MANUAL_REVIEW"


def test_failed_extractor_cannot_support_observed_claim():
    state = _state_for_pipeline()
    ev = next(e for e in state["evidence"] if e["facet"] == "static.imports_summary")
    ev["status"] = "FAILED"
    a = _valid_v2()["assessment"]
    a["claims"] = [{"kind": "OBSERVED", "text": "Imports ReadFile", "evidence_ids": [ev["evidence_id"]]}]
    assert any("source_incomplete" in str(f) for f in check(a, state)["claim_flags"])


def test_detector_cannot_corroborate_itself():
    state = _state_for_pipeline()
    pred_id = state["evidence"][-1]["evidence_id"]
    a = _valid_v2()["assessment"]
    a.update(alignment="CONSISTENT", supporting_evidence_ids=[pred_id], recommendation="MONITOR")
    assert "prediction_used_as_own_corroboration" in check(a, state)["flags"]


@pytest.mark.parametrize("score,label", [(float("nan"), "benign"), (.9, "benign"), (None, "benign")])
def test_bad_prediction_requires_review(score, label):
    r = check_consistency(_valid_v2()["assessment"], static_label=label, raw_score=score, threshold=.83)
    assert r["flags"]
    assert r["safe_recommendation"]["action"] == "MANUAL_REVIEW"


def test_unknown_recommendation_on_benign_never_monitor():
    a = _valid_v2()["assessment"]
    a["recommendation"] = "UNKNOWN"
    assert check(a)["effective_recommendation"]["action"] == "MANUAL_REVIEW"


def test_false_probability_claim_flagged():
    a = _valid_v2()["assessment"]
    a["explanation"] = "99% probability of maliciousness"
    assert "false_confidence_or_probability_claim_suspected" in check(a)["flags"]


def test_assessor_rejects_stale_identity_and_preserves_raw():
    state = _state_for_pipeline()
    a = _valid_v2()
    a["case_revision"] = 999
    # MockPlanner corrects the revision itself; use explicit raw to test stale binding.
    from .test_task06a import _MockV2
    r = assess_once_v2(state, AgentConfig(), _MockV2(json.dumps(a)), max_attempts=1)
    assert r["status"] == "AGENT_INVALID_OUTPUT"
    assert r["attempts"][0]["raw"] == json.dumps(a)


def test_real_transport_timeout_explicit(monkeypatch):
    def timeout(*args, **kwargs):
        raise TimeoutError("test only")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", timeout)
    cfg = AgentConfig()
    r = assess_once_v2(_state_for_pipeline(), cfg, OllamaPlanner(cfg), max_attempts=1)
    assert r["status"] == "AGENT_ERROR"
    assert "TimeoutError" in r["error"]


def test_exact_same_facts_in_both_arms():
    from agent.context import build_context
    cfg, state = AgentConfig(), _state_for_pipeline()
    assert build_context(state, [], cfg, [])["facts"] == build_context_v2(state, cfg)["facts"]


def test_frozen_baseline_unchanged():
    # 06A-R explicitly refactors only planner transport; its default wire contract
    # is compared against the frozen source in test_reviewer_repair.py.
    subprocess.run(
        ["git", "diff", "--exit-code", "edd0a25", "--", "agent", "evaluation/task05c", "evaluation/task05d",
         ":(exclude)agent/planner.py"], cwd=ROOT, check=True, capture_output=True)


def test_saved_v1_monitor_on_malicious_regression():
    # Historical failure is regression material, never a DEV success example.
    found = []
    for p in (ROOT / "evaluation/task05c/results/samples").glob("*.json"):
        row = json.loads(p.read_text(encoding="utf-8"))
        a = row["agent"]["report"].get("assessment") or {}
        if row["predicted_label"] == "malicious" and a.get("agent_recommendation") == "MONITOR":
            found.append(row)
            r = check_consistency(a, static_label="malicious", raw_score=row["score"], threshold=.8321860386013389)
            assert "under_cautious_monitor_on_malicious" in r["flags"]
            assert r["safe_recommendation"]["action"] == "MANUAL_REVIEW"
    assert found, "Expected historical regression data to exist"


def test_unavailable_provider_rejected_without_dispatch():
    state = _state_for_pipeline()
    class Registry:
        def get_tool(self, *args, **kwargs):
            raise KeyError("provider unavailable")
    ctl = Controller(Registry(), None, AgentConfig())
    p = {"action": "TOOL_CALL", "reason": "need evidence", "case_id": state["case_id"],
         "case_revision": 1, "evidence_refs": [], "unknowns_targeted": [],
         "tool": {"tool_id": "missing", "tool_version": "1", "provider_id": "offline", "arguments": {}}}
    with pytest.raises(ControllerReject) as exc:
        ctl.validate(p, state)
    assert exc.value.code == "TOOL_UNKNOWN"


def test_deny_cannot_retry_with_altered_arguments():
    state = _state_for_pipeline()
    spec = {"limits": {"timeout_ms": 100, "max_output_bytes": 100}}
    class Registry:
        def get_tool(self, *args, **kwargs):
            return spec
    class DenyingOrchestrator:
        calls = 0
        def run_tool_call(self, *args):
            self.calls += 1
            return SimpleNamespace(outcome="DENY")
    orch = DenyingOrchestrator()
    ctl = Controller(Registry(), orch, AgentConfig())
    p = {"action": "TOOL_CALL", "reason": "need evidence", "case_id": state["case_id"],
         "case_revision": 1, "evidence_refs": [], "unknowns_targeted": [],
         "tool": {"tool_id": "static.test", "tool_version": "1", "provider_id": "local", "arguments": {}}}
    ctl.run_tool(p, state, None)  # test double: ONLY checks post-D4-denial retry protection
    altered = copy.deepcopy(p)
    altered["tool"]["arguments"] = {"bypass": True}
    with pytest.raises(ControllerReject) as exc:
        ctl.validate(altered, state)
    assert exc.value.code == "TOOL_PREVIOUSLY_DENIED"
    assert orch.calls == 1


def test_saved_alleged_import_hallucinations_have_sources():
    """The inherited judge allegations must not become our new ground truth."""
    artifact = ROOT / "evaluation/task06a/results/legacy_reaudit.json"
    if not artifact.exists():
        pytest.skip("legacy re-audit not generated")
    rows = json.loads(artifact.read_text(encoding="utf-8"))["findings"]
    names = [presence for row in rows for presence in row["name_presence"].values()]
    assert names
    assert all(p["original_import_record"] and p["evidence_sheet"] for p in names)
    # Missing cited prediction in annotation sheet was not a fabricated CaseState ID.
    assert all(not row["state_missing_cited_ids"] for row in rows)


def test_saved_live_pairs_same_evidence_and_no_ground_truth():
    out = ROOT / "evaluation/task06a/results/dev_v2_1"
    if not (out / "summary.json").exists():
        pytest.skip("live paired experiment not generated")
    from evaluation.task05c.agent_replay import _assert_no_ground_truth
    from evaluation.task06a.experiment import digest
    frozen = json.loads((out / "freeze.json").read_text(encoding="utf-8"))
    assert digest(out / "inputs.json") == frozen["inputs_sha256"]
    for path in (out / "responses").glob("*_v1.json"):
        v1 = json.loads(path.read_text(encoding="utf-8"))
        v2 = json.loads(path.with_name(path.name.replace("_v1", "_v2")).read_text(encoding="utf-8"))
        assert v1["context"]["facts"] == v2["context"]["facts"]
        for r in (v1, v2):
            _assert_no_ground_truth(r["context"]["system"] + r["context"]["user"])
            assert r["inference_kind"] == "LOCAL_QWEN"
