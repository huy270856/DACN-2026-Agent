"""TASK 07A deterministic metrics M1-M7 (DEV_DIAGNOSTIC). NOT semantic grading.

Inputs: frozen run traces (`*_C.json`) + the evaluator-only 06B-J v2 manifest
(accessibility_class, relevant_entries). Every metric reports numerator AND denominator,
per variant x seed and per accessibility class. Regex screens are labelled
REGEX_APPROX / RULE_SCREEN_CANDIDATE: they are candidate lists for manual review,
never semantic judgments.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from evaluation.task06b_j import pipeline_metrics
from evaluation.task07a.variants import entry_key, load_relevant, parse_literal

ROOT = Path(__file__).resolve().parents[2]
HOLDOUT_MANIFEST = ROOT / "evaluation/task06b_j/results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json"
FACET = "static.pe_imports_detail"
METRICS_VERSION = "task07a-metrics-v1"

IN_INITIAL, REACHABLE = "IN_INITIAL_TOOL_PROJECTION", "REACHABLE_BY_BOUNDED_RETRIEVAL"
INACCESSIBLE, NOT_STATIC, SUFFICIENT = ("INACCESSIBLE_UNDER_LIMITS", "NOT_STATIC_ANSWERABLE",
                                        "INITIAL_EVIDENCE_SUFFICIENT")
CLASSES = (IN_INITIAL, REACHABLE, INACCESSIBLE, NOT_STATIC, SUFFICIENT)

PARTIAL_RE = re.compile(
    r"only\s+\d+\s+of\s+\d+|\b\d+\s+of\s+(?:the\s+)?\d+\s+(?:committed\s+|import\s+|declared\s+)*(?:entries|imports)"
    r"|partial(?:ly)?\s+(?:import\s+)?(?:visib|coverage|view|visible|list)|not\s+all\s+(?:import\s+)?entries"
    r"|(?:remaining|unseen|unviewed|not[- ]yet[- ](?:seen|visible|viewed))\s+(?:import\s+)?entries"
    r"|(?:entries|imports)\s+(?:are\s+)?(?:not\s+(?:yet\s+)?visible|unseen)|limited\s+(?:import\s+)?visibility"
    r"|visible_entries|incomplete\s+(?:import\s+)?(?:view|coverage|visibility|list)", re.I)
ABSENCE_RE = re.compile(
    r"\bno\s+(?:direct\s+|explicit\s+|clear\s+|standard\s+|specific\s+|obvious\s+|declared\s+|relevant\s+)*"
    r"[\w\-/ ]{0,40}?(?:APIs?|imports?|functions?|calls?)\b"
    r"|\bdoes\s+not\s+(?:import|declare|show|contain|include|reference)\b"
    r"|\bnone\s+of\s+(?:the\s+)?(?:visible\s+|declared\s+|listed\s+)?(?:entries|imports|APIs?)"
    r"|\b(?:lacks?|absence\s+of|absent)\b[^.]{0,60}(?:APIs?|imports?|functions?)", re.I)
SCOPE_RE = re.compile(r"visible|in the (?:entries|page|imports) (?:read|shown|seen)|\bof\s+\d+\b|shown|first\s+\d+"
                      r"|partial|currently|so far|seen|viewed|projection|this page|in view", re.I)
# Limitation statements ("cannot prove the absence of ...") are not absence claims.
LIMITATION_RE = re.compile(r"cannot\s+(?:be\s+)?(?:confirm|prove|determine|rule|establish|verif)|does\s+not\s+prove"
                           r"|not\s+(?:proof|prove)|\bno\s+(?:new\s+|further\s+|additional\s+)?tools?\b", re.I)
SENT_SPLIT = re.compile(r"(?<=[.;!?])\s+")


# --------------------------------------------------------------------------- helpers
def load_manifest(path: Path = HOLDOUT_MANIFEST) -> Dict[str, Dict[str, Any]]:
    man = json.loads(Path(path).read_text(encoding="utf-8"))
    return {c["alias"]: c for c in man["cases"]}


def _imports_evidence(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ok = [e for e in (state or {}).get("evidence", []) if e.get("facet") == FACET and e.get("status") == "SUCCESS"]
    return ok[-1] if ok else None


def _visible_in_turn(turn: Dict[str, Any]) -> Dict[Tuple[str, str], Set[int]]:
    """{evidence_id: visible entry indices} as projected into this turn's prompt."""
    out: Dict[Any, Set[int]] = {}
    for e in ((turn.get("context") or {}).get("facts") or {}).get("evidence", []):
        if e.get("facet") == FACET:
            out[e["evidence_id"]] = {x.get("entry_index") for x in (e.get("value") or {}).get("entries", [])
                                     if isinstance(x, dict)}
    return out


