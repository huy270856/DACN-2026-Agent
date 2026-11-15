"""Reproducible DEV-only paired one-shot replay. No tool execution or target PE.

Usage: python -m evaluation.task06a.experiment prepare|run|summarize --out ...
Prepare freezes code/config/data before inference; run refuses configuration drift.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import time
import urllib.request

from agent.config import AgentConfig
from agent.context import build_context
from agent.planner import OllamaPlanner
from evaluation.task05c import agent_replay, evidence_projection
from .assessor_v2 import assess_once_v2, build_context_v2, prompt_version_v2
from .verification import screen

ROOT = Path(__file__).resolve().parents[2]
MM = ROOT / "research/independent_static_ml/artifacts/model_manifest.json"
MODEL = MM.with_name("model_lightgbm.txt")
BASELINE = "edd0a255cddcc40499f988cf806ed78505dbca8a"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def snapshots():
    # Immutable old benchmarks, baseline code, and the implementation used in this run.
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    paths = {p for p in tracked if p.startswith(("agent/", "evaluation/task05c/", "evaluation/task05d/",
                                               "research/independent_static_ml/artifacts/"))}
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "evaluation/task06a").glob("*.py"))
    return {p: digest(ROOT / p) for p in sorted(paths)}


def ollama_json(route):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            "http://127.0.0.1:11434/api/" + route, timeout=8) as r:
        return json.load(r)


def prepare(out, data, per_label=12):
    if out.exists():
        raise ValueError("Output already exists; use a new versioned directory")
    subprocess.run(["git", "diff", "--exit-code", BASELINE, "--", "agent", "evaluation/task05c"],
                   cwd=ROOT, check=True, capture_output=True)
    mm = read(MM)
    if digest(MODEL) != mm["model_sha256"]:
        raise ValueError("Model digest mismatch")
    # Collect ALL recorded SHA strings, not just the 120 audit IDs. Includes 16 probe,
    # pilot, real PE and provisional output artifacts. Extra model hashes are harmless.
    exclusions, exclusion_sources = set(), {}
    for base in (ROOT / "evaluation/task05c", ROOT / "evaluation/task05d"):
        for p in sorted(base.rglob("*.json")):
            found = set(re.findall(r"\b[0-9a-f]{64}\b", p.read_text(encoding="utf-8")))
            exclusions.update(found)
            exclusion_sources[p.relative_to(ROOT).as_posix()] = digest(p)
    print("Checking full official test SHA disjointness (no test feature inference)...", flush=True)
    test_sha, test_hash = set(), hashlib.sha256()
    with (data / "test_features.jsonl").open("rb") as f:
        for line in f:
            test_hash.update(line)
            match = re.search(rb'"sha256"\s*:\s*"([0-9a-f]{64})"', line)
            if match:
                test_sha.add(match[1].decode())
    if len(test_sha) != 200000:
        raise ValueError("Official test SHA count unexpected")
    excluded = exclusions | test_sha
    selected, counts, shard_hash = [], Counter(), hashlib.sha256()
    shard = data / "train_features_1.jsonl"
    # Deterministic balanced convenience DEV, no model scores or LLM outputs used to select.
    with shard.open("rb") as f:
        for number, line in enumerate(f, 1):
            shard_hash.update(line)
            if number <= 1000 or all(counts[y] >= per_label for y in (0, 1)):
                continue
            record = json.loads(line)
            sha, y = record["sha256"], record.get("label")
            if y not in (0, 1) or counts[y] >= per_label or sha in excluded:
                continue
            excluded.add(sha)
            counts[y] += 1
            selected.append((number, y, record))
    if len(selected) != per_label * 2:
        raise ValueError("Not enough eligible records")
    import lightgbm as lgb
    import numpy as np
    from research.independent_static_ml.ember_v2 import process_raw_record
    booster = lgb.Booster(model_file=str(MODEL))
    cfg = AgentConfig()  # fixed defaults, never read operator env for this comparison
    tags = ollama_json("tags")
    model_info = next(m for m in tags["models"] if m["name"] == cfg.model)
    manifest_rows, inputs = [], []
    threshold = mm["threshold_selection"]["primary_threshold"]
    for number, y, record in selected:
        sha = record["sha256"]
        score = float(booster.predict(np.asarray(process_raw_record(record)).reshape(1, -1))[0])
        prediction = {"predicted_label": "malicious" if score >= threshold else "benign",
                      "raw_score": score, "threshold": threshold, "model_id": mm["model_id"],
                      "model_sha256": mm["model_sha256"], "score_is_calibrated_probability": False,
                      "track": "FEATURE_RECORD_REPLAY"}
        sanitized = {k: v for k, v in record.items() if k not in {"label", "avclass"}}
        projection = evidence_projection.project_record(sanitized)
        state = agent_replay.build_replay_state(sha, projection,
                  evidence_projection.prediction_observation(sha, prediction))
        c1, c2 = build_context(state, [], cfg, []), build_context_v2(state, cfg)
        assert c1["facts"] == c2["facts"]
        for c in (c1, c2):
            agent_replay._assert_no_ground_truth(c["system"] + c["user"])
        inputs.append({"sha256": sha, "state": state, "prediction": prediction,
                       "projection": projection})
        manifest_rows.append({"sha256": sha, "source_line": number, "true_label": y,
                              "record_sha256": hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest(),
                              "correctness": ("T" if int(score >= threshold) == y else "F") + ("P" if score >= threshold else "N"),
                              "score": score, "appeared": record.get("appeared")})
    out.mkdir(parents=True)
    write_new(out / "inputs.json", inputs)
    manifest = {"schema_id": "task06a-dev-manifest-v1", "track": "FEATURE_RECORD_REPLAY",
                "source": str(shard), "source_sha256": shard_hash.hexdigest(),
                "selection": f"first {per_label} records per label after line 1000 in train shard 1; exclude prior/test SHA",
                "official_test_sha_count": len(test_sha), "official_test_file_sha256": test_hash.hexdigest(),
                "overlap_official_test": len({r["sha256"] for r in manifest_rows} & test_sha),
                "overlap_prior_artifacts": len({r["sha256"] for r in manifest_rows} & exclusions),
                "prior_artifacts_sha256": exclusion_sources, "prior_sha_count": len(exclusions),
                "detector_independence": "NO: train source used to fit/validate detector; not a detection holdout",
                "prior_unsaved_inference_overlap": "UNKNOWN; only repository artifacts are auditable",
                "samples": manifest_rows}
    write_new(out / "manifest_EVALUATOR_ONLY.json", manifest)
    freeze = {"created_utc": datetime.now(timezone.utc).isoformat(), "baseline_commit": BASELINE,
              "config": asdict(cfg), "max_attempts_per_arm": 1, "branch_order": "alternate by case index",
              "tools": [], "money_cost": "N/A local inference; token counts measured",
              "v1": agent_replay.prompt_version(), "v2": prompt_version_v2(),
              "model_sha256": digest(MODEL), "ollama_model": model_info,
              "ollama_version": ollama_json("version"),
              "environment": {"python": platform.python_version(), "platform": platform.platform(),
                              "packages": {p: importlib.metadata.version(p) for p in ("lightgbm", "numpy", "jsonschema", "pytest")}},
              "source_sha256": snapshots(), "inputs_sha256": digest(out / "inputs.json"),
              "manifest_sha256": digest(out / "manifest_EVALUATOR_ONLY.json")}
    write_new(out / "freeze.json", freeze)
    print(f"Prepared/frozen {len(inputs)} cases: {out}", flush=True)


class RecordingPlanner:
    """Records the unmodified production planner response and exact context."""
    def __init__(self, cfg):
        self.inner = OllamaPlanner(cfg)
        self.calls = []

    def decide(self, context):
        result = self.inner.decide(context)
        self.calls.append({"context": dict(context), "raw": result.raw,
                           "meta": result.meta, "latency_s": result.latency_s})
        return result


def validate_freeze(out):
    frozen = read(out / "freeze.json")
    if snapshots() != frozen["source_sha256"]:
        raise ValueError("Code or old benchmark drift since freeze")
    if digest(out / "inputs.json") != frozen["inputs_sha256"] or digest(out / "manifest_EVALUATOR_ONLY.json") != frozen["manifest_sha256"]:
        raise ValueError("Data drift since freeze")
    if digest(MODEL) != frozen["model_sha256"]:
        raise ValueError("Model drift")
    return frozen


def run(out):
    frozen = validate_freeze(out)
    cfg = AgentConfig(**frozen["config"])
    info = next(m for m in ollama_json("tags")["models"] if m["name"] == cfg.model)
    if info["digest"] != frozen["ollama_model"]["digest"]:
        raise ValueError("Qwen model drift")
    if ollama_json("version") != frozen["ollama_version"]:
        raise ValueError("Ollama version drift")
    # The runner never reads evaluator manifest contents. It only checks its digest.
    for n, item in enumerate(read(out / "inputs.json")):
        for arm in (("v1", "v2") if n % 2 == 0 else ("v2", "v1")):
            target = out / "responses" / f"{n:03d}_{arm}.json"
            if target.exists():
                prior = read(target)
                if prior["sha256"] != item["sha256"] or prior["arm"] != arm:
                    raise ValueError("Resume artifact identity mismatch")
                continue  # never overwrite saved inference, including failures
            state = item["state"]
            ctx = build_context(state, [], cfg, []) if arm == "v1" else build_context_v2(state, cfg)
            agent_replay._assert_no_ground_truth(ctx["system"] + ctx["user"])
            planner = RecordingPlanner(cfg)
            started = time.monotonic()
            if arm == "v1":
                result = agent_replay.run_agent_once(state, cfg, planner, max_attempts=1)
                assessment = agent_replay.extract_assessment(result["proposal"]) if result["status"] == "OK" else {}
                assessment["alignment"] = assessment.get("evidence_alignment")
                assessment["recommendation"] = assessment.get("agent_recommendation")
                raw = planner.calls
            else:
                result = assess_once_v2(state, cfg, planner.inner, max_attempts=1)
                assessment = result.get("assessment", {})
                raw = result.get("attempts", [])
            elapsed = time.monotonic() - started
            from jsonschema import Draft202012Validator
            from agent.schema import OLLAMA_FORMAT_SCHEMA
            from .schema_v2 import OLLAMA_FORMAT_SCHEMA_V2
            contract = OLLAMA_FORMAT_SCHEMA if arm == "v1" else OLLAMA_FORMAT_SCHEMA_V2
            decoded_schema_valid = False
            if raw:
                try:
                    obj = json.loads(raw[-1]["raw"])
                    decoded_schema_valid = not list(Draft202012Validator(contract).iter_errors(obj))
                except (ValueError, KeyError):
                    pass
            checks = screen(assessment, ctx["facts"], item["prediction"])
            write_new(target, {"sha256": item["sha256"], "arm": arm, "inference_kind": "LOCAL_QWEN",
                               "context": ctx, "run": result, "raw_calls": raw, "assessment": assessment,
                               "screen": checks, "total_latency_s": elapsed,
                               "decoded_schema_valid": decoded_schema_valid})
            print(f"{n + 1:02d} {arm} {result['status']} {elapsed:.2f}s {assessment.get('alignment')}", flush=True)
    validate_freeze(out)


def summarize(out):
    validate_freeze(out)
    rows = {arm: [read(p) for p in sorted((out / "responses").glob(f"*_{arm}.json"))] for arm in ("v1", "v2")}
    total = len(read(out / "inputs.json"))
    metrics = {}
    for arm, cases in rows.items():
        refs = sum(r["screen"]["citation_count"] for r in cases)
        metrics[arm] = {
            "n": len(cases), "expected_n": total,
            "schema_valid": sum(r["run"]["status"] == "OK" for r in cases),
            "decoded_schema_valid": sum(r["decoded_schema_valid"] for r in cases),
            "non_finish_action": sum(r["assessment"].get("action") != "FINISH" for r in cases) if arm == "v1" else 0,
            "valid_citation_count": sum(r["screen"]["valid_citation_count"] for r in cases),
            "citation_count": refs,
            "cases_with_citations": sum(r["screen"]["citation_count"] > 0 for r in cases),
            "cases_with_invalid_citations": sum(bool(r["screen"]["invalid_ids"]) for r in cases),
            "grounding_screen_flags": sum(not r["screen"]["grounding_screen"]["grounded"] for r in cases),
            "unsupported_specifics_suspected": sum(r["screen"]["grounding_screen"]["unsupported_specifics_count"] for r in cases),
            "structured_claim_flag_cases": sum(bool(r["screen"]["claim_flags"]) for r in cases),
            "visible_value_incomplete_cases": sum(bool(r["screen"]["incomplete_visible_ids"]) for r in cases),
            "decision_inconsistent": sum(not r["screen"]["consistency"]["consistent"] for r in cases),
            "raw_review_load": sum(r["assessment"].get("review_required") is True for r in cases),
            "effective_review_load": sum(r["screen"]["effective_recommendation"]["review_required"] for r in cases),
            "invalid_recommendation": sum("invalid_or_missing_recommendation" in r["screen"]["consistency"]["flags"] for r in cases),
            "alignment": dict(Counter(r["assessment"].get("alignment", "MISSING") for r in cases)),
            "latency_s_mean": sum(r["total_latency_s"] for r in cases) / len(cases) if cases else None,
            "prompt_tokens": sum((c.get("meta") or {}).get("prompt_eval_count") or 0 for r in cases for c in r["raw_calls"]),
            "output_tokens": sum((c.get("meta") or {}).get("eval_count") or 0 for r in cases for c in r["raw_calls"]),
            "tool_calls_executed": 0, "tool_call_validity": "N/A no tools available",
            "semantic_grounding": "PENDING independent review; regex flags are suspects only",
            "appropriate_uncertainty": "PENDING independent review; alignment distribution is not correctness",
        }
    paired = []
    for v1, v2 in zip(rows["v1"], rows["v2"]):
        if v1["sha256"] != v2["sha256"]:
            raise ValueError("Unpaired results")
        def errors(r):
            return {"invalid_citations": bool(r["screen"]["invalid_ids"]),
                    "decision_inconsistent": not r["screen"]["consistency"]["consistent"],
                    "grounding_screen_flag": not r["screen"]["grounding_screen"]["grounded"]}
        a, b = errors(v1), errors(v2)
        paired.append({"sha256": v1["sha256"], "v1": a, "v2": b,
                       "improved_flags": [k for k in a if a[k] and not b[k]],
                       "regressed_flags": [k for k in a if b[k] and not a[k]]})
    summary = {"status": "DEV_COMPLETE" if all(len(x) == total for x in rows.values()) else "PARTIAL",
               "metrics": metrics, "paired": paired,
               "confirmatory": "NOT_RUN; no generalization or detection improvement claim",
               "human_grading": "PENDING", "judge": "deterministic screens only; NO LLM judge"}
    write_new(out / "summary.json", summary)
    print(json.dumps(metrics, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("prepare", "run", "summarize"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data", type=Path, default=Path("D:/datasets/ember2018-v2"))
    args = ap.parse_args()
    if args.action == "prepare":
        prepare(args.out, args.data)
    elif args.action == "run":
        run(args.out)
    else:
        summarize(args.out)


if __name__ == "__main__":
    main()
