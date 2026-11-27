"""TASK 07A SUPPLEMENTARY (post-freeze, owner-approved deviation 2026-11-27). NOT a frozen metric.

Why this file exists: the frozen `metrics.py` (`task07a-metrics-v1`) drops cases that have no
trace, so it cannot report fixed denominators for V1 s42 (7 traces + 1 INFRA_INTERRUPTED + 12
NOT_RUN) or for the never-run directories. `metrics.py` is NOT modified. This script only:

  1. classifies EVERY cohort slot of every result directory into an explicit run status
     (COMPLETED_FINAL / MODEL_INCOMPLETE / MODEL_OUTPUT_TRUNCATION / INFRA_OLLAMA_ERROR /
     INFRA_INTERRUPTED / NOT_RUN / NOT_RUN_BLOCKED), so no slot disappears from a denominator;
  2. for V1 s42 reports status, truncation, turn-1 action, cost and thinking_chars, plus the
     frozen `metrics.run_row` behaviour fields on the 7 existing traces labelled EXPLORATORY.

Deterministic counts from frozen traces; not semantic grading. Write-once output.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List

import case_manager as cm
from evaluation.task07a import metrics

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evaluation/task07a/results"
VERSION = "task07a-supplementary-v1"
THINK_RE = re.compile(r"thinking_chars=(\d+), done_reason=(\w+), eval_count=(\d+)")
# Owner-declared statuses for slots with no trace (EVALUATION_LOG 2026-11-27).
DECLARED = {"V1_s42": {"sample_0008": "INFRA_INTERRUPTED"}}
DIR_NOTES = {"V2_s7": "NOT_RUN_BLOCKED: freeze recorded ollama UNAVAILABLE; replaced by V2_s7_r2",
             "V1_s42": "PARTIAL by owner decision: 7 traces + 1 INFRA_INTERRUPTED + 12 NOT_RUN",
             "V1_s7": "NOT_RUN by owner decision (directory never prepared)"}


def classify(r: Dict[str, Any]) -> str:
    failure = str(r.get("failure") or "")
    if r.get("final") is not None:
        return "COMPLETED_FINAL"
    if failure.startswith("Ollama inference failed:"):
        return "INFRA_OLLAMA_ERROR"
    if failure.startswith("Ollama returned empty content") or any(
            (t.get("meta") or {}).get("done_reason") == "length" for t in r.get("turns", [])):
        return "MODEL_OUTPUT_TRUNCATION"
    if r.get("status") == "HARNESS_EXCEPTION":
        return "HARNESS_EXCEPTION"
    return "MODEL_INCOMPLETE"


def slot_status(d: Path, alias: str, freeze: Dict[str, Any]) -> Dict[str, Any]:
    p = d / f"{alias}_C.json"
    if p.exists():
        r = json.loads(p.read_text(encoding="utf-8"))
        return {"alias": alias, "run_status": classify(r), "workflow_status": r.get("status"),
                "failure": r.get("failure")}
    if freeze.get("ollama", {}).get("status") != "AVAILABLE":
        return {"alias": alias, "run_status": "NOT_RUN_BLOCKED", "workflow_status": None, "failure": None}
    declared = DECLARED.get(d.name, {}).get(alias)
    evidence = None
    try:
        row = next(x for x in json.loads((d / "cases.json").read_text(encoding="utf-8")) if x["alias"] == alias)
        state = cm.read_json(Path(row["case_paths"]["C"]))
        init = json.loads((d / row["initial_file"]).read_text(encoding="utf-8"))
        evidence = {"casestate_revision": state["revision"], "initial_revision": init["revision"]}
    except Exception as exc:  # runtime home may be absent on another machine
        evidence = {"error": f"{type(exc).__name__}"}
    status = declared or ("INFRA_INTERRUPTED" if evidence.get("casestate_revision", 0) != evidence.get("initial_revision", 0)
                          else "NOT_RUN")
    return {"alias": alias, "run_status": status, "workflow_status": None, "failure": None, "casestate": evidence}


def v1_detail(d: Path, manifest: Dict[str, Dict[str, Any]], num_ctx: int) -> Dict[str, Any]:
    rows, explo = [], []
    for p in sorted(d.glob("*_C.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        turns = r.get("turns", [])
        metas = [t.get("meta") or {} for t in turns]
        trunc = THINK_RE.search(str(r.get("failure") or ""))
        lost_thinking = int(trunc.group(1)) if trunc else 0
        rows.append({
            "alias": r["alias"], "class": manifest[r["alias"]].get("accessibility_class"),
            "run_status": classify(r), "failure": r.get("failure"), "turns": len(turns),
            "turn1_action": (turns[0].get("proposal") or {}).get("action") if turns else None,
            "truncation_turn": next((t["iteration"] for t in turns if t.get("error", "").startswith(
                "Ollama returned empty content")), None),
            "thinking_chars_recorded": sum(m.get("thinking_chars") or 0 for m in metas),
            "thinking_chars_lost_turn": lost_thinking,
            "thinking_chars_per_turn": [m.get("thinking_chars") for m in metas],
            "prompt_tokens": sum(m.get("prompt_eval_count") or 0 for m in metas),
            "output_tokens": sum(m.get("eval_count") or 0 for m in metas),
            "latency_s": r.get("latency_s")})
        explo.append(metrics.run_row(r, manifest[r["alias"]], num_ctx))
    lat = [x["latency_s"] for x in rows if x["latency_s"] is not None]
    trunc_runs = [x["alias"] for x in rows if x["run_status"] == "MODEL_OUTPUT_TRUNCATION"]
    return {
        "traces": len(rows), "rows": rows,
        "truncation_runs": {"n": len(trunc_runs), "d_traces": len(rows), "aliases": trunc_runs,
                            "integrity_rule": "PROTOCOL §5: truncation > 2 runs -> variant not interpretable"},
        "turn1_tool_call": {"n": sum(x["turn1_action"] == "TOOL_CALL" for x in rows),
                            "d_with_turn1_proposal": sum(x["turn1_action"] is not None for x in rows)},
        "cost": {"llm_calls": sum(x["turns"] for x in rows),
                 "latency_mean_s": round(mean(lat), 1) if lat else None,
                 "latency_median_s": round(median(lat), 1) if lat else None,
                 "thinking_chars_recorded": sum(x["thinking_chars_recorded"] for x in rows),
                 "thinking_chars_in_lost_turns": sum(x["thinking_chars_lost_turn"] for x in rows),
                 "output_tokens_recorded": sum(x["output_tokens"] for x in rows)},
        "EXPLORATORY_behaviour_on_existing_traces": {
            "label": "EXPLORATORY — 7 traces only, denominators are NOT the fixed protocol denominators",
            "summary": metrics.summarize(explo), "rows": explo},
    }


def build(results: Path = RESULTS) -> Dict[str, Any]:
    manifest = metrics.load_manifest()
    cohort_all = sorted(manifest)
    out = {"kind": "SUPPLEMENTARY_DETERMINISTIC_NOT_FROZEN_METRIC", "version": VERSION,
           "evaluation_kind": "DEV_DIAGNOSTIC", "frozen_metrics_file": "results/metrics_v1.json",
           "directories": {}}
    for d in sorted(p for p in results.iterdir() if p.is_dir() and (p / "variant.json").exists()):
        v = json.loads((d / "variant.json").read_text(encoding="utf-8"))
        if v.get("smoke"):
            continue
        freeze = json.loads((d / "freeze.json").read_text(encoding="utf-8"))
        slots = [slot_status(d, a, freeze) for a in v["cohort_aliases"]]
        counts: Dict[str, int] = {}
        for s in slots:
            counts[s["run_status"]] = counts.get(s["run_status"], 0) + 1
        entry = {"variant": v["variant"], "seed": v["seed"], "cohort_slots": len(slots), "status_counts": counts,
                 "slots": slots, "note": DIR_NOTES.get(d.name)}
        if d.name == "V1_s42":
            entry["v1_detail"] = v1_detail(d, manifest, v["decoding"]["num_ctx"])
        out["directories"][d.name] = entry
    out["directories"]["V1_s7"] = {"variant": "V1", "seed": 7, "cohort_slots": len(cohort_all),
                                  "status_counts": {"NOT_RUN": len(cohort_all)}, "note": DIR_NOTES["V1_s7"]}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {a.out}")
    doc = build()
    a.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: {"status_counts": v["status_counts"]} for k, v in doc["directories"].items()}, indent=1))


if __name__ == "__main__":
    main()
