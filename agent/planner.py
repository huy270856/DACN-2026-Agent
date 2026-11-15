"""Planner interface + local local Qwen (Ollama) and deterministic Mock planners.

The planner returns the model's RAW text; the Controller parses/validates it.
The planner never executes anything and talks only to the local Ollama loopback
endpoint. On any model/transport error it raises PlannerError and NEVER silently
falls back to a different model.
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Protocol

from .config import AgentConfig
from .schema import OLLAMA_FORMAT_SCHEMA


class PlannerError(Exception):
    """Model/transport failure. Treated as an error, never as a benign result."""


class Planner(Protocol):
    def decide(self, context: Mapping[str, Any]) -> "PlanResult": ...


class PlanResult:
    def __init__(self, raw: str, latency_s: float, meta: Optional[Dict[str, Any]] = None):
        self.raw = raw
        self.latency_s = latency_s
        self.meta = meta or {}


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Schema-aware evaluation calls never follow an endpoint redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Refuse before urllib can construct a request to the redirect target.
        raise PlannerError("Ollama redirects are forbidden")


class OllamaPlanner:
    """Local local Qwen via Ollama /api/chat with JSON-schema-constrained output."""

    def __init__(self, cfg: AgentConfig):
        if not cfg.is_local_loopback():
            raise PlannerError("Ollama host must be a local loopback address")
        self._cfg = cfg

    def decide(self, context: Mapping[str, Any]) -> PlanResult:
        # Frozen v1 request contract and transport behaviour remain the default.
        return self._decide(context, OLLAMA_FORMAT_SCHEMA)

    def decide_with_schema(self, context: Mapping[str, Any], format_schema: Mapping[str, Any]) -> PlanResult:
        """Explicit schema transport for v2; fail closed before any HTTP object/IO.

        Check the actual config again at the send boundary, including configs
        constructed without __post_init__ or mutated after planner construction.
        Use the trusted implementation, not a caller-supplied validator override.
        """
        try:
            local = AgentConfig.is_local_loopback(self._cfg)
        except (ValueError, TypeError, AttributeError):
            local = False
        if not local:
            raise PlannerError("Ollama host must be a local loopback address")
        return self._decide(context, format_schema, reject_redirects=True)

    def _decide(self, context: Mapping[str, Any], format_schema: Mapping[str, Any],
                *, reject_redirects: bool = False) -> PlanResult:
        cfg = self._cfg
        body = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": context["system"] + "\nRequired output contract: " + json.dumps(format_schema)},
                {"role": "user", "content": context["user"]},
            ],
            "stream": False,
            "think": cfg.think,
            "format": format_schema,   # constrained decoding when supported
            "options": {"temperature": cfg.temperature, "seed": 42, "num_predict": min(cfg.num_predict, context.get("output_token_limit", cfg.num_predict)), "num_ctx": 8192},
        }
        req = urllib.request.Request(
            cfg.ollama_host.rstrip("/") + "/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            handlers = [urllib.request.ProxyHandler({})]
            if reject_redirects:
                handlers.append(_RejectRedirects())
            with urllib.request.build_opener(*handlers).open(req, timeout=min(cfg.inference_timeout_s, context.get("remaining_s", cfg.inference_timeout_s))) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # transport/timeout/http
            raise PlannerError(f"Ollama inference failed: {type(exc).__name__}: {exc}") from exc
        latency = round(time.time() - t0, 2)
        content = (payload.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise PlannerError("Ollama returned empty content")
        return PlanResult(content, latency, {"model": cfg.model, "think": cfg.think,
                                             "eval_count": payload.get("eval_count"), "prompt_eval_count": payload.get("prompt_eval_count"), "done_reason": payload.get("done_reason")})


class MockPlanner:
    """MOCK_LLM planner for deterministic tests. NOT a real AI agent.

    Returns a fixed sequence of action JSON strings; raises if exhausted.
    """

    is_mock = True

    def __init__(self, scripted_actions: List[Dict[str, Any]]):
        self._queue = list(scripted_actions)
        self._i = 0

    def decide(self, context: Mapping[str, Any]) -> PlanResult:
        if self._i >= len(self._queue):
            raise PlannerError("MockPlanner script exhausted")
        action = dict(self._queue[self._i])
        self._i += 1
        # A realistic planner reads the current case_id/revision from the context;
        # the mock fills them so scripted actions stay revision-correct across turns.
        facts = context.get("facts", {})
        action.setdefault("case_id", facts.get("case_id"))
        action["case_id"] = facts.get("case_id", action.get("case_id"))
        action["case_revision"] = facts.get("case_revision", action.get("case_revision"))
        return PlanResult(json.dumps(action), 0.0, {"mock": True})