def _visible_keys(turn: Dict[str, Any]) -> Set[Tuple[str, str]]:
    keys = set()
    for e in ((turn.get("context") or {}).get("facts") or {}).get("evidence", []):
        if e.get("facet") == FACET:
            keys |= {entry_key(x) for x in (e.get("value") or {}).get("entries", []) if isinstance(x, dict)}
    return keys


def _final_texts(r: Dict[str, Any]) -> List[str]:
    a = ((r.get("final") or {}).get("assessment")) or {}
    texts = [a.get("explanation") or ""] + [c.get("text") or "" for c in a.get("claims", [])]
    texts += [(r.get("final") or {}).get(k) or "" for k in ("reason", "change_explanation", "stop_reason")]
    return [t for t in texts if t]


def _model_texts(r: Dict[str, Any]) -> List[str]:
    out = list(_final_texts(r))
    for t in r.get("turns", []):
        out.append(((t.get("proposal") or {}).get("reason")) or "")
        m = t.get("meta") or {}
        out += [m.get("analysis") or "", m.get("thinking") or ""]
    return [x for x in out if x]


def _actions(r):
    return [(t.get("proposal") or {}).get("action") for t in r.get("turns", [])]


# --------------------------------------------------------------------------- per-run
def run_row(r: Dict[str, Any], case: Dict[str, Any], num_ctx: int) -> Dict[str, Any]:
    cls = case.get("accessibility_class")
    literals = load_relevant(case.get("reference_EVALUATOR_ONLY"))
    rel_keys = {parse_literal(x) for x in literals}
    turns = r.get("turns", [])
    final_present = r.get("final") is not None
    ev = _imports_evidence(r.get("final_state") or {})
    committed = (ev.get("value") or {}).get("entries", []) if ev else []
    rel_committed = {i for i, e in enumerate(committed) if entry_key(e) in rel_keys}

    seen_keys = set().union(*[_visible_keys(t) for t in turns]) if turns else set()
    m1 = bool(rel_keys & seen_keys)
    resolved = ((r.get("trusted_metadata") or {}).get("resolved_import_refs")) or []
    cited = sorted({x["resolved_import"] for x in resolved
                    if (str(x.get("library") or "").lower(),
                        x["symbol"] if x.get("symbol") is not None else "#" + str(x.get("ordinal"))) in rel_keys})
    actions = _actions(r)
    tool_proposed = "TOOL_CALL" in actions
    reads = [t for t in turns if t.get("retrieved_page")]
    targeted = [t["retrieved_page"]["offset"] for t in reads
                if any(entry_key(x) in rel_keys for x in t["retrieved_page"]["entries"])]
    read_offsets = [t["retrieved_page"]["offset"] for t in reads]

    # M3b: FINISH selected with <2 reads while a committed relevant entry was not yet visible.
    stopped_with_gap, reads_so_far = False, 0
    for t in turns:
        if t.get("finalization_selected"):
            vis = set().union(*_visible_in_turn(t).values()) if _visible_in_turn(t) else set()
            if reads_so_far < 2 and rel_committed and (rel_committed - vis):
                stopped_with_gap = True
            break
        if t.get("retrieved_page"):
            reads_so_far += 1

    # M3c: self-acknowledged partial visibility while read budget remained.
    texts = _model_texts(r)
    ack = [m.group(0) for x in texts for m in PARTIAL_RE.finditer(x)]
    last_vis = set().union(*_visible_in_turn(turns[-1]).values()) if turns and _visible_in_turn(turns[-1]) else set()
    budget_left = bool(ev) and (r.get("retrieval_attempts") or 0) < 2 and len(last_vis) < len(committed)
    m3c = final_present and bool(ack) and budget_left

    # M4: absence screen on final text, against the full evaluator-only relevant list.
    absence = []
    if final_present:
        for text in _final_texts(r):
            for sent in SENT_SPLIT.split(text):
                if ABSENCE_RE.search(sent) and not LIMITATION_RE.search(sent):
                    absence.append({"sentence": sent.strip(), "scope": "SCOPED" if SCOPE_RE.search(sent) else "UNSCOPED"})
    flags = list(((r.get("verification") or {}).get("flags")) or [])
    metas = [t.get("meta") or {} for t in turns]
    overflow = [i + 1 for i, m in enumerate(metas)
                if (m.get("prompt_eval_count") or 0) + (m.get("eval_count") or 0) >= 0.95 * num_ctx]
    return {
        "alias": r.get("alias"), "class": cls, "status": r.get("status"), "failure": r.get("failure"),
        "final_present": final_present, "relevant_literals": literals,
        "relevant_committed_indices": sorted(rel_committed),
        "M1_relevant_seen": m1, "M1b_relevant_cited": bool(cited), "M1b_cited_literals": cited,
        "M2_tool_proposed": tool_proposed, "M3a_targeted_read": bool(targeted), "read_offsets": read_offsets,
        "M3b_stopped_with_gap": stopped_with_gap,
        "M3c_self_acknowledged_gap": m3c, "M3c_matches": ack[:8], "M3c_label": "REGEX_APPROX",
        "M4_absence_sentences": absence, "M4_unscoped": any(a["scope"] == "UNSCOPED" for a in absence),
        "M4_scoped": any(a["scope"] == "SCOPED" for a in absence), "M4_label": "RULE_SCREEN_CANDIDATE",
        "M5_prediction_in_support": "prediction_used_as_own_corroboration" in flags,
        "llm_calls": len(turns), "latency_s": r.get("latency_s"),
        "prompt_tokens": sum(m.get("prompt_eval_count") or 0 for m in metas),
        "output_tokens": sum(m.get("eval_count") or 0 for m in metas),
        "thinking_chars": sum(m.get("thinking_chars") or 0 for m in metas),
        "analysis_chars": sum(m.get("analysis_chars") or 0 for m in metas),
        "validation_errors": [t.get("validation_error") for t in turns if t.get("validation_error")],
        "done_reason_length": sum(m.get("done_reason") == "length" for m in metas),
        "analysis_first": [m.get("analysis_first") for m in metas if "analysis_first" in m],
        "analysis_parse": [m.get("analysis_parse") for m in metas if "analysis_parse" in m],
        "overflow_turns": overflow, "actions": actions,
        "isolation_passed": (r.get("isolation_checks") or {}).get("passed"),
        "pipeline": pipeline_metrics.run_metrics(r) if "turns" in r else None,
    }


