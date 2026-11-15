"""06A-R security/provenance tests. HTTP responses here are test doubles, not inference."""
import copy
import io
import json
from pathlib import Path
import subprocess
import types
import urllib.request
from unittest.mock import Mock

import pytest

from agent.config import AgentConfig
from agent.planner import OllamaPlanner, PlannerError, _RejectRedirects
from evaluation.task06a import assessor_v2, experiment, schema_v2
from evaluation.task06a.verification import screen
from .test_task06a import _state_for_pipeline, _valid_v2, _MockV2

ROOT = Path(__file__).resolve().parents[3]
REVIEWED = "f913786822fb49608347013c884446000453fd79"


def unsafe_cfg(endpoint):
    # Deliberately bypass frozen dataclass validation, reproducing the reviewer's
    # send-boundary concern rather than merely testing AgentConfig.__post_init__.
    cfg = AgentConfig()
    object.__setattr__(cfg, "ollama_host", endpoint)
    return cfg


@pytest.mark.parametrize("endpoint", [
    "http://example.com:11434", "http://8.8.8.8:11434", "http://192.168.1.2:11434",
    "http://0.0.0.0:11434", "http://[2001:4860:4860::8888]:11434",
    "http://localhost.evil:11434", "http://127.0.0.1.evil:11434",
    "http://localhost@evil:11434", "http://user:password@127.0.0.1:11434",
    "https://127.0.0.1:11434", "http://127.0.0.1:11434/evil",
    "http://127.0.0.1:11434?host=evil", "http://[invalid",
])
def test_non_loopback_denied_before_request_or_io(monkeypatch, endpoint):
    cfg = unsafe_cfg(endpoint)
    request, opener, send = Mock(), Mock(), Mock()
    monkeypatch.setattr(urllib.request, "Request", request)
    monkeypatch.setattr(urllib.request, "build_opener", opener)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", send)
    with pytest.raises(PlannerError, match="loopback"):
        assessor_v2._decide_v2(object(), {}, cfg)
    request.assert_not_called()
    opener.assert_not_called()
    send.assert_not_called()


def test_caller_validator_override_cannot_authorize_remote(monkeypatch):
    cfg = unsafe_cfg("http://8.8.8.8:11434")
    object.__setattr__(cfg, "is_local_loopback", lambda: True)
    request = Mock()
    monkeypatch.setattr(urllib.request, "Request", request)
    with pytest.raises(PlannerError, match="loopback"):
        assessor_v2._decide_v2(object(), {}, cfg)
    request.assert_not_called()


def test_shared_schema_transport_rechecks_mutated_config(monkeypatch):
    cfg = AgentConfig()
    planner = OllamaPlanner(cfg)
    object.__setattr__(cfg, "ollama_host", "http://8.8.8.8:11434")
    request, opener = Mock(), Mock()
    monkeypatch.setattr(urllib.request, "Request", request)
    monkeypatch.setattr(urllib.request, "build_opener", opener)
    with pytest.raises(PlannerError, match="loopback"):
        planner.decide_with_schema({}, schema_v2.OLLAMA_FORMAT_SCHEMA_V2)
    request.assert_not_called()
    opener.assert_not_called()


