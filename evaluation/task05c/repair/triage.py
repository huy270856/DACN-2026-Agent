"""REPAIR #2 — fair triage comparison with a COMMON review definition.

The original metric used two non-equivalent definitions:
  * static-only review_required = (recommendation.action == MANUAL_REVIEW)
  * agent review_required       = the agent's own boolean field
This recomputes a single, published `human_review_required` decision applied
IDENTICALLY to both branches, from a recommendation -> review mapping, using only
SAVED data (no Qwen re-run). Raw flags are also reported, not discarded.

Published mapping (a recommendation that needs a human decision -> review=True):
  MANUAL_REVIEW        -> True
  CONSIDER_QUARANTINE  -> True   (a containment *decision* is for a human; not executed)
  AVOID_EXECUTION      -> True
  MONITOR              -> False  (routine monitoring is not a human-review trigger)
MONITOR is NOT counted as review; CONSIDER_QUARANTINE is a *recommendation*, never
an executed action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from evaluation.task05c import metrics

REVIEW_MAP = {"MANUAL_REVIEW": True, "CONSIDER_QUARANTINE": True,
              "AVOID_EXECUTION": True, "MONITOR": False}


def normalized_review(action) -> bool:
    return bool(REVIEW_MAP.get(action, False))


def recompute(samples_dir: Path) -> Dict[str, Any]:
    rows = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(samples_dir.glob("*.json"))]

    per = []
    for r in rows:
        static_action = r["static"]["report"]["recommendation"]["action"]
        ass = r["agent"]["report"].get("assessment") or {}
        agent_action = ass.get("agent_recommendation")
        per.append({
            "sha256": r["sha256"], "strata": r["strata"],
            "predicted_label": r["predicted_label"],
            "static_action": static_action,
            "static_review_normalized": normalized_review(static_action),
            "static_review_raw_manual_only": static_action == "MANUAL_REVIEW",
            "agent_action": agent_action,
            "agent_review_normalized": normalized_review(agent_action) if agent_action else None,
            "agent_review_raw_flag": bool(ass.get("review_required")),
        })

    def rate(key, pool):
        vals = [p[key] for p in pool if p[key] is not None]
        k = sum(1 for v in vals if v)
        return metrics.proportion(k, len(vals))

    strata = ("TP", "TN", "FP", "FN", "NEAR")
    by_stratum = {}
    for st in strata:
        pool = [p for p in per if st in p["strata"]]
        if pool:
            by_stratum[st] = {
                "n": len(pool),
                "static_review_normalized": rate("static_review_normalized", pool),
                "agent_review_normalized": rate("agent_review_normalized", pool),
                "agent_review_raw_flag": rate("agent_review_raw_flag", pool),
            }

    # Paired (same samples) normalized review decision.
    s_norm = [p["static_review_normalized"] for p in per]
    a_norm = [p["agent_review_normalized"] if p["agent_review_normalized"] is not None
              else False for p in per]
    paired = metrics.mcnemar_counts(s_norm, a_norm)

    return {
        "schema_version": "triage-corrected-v1",
        "note": "Fair common human_review_required recomputed from saved data; "
                "original per-branch review metric retained as baseline in eval_results.json.",
        "review_mapping": REVIEW_MAP,
        "n": len(per),
        "overall": {
            "static_review_normalized": rate("static_review_normalized", per),
            "static_review_raw_manual_only": rate("static_review_raw_manual_only", per),
            "agent_review_normalized": rate("agent_review_normalized", per),
            "agent_review_raw_flag": rate("agent_review_raw_flag", per),
        },
        "by_stratum": by_stratum,
        "paired_normalized_review": paired,
        "interpretation": (
            "On FP (benign truly, model says malicious) a high review rate is GOOD "
            "(a human could catch the false alarm); on FN (malware the model missed) "
            "review is the only chance to recover, but the agent's near-constant review "
            "on FN also fires on everything else, so it does not *discriminate*. "
            "A higher review rate is not automatically better: indiscriminate review has "
            "low triage value. Compare review rates together with alignment (all CONSISTENT) "
            "and cost."),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 05C-R fair triage recompute")
    ap.add_argument("--samples", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rep = recompute(Path(args.samples))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"overall": rep["overall"],
                      "by_stratum_agent_norm": {k: v["agent_review_normalized"]["rate"]
                                                for k, v in rep["by_stratum"].items()},
                      "by_stratum_static_norm": {k: v["static_review_normalized"]["rate"]
                                                 for k, v in rep["by_stratum"].items()}},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
