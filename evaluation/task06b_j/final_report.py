"""TASK 06B-J final confirmatory report (post-lock aggregation only; no new metrics, no grading).

Primary (owner CONDITIONAL GO): claim-level verdicts, R2, R3, R4, R6, R7, deterministic metrics.
Exploratory: R1, R5, R8, R9, Judge-assigned evidence_access.
The two Judge passes are the same model family: pass agreement is self-consistency, not accuracy.
Every number is labelled LLM_JUDGE_PROVISIONAL (human_verified=false) or DETERMINISTIC.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from evaluation.task06b_j.analysis import analyze

PRIMARY = ("R2_evidence_traceability", "R3_tool_decision_quality", "R4_new_evidence_relevance",
           "R6_incremental_value", "R7_uncertainty_limitations")
EXPLORATORY = ("R1_factual_support", "R5_new_evidence_consumption", "R8_decision_quality_safety",
               "R9_next_step_planning")


def build(lock: Path, packages: List[Path], det_summary: Path) -> Dict[str, Any]:
    rep = analyze(lock, [p / "EVALUATOR_ONLY/mapping.json" for p in packages])
    det = json.loads(det_summary.read_text(encoding="utf-8"))
    per_pass: Dict[str, Dict[str, Any]] = {}
    for key, ev in rep["evaluators"].items():
        p = "P1" if "P1" in key else "P2"
        slot = per_pass.setdefault(p, {"per_arm": {}, "paired": {}, "claims": {}, "tags": {}})
        for arm, crits in ev["per_arm"].items():
            slot["per_arm"].setdefault(arm, {}).update(crits)
        slot["paired"].update(ev["paired"])
        for arm, v in ev["claim_verdicts"].items():
            c = Counter(slot["claims"].get(arm, {})); c.update(v); slot["claims"][arm] = dict(c)
        for arm, v in ev["claim_tags"].items():
            c = Counter(slot["tags"].get(arm, {})); c.update(v); slot["tags"][arm] = dict(c)
    consistency = {k.split(":")[-1]: v for k, v in rep["agreement"].items()
                   if v["relation"] == "SELF_CONSISTENCY_NOT_CORRECTNESS"}
    return {"status": "LLM_JUDGE_PROVISIONAL (human_verified=false); deterministic metrics separate",
            "primary": PRIMARY, "exploratory": EXPLORATORY, "per_pass": per_pass,
            "self_consistency": consistency, "deterministic": {"by_arm": det["by_arm"], "by_class": det["by_class"]},
            "checker_vs_judge_semantic_self_corroboration": rep["checker_vs_evaluator"]}


def markdown(doc: Dict[str, Any]) -> str:
    L = ["# TASK 06B-J — Confirmatory results (auto-generated, post-lock)", "",
         f"Status: {doc['status']}. Exploratory criteria are reported but are NOT primary outcomes.", ""]
    for p, slot in sorted(doc["per_pass"].items()):
        L += [f"## Judge {p}: criterion means by arm (assessable only; NA/NOT_ASSESSABLE counted, never imputed)", "",
              "| Criterion | Role | " + " | ".join(sorted(slot["per_arm"])) + " |",
              "|---|---|" + "---|" * len(slot["per_arm"])]
        crits = sorted({c for a in slot["per_arm"].values() for c in a})
        for c in crits:
            role = "PRIMARY" if c in doc["primary"] else "EXPLORATORY"
            cells = []
            for arm in sorted(slot["per_arm"]):
                v = slot["per_arm"][arm].get(c)
                cells.append("—" if v is None else f"{v['mean']} (n={v['n_assessable']}, NA={v['NA']}, NX={v['NOT_ASSESSABLE']})")
            L.append(f"| {c} | {role} | " + " | ".join(cells) + " |")
        L += ["", f"### {p}: paired differences (same sample)", "", "| Pair:criterion | n | mean diff | W/T/L | bootstrap95 |",
              "|---|---|---|---|---|"]
        for k, v in sorted(slot["paired"].items()):
            L.append(f"| {k} | {v['n_pairs']} | {v['mean_diff']} | {v['wins']}/{v['ties']}/{v['losses']} | {v['bootstrap95']} |")
        L += ["", f"### {p}: claim-level verdicts (PRIMARY)", "", "| Arm | verdict counts |", "|---|---|"]
        for arm, v in sorted(slot["claims"].items()):
            L.append(f"| {arm} | {json.dumps(v)} |")
        L.append("")
    L += ["## Self-consistency P1 vs P2 (not accuracy)", "", "| Criterion | n | exact agreement | kappa |", "|---|---|---|---|"]
    for c, v in sorted(doc["self_consistency"].items()):
        L.append(f"| {c} | {v['n']} | {v['percent_agreement']} | {v['cohen_kappa']} |")
    L += ["", "## Deterministic pipeline metrics by arm (DETERMINISTIC, not semantic)", "", "```json",
          json.dumps(doc["deterministic"]["by_arm"], indent=1), "```", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", type=Path, required=True)
    ap.add_argument("--package", type=Path, nargs="+", required=True)
    ap.add_argument("--deterministic", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {a.out}")
    doc = build(a.lock, a.package, a.deterministic)
    a.out.mkdir(parents=True)
    (a.out / "final_results.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    (a.out / "FINAL_RESULTS.md").write_text(markdown(doc), encoding="utf-8")
    print(f"wrote {a.out}")
