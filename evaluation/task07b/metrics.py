"""TASK 07B deterministic metrics M1-M10 for arms BASE / V4_NOQ / V4. NOT semantic grading.

Inputs: frozen traces `<alias>_<ARM>.json` + the evaluator-only fresh-cohort manifest. Every
metric reports numerator AND denominator per arm x seed and per class. A run without an accepted
final is a FAILURE for every "good" metric (M1b, M8, M9, M10) and is never dropped from a
denominator. Regex screens are labelled RULE_SCREEN_CANDIDATE.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Optional, Set, Tuple

from evaluation.task07a.metrics import ABSENCE_RE, LIMITATION_RE, SCOPE_RE, SENT_SPLIT
from evaluation.task07a.variants import entry_key, load_relevant, parse_literal

METRICS_VERSION = "task07b-metrics-v2"  # v2 (TASK 07C): absence_claims accepted/rejected; v1 unchanged otherwise
RP, RA, NS, IS = "RELEVANT_PRESENT", "RELEVANT_ABSENT", "NOT_STATIC_ANSWERABLE", "INITIAL_EVIDENCE_SUFFICIENT"
CLASSES = (RP, RA, NS, IS)
V3_FACET = "static.pe_imports_detail"
V4_FACET = "static.pe_imports_table"
EMPTY_RE = re.compile(r"Ollama returned empty content")


def _lit_key(literal: str) -> Tuple[str, str]:
    lib, _, sym = literal.partition("!")
    return (lib.lower(), sym)


def _engine(r: Dict[str, Any]) -> str:
    return "v4" if str(r.get("schema_version", "")).startswith("investigation-v4") else "v3.4"


def _final_texts(r: Dict[str, Any]) -> List[str]:
    f = r.get("final") or {}
    if _engine(r) == "v4":
        texts = [f.get("answer") or ""] + [x.get("text") or "" for x in f.get("findings", [])]
    else:
        a = f.get("assessment") or {}
        texts = [a.get("explanation") or ""] + [c.get("text") or "" for c in a.get("claims", [])]
    return [t for t in texts if t]


def _seen_keys(r: Dict[str, Any]) -> Set[Tuple[str, str]]:
    if _engine(r) == "v4":
        return {_lit_key(l) for l in (r.get("trusted_metadata") or {}).get("viewed_literals", {}).values()}
    keys = set()
    for t in r.get("turns", []):
        for e in ((t.get("context") or {}).get("facts") or {}).get("evidence", []):
            if e.get("facet") == V3_FACET:
                keys |= {entry_key(x) for x in (e.get("value") or {}).get("entries", []) if isinstance(x, dict)}
    return keys


def _cited_keys(r: Dict[str, Any]) -> Set[Tuple[str, str]]:
    if r.get("final") is None:
        return set()
    tm = r.get("trusted_metadata") or {}
    if _engine(r) == "v4":
        return {_lit_key(s["literal"]) for s in tm.get("resolved_sources", []) if s.get("literal")}
    return {(str(x.get("library") or "").lower(), x["symbol"] if x.get("symbol") is not None else "#" + str(x.get("ordinal")))
            for x in tm.get("resolved_import_refs", [])}


def _tool_proposed(r: Dict[str, Any]) -> bool:
    acts = [(t.get("proposal") or {}).get("action") for t in r.get("turns", [])]
    return "TOOL_CALL" in acts or "RUN_ANALYZER" in acts


def _query_hit(r: Dict[str, Any], keys) -> Tuple[bool, Optional[int]]:
    n = 0
    for t in r.get("turns", []):
        q = t.get("query_result")
        if t.get("action") in ("QUERY_IMPORTS", "READ_TABLE"):
            n += 1
        if q and any(_lit_key(e["library"] + "!" + (e["symbol"] if e["symbol"] is not None else "#" + str(e["ordinal"])))
                     in keys for e in q["entries"]):
            return True, n
    return False, None


def run_row(r: Dict[str, Any], case: Dict[str, Any], num_ctx: int) -> Dict[str, Any]:
    cls = case["accessibility_class"]
    ref = case.get("reference_EVALUATOR_ONLY") or {}
    keys = {parse_literal(x) for x in load_relevant(ref)}
    final = r.get("final")
    turns = r.get("turns", [])
    metas = [t.get("meta") or {} for t in turns]
    failure = str(r.get("failure") or "")
    trunc = sum(m.get("done_reason") == "length" for m in metas) + sum(
        bool(t.get("error_payload")) or bool(EMPTY_RE.search(str(t.get("error") or ""))) for t in turns)
    seen = bool(keys & _seen_keys(r))
    cited = bool(keys & _cited_keys(r))
    hit, first = _query_hit(r, keys) if _engine(r) == "v4" else (None, None)
    query_mode = _engine(r) == "v4" and r.get("retrieval_mode") == "QUERY"
    qhit, first_q = (hit, first) if query_mode else (None, None)
    read_hit = hit if (_engine(r) == "v4" and not query_mode) else None
    status_ans = (final or {}).get("answer_status") if _engine(r) == "v4" else None
    tool = _tool_proposed(r)
    if cls == NS:
        m9 = final is not None and status_ans in ("NOT_STATICALLY_ANSWERABLE", "PARTIALLY_ANSWERED")
    elif cls == IS:
        m9 = final is not None and status_ans == "ANSWERED" and not tool
    else:
        m9 = None
    absence = []
    for text in _final_texts(r):
        for s in SENT_SPLIT.split(text):
            if ABSENCE_RE.search(s) and not LIMITATION_RE.search(s):
                absence.append({"sentence": s.strip(), "scope": "SCOPED" if SCOPE_RE.search(s) else "UNSCOPED"})
    flags = list(((r.get("verification") or {}).get("flags")) or [])
    return {
        "alias": r.get("alias"), "class": cls, "engine": _engine(r), "status": r.get("status"), "failure": r.get("failure"),
        "final_present": final is not None, "relevant_literals": sorted(load_relevant(ref)),
        "beyond_v3": bool(ref.get("beyond_v3_reach")),
        "M1_relevant_seen": seen, "M1b_relevant_cited": cited,
        "M8_query_hit": qhit, "M8_first_query_hit": first_q,
        "M8_read_hit_reference": read_hit,
        "M2_tool_proposed": tool,
        # Good-direction M2 (owner rule: a broken run never makes a metric look better):
        "M2_correct_no_tool": final is not None and not tool,
        "M4_absence_sentences": absence, "M4_unscoped": any(a["scope"] == "UNSCOPED" for a in absence),
        "M4_scoped": any(a["scope"] == "SCOPED" for a in absence), "M4_label": "RULE_SCREEN_CANDIDATE",
        "M5_structural_self_corroboration": ("prediction_used_as_own_corroboration" in flags) if _engine(r) == "v3.4" else False,
        "M5_note": None if _engine(r) == "v3.4" else "STRUCTURALLY_IMPOSSIBLE (detector has no handle in investigation-v4.0)",
        "M9_answer_status_fit": m9, "answer_status": status_ans,
        "M10_final_present": final is not None,
        "llm_calls": len(turns), "latency_s": r.get("latency_s"),
        "prompt_tokens": sum(m.get("prompt_eval_count") or 0 for m in metas),
        "output_tokens": sum(m.get("eval_count") or 0 for m in metas),
        "max_prompt_tokens": max([m.get("prompt_eval_count") or 0 for m in metas] or [0]),
        "truncations": trunc,
        "overflow": any((m.get("prompt_eval_count") or 0) + (m.get("eval_count") or 0) >= 0.95 * num_ctx for m in metas),
        "infra_error": failure.startswith("Ollama inference failed") or r.get("status") == "HARNESS_EXCEPTION",
        "validation_error_runs": any(t.get("validation_error") for t in turns),
        "verifier_flags": flags, "isolation_passed": (r.get("isolation_checks") or {}).get("passed"),
        "query_attempts": r.get("query_attempts"), "tool_attempts": r.get("tool_attempts"),
        "absence_claims_accepted": len(((r.get("verification") or {}).get("absence_claims") or {}).get("accepted", [])),
        "absence_claims_rejected": len(((r.get("verification") or {}).get("absence_claims") or {}).get("rejected", [])),
        "free_text_absence_rejected": len(((r.get("verification") or {}).get("absence_claims") or {}).get("free_text_absence_rejected", [])),
    }


def missing_row(alias: str, case: Dict[str, Any], engine: str, retrieval_mode: Optional[str]) -> Dict[str, Any]:
    """A cohort slot with NO trace (interrupted / not run). Kept in every denominator as a failure."""
    ref = case.get("reference_EVALUATOR_ONLY") or {}
    query_mode = engine == "v4" and retrieval_mode == "QUERY"
    return {"alias": alias, "class": case["accessibility_class"], "engine": engine, "status": "MISSING_TRACE",
            "failure": "NO_TRACE_IN_RUN_DIRECTORY", "final_present": False,
            "relevant_literals": sorted(load_relevant(ref)), "beyond_v3": bool(ref.get("beyond_v3_reach")),
            "M1_relevant_seen": False, "M1b_relevant_cited": False,
            "M8_query_hit": False if query_mode else None, "M8_first_query_hit": None,
            "M8_read_hit_reference": False if (engine == "v4" and not query_mode) else None,
            "M2_tool_proposed": False, "M2_correct_no_tool": False, "M4_absence_sentences": [], "M4_unscoped": False, "M4_scoped": False,
            "M4_label": "RULE_SCREEN_CANDIDATE", "M5_structural_self_corroboration": False, "M5_note": "NO_TRACE",
            "M9_answer_status_fit": False if case["accessibility_class"] in (NS, IS) else None, "answer_status": None,
            "M10_final_present": False, "llm_calls": 0, "latency_s": None, "prompt_tokens": 0, "output_tokens": 0,
            "max_prompt_tokens": 0, "truncations": 0, "overflow": False, "infra_error": True,
            "validation_error_runs": False, "verifier_flags": [], "isolation_passed": None,
            "query_attempts": None, "tool_attempts": None, "missing_trace": True}


def _rate(n: int, d: int) -> Dict[str, Any]:
    """M4 is compared by RATE n/d (denominators differ across arms); n and d are always reported."""
    return {"n": n, "d": d, "rate": round(n / d, 4) if d else None, "label": "RULE_SCREEN_CANDIDATE"}


def _frac(rows, key, classes, subset=None):
    den = [x for x in rows if x["class"] in classes and (subset is None or subset(x))]
    return {"n": sum(bool(x[key]) for x in den), "d": len(den), "aliases": sorted(x["alias"] for x in den if x[key])}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    finals = [x for x in rows if x["final_present"]]
    lat = [x["latency_s"] for x in rows if x["latency_s"] is not None]
    st: Dict[str, int] = {}
    for x in rows:
        st[str(x["status"])] = st.get(str(x["status"]), 0) + 1
    v4 = bool(rows) and rows[0]["engine"] == "v4"
    query_mode = v4 and any(x["M8_query_hit"] is not None for x in rows)
    return {
        "n_runs": len(rows),
        "M1_relevant_seen": _frac(rows, "M1_relevant_seen", (RP,)),
        "M1_relevant_seen_beyond_v3": _frac(rows, "M1_relevant_seen", (RP,), lambda x: x["beyond_v3"]),
        "M1b_relevant_cited": _frac(rows, "M1b_relevant_cited", (RP,)),
        "M1b_relevant_cited_beyond_v3": _frac(rows, "M1b_relevant_cited", (RP,), lambda x: x["beyond_v3"]),
        "M1_relevant_seen_within_v3": _frac(rows, "M1_relevant_seen", (RP,), lambda x: not x["beyond_v3"]),
        "M1b_relevant_cited_within_v3": _frac(rows, "M1b_relevant_cited", (RP,), lambda x: not x["beyond_v3"]),
        "M8_query_hit": _frac(rows, "M8_query_hit", (RP,)) if query_mode else "NOT_APPLICABLE",
        "M8_read_hit_reference": (_frac(rows, "M8_read_hit_reference", (RP,)) if (v4 and not query_mode)
                                  else "NOT_APPLICABLE"),
        "M2_unnecessary_tool": _frac(rows, "M2_tool_proposed", (IS, NS)),
        "M2_correct_no_tool": _frac(rows, "M2_correct_no_tool", (IS, NS)),
        "M2_correct_no_tool_initial_sufficient": _frac(rows, "M2_correct_no_tool", (IS,)),
        "M2_broken_runs": sum(not x["final_present"] for x in rows if x["class"] in (IS, NS)),
        "M2_tool_initial_sufficient": _frac(rows, "M2_tool_proposed", (IS,)),
        "M4_absence_unscoped": _rate(sum(x["M4_unscoped"] for x in finals), len(finals)),
        "M4_absence_scoped": _rate(sum(x["M4_scoped"] for x in finals), len(finals)),
        "M5_structural_self_corroboration": {"n": sum(x["M5_structural_self_corroboration"] for x in finals),
                                             "d": len(finals),
                                             "note": "v4: structurally impossible; not a behavioural improvement" if v4 else None},
        "M9_answer_status_fit": _frac(rows, "M9_answer_status_fit", (NS, IS)) if v4 else "NOT_APPLICABLE (v3.4 has no answer_status)",
        "M10_final_present": {"n": len(finals), "d": len(rows)},
        "absence_claims": {"accepted": sum(x.get("absence_claims_accepted", 0) for x in rows),
                           "rejected": sum(x.get("absence_claims_rejected", 0) for x in rows),
                           "free_text_rejected": sum(x.get("free_text_absence_rejected", 0) for x in rows),
                           "runs_with_rejection": sum((x.get("absence_claims_rejected", 0) + x.get("free_text_absence_rejected", 0)) > 0 for x in rows)},
        "M6_cost": {"llm_calls": sum(x["llm_calls"] for x in rows),
                    "latency_mean_s": round(mean(lat), 2) if lat else None,
                    "latency_median_s": round(median(lat), 2) if lat else None,
                    "prompt_tokens": sum(x["prompt_tokens"] for x in rows),
                    "output_tokens": sum(x["output_tokens"] for x in rows),
                    "max_prompt_tokens": max([x["max_prompt_tokens"] for x in rows] or [0])},
        "M7_integrity": {"status_counts": st, "runs_with_truncation": sum(x["truncations"] > 0 for x in rows),
                         "runs_with_overflow": sum(x["overflow"] for x in rows),
                         "infra_errors": sum(x["infra_error"] for x in rows),
                         "missing_traces": sum(bool(x.get("missing_trace")) for x in rows),
                         "runs_with_validation_error": sum(x["validation_error_runs"] for x in rows),
                         "isolation_failed": sum(x["isolation_passed"] is False for x in rows)},
        "per_class": {c: {"n_runs": sum(x["class"] == c for x in rows),
                          "final_present": sum(x["final_present"] for x in rows if x["class"] == c),
                          "tool_proposed": sum(x["M2_tool_proposed"] for x in rows if x["class"] == c),
                          "relevant_seen": sum(x["M1_relevant_seen"] for x in rows if x["class"] == c),
                          "relevant_cited": sum(x["M1b_relevant_cited"] for x in rows if x["class"] == c)}
                      for c in CLASSES},
    }


KEY = ("M1_relevant_seen", "M1b_relevant_cited", "M1b_relevant_cited_beyond_v3", "M1b_relevant_cited_within_v3",
       "M1_relevant_seen_beyond_v3", "M1_relevant_seen_within_v3", "M2_unnecessary_tool", "M2_correct_no_tool",
       "M4_absence_unscoped", "M10_final_present")


def _n(summary, k):
    v = summary.get(k)
    return v["n"] if isinstance(v, dict) else None


RATE_KEYS = ("M4_absence_unscoped", "M4_absence_scoped")


def latency_ratios(groups: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """V4/BASE and V4_NOQ/BASE median-latency ratios per seed (decision rule: <= 3 in BOTH seeds)."""
    out = {}
    for seed in (42, 7):
        base = groups.get(f"BASE_s{seed}")
        for arm in ("V4", "V4_NOQ"):
            g = groups.get(f"{arm}_s{seed}")
            if base and g:
                b, x = base["summary"]["M6_cost"]["latency_median_s"], g["summary"]["M6_cost"]["latency_median_s"]
                out[f"{arm}/BASE_s{seed}"] = round(x / b, 3) if b and x is not None else None
    return out


def noise(groups: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    out = {}
    for arm in ("BASE", "V4_NOQ", "V4", "V4_1"):
        a, b = groups.get(f"{arm}_s42"), groups.get(f"{arm}_s7")
        if a and b:
            ks = KEY + {"BASE": (), "V4_NOQ": ("M8_read_hit_reference", "M9_answer_status_fit"),
                        "V4": ("M8_query_hit", "M9_answer_status_fit"),
                        "V4_1": ("M8_query_hit", "M9_answer_status_fit")}[arm]
            out[arm] = {k: abs((_n(a["summary"], k) or 0) - (_n(b["summary"], k) or 0)) for k in ks
                        if k not in RATE_KEYS}
            for k in RATE_KEYS:  # M4: noise = |rate_s42 - rate_s7| (owner, 2026-11-27)
                ra, rb = a["summary"][k].get("rate"), b["summary"][k].get("rate")
                out[arm][k + "_rate"] = round(abs(ra - rb), 4) if ra is not None and rb is not None else None
            la, lb = a["summary"]["M6_cost"]["latency_median_s"], b["summary"]["M6_cost"]["latency_median_s"]
            out[arm]["latency_median_s"] = {"s42": la, "s7": lb}
    return out


def collect(results: Path, manifest_path: Path) -> Dict[str, Any]:
    man = {c["alias"]: c for c in json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]}
    groups = {}
    for d in sorted(p for p in results.iterdir() if p.is_dir() and (p / "arm.json").exists()):
        a = json.loads((d / "arm.json").read_text(encoding="utf-8"))
        rows, missing = [], []
        for alias in a["cohort_aliases"]:
            p = d / f"{alias}_{a['arm']}.json"
            if not p.exists():
                missing.append(alias)
                rows.append(missing_row(alias, man[alias], "v3.4" if a["engine"] == "v3.4" else "v4",
                                        (a.get("v4_config") or {}).get("retrieval_mode")))
                continue
            r = json.loads(p.read_text(encoding="utf-8"))
            if man[alias]["sha256"] != r["initial_state"]["target_ref"]["verified_digest"]["value"]:
                raise ValueError(f"MANIFEST_SHA_MISMATCH {alias}")
            rows.append(run_row(r, man[alias], a["decoding"]["num_ctx"]))
        groups[d.name] = {"arm": a["arm"], "seed": a["seed"], "missing_runs": missing,
                          "summary": summarize(rows), "rows": rows}
    return {"kind": "DETERMINISTIC_METRICS_NOT_SEMANTIC", "metrics_version": METRICS_VERSION,
            "evaluation_kind": "DEV_EVALUATION_FRESH_COHORT", "groups": groups, "noise": noise(groups),
            "latency_median_ratio": latency_ratios(groups)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 07B deterministic metrics")
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    x = ap.parse_args(argv)
    if x.out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {x.out}")
    doc = collect(x.results, x.manifest)
    x.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({g: {k: v["summary"][k] for k in ("M1b_relevant_cited", "M10_final_present")}
                      for g, v in doc["groups"].items()}, indent=1))


if __name__ == "__main__":
    main()
