"""Deterministic summary of the confirmatory run (NOT semantic grading; no Judge scores used).

Reads the frozen run directory and the evaluator-only v2 manifest. Every case is in every
denominator (incomplete runs included). Relevant-evidence visibility uses the manifest's
static reference indices (exact-name lexicon) against the entry indices that actually
appeared in the Agent's prompts - a deterministic accessibility fact, not a semantic verdict.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict

from evaluation.task06b_j.pipeline_metrics import run_metrics

IMPORTS_FACET = "static.pe_imports_detail"


def _visible_import_indices(r: Dict[str, Any]) -> set:
    seen = set()
    for t in r.get("turns", []):
        for e in t["context"]["facts"].get("evidence", []):
            if e.get("facet") == IMPORTS_FACET:
                seen |= {x.get("entry_index") for x in (e.get("value") or {}).get("entries", [])}
    return seen


def summarize(run_dir: Path, manifest_path: Path) -> Dict[str, Any]:
    man = {c["alias"]: c for c in json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]}
    rows = []
    for row in json.loads((run_dir / "cases.json").read_text(encoding="utf-8")):
        a = row["alias"]
        c = man[a]
        for arm in ("A", "B", "C"):
            r = json.loads((run_dir / f"{a}_{arm}.json").read_text(encoding="utf-8"))
            m = run_metrics(r)
            out = {"alias": a, "arm": arm, "class": c["question_category"], "family": c["capability_family"], **m}
            if arm != "A":
                out["isolation_passed"] = r["isolation_checks"]["passed"]
                lk = json.loads((run_dir / "EVALUATOR_ONLY" / f"{a}_{arm}_leakage_all_turns.json").read_text(encoding="utf-8"))
                out["leakage_status"] = lk["summary"]["status"]
                out["agent_recommendation"] = ((r.get("final") or {}).get("assessment") or {}).get("recommendation")
                out["structural_self_corroboration"] = "prediction_used_as_own_corroboration" in (m.get("grounding_flags") or [])
                rel = (c["reference_EVALUATOR_ONLY"].get("relevant_indices") or [])
                vis = _visible_import_indices(r)
                out["relevant_indices_reference"] = rel
                out["relevant_seen"] = sorted(set(rel) & vis)
                out["any_relevant_seen"] = bool(set(rel) & vis) if rel else None
                out["target_sha_matches"] = r["initial_state"]["target_ref"]["verified_digest"]["value"] == c["sha256"]
                out["turn_errors"] = [t.get("validation_error") or t.get("error") for t in r.get("turns", [])
                                      if t.get("validation_error") or t.get("error")]
            rows.append(out)

    def agg(sel):
        ag = [x for x in sel if x["arm_kind"] == "AGENT"]
        lat = [x["latency_s"] for x in ag if x.get("latency_s") is not None]
        return {"n": len(sel),
                "final_present": sum(x.get("final_present", False) for x in ag),
                "incomplete": sum(not x.get("final_present", True) for x in ag),
                "finished_clean": sum(x.get("status") == "FINISHED" for x in ag),
                "finished_flagged": sum(x.get("status") == "FINISHED_FLAGGED" for x in ag),
                "tool_proposed": sum(x.get("tool_proposed", False) for x in ag),
                "d4": dict(Counter(o for x in ag for o in x.get("d4_outcomes", []))),
                "d9_commits": sum(x.get("d9_commits", 0) for x in ag),
                "retrieval_reads": sum(x.get("retrieval_reads", 0) for x in ag),
                "cases_with_reads": sum(x.get("retrieval_reads", 0) > 0 for x in ag),
                "repairs": sum(x.get("repairs", 0) for x in ag),
                "llm_calls": sum(x.get("llm_calls", 0) for x in ag),
                "structural_self_corroboration": sum(x.get("structural_self_corroboration", False) for x in ag),
                "effective_action": dict(Counter(x.get("effective_action") for x in ag)),
                "agent_recommendation": dict(Counter(x.get("agent_recommendation") for x in ag)),
                "failures": dict(Counter(x.get("failure") for x in ag if x.get("failure"))),
                "turn_errors": sum(len(x.get("turn_errors", [])) for x in ag),
                "relevant_seen_cases": sum(bool(x.get("any_relevant_seen")) for x in ag),
                "relevant_reference_cases": sum(x.get("any_relevant_seen") is not None for x in ag),
                "latency_mean_s": round(mean(lat), 2) if lat else None,
                "latency_median_s": round(median(lat), 2) if lat else None,
                "prompt_tokens": sum(x.get("prompt_tokens") or 0 for x in ag),
                "output_tokens": sum(x.get("output_tokens") or 0 for x in ag),
                "isolation_failures": sum(x.get("isolation_passed") is False for x in ag),
                "accidental_leak_runs": sum(str(x.get("leakage_status", "")).startswith("FAIL") for x in ag),
                "target_sha_mismatch": sum(x.get("target_sha_matches") is False for x in ag)}

    by_arm = {arm: agg([x for x in rows if x["arm"] == arm]) for arm in ("A", "B", "C")}
    by_class = defaultdict(dict)
    for cls in sorted({x["class"] for x in rows}):
        for arm in ("B", "C"):
            by_class[cls][arm] = agg([x for x in rows if x["class"] == cls and x["arm"] == arm])
    return {"kind": "DETERMINISTIC_CONFIRMATORY_SUMMARY_NOT_SEMANTIC", "semantic_grading": "SEMANTIC_GRADING_PENDING",
            "by_arm": by_arm, "by_class": by_class, "rows": rows}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    doc = summarize(a.run, a.manifest)
    a.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(doc["by_arm"], indent=1))
    for cls, v in doc["by_class"].items():
        print(cls, {arm: {k: v[arm][k] for k in ("n", "final_present", "finished_clean", "tool_proposed", "cases_with_reads",
                                                   "relevant_seen_cases", "relevant_reference_cases", "effective_action")}
                     for arm in v})
