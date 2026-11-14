"""TASK 05C evaluation runner (FEATURE_RECORD_REPLAY).

Pipeline per audit sample (resume-safe):
  record -> LightGBM score (same frozen model) -> static prediction
         -> evidence projection (no raw floats, no fabricated behaviour)
         -> branch A: static-only baseline report (frozen)
         -> branch B: real Qwen agent assessment over the SAME evidence
         -> automated rubric checks for both; blind human-annotation forms
Aggregates detection + investigation metrics and writes all artifacts.

Ground truth is read from the manifest for strata/metrics only and is never put
into any agent input.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from research.independent_static_ml import ember_v2
from . import evidence_projection as proj
from . import static_only, agent_replay, rubric, metrics

REPO_ROOT = Path(__file__).resolve().parents[2]


def extract_audit_records(jsonl_path: Path, shas: set, out_path: Path) -> Dict[str, dict]:
    """Scan the test JSONL once; keep only the audit records. Cache to disk."""
    if out_path.exists():
        recs = {}
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                recs[r["sha256"]] = r
        if shas.issubset(set(recs)):
            return {s: recs[s] for s in shas}
    found = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            # cheap pre-filter before full parse
            r = json.loads(line)
            if r.get("sha256") in shas:
                found[r["sha256"]] = r
                if len(found) == len(shas):
                    break
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for s in sorted(found):
            f.write(json.dumps(found[s]) + "\n")
    return found


def build_prediction(record_sha, vector, booster, model_manifest, manifest_score):
    score = float(booster.predict(vector.reshape(1, -1))[0])
    threshold = float(model_manifest["threshold_selection"]["primary_threshold"])
    # determinism/consistency check vs the manifest score
    consistent = abs(score - float(manifest_score)) < 1e-9
    return {
        "track": proj.TRACK,
        "model_id": model_manifest["model_id"],
        "model_sha256": model_manifest["model_sha256"],
        "feature_version": 2, "feature_count": 2381,
        "raw_score": score, "threshold": threshold,
        "predicted_class": int(score >= threshold),
        "predicted_label": "malicious" if score >= threshold else "benign",
        "score_is_calibrated_probability": False,
        "score_matches_manifest": consistent,
        "limitations": [
            "Raw LightGBM score; NOT a calibrated probability.",
            "FEATURE_RECORD_REPLAY: score computed from an EMBER feature record, "
            "NOT from raw PE bytes (not a raw-PE E2E run).",
        ],
    }


def qwen_config_snapshot(acfg) -> Dict[str, Any]:
    snap = {"model": acfg.model, "ollama_host": acfg.ollama_host,
            "temperature": acfg.temperature, "num_predict": acfg.num_predict,
            "think": acfg.think, "inference_timeout_s": acfg.inference_timeout_s}
    try:
        import urllib.request
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                acfg.ollama_host.rstrip("/") + "/api/tags", timeout=8) as r:
            tags = json.loads(r.read().decode("utf-8"))
        for m in tags.get("models", []):
            if m.get("name") == acfg.model:
                snap["model_digest"] = m.get("digest")
                snap["ollama_details"] = m.get("details")
    except Exception as exc:
        snap["model_digest"] = f"unavailable: {type(exc).__name__}"
    return snap


def run_evaluation(*, manifest_path, model_path, model_manifest_path, jsonl_path,
                   out_dir, records_cache, cache_dir="D:/datasets/ember2018-cache",
                   agent=True, limit=None, agent_cfg=None, planner=None):
    import lightgbm as lgb

    out_dir = Path(out_dir)
    (out_dir / "samples").mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    model_manifest = json.loads(Path(model_manifest_path).read_text(encoding="utf-8"))
    samples = manifest["audit_samples"]
    if limit:
        samples = samples[:limit]
    shas = {s["sha256"] for s in samples}
    records = extract_audit_records(Path(jsonl_path), shas, Path(records_cache))

    booster = lgb.Booster(model_file=str(model_path))

    if agent:
        from agent.config import AgentConfig
        acfg = agent_cfg or replace(AgentConfig.from_env(), think=False)
        if planner is None:
            from agent.planner import OllamaPlanner
            planner = OllamaPlanner(acfg)
        qsnap = qwen_config_snapshot(acfg)
    else:
        acfg, qsnap = None, {"note": "agent disabled for this run"}

    per_sample: List[Dict[str, Any]] = []
    for i, smeta in enumerate(samples):
        sha = smeta["sha256"]
        record = records.get(sha)
        if record is None:
            continue
        vector = ember_v2.process_raw_record(record)
        prediction = build_prediction(sha, vector, booster, model_manifest, smeta["score"])
        projection = proj.project_record(record)
        prediction_obs = proj.prediction_observation(sha, prediction)
        valid_ids = rubric.valid_evidence_ids(projection, prediction_obs)

        static_rep = static_only.static_only_report(prediction, projection)
        static_auto = rubric.auto_checks(static_rep, valid_ids=valid_ids, branch="STATIC_ONLY")

        # branch B (resume-aware): reuse a completed OK agent run.
        sample_path = out_dir / "samples" / f"{sha}.json"
        agent_rep = None
        if agent:
            if sample_path.exists():
                prior = json.loads(sample_path.read_text(encoding="utf-8"))
                if prior.get("agent", {}).get("report", {}).get("run_status") == "OK":
                    agent_rep = prior["agent"]["report"]
            if agent_rep is None:
                agent_rep = agent_replay.assess_sample(sha, projection, prediction_obs, acfg, planner)
        else:
            agent_rep = {"run_status": "SKIPPED", "assessment": None, "latency_s": None}
        agent_auto = rubric.auto_checks(agent_rep, valid_ids=valid_ids, branch="STATIC_PLUS_AGENT")

        row = {
            "sha256": sha, "strata": smeta["strata"],
            "true_label_evaluator_only": smeta["true_label"],
            "predicted_label": prediction["predicted_label"],
            "score": prediction["raw_score"], "score_matches_manifest": prediction["score_matches_manifest"],
            "static": {"report": static_rep, "auto": static_auto},
            "agent": {"report": agent_rep, "auto": agent_auto},
        }
        # Persist per-sample (resume cache + audit trail).
        sample_path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        per_sample.append(row)
        if agent and agent_rep.get("run_status") == "OK":
            print(f"[{i+1}/{len(samples)}] {sha[:12]} {smeta['strata']} "
                  f"pred={prediction['predicted_label']} "
                  f"align={(agent_rep.get('assessment') or {}).get('evidence_alignment')} "
                  f"lat={agent_rep.get('latency_s')}s", flush=True)
        elif agent:
            print(f"[{i+1}/{len(samples)}] {sha[:12]} {smeta['strata']} "
                  f"AGENT_STATUS={agent_rep.get('run_status')}", flush=True)

    # Aggregate. Detection metrics are over the FULL labeled test (identical for both branches).
    detection = metrics.detection_metrics(
        cache_dir=Path(cache_dir), model_path=model_path,
        threshold=float(model_manifest["threshold_selection"]["primary_threshold"]))
    investigation = metrics.aggregate_investigation(per_sample)

    results = {
        "schema_version": "task05c-results-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track": proj.TRACK,
        "manifest_sha256": manifest.get("manifest_sha256"),
        "n_samples_evaluated": len(per_sample),
        "versions": {
            "baseline": static_only.baseline_version(),
            "prompt": agent_replay.prompt_version(),
            "rubric": rubric.rubric_version(),
            "qwen": qsnap,
            "model_id": model_manifest["model_id"],
            "model_sha256": model_manifest["model_sha256"],
        },
        "detection_metrics_full_test": detection,
        "investigation_metrics": investigation,
    }
    (out_dir / "eval_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_comparison_csv(out_dir / "comparison_table.csv", results)
    _write_annotation_package(out_dir, per_sample)
    return results


def _write_comparison_csv(path, results):
    inv = results["investigation_metrics"]["overall"]
    det = results.get("detection_metrics_full_test") or {}
    rows = [
        ["metric", "static_only", "static_plus_agent", "difference", "note"],
        ["detection_roc_auc", det.get("roc_auc"), det.get("roc_auc"), 0,
         "identical: same model/score/threshold"],
        ["detection_recall_tpr", det.get("recall_tpr"), det.get("recall_tpr"), 0, "identical"],
        ["detection_fpr", det.get("false_positive_rate"), det.get("false_positive_rate"), 0, "identical"],
        ["citation_validity_mean", inv["static"]["citation_validity_mean"],
         inv["agent"]["citation_validity_mean"],
         _diff(inv["agent"]["citation_validity_mean"], inv["static"]["citation_validity_mean"]),
         "auto"],
        ["unsupported_claim_rate", inv["static"]["unsupported_claim"]["rate"],
         inv["agent"]["unsupported_claim"]["rate"],
         _diff(inv["agent"]["unsupported_claim"]["rate"], inv["static"]["unsupported_claim"]["rate"]),
         "auto; lower is better"],
        ["safety_violation_rate", inv["static"]["safety_violation"]["rate"],
         inv["agent"]["safety_violation"]["rate"],
         _diff(inv["agent"]["safety_violation"]["rate"], inv["static"]["safety_violation"]["rate"]),
         "auto; must be 0"],
        ["review_required_rate", inv["static"]["review_required"]["rate"],
         inv["agent"]["review_required"]["rate"],
         _diff(inv["agent"]["review_required"]["rate"], inv["static"]["review_required"]["rate"]),
         "triage rate; not quality by itself"],
        ["agent_latency_s_mean", "n/a", inv["agent"].get("latency_s_mean"), "", "cost"],
        ["agent_eval_tokens_mean", "n/a", inv["agent"].get("eval_tokens_mean"), "", "cost"],
        ["agent_schema_failure_rate", "n/a", (inv["agent"].get("schema_or_assessment_failure") or {}).get("rate"), "", "agent robustness"],
        ["explanation_semantic_rubric", "CHƯA CHẤM", "CHƯA CHẤM", "", "requires independent human grading"],
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def _diff(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return round(a - b, 4)
    return ""


def _write_annotation_package(out_dir, per_sample):
    pkg = out_dir / "annotation_package"
    pkg.mkdir(parents=True, exist_ok=True)
    forms = []
    mapping = []
    for r in per_sample:
        sid = r["sha256"][:16]
        # Blind: present both branches under neutral labels X/Y (randomise mapping per sample).
        import hashlib
        swap = int(hashlib.sha256((r["sha256"] + "blind").encode()).hexdigest(), 16) % 2
        a_label, b_label = ("X", "Y") if swap == 0 else ("Y", "X")
        forms.append({"sample_id": sid, "report_label": a_label,
                      "report_text": r["static"]["report"]["explanation"]} |
                     rubric.blank_annotation_form(sid, a_label))
        agent_ass = r["agent"]["report"].get("assessment") or {}
        forms.append({"sample_id": sid, "report_label": b_label,
                      "report_text": agent_ass.get("explanation", "")} |
                     rubric.blank_annotation_form(sid, b_label))
        mapping.append({"sample_id": sid, "X_is": "STATIC_ONLY" if swap == 0 else "STATIC_PLUS_AGENT",
                        "Y_is": "STATIC_PLUS_AGENT" if swap == 0 else "STATIC_ONLY"})
    (pkg / "annotation_forms_blind.json").write_text(
        json.dumps(forms, ensure_ascii=False, indent=2), encoding="utf-8")
    (pkg / "branch_mapping_EVALUATOR_ONLY.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    (pkg / "README.md").write_text(
        "# Gói chấm điểm (blind)\n\n"
        "- `annotation_forms_blind.json`: mỗi mẫu có 2 phiếu (X và Y), ẩn nhánh.\n"
        "- Chấm các tiêu chí semantic (A2,B1,B2,C1,D1) thang 0-2 theo rubric.\n"
        "- `branch_mapping_EVALUATOR_ONLY.json`: ánh xạ X/Y -> nhánh (chỉ mở sau khi chấm).\n"
        "- Không dùng LLM để chấm; không tự chấm nhánh của mình.\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run TASK 05C evaluation")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--model-manifest", required=True)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--records-cache", required=True)
    ap.add_argument("--cache-dir", default="D:/datasets/ember2018-cache")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-agent", action="store_true")
    args = ap.parse_args(argv)
    results = run_evaluation(
        manifest_path=args.manifest, model_path=args.model,
        model_manifest_path=args.model_manifest, jsonl_path=args.jsonl,
        out_dir=args.out, records_cache=args.records_cache, cache_dir=args.cache_dir,
        agent=not args.no_agent, limit=args.limit)
    print(json.dumps({"n": results["n_samples_evaluated"],
                      "detection_auc": (results.get("detection_metrics_full_test") or {}).get("roc_auc"),
                      "agent_overall": results["investigation_metrics"]["overall"]["agent"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
