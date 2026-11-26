"""TASK 07A (D3): additive decoding options in agent/planner.py.

Unit tests with a fake HTTP transport only. No Ollama call, no model inference.
"""
import io
import json
import subprocess
import types
import urllib.request
from pathlib import Path

import pytest

from agent.config import AgentConfig
from agent.planner import DEFAULT_DECODING, DecodingOptions, OllamaPlanner, PlannerError

ROOT = Path(__file__).resolve().parents[1]
PRE_07A = "e31ee31"  # last commit before TASK 07A touched agent/planner.py
CTX = {"system": "system", "user": "evidence", "remaining_s": 4, "output_token_limit": 123}
OK = {"message": {"content": "{\"a\": 1}"}, "eval_count": 3, "prompt_eval_count": 5, "done_reason": "stop"}


def _capture(monkeypatch, payload):
    calls = []

    def fake_open(self, req, **kwargs):
        calls.append(json.loads(req.data.decode("utf-8")))
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    return calls


def _reference_planner_module():
    source = subprocess.check_output(["git", "show", PRE_07A + ":agent/planner.py"], cwd=ROOT)
    ref = types.ModuleType("agent._task07a_reference")
    ref.__package__ = "agent"
    exec(compile(source, "pre-07a-agent-planner", "exec"), ref.__dict__)
    return ref


@pytest.mark.parametrize("method", ["decide", "decide_with_schema"])
def test_a_default_request_body_identical_to_pre_07a(monkeypatch, method):
    calls = _capture(monkeypatch, OK)
    ref = _reference_planner_module()
    cfg = AgentConfig()
    outs = []
    for cls in (ref.OllamaPlanner, OllamaPlanner):
        p = cls(cfg)
        r = p.decide(CTX) if method == "decide" else p.decide_with_schema(CTX, {"type": "object"})
        outs.append((r.raw, r.meta))
    assert calls[0] == calls[1]
    assert json.dumps(calls[0]) == json.dumps(calls[1])  # key order too
    assert outs[0] == outs[1]
    # Explicit default object is equivalent to omitting it.
    p = OllamaPlanner(cfg, DecodingOptions())
    p.decide(CTX) if method == "decide" else p.decide_with_schema(CTX, {"type": "object"})
    assert json.dumps(calls[2]) == json.dumps(calls[0])


def test_b_defaults():
    d = DecodingOptions()
    assert (d.num_ctx, d.seed, d.top_p, d.top_k, d.presence_penalty) == (8192, 42, None, None, None)
    assert DEFAULT_DECODING == d
    assert d.options(0.1, 10) == {"temperature": 0.1, "seed": 42, "num_predict": 10, "num_ctx": 8192}


@pytest.mark.parametrize("kwargs", [
    {"num_ctx": 1024}, {"num_ctx": 70000}, {"num_ctx": True}, {"num_ctx": 8192.0},
    {"seed": -1}, {"seed": "42"}, {"top_p": 0}, {"top_p": 1.5}, {"top_p": float("nan")},
    {"top_k": 0}, {"top_k": 2.5}, {"presence_penalty": 3.0}, {"presence_penalty": float("inf")},
])
def test_c_out_of_range_rejected(kwargs):
    with pytest.raises(ValueError):
        DecodingOptions(**kwargs)


def test_c_non_options_object_rejected():
    with pytest.raises(PlannerError):
        OllamaPlanner(AgentConfig(), {"num_ctx": 16384})


def test_optional_sampling_keys_only_when_set(monkeypatch):
    calls = _capture(monkeypatch, OK)
    d = DecodingOptions(num_ctx=16384, seed=7, top_p=0.95, top_k=20, presence_penalty=0.0)
    OllamaPlanner(AgentConfig(), d).decide_with_schema(CTX, {"type": "object"})
    assert calls[0]["options"] == {"temperature": 0.1, "seed": 7, "num_predict": 123, "num_ctx": 16384,
                                   "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0}
    OllamaPlanner(AgentConfig(), DecodingOptions(seed=7)).decide(CTX)
    assert set(calls[1]["options"]) == {"temperature", "seed", "num_predict", "num_ctx"}


def test_d_thinking_recorded_in_meta(monkeypatch):
    payload = dict(OK, message={"content": "{}", "thinking": "step 1 ... step 2"})
    _capture(monkeypatch, payload)
    r = OllamaPlanner(AgentConfig(think=True)).decide_with_schema(CTX, {"type": "object"})
    assert r.raw == "{}"
    assert r.meta["thinking"] == "step 1 ... step 2"
    assert r.meta["thinking_chars"] == len("step 1 ... step 2")
    assert r.meta["think"] is True


def test_d_no_thinking_field_meta_unchanged(monkeypatch):
    _capture(monkeypatch, OK)
    r = OllamaPlanner(AgentConfig()).decide(CTX)
    assert set(r.meta) == {"model", "think", "eval_count", "prompt_eval_count", "done_reason"}


def test_empty_content_with_thinking_is_error_not_fallback(monkeypatch):
    payload = {"message": {"content": "", "thinking": "x" * 50}, "done_reason": "length", "eval_count": 9}
    _capture(monkeypatch, payload)
    with pytest.raises(PlannerError, match=r"empty content \(thinking_chars=50, done_reason=length"):
        OllamaPlanner(AgentConfig(think=True)).decide(CTX)
