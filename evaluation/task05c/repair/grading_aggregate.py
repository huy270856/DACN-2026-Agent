"""Aggregate human semantic grades after the blind forms are filled.

Reads the v2 blind forms + the evaluator-only X/Y->branch mapping, maps each
filled score back to its branch, and reports per-branch per-criterion means.
Until a human fills scores, every criterion reports CHƯA CHẤM. Never fills or
estimates scores; never uses an LLM as judge.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict

CRITERIA = ["A2_claims_supported", "B1_score_vs_truth_distinction",
            "B2_no_feature_importance_from_score", "C1_uncertainty",
            "D1_recommendation_appropriate"]


def aggregate(forms_path: Path, mapping_path: Path) -> Dict[str, Any]:
    data = json.loads(forms_path.read_text(encoding="utf-8"))
    forms = data["forms"]
    mapping = {m["sample_id"]: m for m in json.loads(mapping_path.read_text(encoding="utf-8"))}

    collected = {"STATIC_ONLY": {c: [] for c in CRITERIA},
                 "STATIC_PLUS_AGENT": {c: [] for c in CRITERIA}}
    n_filled = 0
    n_total = 0
    for form in forms:
        sid = form["sample_id"]
        m = mapping.get(sid, {})
        label_to_branch = {"X": m.get("X_is"), "Y": m.get("Y_is")}
        for label, scores in form["scores_to_fill"].items():
            n_total += 1
            branch = label_to_branch.get(label)
            if branch is None:
                continue
            for c in CRITERIA:
                v = scores.get(c)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    collected[branch][c].append(v)
            if all(isinstance(scores.get(c), (int, float)) and not isinstance(scores.get(c), bool)
                   for c in CRITERIA):
                n_filled += 1

    def summarize(branch):
        out = {}
        for c in CRITERIA:
            vals = collected[branch][c]
            out[c] = {"mean": round(mean(vals), 3), "n": len(vals)} if vals else "CHƯA CHẤM"
        return out

    status = "COMPLETE" if n_filled == n_total and n_total > 0 else (
        "PARTIAL" if n_filled > 0 else "CHƯA CHẤM")
    return {
        "schema_version": "grading-aggregate-v1",
        "status": status,
        "forms_total": n_total, "forms_fully_filled": n_filled,
        "per_branch": {b: summarize(b) for b in collected},
        "note": "Semantic scores are HUMAN-entered; this tool only aggregates. "
                "No LLM-as-judge, no auto-fill.",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aggregate human semantic grades")
    ap.add_argument("--forms", required=True)
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    rep = aggregate(Path(args.forms), Path(args.mapping))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    # ensure_ascii=True so a Vietnamese status prints safely on a cp1252 console.
    print(json.dumps({"status": rep["status"], "filled": rep["forms_fully_filled"],
                      "total": rep["forms_total"]}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
