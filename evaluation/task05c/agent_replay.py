"""Static + Agent branch (B): run the REAL Qwen agent over projected evidence.

Reuses the production agent stack (agent.context + agent.planner + agent.schema)
unchanged. For FEATURE_RECORD_REPLAY there is no raw PE to execute, so the D5
executor is not involved; the agent assesses the SAME static prediction and the
SAME evidence projection used by the static-only baseline. The agent never
receives ground truth and cannot override the static label.

Logs FAIL / TIMEOUT explicitly; an incomplete run is never recorded as success.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Mapping, Optional

from agent import context as agent_context
from agent import schema as agent_schema
from agent.planner import PlannerError

VALID_ALIGNMENT = {"CONSISTENT", "CONFLICT", "INSUFFICIENT_EVIDENCE"}


def prompt_version() -> Dict[str, str]:
    """Stable hash of the agent prompt + action contract used for branch B."""
    import inspect
    blob = (agent_context._SYSTEM
            + inspect.getsource(agent_context.build_context)
            + json.dumps(agent_schema.OLLAMA_FORMAT_SCHEMA, sort_keys=True))
    return {"prompt_id": "agent-context-v1",
            "prompt_sha256": hashlib.sha256(blob.encode()).hexdigest()[:16]}


def build_replay_state(sha256: str, projection: Mapping[str, Any],
                       prediction_obs: Mapping[str, Any]) -> Dict[str, Any]:
    """A CaseState-shaped dict for the agent. Contains NO ground-truth label."""
    evidence = list(projection["observations"]) + [prediction_obs]
    return {
        "case_id": "CASE-replay-" + sha256[:24],
        "revision": 1,
        "lifecycle_status": "INVESTIGATING",
        "target_type": "FILE",
        "target_ref": {"kind": "FILE", "identity_strength": "STRONG",
                       "verified_digest": {"algo": "sha256", "value": sha256}},
        "evidence": evidence,
        "residual_unknowns": [],
    }


def _assert_no_ground_truth(context_text: str) -> None:
    """Defensive: the rendered context must not contain a ground-truth field."""
    lowered = context_text.lower()
    for banned in ("true_label", "ground_truth", "groundtruth", "\"label\":", "'label':"):
        if banned in lowered:
            raise AssertionError(f"ground-truth token leaked into agent context: {banned!r}")


def run_agent_once(state: Mapping[str, Any], cfg, planner, *, max_attempts=2) -> Dict[str, Any]:
    """Ask the real agent for a single FINISH assessment. Returns a result dict."""
    attempts: List[Dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        context = agent_context.build_context(state, [], cfg, history=[])
        rendered = context["system"] + "\n" + context["user"]
        _assert_no_ground_truth(rendered)
        context["remaining_s"] = cfg.inference_timeout_s
        t0 = time.time()
        try:
            result = planner.decide(context)
        except PlannerError as exc:
            attempts.append({"attempt": attempt, "error": f"planner:{exc}"})
            return {"status": "AGENT_ERROR", "error": str(exc), "attempts": attempts,
                    "latency_s": round(time.time() - t0, 2)}
        latency = round(time.time() - t0, 2)
        try:
            proposal = agent_schema.parse_and_validate(result.raw)
        except agent_schema.ActionError as exc:
            attempts.append({"attempt": attempt, "parse_error": str(exc),
                             "raw": result.raw[:300]})
            continue
        meta = dict(result.meta)
        meta["latency_s"] = latency
        meta["prompt_eval_count"] = result.meta.get("prompt_eval_count")
        meta["eval_count"] = result.meta.get("eval_count")
        return {"status": "OK", "proposal": proposal, "meta": meta,
                "attempts": attempts, "latency_s": latency}
    return {"status": "AGENT_INVALID_OUTPUT", "attempts": attempts}


def extract_assessment(proposal: Mapping[str, Any]) -> Dict[str, Any]:
    """Pull the alignment assessment from a FINISH proposal; never fabricate."""
    action = proposal.get("action")
    finding = proposal.get("finding") or {}
    assessment = finding.get("assessment") if isinstance(finding, dict) else None
    out = {
        "action": action,
        "agent_own_verdict": finding.get("verdict"),
        "evidence_refs": list(proposal.get("evidence_refs", [])),
        "rationale": finding.get("rationale", ""),
        "limitations": list(finding.get("limitations", [])),
        "overrides_static_label": False,
    }
    if isinstance(assessment, dict) and assessment.get("alignment") in VALID_ALIGNMENT:
        out.update(
            evidence_alignment=assessment["alignment"],
            review_required=bool(assessment.get("review_required", True)),
            agent_recommendation=assessment.get("recommendation"),
            explanation=assessment.get("explanation") or finding.get("rationale", ""),
            structured_assessment=True,
        )
    else:
        out.update(evidence_alignment="INSUFFICIENT_EVIDENCE", review_required=True,
                   agent_recommendation=None,
                   explanation=finding.get("rationale", ""), structured_assessment=False)
    return out


def assess_sample(sha256: str, projection: Mapping[str, Any],
                  prediction_obs: Mapping[str, Any], cfg, planner) -> Dict[str, Any]:
    """Full branch-B result for one sample."""
    state = build_replay_state(sha256, projection, prediction_obs)
    run = run_agent_once(state, cfg, planner)
    base = {"branch": "STATIC_PLUS_AGENT", "sha256": sha256,
            "planner_kind": "MOCK_LLM" if getattr(planner, "is_mock", False) else "LOCAL_QWEN",
            "run_status": run["status"], "latency_s": run.get("latency_s")}
    if run["status"] != "OK":
        base.update(assessment=None, meta=run.get("attempts"),
                    error=run.get("error"))
        return base
    assessment = extract_assessment(run["proposal"])
    base.update(assessment=assessment, meta=run.get("meta"),
                raw_proposal=run["proposal"])
    return base