# --------------------------------------------------------------------------- aggregate
def _frac(rows, key, classes):
    den = [x for x in rows if x["class"] in classes]
    return {"n": sum(bool(x[key]) for x in den), "d": len(den), "aliases": sorted(x["alias"] for x in den if x[key])}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    finals = [x for x in rows if x["final_present"]]
    with_rel = [x for x in finals if x["relevant_literals"]]
    lat = [x["latency_s"] for x in rows if x["latency_s"] is not None]
    statuses = defaultdict(int)
    for x in rows:
        statuses[x["status"]] += 1
    af = [a for x in rows for a in x["analysis_first"]]
    return {
        "n_runs": len(rows),
        "M1_relevant_seen": _frac(rows, "M1_relevant_seen", (IN_INITIAL, REACHABLE)),
        "M1b_relevant_cited": _frac(rows, "M1b_relevant_cited", (IN_INITIAL, REACHABLE)),
        "M2_unnecessary_tool": _frac(rows, "M2_tool_proposed", (SUFFICIENT, NOT_STATIC)),
        "M2_tool_proposed_all": _frac(rows, "M2_tool_proposed", CLASSES),
        "M3a_targeted_read": _frac(rows, "M3a_targeted_read", (REACHABLE,)),
        "M3b_stopped_with_gap": _frac(rows, "M3b_stopped_with_gap", (REACHABLE,)),
        "M3c_self_acknowledged_gap": {"n": sum(x["M3c_self_acknowledged_gap"] for x in finals), "d": len(finals),
                                      "label": "REGEX_APPROX"},
        "M4_absence_unscoped": {"n": sum(x["M4_unscoped"] for x in with_rel), "d": len(with_rel),
                                "label": "RULE_SCREEN_CANDIDATE"},
        "M4_absence_scoped": {"n": sum(x["M4_scoped"] for x in with_rel), "d": len(with_rel),
                              "label": "RULE_SCREEN_CANDIDATE"},
        "M5_prediction_in_support": {"n": sum(x["M5_prediction_in_support"] for x in finals), "d": len(finals)},
        "M6_cost": {"llm_calls": sum(x["llm_calls"] for x in rows),
                    "latency_mean_s": round(mean(lat), 2) if lat else None,
                    "latency_median_s": round(median(lat), 2) if lat else None,
                    "prompt_tokens": sum(x["prompt_tokens"] for x in rows),
                    "output_tokens": sum(x["output_tokens"] for x in rows),
                    "thinking_chars": sum(x["thinking_chars"] for x in rows),
                    "analysis_chars": sum(x["analysis_chars"] for x in rows)},
        "M7_integrity": {"status_counts": dict(statuses), "final_present": len(finals),
                         "failures": sorted(str(x["failure"]) for x in rows if x["failure"]),
                         "runs_with_validation_error": sum(bool(x["validation_errors"]) for x in rows),
                         "runs_with_done_reason_length": sum(x["done_reason_length"] > 0 for x in rows),
                         "runs_with_overflow_risk": sum(bool(x["overflow_turns"]) for x in rows),
                         "analysis_first_turns": {"true": sum(a is True for a in af), "total": len(af)},
                         "isolation_failed": sum(x["isolation_passed"] is False for x in rows)},
        "per_class": {c: {"n_runs": sum(x["class"] == c for x in rows),
                          "final_present": sum(x["final_present"] for x in rows if x["class"] == c),
                          "tool_proposed": sum(x["M2_tool_proposed"] for x in rows if x["class"] == c),
                          "relevant_seen": sum(x["M1_relevant_seen"] for x in rows if x["class"] == c),
                          "relevant_cited": sum(x["M1b_relevant_cited"] for x in rows if x["class"] == c),
                          "reads": sum(len(x["read_offsets"]) for x in rows if x["class"] == c)}
                      for c in CLASSES},
    }


