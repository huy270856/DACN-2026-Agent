"""Agent runtime configuration (model, budgets, timeouts).

Values come from explicit construction or trusted environment variables, never
from CaseState, evidence or model output. No secrets are stored here (the local
Ollama endpoint needs none).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentConfig:
    # Local SLM runtime (Ollama on loopback only).
    model: str = "qwen3.5:4b"
    ollama_host: str = "http://127.0.0.1:11434"
    temperature: float = 0.1          # low for stable tool selection
    num_predict: int = 1536            # max output tokens per call
    think: bool = False               # thinking mode (configurable; off by default)
    inference_timeout_s: float = 180.0

    # Investigation budgets (deterministic guardrails).
    # Trusted operator-maintained hash reputation policy; never populated by model/evidence text.
    known_reputations: dict = field(default_factory=dict)
    max_tokens: int = 100000
    max_iterations: int = 8
    max_tool_calls: int = 6
    wall_clock_s: float = 900.0
    max_context_chars: int = 12000    # bound the CaseState context fed to the model
    max_value_chars: int = 800        # truncate large evidence values (e.g. pseudocode)

    def __post_init__(self):
        if self.model not in {"qwen3.5:4b", "qwen3:1.7b"} or not self.is_local_loopback():
            raise ValueError("Only local qwen3.5:4b is supported")
        for name in ("max_tokens", "max_iterations", "max_tool_calls", "wall_clock_s", "num_predict", "inference_timeout_s", "max_context_chars", "max_value_chars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1000000:
                raise ValueError(f"Invalid budget: {name}")

    @classmethod
    def from_env(cls) -> "AgentConfig":
        g = os.environ.get
        return cls(
            model=g("DACN_AGENT_MODEL", "qwen3.5:4b"),
            ollama_host=g("DACN_OLLAMA_HOST", "http://127.0.0.1:11434"),
            think=g("DACN_AGENT_THINK", "0") == "1",
            max_iterations=int(g("DACN_AGENT_MAX_ITERS", "8")),
            max_tool_calls=int(g("DACN_AGENT_MAX_TOOLS", "6")),
        )

    def is_local_loopback(self) -> bool:
        from urllib.parse import urlsplit
        u = urlsplit(self.ollama_host)
        return (u.scheme == "http" and u.hostname in {"127.0.0.1", "localhost", "::1"}
                and not u.username and not u.password and u.path in ("", "/")
                and not u.query and not u.fragment)
