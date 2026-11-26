"""TASK 06B-J analysis: lock scores, then unblind and aggregate (evaluation-only).

Order is enforced: `lock` records SHA-256 of every validated judgment file BEFORE the
evaluator-only mapping is read; `analyze` refuses to run without a matching lock.
NOT_APPLICABLE / NOT_ASSESSABLE are excluded from means (never 0, never 2) and always
reported as counts. No single overall mean across criteria is computed.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List

from evaluation.task05d.grading_import import _cohen_kappa  # reused 05D-J agreement code
from evaluation.task06b_j import rubric, rubrics
from evaluation.task06b_j.blind_package import sha256_file
from evaluation.task06b_j.score_validation import validate

COMMON = [c for c, s in rubric.CRITERIA.items() if s["view"] == "common"]
PAIRS = (("C", "A"), ("C", "B"), ("B", "A"))


def arm_key(m: Dict[str, Any]) -> str:
    """Arm label; DEV variants (other contract versions) stay separate and never enter PAIRS."""
    return m["arm"] if not m.get("variant") else f"{m['arm']}[{m['variant']}]"


def lock(judgment_files: List[Path], package_views: Dict[str, Path], lock_path: Path) -> Dict[str, Any]:
    if lock_path.exists():
        raise FileExistsError("scores already locked; create a new lock version")
    entries = []
    for jf in judgment_files:
        j = json.loads(jf.read_text(encoding="utf-8"))
        key = (j.get("package_id"), j.get("view"))
        view = package_views[key] if key in package_views else package_views[j.get("view")]
        errs = validate(j, json.loads(view.read_text(encoding="utf-8")))
        if errs:
            raise ValueError(f"{jf.name}: invalid judgments, not locked: {errs[:5]}")
        entries.append({"file": str(jf), "sha256": sha256_file(jf), "view": j["view"],
                        "evaluator": j["evaluator"], "pass_id": j["pass_id"]})
    doc = {"locked_utc": datetime.now(timezone.utc).isoformat(), "judgments": entries,
           "rule": "mapping must not be read before this lock exists"}
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc


def _bootstrap_ci(diffs: List[float], seed: int = 0, n: int = 2000):
    if len(diffs) < 2:
        return None
    rng = random.Random(seed)
    stats = sorted(mean(rng.choice(diffs) for _ in diffs) for _ in range(n))
    return [round(stats[int(0.025 * n)], 3), round(stats[int(0.975 * n) - 1], 3)]


def canonical(m: Dict[str, Any]) -> str:
    """Package-independent identity of a graded report, so passes built with different seeds
    (different blind IDs/order) can be aligned for self-consistency."""
    return "|".join([m["sample_sha256"], m["arm"], str(m.get("variant")), m["source"]])


def analyze(lock_path: Path, mapping_path) -> Dict[str, Any]:
    lk = json.loads(lock_path.read_text(encoding="utf-8"))
    for e in lk["judgments"]:
        if sha256_file(Path(e["file"])) != e["sha256"]:
            raise ValueError(f"judgment file changed after lock: {e['file']}")
    paths = mapping_path if isinstance(mapping_path, (list, tuple)) else [mapping_path]
    mapping = {}
    for mp in paths:
        for m in json.loads(Path(mp).read_text(encoding="utf-8"))["items"]:
            if m["item_id"] in mapping:
                raise ValueError(f"duplicate blind item id across packages: {m['item_id']}")
            mapping[m["item_id"]] = m

    per_eval: Dict[str, Dict[str, Any]] = {}
    for e in lk["judgments"]:
        j = json.loads(Path(e["file"]).read_text(encoding="utf-8"))
        who = f"{j['evaluator']['kind']}:{j['evaluator']['evaluator_id']}:{j['pass_id']}"
        bucket = per_eval.setdefault(who, {"evaluator": j["evaluator"], "scores": {}, "canon": {}, "claims": [],
                                           "rubric_id": j["rubric_id"]})
        for jj in j["judgments"]:
            m = mapping[jj["item_id"]]
            for c, v in jj["criteria"].items():
                bucket["scores"][(jj["item_id"], c)] = v["score"]
                bucket["canon"][(canonical(m), c)] = v["score"]
            for cv in jj.get("claims", []) + [dict(x, claim_id="extra") for x in jj.get("additional_claims", [])]:
                bucket["claims"].append({"item_id": jj["item_id"], "arm": arm_key(m), "probe": m["is_probe"], **cv})

    report: Dict[str, Any] = {"note": "Arm results exclude constructed probes. Means use assessable "
                              "numeric scores only; NA/NOT_ASSESSABLE are counted, never imputed.",
                              "evaluators": {}}
    for who, b in per_eval.items():
        arms: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(lambda: defaultdict(lambda: {"scores": [], "NA": 0, "NOT_ASSESSABLE": 0}))
        by_sample: Dict[tuple, Dict[str, Any]] = defaultdict(dict)
        for (iid, c), s in b["scores"].items():
            m = mapping[iid]
            if m["is_probe"]:
                continue
            cell = arms[arm_key(m)][c]
            if s == rubric.NA:
                cell["NA"] += 1
            elif s == rubric.NX:
                cell["NOT_ASSESSABLE"] += 1
            else:
                cell["scores"].append(s)
                by_sample[(m["sample_sha256"], c)][arm_key(m)] = s
        per_arm = {a: {c: {"n_assessable": len(v["scores"]),
                           "mean": round(mean(v["scores"]), 3) if v["scores"] else None,
                           "median": median(v["scores"]) if v["scores"] else None,
                           "NA": v["NA"], "NOT_ASSESSABLE": v["NOT_ASSESSABLE"]}
                       for c, v in crits.items()} for a, crits in arms.items()}
        paired = {}
        rb = rubrics.get(b["rubric_id"])
        comparable = [c for c, sp in rb.CRITERIA.items() if sp["view"] == "common"] + ["R6_incremental_value"]
        for x, y in PAIRS:
            for c in comparable:
                diffs = [d[x] - d[y] for (sha, cc), d in by_sample.items() if cc == c and x in d and y in d]
                if diffs:
                    paired[f"{x}-{y}:{c}"] = {"n_pairs": len(diffs), "mean_diff": round(mean(diffs), 3),
                                              "wins": sum(d > 0 for d in diffs), "ties": sum(d == 0 for d in diffs),
                                              "losses": sum(d < 0 for d in diffs), "bootstrap95": _bootstrap_ci(diffs)}
        claims = defaultdict(lambda: defaultdict(int))
        tags = defaultdict(lambda: defaultdict(int))
        for cv in b["claims"]:
            key = "PROBE" if cv["probe"] else cv["arm"]
            claims[key][cv["verdict"]] += 1
            for t in cv.get("tags", []):
                tags[key][t] += 1
        report["evaluators"][who] = {"evaluator": b["evaluator"], "rubric_id": b["rubric_id"],
                                     "per_arm": per_arm, "paired": paired,
                                     "claim_verdicts": {k: dict(v) for k, v in claims.items()},
                                     "claim_tags": {k: dict(v) for k, v in tags.items()}}
    report["agreement"] = agreement(per_eval)
    report["checker_vs_evaluator"] = checker_comparison(per_eval, mapping)
    return report


def agreement(per_eval: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Pairwise agreement on shared numeric scores. Same-evaluator passes = self-consistency only."""
    out = {}
    keys = sorted(per_eval)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ea, eb = per_eval[a]["evaluator"], per_eval[b]["evaluator"]
            same = (ea["kind"], ea["evaluator_id"]) == (eb["kind"], eb["evaluator_id"])
            if per_eval[a]["rubric_id"] != per_eval[b]["rubric_id"]:
                continue  # never compare scores across rubric versions
            crits = sorted({c for (_k, c) in per_eval[a]["canon"]})
            for c in crits:
                xs, ys = [], []
                for (key, cc), s in per_eval[a]["canon"].items():
                    t = per_eval[b]["canon"].get((key, cc))
                    if cc == c and isinstance(s, int) and isinstance(t, int):
                        xs.append(s); ys.append(t)
                if xs:
                    out[f"{a} vs {b}:{c}"] = {
                        "relation": "SELF_CONSISTENCY_NOT_CORRECTNESS" if same else "INTER_EVALUATOR",
                        "n": len(xs), "percent_agreement": round(sum(x == y for x, y in zip(xs, ys)) / len(xs), 3),
                        "cohen_kappa": round(_cohen_kappa(xs, ys, cats=tuple(sorted(set(xs) | set(ys) | {0, 1, 2}))), 3)}
    return out


