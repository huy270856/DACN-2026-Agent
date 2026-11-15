"""Import + validate + aggregate human annotation exports (multi-reviewer).

Reads reviewer annotation JSON files exported by the offline grading UI, validates
them strictly, aggregates per reviewer, and computes inter-rater agreement when >=2
reviewers scored the same items. Raw scores are preserved; disagreements are flagged
for HUMAN adjudication and never auto-resolved. No scores are generated here and no
LLM is used as a judge. Nothing is reported COMPLETE unless every expected slot is
validly filled.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from evaluation.task05c.repair.grading_aggregate import CRITERIA, _valid_score


def _validate_file(obj, path) -> List[str]:
    errs = []
    if obj.get("schema_version") != "task05d-annotations-v1":
        errs.append(f"{path.name}: bad schema_version {obj.get('schema_version')!r}")
    if not obj.get("reviewer_id"):
        errs.append(f"{path.name}: missing reviewer_id")
    if not obj.get("rubric_version"):
        errs.append(f"{path.name}: missing rubric_version")
    if not obj.get("exported_at"):
        errs.append(f"{path.name}: missing exported_at timestamp")
    return errs


def load_reviews(paths: List[Path]):
    reviews = []
    errors = []
    seen_reviewers = {}
    for p in paths:
        obj = json.loads(p.read_text(encoding="utf-8"))
        errors += _validate_file(obj, p)
        rid = obj.get("reviewer_id")
        if rid in seen_reviewers:
            errors.append(f"duplicate reviewer_id {rid!r} in {p.name} and {seen_reviewers[rid]}")
        seen_reviewers[rid] = p.name
        # per (sample,label) scores; detect duplicates + invalid scores
        scores = {}
        seen_items = set()
        for a in obj.get("annotations", []):
            key = (a.get("sample_id"), a.get("blind_label"))
            if a.get("blind_label") not in ("X", "Y"):
                errors.append(f"{rid}: bad blind_label {a.get('blind_label')!r} for {a.get('sample_id')}")
            if key in seen_items:
                errors.append(f"{rid}: duplicate annotation for {key}")
            seen_items.add(key)
            sc = a.get("scores") or {}
            clean = {}
            for c in CRITERIA:
                v = sc.get(c)
                if v is None or v == "CHƯA CHẤM":
                    continue
                if not _valid_score(v):
                    errors.append(f"{rid}/{key}/{c}: invalid score {v!r} (only 0/1/2)")
                else:
                    clean[c] = int(v)
            scores[key] = clean
        reviews.append({"reviewer_id": rid, "rubric_version": obj.get("rubric_version"),
                        "exported_at": obj.get("exported_at"), "scores": scores,
                        "source": p.name})
    return reviews, errors


def _cohen_kappa(a: List[int], b: List[int], cats=(0, 1, 2)) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = 0.0
    for c in cats:
        pa = sum(1 for x in a if x == c) / n
        pb = sum(1 for x in b if x == c) / n
        pe += pa * pb
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1 - pe)


def aggregate(reviews, expected_items=None) -> Dict[str, Any]:
    per_reviewer = {}
    for r in reviews:
        filled_items = sum(1 for k, sc in r["scores"].items()
                           if all(c in sc for c in CRITERIA))
        means = {}
        for c in CRITERIA:
            vals = [sc[c] for sc in r["scores"].values() if c in sc]
            means[c] = {"mean": round(mean(vals), 3), "n": len(vals)} if vals else "CHƯA CHẤM"
        missing = None
        if expected_items is not None:
            have = {k for k, sc in r["scores"].items() if all(c in sc for c in CRITERIA)}
            missing = sorted(expected_items - have)
        status = ("COMPLETE" if (expected_items is not None and not missing)
                  else ("PARTIAL" if filled_items > 0 else "CHƯA CHẤM"))
        per_reviewer[r["reviewer_id"]] = {
            "status": status, "filled_items": filled_items,
            "expected_items": len(expected_items) if expected_items is not None else None,
            "missing_items": missing, "per_criterion_mean": means,
            "rubric_version": r["rubric_version"], "exported_at": r["exported_at"]}

    # Inter-rater agreement (pairwise) on commonly-scored items.
    inter = {}
    disagreements = []
    rids = [r["reviewer_id"] for r in reviews]
    by_rid = {r["reviewer_id"]: r["scores"] for r in reviews}
    for i in range(len(rids)):
        for j in range(i + 1, len(rids)):
            ra, rb = rids[i], rids[j]
            common = set(by_rid[ra]) & set(by_rid[rb])
            pair = {}
            for c in CRITERIA:
                a, b, items = [], [], []
                for k in sorted(common):
                    if c in by_rid[ra][k] and c in by_rid[rb][k]:
                        a.append(by_rid[ra][k][c]); b.append(by_rid[rb][k][c]); items.append(k)
                if a:
                    agree = sum(1 for x, y in zip(a, b) if x == y) / len(a)
                    pair[c] = {"n": len(a), "percent_agreement": round(agree, 3),
                               "cohen_kappa": round(_cohen_kappa(a, b), 3)}
                    for k, x, y in zip(items, a, b):
                        if x != y:
                            disagreements.append({"reviewers": [ra, rb], "sample": k[0],
                                                  "blind_label": k[1], "criterion": c,
                                                  "scores": [x, y]})
                else:
                    pair[c] = "insufficient overlap"
            inter[f"{ra}|{rb}"] = pair

    overall = "CHƯA CHẤM"
    statuses = {v["status"] for v in per_reviewer.values()}
    if statuses == {"COMPLETE"} and per_reviewer:
        overall = "COMPLETE"
    elif any(s in ("COMPLETE", "PARTIAL") for s in statuses):
        overall = "PARTIAL"

    return {
        "schema_version": "task05d-grading-aggregate-v1",
        "n_reviewers": len(reviews),
        "overall_status": overall,
        "per_reviewer": per_reviewer,
        "inter_rater_agreement": inter if len(reviews) >= 2 else "N/A (need >=2 reviewers)",
        "disagreements_for_adjudication": disagreements,
        "n_disagreements": len(disagreements),
        "note": "Raw human scores preserved; disagreements are for HUMAN adjudication, not "
                "auto-resolved. No auto-fill, no LLM-as-judge. COMPLETE needs every expected "
                "slot validly filled by the reviewer.",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Import + aggregate human annotations")
    ap.add_argument("--annotations", nargs="+", required=True, help="reviewer export JSON files")
    ap.add_argument("--forms", default=None, help="blind forms (to compute expected item set)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    expected = None
    if args.forms:
        forms = json.loads(Path(args.forms).read_text(encoding="utf-8"))
        expected = set()
        for s in forms["forms"]:
            for f in s["forms"]:
                expected.add((s["sample_id"], f["report_label"]))

    reviews, errors = load_reviews([Path(p) for p in args.annotations])
    if errors:
        rep = {"status": "INVALID", "validation_errors": errors}
    else:
        rep = aggregate(reviews, expected_items=expected)
        rep["validation_errors"] = []
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"n_reviewers": rep.get("n_reviewers", 0),
                      "overall_status": rep.get("overall_status", rep.get("status")),
                      "n_disagreements": rep.get("n_disagreements"),
                      "validation_errors": rep["validation_errors"][:5]},
                     indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