@pytest.mark.parametrize("endpoint", ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"])
def test_v2_uses_shared_transport_and_unchanged_schema(monkeypatch, endpoint):
    cfg = unsafe_cfg(endpoint)
    calls = []
    def fake_open(self, req, **kwargs):
        calls.append((req, kwargs, self.handlers))
        return io.BytesIO(json.dumps({"message": {"content": "unit-test-response"},
                                     "eval_count": 7, "prompt_eval_count": 11}).encode())
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    ctx = {"system": "system", "user": "data", "remaining_s": 5, "output_token_limit": 100}
    result = assessor_v2._decide_v2(object(), ctx, cfg)
    assert result["raw"] == "unit-test-response"
    assert len(calls) == 1
    request, kwargs, handlers = calls[0]
    body = json.loads(request.data)
    assert body["format"] == schema_v2.OLLAMA_FORMAT_SCHEMA_V2
    assert body["think"] is False and body["stream"] is False
    assert body["options"]["num_predict"] == 100
    assert kwargs["timeout"] == 5
    assert request.full_url == endpoint + "/api/chat"
    assert any(isinstance(h, _RejectRedirects) for h in handlers)
    assert not any(isinstance(h, urllib.request.ProxyHandler) and h.proxies for h in handlers)


@pytest.mark.parametrize("destination", ["http://8.8.8.8/api/chat", "http://127.0.0.1:11434/new"])
def test_redirect_rejected_before_followup_request(monkeypatch, destination):
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat")
    request = Mock()
    monkeypatch.setattr(urllib.request, "Request", request)
    handler = _RejectRedirects()
    handler.add_parent(urllib.request.build_opener(handler))
    with pytest.raises(PlannerError, match="redirects are forbidden"):
        handler.http_error_302(req, io.BytesIO(b""), 302, "Found", {"location": destination})
    request.assert_not_called()


@pytest.mark.parametrize("payload", [
    {"message": {"content": "unit response"}, "eval_count": 3, "prompt_eval_count": 5, "done_reason": "stop"},
    {"message": {"content": ""}},
])
def test_v1_wire_contract_and_response_match_reviewed_source(monkeypatch, payload):
    # Execute ONLY the explicitly pinned, trusted repository module as a reference.
    # This is not target-derived code and no network/model inference occurs.
    source = subprocess.check_output(["git", "show", REVIEWED + ":agent/planner.py"], cwd=ROOT)
    reference = types.ModuleType("agent._task06a_r_reference")
    reference.__package__ = "agent"
    exec(compile(source, "frozen-agent-planner", "exec"), reference.__dict__)
    calls = []
    def fake_open(self, req, **kwargs):
        calls.append((req.full_url, req.data, dict(req.header_items()), kwargs))
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    cfg = AgentConfig()
    ctx = {"system": "system", "user": "evidence", "remaining_s": 4, "output_token_limit": 123}
    outcomes = []
    for cls in (reference.OllamaPlanner, OllamaPlanner):
        try:
            result = cls(cfg).decide(ctx)
            outcomes.append((result.raw, result.meta))
        except Exception as exc:
            outcomes.append((type(exc).__name__, str(exc)))
    assert calls[0] == calls[1]
    assert outcomes[0] == outcomes[1]


def test_schema_transport_failure_has_no_fallback(monkeypatch):
    send = Mock(side_effect=TimeoutError("unit timeout"))
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", send)
    cfg = AgentConfig()
    result = assessor_v2.assess_once_v2(_state_for_pipeline(), cfg, OllamaPlanner(cfg), max_attempts=2)
    assert result["status"] == "AGENT_ERROR"
    assert len(result["attempts"]) == 1
    assert send.call_count == 1


def test_insufficient_monitor_preserves_raw_and_requires_human_without_execution(monkeypatch):
    state, cfg = _state_for_pipeline(), AgentConfig()
    obj = _valid_v2()
    obj["case_id"] = state["case_id"]
    obj["assessment"].update(alignment="INSUFFICIENT_EVIDENCE", review_required=False, recommendation="MONITOR")
    raw = json.dumps(obj)
    # No containment or child process is permitted on this read-only assessment path.
    execute = Mock(side_effect=AssertionError("must not execute"))
    monkeypatch.setattr(subprocess, "Popen", execute)
    result = assessor_v2.assess_once_v2(state, cfg, _MockV2(raw), max_attempts=1)
    before = copy.deepcopy(result)
    facts = assessor_v2.build_context_v2(state, cfg)["facts"]
    checks = screen(result["assessment"], facts, state["evidence"][-1]["value"])
    assert result == before
    assert result["attempts"][0]["raw"] == raw
    assert result["assessment"]["recommendation"] == "MONITOR"
    assert result["assessment"]["review_required"] is False
    assert "insufficient_evidence_without_review" in checks["consistency"]["flags"]
    effective = checks["effective_recommendation"]
    assert effective["action"] == "MANUAL_REVIEW"
    assert effective["review_required"] is True
    assert effective["requires_human_decision"] is True
    assert effective["execution_status"] == "NOT_EXECUTED"
    execute.assert_not_called()


def test_grounding_flag_is_unverified_screen_not_confirmed_hallucination():
    state = _state_for_pipeline()
    a = _valid_v2()["assessment"]
    a["explanation"] = "No command-and-control activity was observed."
    facts = assessor_v2.build_context_v2(state, AgentConfig())["facts"]
    checks = screen(a, facts, state["evidence"][-1]["value"])
    assert checks["grounding_screen"]["runtime_behaviour_claims"]  # known heuristic false positive
    assert checks["semantic_grounding"] == "NOT_ESTABLISHED_RULE_SCREEN_ONLY"
    assert "confirmed" not in checks


def test_inference_runner_does_not_parse_evaluator_labels(tmp_path, monkeypatch):
    cfg, state = AgentConfig(), _state_for_pipeline()
    prediction = state["evidence"][-1]["value"]
    (tmp_path / "inputs.json").write_text(json.dumps([{"sha256": "b" * 64, "state": state, "prediction": prediction}]))
    (tmp_path / "manifest_EVALUATOR_ONLY.json").write_text('{"true_label": "must never reach inference"}')
    original_read, opened = experiment.read, []
    def guarded_read(path):
        opened.append(Path(path).name)
        assert Path(path).name != "manifest_EVALUATOR_ONLY.json"
        return original_read(path)
    monkeypatch.setattr(experiment, "read", guarded_read)
    # Isolate the inference stage from source-freeze validation, which deliberately
    # hashes manifest BYTES but does not parse/use labels. All inference is mocked.
    from dataclasses import asdict
    frozen = {"config": asdict(cfg), "ollama_model": {"digest": "unit"}, "ollama_version": {"version": "unit"}}
    monkeypatch.setattr(experiment, "validate_freeze", lambda out: frozen)
    monkeypatch.setattr(experiment, "ollama_json", lambda route: {"models": [{"name": cfg.model, "digest": "unit"}]} if route == "tags" else {"version": "unit"})
    monkeypatch.setattr(experiment, "RecordingPlanner", lambda cfg: types.SimpleNamespace(inner=None, calls=[]))
    # Test doubles never produce committed real-inference artifacts; outputs live only in tmp_path.
    monkeypatch.setattr(experiment.agent_replay, "run_agent_once", lambda *a, **kw: {"status": "AGENT_ERROR"})
    monkeypatch.setattr(experiment, "assess_once_v2", lambda *a, **kw: {"status": "AGENT_ERROR"})
    experiment.run(tmp_path)
    assert opened == ["inputs.json"]


def test_historical_freeze_rejects_current_repaired_source():
    with pytest.raises(ValueError, match="Code or old benchmark drift"):
        experiment.validate_freeze(ROOT / "evaluation/task06a/results/dev_v2_1")


def test_prompt_and_v2_schema_unchanged():
    frozen = experiment.read(ROOT / "evaluation/task06a/results/dev_v2_1/freeze.json")
    assert assessor_v2.prompt_version_v2() == frozen["v2"]
    subprocess.run(["git", "diff", "--exit-code", REVIEWED, "--", "evaluation/task06a/schema_v2.py"],
                   cwd=ROOT, check=True, capture_output=True)
