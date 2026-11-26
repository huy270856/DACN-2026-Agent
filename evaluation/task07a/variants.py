"""TASK 07A diagnostic variants V0-V3 (DEV_DIAGNOSTIC only; never confirmatory).

The Agent under test is investigation v3.4 UNCHANGED (`investigation_v3.workflow_v34`,
`final_v34`, `repair_context`). Variants differ only in:
  * AgentConfig budgets / think / temperature and planner DecodingOptions (V0, V1, V2);
  * a harness-level decoding wrapper that prepends a model-authored `analysis` field (V2);
  * a harness-level ORACLE page selection over already-committed imports (V3).

Evaluator-only data (relevant_entries) is used by V3 ONLY to choose which committed page
`repair_context.build` projects. No label, reference answer or evaluator text enters a prompt.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple
from unittest import mock

from agent.config import AgentConfig
from agent.planner import DecodingOptions, OllamaPlanner, PlanResult
from investigation_v3 import final_v34, repair_context
from investigation_v3.imports_tool import FACET
from investigation_v3.retrieval import PAGE_SIZE

# Identical to evaluation.task06b_j.runner.CFG (verified by test); V0 must equal it.
BASE_CFG = dict(max_iterations=5, max_tool_calls=1, max_context_chars=24000, num_predict=2048,
                inference_timeout_s=90, wall_clock_s=180)

COHORT_CLASSES_ALL = ("IN_INITIAL_TOOL_PROJECTION", "REACHABLE_BY_BOUNDED_RETRIEVAL",
                      "INACCESSIBLE_UNDER_LIMITS", "NOT_STATIC_ANSWERABLE", "INITIAL_EVIDENCE_SUFFICIENT")
ORACLE_CLASSES = ("IN_INITIAL_TOOL_PROJECTION", "REACHABLE_BY_BOUNDED_RETRIEVAL")

ANALYSIS_DESCRIPTION = ("Before choosing the action, reason step by step: what the question asks, what visible "
                        "evidence answers it, what is still missing, and whether a listed action can obtain it.")
ANALYSIS_MAX = 1500

VARIANTS: Dict[str, Dict[str, Any]] = {
    "V0": {"hypothesis": "baseline / seed noise", "planner": "V34",
           "cfg": dict(BASE_CFG), "decoding": {"num_ctx": 8192}, "seeds": [42, 7],
           "classes": COHORT_CLASSES_ALL},
    # V1 budgets raised after G1 smoke FAIL (truncation at num_predict 6144), before protocol freeze,
    # by owner decision 2026-11-26 (EVALUATION_LOG). V1b dropped by the same decision.
    # max_tokens 200000: workflow_v34 charges max(8192 + 2*num_predict, actual) per turn.
    "V1": {"hypothesis": "H1 native thinking (E1); confound: also changes sampling", "planner": "V34",
           "cfg": dict(BASE_CFG, think=True, temperature=0.6, num_predict=12288, inference_timeout_s=240,
                       wall_clock_s=900, max_tokens=200000),
           "decoding": {"num_ctx": 24576, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0},
           "seeds": [42, 7], "classes": COHORT_CLASSES_ALL},
    "V2": {"hypothesis": "H1 analysis-first field order (E2), think OFF", "planner": "ANALYSIS_FIRST",
           "cfg": dict(BASE_CFG, num_predict=3072, wall_clock_s=300),
           "decoding": {"num_ctx": 12288}, "seeds": [42, 7], "classes": COHORT_CLASSES_ALL},
    "V3": {"hypothesis": "H3 vs H2: ORACLE_DIAGNOSTIC committed page made visible (E4)", "planner": "V34",
           "cfg": dict(BASE_CFG), "decoding": {"num_ctx": 8192}, "seeds": [42], "classes": ORACLE_CLASSES,
           "oracle": True},
}


def make_cfg(variant: str, seed: int) -> Tuple[AgentConfig, DecodingOptions]:
    spec = VARIANTS[variant]
    if seed not in spec["seeds"]:
        raise ValueError(f"SEED_NOT_IN_PROTOCOL {variant} {seed}")
    return AgentConfig(**spec["cfg"]), DecodingOptions(seed=seed, **spec["decoding"])


def sha_json(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- planners
class V34Planner:
    """Same as `workflow_v34.Planner`, plus explicit DecodingOptions (seed/num_ctx/sampling).

    With default DecodingOptions the request body equals workflow_v34.Planner's (tested).
    """
    is_mock = False

    def __init__(self, cfg: AgentConfig, decoding: DecodingOptions):
        self.transport = OllamaPlanner(cfg, decoding)

    def decide(self, ctx):
        return self.transport.decide_with_schema(ctx, final_v34.contract(ctx))


def add_analysis(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Deep copy of a v3.4 contract with a required `analysis` string FIRST in every branch."""
    out = copy.deepcopy(schema)
    for br in out["oneOf"]:
        props = {"analysis": {"type": "string", "minLength": 1, "maxLength": ANALYSIS_MAX,
                              "description": ANALYSIS_DESCRIPTION}}
        props.update(br["properties"])
        br["properties"] = props
        br["required"] = ["analysis"] + [r for r in br["required"] if r != "analysis"]
    return out


