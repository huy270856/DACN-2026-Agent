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


VALID_SCORES = (0, 1, 2)


def _valid_score(v) -> bool:
    """Accept ONLY integer 0/1/2. Reject bool, non-integer float, out-of-range,
    strings (including 'CHƯA CHẤM')."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return v in VALID_SCORES
    if isinstance(v, float):
        return v.is_integer() and int(v) in VALID_SCORES  # 2.0 ok, 1.5 rejected
    return False


def aggregate(forms_path: Path, mapping_path: Path) -> Dict[str, Any]:
    data = json.loads(forms_path.read_text(encoding="utf-8"))
    forms = data["forms"]
    mapping_list = json.loads(mapping_path.read_text(encoding="utf-8"))

    errors: List[str] = []

    # --- mapping integrity (duplicates / missing / extra) ---
    form_ids = [f.get("sample_id") for f in forms]
    dup_form_ids = sorted({i for i in form_ids if form_ids.count(i) > 1})
    if dup_form_ids:
        errors.append(f"duplicate sample_id in forms: {dup_form_ids}")
    map_ids = [m.get("sample_id") for m in mapping_list]
    dup_map_ids = sorted({i for i in map_ids if map_ids.count(i) > 1})
    if dup_map_ids:
        errors.append(f"duplicate sample_id in mapping: {dup_map_ids}")
    mapping = {m["sample_id"]: m for m in mapping_list}
    missing_map = sorted(set(form_ids) - set(map_ids))
    extra_map = sorted(set(map_ids) - set(form_ids))
    if missing_map:
        errors.append(f"forms missing a mapping entry: {missing_map}")
    if extra_map:
        errors.append(f"mapping has entries with no form: {extra_map}")

    collected = {"STATIC_ONLY": {c: [] for c in CRITERIA},
                 "STATIC_PLUS_AGENT": {c: [] for c in CRITERIA}}
    n_label_slots = 0
    n_label_filled = 0
    for form in forms:
        sid = form.get("sample_id")
        scores_to_fill = form.get("scores_to_fill", {})
        labels = set(scores_to_fill)
        if labels != {"X", "Y"}:
            errors.append(f"{sid}: form must have exactly X and Y, found {sorted(labels)}")
        m = mapping.get(sid)
        branch_of = {"X": (m or {}).get("X_is"), "Y": (m or {}).get("Y_is")}
        if m and set(branch_of.values()) != {"STATIC_ONLY", "STATIC_PLUS_AGENT"}:
            errors.append(f"{sid}: mapping must cover both branches, got {branch_of}")
        for label, scores in scores_to_fill.items():
            n_label_slots += 1
            branch = branch_of.get(label)
            present_criteria = set(scores)
            if present_criteria != set(CRITERIA):
                errors.append(f"{sid}/{label}: rubric criteria mismatch "
                              f"(missing {sorted(set(CRITERIA) - present_criteria)}, "
                              f"extra {sorted(present_criteria - set(CRITERIA))})")
            filled = all(_valid_score(scores.get(c)) for c in CRITERIA)
            # Reject any invalid non-pending value explicitly.
            for c in CRITERIA:
                v = scores.get(c)
                if v == "CHƯA CHẤM" or v is None:
                    continue  # legitimately unfilled
                if not _valid_score(v):
                    errors.append(f"{sid}/{label}/{c}: invalid score {v!r} "
                                  f"(only integer 0/1/2 allowed)")
            if filled and branch in collected:
                n_label_filled += 1
                for c in CRITERIA:
                    collected[branch][c].append(int(scores[c]))

    def summarize(branch):
        out = {}
        for c in CRITERIA:
            vals = collected[branch][c]
            out[c] = {"mean": round(mean(vals), 3), "n": len(vals)} if vals else "CHƯA CHẤM"
        return out

    # Status gating: never COMPLETE if any integrity error or any unfilled slot.
    if errors:
        status = "INVALID"
    elif n_label_slots > 0 and n_label_filled == n_label_slots:
        status = "COMPLETE"
    elif n_label_filled > 0:
        status = "PARTIAL"
    else:
        status = "CHƯA CHẤM"

    return {
        "schema_version": "grading-aggregate-v2",
        "status": status,
        "validation_errors": errors,
        "forms_total_label_slots": n_label_slots,
        "forms_fully_filled": n_label_filled,
        "per_branch": {b: summarize(b) for b in collected},
        "note": "Semantic scores are HUMAN-entered integers 0/1/2; this tool only validates "
                "and aggregates. No LLM-as-judge, no auto-fill. COMPLETE requires every X/Y "
                "slot filled with a valid score and a clean mapping.",
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
                      "total_label_slots": rep["forms_total_label_slots"],
                      "validation_errors": rep["validation_errors"][:5]},
                     indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
