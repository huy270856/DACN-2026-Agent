"""TASK 06B-J final confirmatory analysis tables (post-lock; reads locked judgments + frozen run).

Per case x arm x Judge pass: primary criteria, claim verdict counts, semantic self-corroboration tags,
joined with deterministic run facts. Per accessibility class aggregates. No new scoring; Judge values
are LLM_JUDGE_PROVISIONAL (human_verified=false); deterministic facts are labelled as such.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from evaluation.task06b_j.blind_package import sha256_file

CRITS = ("R1_factual_support", "R2_evidence_traceability", "R3_tool_decision_quality", "R4_new_evidence_relevance",
         "R5_new_evidence_consumption", "R6_incremental_value", "R7_uncertainty_limitations",
         "R8_decision_quality_safety", "R9_next_step_planning")
NEG = ("UNSUPPORTED", "CONTRADICTED")


def build(lock: Path, packages: List[Path], det_summary: Path, manifest: Path) -> Dict[str, Any]:
    lk = json.loads(lock.read_text(encoding="utf-8"))
    for e in lk["judgments"]:
        if sha256_file(Path(e["file"])) != e["sha256"]:
            raise ValueError("judgment changed after lock")
    mapping = {}
    for p in packages:
        for m in json.loads((p / "EVALUATOR_ONLY/mapping.json").read_text(encoding="utf-8"))["items"]:
            mapping[m["item_id"]] = m
    man = {c["sha256"]: c for c in json.loads(manifest.read_text(encoding="utf-8"))["cases"]}
    det = {(r["alias"], r["arm"]): r for r in json.loads(det_summary.read_text(encoding="utf-8"))["rows"]}
    cells: Dict[tuple, Dict[str, Any]] = defaultdict(dict)   # (alias, arm, pass) -> data
    for e in lk["judgments"]:
        j = json.loads(Path(e["file"]).read_text(encoding="utf-8"))
        pas = "P1" if "P1" in j["pass_id"] else "P2"
        for jj in j["judgments"]:
            m = mapping[jj["item_id"]]
            alias = man[m["sample_sha256"]]["alias"]
            c = cells[(alias, m["arm"], pas)]
            c.setdefault("scores", {}).update({k: v["score"] for k, v in jj["criteria"].items()})
            if j["view"] == "common":   # claim verdicts counted once, from the common track
                allc = jj.get("claims", []) + jj.get("additional_claims", [])
                c["claims"] = dict(Counter(x["verdict"] for x in allc))
                c["n_claims"] = len(allc)
                c["semantic_self_corroboration"] = any("SEMANTIC_SELF_CORROBORATION" in x.get("tags", []) for x in allc)
                c["scope_overclaim"] = sum("SCOPE_OVERCLAIM" in x.get("tags", []) for x in allc)
                c["unsupported_api"] = sum("UNSUPPORTED_API_OR_FEATURE" in x.get("tags", []) for x in allc)
                c["runtime_overclaim"] = sum("RUNTIME_BEHAVIOUR_OVERCLAIM" in x.get("tags", []) for x in allc)
                c["score_as_prob"] = sum("SCORE_AS_PROBABILITY_OR_TRUTH" in x.get("tags", []) for x in allc)
    rows = []
    for (alias, arm, pas), c in sorted(cells.items()):
        d = det[(alias, arm)]
        rows.append({"alias": alias, "arm": arm, "pass": pas, "class": man_alias(man, alias)["question_category"],
                     "family": man_alias(man, alias)["capability_family"],
                     "status": d.get("status") if arm != "A" else "STATIC_TEMPLATE",
                     "tool_called": d.get("tool_proposed"), "reads": d.get("retrieval_reads"),
                     "relevant_seen": d.get("any_relevant_seen"),
                     "structural_self_corroboration": d.get("structural_self_corroboration"),
                     "effective_action": d.get("effective_action"), **c})

    def agg(sel):
        out = {"n_reports": len(sel)}
        for k in CRITS:
            vals = [r["scores"].get(k) for r in sel if isinstance(r["scores"].get(k), int)]
            out[k] = {"mean": round(mean(vals), 3) if vals else None, "n": len(vals)}
        claims = Counter()
        for r in sel:
            claims.update(r.get("claims", {}))
        tot = sum(claims.values())
        out["claims"] = dict(claims)
        out["claim_negative_rate"] = round(sum(claims[v] for v in NEG) / tot, 3) if tot else None
        out["reports_with_any_negative_claim"] = sum(any(r.get("claims", {}).get(v) for v in NEG) for r in sel)
        out["semantic_self_corroboration_reports"] = sum(bool(r.get("semantic_self_corroboration")) for r in sel)
        for t in ("scope_overclaim", "unsupported_api", "runtime_overclaim", "score_as_prob"):
            out[t] = sum(r.get(t, 0) for r in sel)
        return out

    by_arm = {f"{arm}|{p}": agg([r for r in rows if r["arm"] == arm and r["pass"] == p])
              for arm in ("A", "B", "C") for p in ("P1", "P2")}
    by_class = {f"{cls}|{arm}|{p}": agg([r for r in rows if r["class"] == cls and r["arm"] == arm and r["pass"] == p])
                for cls in sorted({r["class"] for r in rows}) for arm in ("A", "B", "C") for p in ("P1", "P2")}
    return {"kind": "LLM_JUDGE_PROVISIONAL + DETERMINISTIC (human_verified=false)", "by_arm": by_arm,
            "by_class": by_class, "rows": rows}


def man_alias(man, alias):
    return next(c for c in man.values() if c["alias"] == alias)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", type=Path, required=True)
    ap.add_argument("--package", type=Path, nargs="+", required=True)
    ap.add_argument("--deterministic", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    doc = build(a.lock, a.package, a.deterministic, a.manifest)
    a.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    for k, v in doc["by_arm"].items():
        print(k, {c[:2]: v[c]["mean"] for c in CRITS}, "neg_rate", v["claim_negative_rate"], "neg_reports",
              v["reports_with_any_negative_claim"], "semSC", v["semantic_self_corroboration_reports"],
              "scope", v["scope_overclaim"], "api", v["unsupported_api"], "rt", v["runtime_overclaim"], "prob", v["score_as_prob"])
