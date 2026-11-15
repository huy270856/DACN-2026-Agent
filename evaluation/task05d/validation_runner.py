"""Run the REAL TASK 05B pipeline on each benign PE (RAW_PE_E2E), read-only.

For every sample: (A) static-only = investigate_real(run_agent=False), and
(B) static+agent = investigate_real(run_agent=True). Both go through the real
Node B -> D1-D9 -> EMBER v2 + LightGBM -> Node C path; the agent only assesses.
The target PE is never executed. Resume-safe (per-sample cache).

No Precision/Recall/F1 is computed on this benign-only set; a false-positive count
within this set is reported but NOT generalised to real-world rates.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _run_one(app, cfg_home, acfg, path, run_agent):
    from dacn.config import AppConfig
    config = AppConfig.from_home(str(cfg_home))
    t0 = time.perf_counter()
    res = app.investigate_real(config, file=path, agent_config=acfg, run_agent=run_agent)
    return res, round(time.perf_counter() - t0, 3)


def run(manifest_path: Path, out_dir: Path, home_dir: Path, max_iters=3, limit=None):
    from dacn import application as app
    from agent.config import AgentConfig

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = manifest["samples"]
    if limit:
        samples = samples[:limit]
    (out_dir / "samples").mkdir(parents=True, exist_ok=True)
    acfg = replace(AgentConfig.from_env(), think=False, max_iterations=max_iters, max_tool_calls=2)

    rows: List[Dict[str, Any]] = []
    for i, s in enumerate(samples):
        sid = s["sample_id"]
        cache = out_dir / "samples" / f"{sid}.json"
        if cache.exists():
            rows.append(json.loads(cache.read_text(encoding="utf-8")))
            continue
        path = s["local_path"]

        static_res, static_lat = _run_one(app, home_dir / "static", None, path, False)
        agent_res, agent_lat = _run_one(app, home_dir / "agent", acfg, path, True)

        sp = (agent_res.get("report") or {}).get("static_prediction") or \
             (static_res.get("report") or {}).get("static_prediction") or {}
        ag = (agent_res.get("report") or {}).get("agent_assessment")
        row = {
            "sample_id": sid, "filename": s["filename"], "sha256": s["sha256"],
            "pe_format": s["pe_format"], "kind": s["kind"], "machine": s["machine"],
            "size_bytes": s["size_bytes"], "signature_status": s["signature_status"],
            "label": s["label"],
            "static_only": {
                "overall_status": static_res.get("overall_status"),
                "prediction_outcome": static_res.get("prediction_outcome"),
                "report_written": bool(static_res.get("report_paths")),
                "latency_s": static_lat,
            },
            "static_plus_agent": {
                "overall_status": agent_res.get("overall_status"),
                "prediction_outcome": agent_res.get("prediction_outcome"),
                "report_written": bool(agent_res.get("report_paths")),
                "latency_s": agent_lat,
                "planner_kind": (ag or {}).get("planner_kind"),
                "evidence_alignment": (ag or {}).get("evidence_alignment"),
                "review_required": (ag or {}).get("review_required"),
                "agent_completed": ag is not None and (ag or {}).get("planner_kind") == "LOCAL_QWEN",
            },
            "prediction": {
                "status": sp.get("status"),
                "predicted_label": sp.get("predicted_label"),
                "raw_score": sp.get("raw_score"),
                "threshold": sp.get("threshold"),
                "parser_status": sp.get("parser_status"),
                "model_id": sp.get("model_id"),
                "evidence_id": sp.get("evidence_id"),
            },
            "run_at": datetime.now(timezone.utc).isoformat(),
        }
        cache.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append(row)
        print(f"[{i+1}/{len(samples)}] {s['filename']:<16} "
              f"pred={row['prediction'].get('predicted_label')} "
              f"score={row['prediction'].get('raw_score')} "
              f"align={row['static_plus_agent'].get('evidence_alignment')} "
              f"lat(s/a)={static_lat}/{agent_lat}", flush=True)

    results = aggregate(rows, manifest)
    (out_dir / "validation_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(out_dir / "validation_results.csv", rows)
    return results


def aggregate(rows, manifest) -> Dict[str, Any]:
    n = len(rows)

    def rate(pred):
        k = sum(1 for r in rows if pred(r))
        return {"k": k, "n": n, "rate": round(k / n, 4) if n else None}

    pred_ok = lambda r: r["prediction"]["status"] == "AVAILABLE"
    mal = [r for r in rows if r["prediction"].get("predicted_label") == "malicious"]
    static_lat = [r["static_only"]["latency_s"] for r in rows]
    agent_lat = [r["static_plus_agent"]["latency_s"] for r in rows]
    anomalies = [{"sample_id": r["sample_id"], "filename": r["filename"],
                  "why": "predicted malicious on provenance-benign signed binary",
                  "raw_score": r["prediction"]["raw_score"]}
                 for r in mal]
    parse_fail = [r["sample_id"] for r in rows if r["prediction"].get("parser_status") not in ("OK", None)
                  and r["prediction"]["status"] != "AVAILABLE"]

    return {
        "schema_version": "task05d-validation-v1",
        "track": "RAW_PE_E2E",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": manifest["samples"][0].get("model_id") if manifest.get("samples") else None,
        "n_targets": n,
        "parse_or_inference_success": rate(pred_ok),
        "detector_inference_success": rate(pred_ok),
        "agent_completion": rate(lambda r: r["static_plus_agent"]["agent_completed"]),
        "evidence_commit_success": rate(lambda r: bool(r["prediction"].get("evidence_id"))),
        "report_generation_success": rate(lambda r: r["static_plus_agent"]["report_written"]),
        "latency": {
            "static_only_mean_s": round(sum(static_lat) / n, 3) if n else None,
            "static_plus_agent_mean_s": round(sum(agent_lat) / n, 3) if n else None,
            "agent_overhead_mean_s": round((sum(agent_lat) - sum(static_lat)) / n, 3) if n else None,
        },
        "benign_set_false_positive_count": len(mal),
        "benign_set_false_positive_rate_THIS_SET_ONLY": round(len(mal) / n, 4) if n else None,
        "fp_caveat": ("False positives are counted WITHIN this homogeneous Microsoft-signed set "
                      "only; NOT a real-world FPR. No Precision/Recall/F1 on a benign-only set."),
        "anomalies_predicted_malicious": anomalies,
        "parse_failures": parse_fail,
        "agent_alignment_distribution": _count(rows, lambda r: r["static_plus_agent"].get("evidence_alignment")),
        "agent_review_required_rate": rate(lambda r: r["static_plus_agent"].get("review_required") is True),
    }


def _count(rows, key):
    d = {}
    for r in rows:
        v = key(r)
        d[v] = d.get(v, 0) + 1
    return d


def _write_csv(path, rows):
    import csv
    cols = ["sample_id", "filename", "pe_format", "kind", "machine", "size_bytes",
            "signature_status", "predicted_label", "raw_score", "parser_status",
            "evidence_alignment", "review_required", "static_latency_s", "agent_latency_s"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r["sample_id"], r["filename"], r["pe_format"], r["kind"], r["machine"],
                        r["size_bytes"], r["signature_status"],
                        r["prediction"].get("predicted_label"), r["prediction"].get("raw_score"),
                        r["prediction"].get("parser_status"),
                        r["static_plus_agent"].get("evidence_alignment"),
                        r["static_plus_agent"].get("review_required"),
                        r["static_only"]["latency_s"], r["static_plus_agent"]["latency_s"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 05D real-PE validation runner")
    ap.add_argument("--manifest", required=True, help="evaluator-only manifest (with local_path)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--home", required=True, help="DACN home dir (gitignored; holds cases)")
    ap.add_argument("--max-iters", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    results = run(Path(args.manifest), Path(args.out), Path(args.home),
                  max_iters=args.max_iters, limit=args.limit)
    print(json.dumps({k: results[k] for k in (
        "n_targets", "detector_inference_success", "agent_completion",
        "report_generation_success", "benign_set_false_positive_count",
        "latency", "agent_alignment_distribution")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