def checker_comparison(per_eval: Dict[str, Dict[str, Any]], mapping: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deterministic self-corroboration flag vs evaluator SELF_CORROBORATION tag, per item.
    Disagreements are preserved for human adjudication, never auto-resolved."""
    rows = []
    for who, b in per_eval.items():
        judged = {iid for (iid, _c) in b["scores"]}
        tagged = {cv["item_id"] for cv in b["claims"]
                  if {"SELF_CORROBORATION", "SEMANTIC_SELF_CORROBORATION"} & set(cv.get("tags", []))}
        for iid in sorted(judged):
            m = mapping[iid]
            if m["arm"] == "A" or m["is_probe"]:
                continue
            flag = "prediction_used_as_own_corroboration" in (m["deterministic_checker"].get("grounding_flags") or [])
            tag = iid in tagged
            rows.append({"evaluator": who, "item_id": iid, "arm": m["arm"], "checker_flag": flag,
                         "evaluator_tag": tag,
                         "status": "AGREE" if flag == tag else "DISAGREE_NEEDS_HUMAN_ADJUDICATION"})
    return rows


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="06B-J: lock judgments, then unblind and aggregate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lk = sub.add_parser("lock")
    lk.add_argument("--judgments", type=Path, nargs="+", required=True)
    lk.add_argument("--package", type=Path, nargs="+", required=True)
    lk.add_argument("--lock", type=Path, required=True)
    an = sub.add_parser("analyze")
    an.add_argument("--lock", type=Path, required=True)
    an.add_argument("--package", type=Path, nargs="+", required=True)
    an.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "lock":
        views = {}
        for pkg in a.package:
            pid = json.loads((pkg / "package_manifest.json").read_text(encoding="utf-8"))["package_id"]
            for v in ("common", "investigation"):
                views[(pid, v)] = pkg / "grader" / f"items_{v}.json"
        print(json.dumps(lock(a.judgments, views, a.lock), indent=2, ensure_ascii=False))
    else:
        if a.out.exists():
            raise FileExistsError(f"NEW_VERSION_REQUIRED: {a.out}")
        rep = analyze(a.lock, [pkg / "EVALUATOR_ONLY" / "mapping.json" for pkg in a.package])
        a.out.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