class AnalysisFirstPlanner:
    """V2: decode with `analysis` before `action`; strip it before the v3.4 workflow parses.

    `final_v34` is NOT modified: the remaining object is validated by v3.4 exactly as before.
    The analysis text is model-authored and is kept only in turn meta (never fed back).
    """
    is_mock = False

    def __init__(self, cfg: AgentConfig, decoding: DecodingOptions):
        self.transport = OllamaPlanner(cfg, decoding)

    def decide(self, ctx):
        schema = add_analysis(final_v34.contract(ctx))
        resp = self.transport.decide_with_schema(ctx, schema)
        return strip_analysis(resp, sha_json(schema))


def strip_analysis(resp: PlanResult, schema_sha256: Optional[str] = None) -> PlanResult:
    meta = dict(resp.meta)
    meta["augmented_schema_sha256"] = schema_sha256
    try:
        obj = json.loads(resp.raw)
    except (TypeError, ValueError):
        meta["analysis_parse"] = "JSON_ERROR"
        return PlanResult(resp.raw, resp.latency_s, meta)
    if not isinstance(obj, dict):
        meta["analysis_parse"] = "NOT_OBJECT"
        return PlanResult(resp.raw, resp.latency_s, meta)
    meta["analysis_first"] = bool(obj) and list(obj)[0] == "analysis"
    meta["raw_with_analysis"] = resp.raw
    if "analysis" not in obj:
        meta["analysis_parse"] = "MISSING"
        return PlanResult(resp.raw, resp.latency_s, meta)
    analysis = obj.pop("analysis")
    meta.update(analysis=analysis, analysis_chars=len(analysis) if isinstance(analysis, str) else None,
                analysis_parse="OK")
    return PlanResult(json.dumps(obj), resp.latency_s, meta)


# --------------------------------------------------------------------------- oracle (V3)
def load_relevant(reference: Any) -> List[str]:
    """relevant_entries from a reference_EVALUATOR_ONLY field (dict, or a Python-repr string)."""
    if isinstance(reference, str):
        reference = ast.literal_eval(reference)  # literal parsing only; never eval()
    if not isinstance(reference, dict):
        return []
    rel = reference.get("relevant_entries") or []
    if isinstance(rel, str):
        rel = ast.literal_eval(rel)
    return [str(x) for x in rel]


def literal_key(lib: Any, sym_or_ordinal: Any) -> Tuple[str, str]:
    return (str(lib or "").lower(), str(sym_or_ordinal))


def parse_literal(literal: str) -> Tuple[str, str]:
    lib, sep, sym = literal.partition("!")
    if not sep or not lib or not sym:
        raise ValueError(f"BAD_IMPORT_LITERAL {literal!r}")
    return literal_key(lib, sym)


def entry_key(entry: Dict[str, Any]) -> Tuple[str, str]:
    sym = entry.get("symbol")
    return literal_key(entry.get("library"), sym if sym is not None else "#" + str(entry.get("ordinal")))


def relevant_indices(entries: Iterable[Dict[str, Any]], literals: Iterable[str]) -> List[int]:
    keys = {parse_literal(x) for x in literals}
    return [i for i, e in enumerate(entries) if entry_key(e) in keys]


def oracle_page_for(state: Dict[str, Any], literals: List[str]) -> Dict[str, Tuple[int, int]]:
    """{imports evidence_id: (offset, 16)} for the first committed relevant entry, if any."""
    out = {}
    for ev in state.get("evidence", []):
        if ev.get("facet") != FACET or ev.get("status") != "SUCCESS":
            continue
        idx = relevant_indices((ev.get("value") or {}).get("entries", []), literals)
        if idx:
            out[ev["evidence_id"]] = ((idx[0] // PAGE_SIZE) * PAGE_SIZE, PAGE_SIZE)
    return out


@contextmanager
def oracle_pages(literals: List[str], record: List[Dict[str, Any]]):
    """Patch repair_context.build so the committed page holding the first relevant entry is shown.

    The workflow's `pages` dict is copied, never mutated, and data still flows through
    retrieval.fetch (case/revision/SHA binding unchanged). `record` collects evaluator-only
    notes (offset per turn) for the run's EVALUATOR_ONLY file.
    """
    original = repair_context.build

    def wrapped(state, tools, cfg, *, pages, **kw):
        new_pages = {k: list(v) for k, v in pages.items()}
        for evidence_id, page in oracle_page_for(state, literals).items():
            existing = list(new_pages.get(evidence_id, [(0, PAGE_SIZE)]))
            added = page not in existing
            if added:
                new_pages[evidence_id] = existing + [page]
            record.append({"evidence_id": evidence_id, "oracle_offset": page[0], "page_added": added,
                           "case_revision": state.get("revision")})
        return original(state, tools, cfg, pages=new_pages, **kw)

    with mock.patch.object(repair_context, "build", wrapped):
        yield


def describe(variant: str, seed: int) -> Dict[str, Any]:
    cfg, dec = make_cfg(variant, seed)
    from dataclasses import asdict
    spec = VARIANTS[variant]
    d = {"variant": variant, "seed": seed, "hypothesis": spec["hypothesis"], "planner": spec["planner"],
         "oracle": bool(spec.get("oracle")), "cohort_classes": list(spec["classes"]),
         "agent_config": asdict(cfg), "decoding": asdict(dec)}
    if spec["planner"] == "ANALYSIS_FIRST":
        schema = add_analysis(final_v34.contract())
        d["augmented_schema_generic"] = schema
        d["augmented_schema_generic_sha256"] = sha_json(schema)
    return d