KEY_METRICS = ("M1_relevant_seen", "M1b_relevant_cited", "M2_unnecessary_tool", "M3a_targeted_read",
               "M3b_stopped_with_gap", "M3c_self_acknowledged_gap", "M4_absence_unscoped", "M5_prediction_in_support")


def deltas(a: Dict[str, Any], b: Dict[str, Any], aliases: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    return {k: {"a": a[k]["n"], "b": b[k]["n"], "d_a": a[k]["d"], "d_b": b[k]["d"], "abs_diff": abs(a[k]["n"] - b[k]["n"])}
            for k in KEY_METRICS}


def collect(results: Path, manifest: Dict[str, Dict[str, Any]], baseline: Optional[Path] = None) -> Dict[str, Any]:
    groups: Dict[str, Dict[str, Any]] = {}
    dirs = sorted(p for p in results.iterdir() if p.is_dir() and (p / "variant.json").exists())
    for d in dirs:
        v = json.loads((d / "variant.json").read_text(encoding="utf-8"))
        if v.get("smoke"):
            continue
        rows = []
        for alias in v["cohort_aliases"]:
            p = d / f"{alias}_C.json"
            if not p.exists():
                rows.append({"alias": alias, "missing": True})
                continue
            r = json.loads(p.read_text(encoding="utf-8"))
            if manifest[alias]["sha256"] != r["initial_state"]["target_ref"]["verified_digest"]["value"]:
                raise ValueError(f"MANIFEST_SHA_MISMATCH {alias}")
            rows.append(run_row(r, manifest[alias], v["decoding"]["num_ctx"]))
        missing = [x["alias"] for x in rows if x.get("missing")]
        rows = [x for x in rows if not x.get("missing")]
        groups[d.name] = {"variant": v["variant"], "seed": v["seed"], "dir": d.name, "missing_runs": missing,
                          "summary": summarize(rows), "rows": rows}
    if baseline is not None:
        rows = []
        for alias, case in sorted(manifest.items()):
            r = json.loads((baseline / f"{alias}_C.json").read_text(encoding="utf-8"))
            rows.append(run_row(r, case, 8192))
        groups["06BJ_run_v1_C"] = {"variant": "06BJ_run_v1", "seed": 42, "dir": str(baseline), "missing_runs": [],
                                   "summary": summarize(rows), "rows": rows,
                                   "note": "frozen 06B-J confirmatory arm C (same config as V0 s42); read-only"}
    noise = {}
    if "V0_s42" in groups and "V0_s7" in groups:
        noise["V0_s42_vs_V0_s7"] = deltas(groups["V0_s42"]["summary"], groups["V0_s7"]["summary"])
    for g in ("V0_s42", "V0_s7"):
        if g in groups and "06BJ_run_v1_C" in groups:
            noise[f"{g}_vs_06BJ_run_v1"] = deltas(groups[g]["summary"], groups["06BJ_run_v1_C"]["summary"])
    return {"kind": "DETERMINISTIC_METRICS_NOT_SEMANTIC", "evaluation_kind": "DEV_DIAGNOSTIC",
            "metrics_version": METRICS_VERSION, "groups": groups, "noise": noise}


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 07A deterministic metrics M1-M7")
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--baseline", type=Path, default=None, help="frozen 06B-J run dir (read-only)")
    a = ap.parse_args(argv)
    if a.out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {a.out}")
    doc = collect(a.results, load_manifest(), a.baseline)
    a.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({g: {k: (v["summary"][k] if k in v["summary"] else None) for k in KEY_METRICS}
                      for g, v in doc["groups"].items()}, indent=1))


if __name__ == "__main__":
    main()
