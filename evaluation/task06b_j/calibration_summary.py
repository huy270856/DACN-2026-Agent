"""Deterministic post-lock calibration summary (reads only locked judgments + evaluator files).

Probe detection is checked at CLAIM level (the injected claim is always the last claim) and
compared with the developer's expected verdict/tags - which are hypotheses, not ground truth.
Criterion deltas vs the unmodified base report are reported to expose cross-criterion
propagation (one injected error lowering several criteria).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from evaluation.task06b_j.analysis import arm_key


def summarize(lock_path: Path, package_dir: Path) -> Dict[str, Any]:
    lk = json.loads(lock_path.read_text(encoding="utf-8"))
    mapping = {m["item_id"]: m for m in json.loads((package_dir / "EVALUATOR_ONLY/mapping.json").read_text(encoding="utf-8"))["items"]}
    key = {k["item_id"]: k for k in json.loads((package_dir / "EVALUATOR_ONLY/calibration_key.json").read_text(encoding="utf-8"))["items"]}
    views = {}
    for e in lk["judgments"]:
        j = json.loads(Path(e["file"]).read_text(encoding="utf-8"))
        views[j["view"]] = {x["item_id"]: x for x in j["judgments"]}
    probes = [i for i, m in mapping.items() if m["is_probe"]]
    base = next(i for i, m in mapping.items() if not m["is_probe"] and m["variant"] == "dev-v3.4-debug"
                and m["sample_sha256"] == mapping[probes[0]]["sample_sha256"])
    out = {"base_item": base, "probes": [], "note": "Expected verdicts/tags are developer hypotheses, not ground truth."}
    for pid in sorted(probes, key=lambda i: mapping[i]["variant"]):
        exp = key[pid]["probe"]
        row = {"item_id": pid, "variant": mapping[pid]["variant"], "probe_text": exp["text"],
               "expected_verdict": exp["expected_verdict"], "expected_tags": exp["expected_tags"]}
        for view, js in views.items():
            j = js[pid]
            injected = j["claims"][-1] if j.get("claims") else None
            row[view] = {
                "injected_claim_verdict": injected and injected["verdict"],
                "injected_claim_tags": injected and injected.get("tags", []),
                "detected": bool(injected) and injected["verdict"] in ("UNSUPPORTED", "CONTRADICTED"),
                "verdict_matches_expected": bool(injected) and injected["verdict"] in exp["expected_verdict"],
                "expected_tags_present": bool(injected) and set(exp["expected_tags"]) <= set(injected.get("tags", [])),
                "criterion_delta_vs_base": {c: {"probe": v["score"], "base": js[base]["criteria"][c]["score"]}
                                            for c, v in j["criteria"].items()
                                            if v["score"] != js[base]["criteria"][c]["score"]},
                "base_claims_same_verdicts": [c["verdict"] for c in j["claims"][:-1]] ==
                                             [c["verdict"] for c in js[base]["claims"]]}
        out["probes"].append(row)
    exp_rows = []
    for iid, k in key.items():
        if k.get("probe"):
            continue
        m = mapping[iid]
        exp_rows.append({"item_id": iid, "group": arm_key(m), "sample_prefix": m["sample_sha256"][:8],
                         "developer_expectation": k["expectation"],
                         "scores": {v: {c: x["score"] for c, x in js[iid]["criteria"].items()}
                                    for v, js in views.items() if iid in js}})
    out["expectations"] = exp_rows
    common = views.get("common", {})
    out["self_corroboration_checker_vs_trackA"] = [
        {"item_id": i, "group": arm_key(m),
         "checker_flag": "prediction_used_as_own_corroboration" in (m["deterministic_checker"].get("grounding_flags") or []),
         "judge_tag": any("SELF_CORROBORATION" in c.get("tags", []) for c in common[i].get("claims", []) + common[i].get("additional_claims", []))}
        for i, m in mapping.items() if i in common and m["arm"] != "A" and not m["is_probe"]]
    for r in out["self_corroboration_checker_vs_trackA"]:
        r["status"] = "AGREE" if r["checker_flag"] == r["judge_tag"] else "DISAGREE_NEEDS_HUMAN_ADJUDICATION"
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", type=Path, required=True)
    ap.add_argument("--package", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    doc = summarize(a.lock, a.package)
    a.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    for p in doc["probes"]:
        print(p["variant"], {v: (p[v]["injected_claim_verdict"], p[v]["expected_tags_present"], p[v]["criterion_delta_vs_base"]) for v in ("common", "investigation")})
    for r in doc["self_corroboration_checker_vs_trackA"]:
        print(r["group"], r["sample_prefix"] if "sample_prefix" in r else "", r["checker_flag"], r["judge_tag"], r["status"])
