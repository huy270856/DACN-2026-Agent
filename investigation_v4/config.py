"""TASK 07B: v4-only configuration (agent/config.py is pinned by the 06A frozen-baseline guard)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class V4Config:
    max_turns: int = 8              # the last turn is always reserved for the final answer
    max_queries: int = 6            # QUERY_IMPORTS (V4) or READ_TABLE (V4_NOQ) budget
    max_context_chars: int = 16000  # facts JSON; exceeding raises, never silently truncated
    retrieval_mode: str = "QUERY"   # "QUERY" (V4) or "READ_TABLE" (V4_NOQ ablation)
    max_repairs: int = 1            # format-only repair
    contract_version: str = "4.0"   # "4.1" (TASK 07C) adds ledger-bound absence_claims

    def __post_init__(self):
        for name in ("max_turns", "max_queries", "max_context_chars"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
                raise ValueError(f"Invalid V4Config.{name}")
        if self.max_turns < 2:
            raise ValueError("max_turns must leave one turn for the final answer")
        if self.retrieval_mode not in ("QUERY", "READ_TABLE"):
            raise ValueError("retrieval_mode must be QUERY or READ_TABLE")
        if self.contract_version not in ("4.0", "4.1", "4.2", "4.3"):
            raise ValueError("contract_version must be 4.0, 4.1, 4.2 or 4.3")
        if self.max_repairs not in (0, 1):
            raise ValueError("max_repairs must be 0 or 1")
