"""Calibration v2 summary applying the LOCKED stopping rule of RUBRIC_V2.md section 3 (read-only, post-lock).

Rule (fixed before results):
  (1) self-consistency pass1 vs pass2: exact percent agreement >= 0.8 on REAL assessable reports
      (probes excluded; NA / NOT_ASSESSABLE excluded; pairs aligned by evaluator-only mapping);
  (2) probe direction: a NEGATIVE probe must not score higher than its unmodified base report,
      a POSITIVE probe must not score lower, in each pass.
A criterion failing either is UNRELIABLE (reported, excluded from the primary aggregate).
Within-one agreement and Cohen's kappa are reported as secondary information only.
The two passes come from the same model family: this is self-consistency, not inter-rater
reliability and not correctness.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict

from evaluation.task05d.grading_import import _cohen_kappa
from evaluation.task06b_j import rubric_v2
from evaluation.task06b_j.analysis import canonical
from evaluation.task06b_j.blind_package import sha256_file

THRESHOLD = 0.8


def load(lock_path: Path, packages):
    lk = json.loads(lock_path.read_text(encoding="utf-8"))
    for e in lk["judgments"]:
        if sha256_file(Path(e["file"])) != e["sha256"]:
            raise ValueError(f"judgment changed after lock: {e['file']}")
    mapping, keys = {}, {}
    for pkg in packages:
        pid = json.loads((pkg / "package_manifest.json").read_text(encoding="utf-8"))["package_id"]
        for m in json.loads((pkg / "EVALUATOR_ONLY/mapping.json").read_text(encoding="utf-8"))["items"]:
            mapping[m["item_id"]] = dict(m, package_id=pid)
        for k in json.loads((pkg / "EVALUATOR_ONLY/calibration_key.json").read_text(encoding="utf-8"))["items"]:
            keys[k["item_id"]] = k
    passes = defaultdict(dict)   # pass_no -> canonical -> judgment
    for e in lk["judgments"]:
        j = json.loads(Path(e["file"]).read_text(encoding="utf-8"))
        p = 1 if j["package_id"].endswith("P1") else 2
        for jj in j["judgments"]:
            m = mapping[jj["item_id"]]
            passes[(p, j["view"])][canonical(m)] = {"j": jj, "m": m, "key": keys.get(jj["item_id"])}
    return passes


def summarize(lock_path: Path, packages) -> Dict[str, Any]:
    passes = load(lock_path, packages)
    out: Dict[str, Any] = {"rule": __doc__.strip(), "threshold": THRESHOLD, "criteria": {}, "probes": [],
                           "disagreements": []}
    for name, spec in rubric_v2.CRITERIA.items():
        view = spec["view"]
        p1, p2 = passes[(1, view)], passes[(2, view)]
        xs, ys, dis = [], [], []
        dist1, dist2 = Counter(), Counter()
        for key, a in p1.items():
            b = p2.get(key)
            if b is None or a["m"]["is_probe"]:
                continue
            s1, s2 = a["j"]["criteria"][name]["score"], b["j"]["criteria"][name]["score"]
            dist1[str(s1)] += 1; dist2[str(s2)] += 1
            if isinstance(s1, int) and isinstance(s2, int):
                xs.append(s1); ys.append(s2)
                if s1 != s2:
                    dis.append({"criterion": name, "variant": a["m"]["variant"], "sample": a["m"]["sample_sha256"][:8],
                                "p1": s1, "p2": s2, "p1_rationale": a["j"]["criteria"][name]["rationale"],
                                "p2_rationale": b["j"]["criteria"][name]["rationale"]})
            elif s1 != s2:
                dis.append({"criterion": name, "variant": a["m"]["variant"], "sample": a["m"]["sample_sha256"][:8],
                            "p1": s1, "p2": s2, "note": "assessability differs"})
        n = len(xs)
        exact = sum(x == y for x, y in zip(xs, ys))
        within1 = sum(abs(x - y) <= 1 for x, y in zip(xs, ys))
        cats = tuple(sorted(set(xs) | set(ys) | {0, 1, 2}))
        # probe direction
        probe_checks = []
        for p in (1, 2):
            items = passes[(p, view)]
            base = next((v for v in items.values() if not v["m"]["is_probe"] and v["m"]["variant"] == "dev-v3.4-debug"
                         and v["m"]["sample_sha256"].startswith("f4d29fd9")), None)
            for v in items.values():
                if not v["m"]["is_probe"] or base is None:
                    continue
                pol = v["key"]["probe"]["polarity"]
                sp, sb = v["j"]["criteria"][name]["score"], base["j"]["criteria"][name]["score"]
                if not (isinstance(sp, int) and isinstance(sb, int)):
                    continue
                ok = sp <= sb if pol == "NEG" else sp >= sb
                probe_checks.append({"pass": p, "probe": v["key"]["probe"]["probe_name"], "polarity": pol,
                                     "probe_score": sp, "base_score": sb, "ok": ok})
        rate = exact / n if n else None
        agree_ok = rate is not None and rate >= THRESHOLD
        probe_ok = all(c["ok"] for c in probe_checks)
        status = ("EXPLORATORY" if spec.get("exploratory") else
                  "RELIABLE" if agree_ok and probe_ok else "UNRELIABLE")
        if spec.get("exploratory"):
            status += "_" + ("WOULD_PASS" if agree_ok and probe_ok else "WOULD_FAIL")
        out["criteria"][name] = {
            "view": view, "n_paired_real_assessable": n, "exact_agreement": exact,
            "exact_rate": round(rate, 3) if rate is not None else None,
            "within_one": within1, "within_one_rate": round(within1 / n, 3) if n else None,
            "cohen_kappa": round(_cohen_kappa(xs, ys, cats=cats), 3) if n else None,
            "distribution_p1": dict(dist1), "distribution_p2": dict(dist2),
            "probe_checks": len(probe_checks), "probe_failures": [c for c in probe_checks if not c["ok"]],
            "agreement_ok": agree_ok, "probe_direction_ok": probe_ok, "status": status}
        out["disagreements"] += dis
    # claim-level probe detection (injected claim = last claim)
    for p in (1, 2):
        for view in ("common", "investigation"):
            for v in passes[(p, view)].values():
                if not v["m"]["is_probe"]:
                    continue
                pr = v["key"]["probe"]
                c = v["j"]["claims"][-1] if v["j"].get("claims") else None
                out["probes"].append({"pass": p, "view": view, "probe": pr["probe_name"], "polarity": pr["polarity"],
                                      "expected_verdict": pr["expected_verdict"], "expected_tags": pr["expected_tags"],
                                      "expected_access": pr.get("expected_evidence_access"),
                                      "verdict": c and c["verdict"], "tags": c and c.get("tags", []),
                                      "evidence_access": c and c.get("evidence_access"),
                                      "rationale": c and c["rationale"]})
    # semantic self-corroboration tag per real item, both passes (Track A)
    sc = []
    for key, a in passes[(1, "common")].items():
        if a["m"]["is_probe"] or a["m"]["arm"] == "A":
            continue
        b = passes[(2, "common")].get(key)
        tag = lambda x: any("SEMANTIC_SELF_CORROBORATION" in c.get("tags", [])
                            for c in x["j"].get("claims", []) + x["j"].get("additional_claims", []))
        sc.append({"variant": a["m"]["variant"], "sample": a["m"]["sample_sha256"][:8],
                   "structural_checker": "prediction_used_as_own_corroboration" in (a["m"]["deterministic_checker"].get("grounding_flags") or []),
                   "semantic_p1": tag(a), "semantic_p2": tag(b) if b else None,
                   "p1_item": a["m"]["item_id"], "p2_item": b["m"]["item_id"] if b else None})
    out["self_corroboration"] = sc
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", type=Path, required=True)
    ap.add_argument("--package", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    doc = summarize(a.lock, a.package)
    a.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    for k, v in doc["criteria"].items():
        print(f"{k:30s} n={v['n_paired_real_assessable']:2d} exact={v['exact_agreement']}/{v['n_paired_real_assessable']} rate={v['exact_rate']} w1={v['within_one_rate']} kappa={v['cohen_kappa']} probes_fail={len(v['probe_failures'])}/{v['probe_checks']} -> {v['status']}")
