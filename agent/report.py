"""Grounded investigation report generator.

Summarizes the investigation into a verdict with confidence, uncertainty,
limitations and the exact evidence it rests on. Never forces a malicious/benign
verdict: insufficient evidence yields INSUFFICIENT_EVIDENCE.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional


def build_report(state: Mapping[str, Any], *, outcome: str,
                 finding: Optional[Mapping[str, Any]] = None,
                 stop_reason: Optional[str] = None,
                 history: Optional[List[Mapping[str, Any]]] = None,
                 decision_log: Optional[List[Mapping[str, Any]]] = None) -> Dict[str, Any]:
    tref = state.get("target_ref") or {}
    f = dict(finding or {})
    verdict = f.get("verdict") or "INSUFFICIENT_EVIDENCE"
    report = {
        "schema_version": "agent-report-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_id": state["case_id"],
        "case_revision": state.get("revision", 1),
        "target_type": state["target_type"],
        "target_verified_sha256": (tref.get("verified_digest") or {}).get("value"),
        "outcome": outcome,                      # FINISHED | DYNAMIC_REQUESTED | BUDGET_EXHAUSTED | ERROR
        "stop_reason": stop_reason,
        "verdict": verdict,
        "confidence": f.get("confidence", 0.0),
        "rationale": f.get("rationale", ""),
        "limitations": list(f.get("limitations", [])) + [
            "Local SLM (local Qwen) planner; reasoning quality is limited and must be reviewed.",
            "No REA/Ghidra adapter, no LightGBM inference, no VM dynamic analysis in this build.",
        ],
        "evidence_cited": list(f.get("evidence_refs", [])),
        "tool_runs": [{"tool_run_id": r.get("tool_run_id"), "tool": r.get("tool"),
                       "status": r.get("status")} for r in state.get("tool_runs", [])],
        "iterations": max((d.get("iteration", 0) for d in (decision_log or [])), default=0),
        "decision_log": list(decision_log or []),
    }
    return report
