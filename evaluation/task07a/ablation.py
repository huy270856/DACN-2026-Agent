"""TASK 07A ablation harness CLI: prepare / run / smoke (arm C only; DEV_DIAGNOSTIC).

Reuses the frozen 06B-J runner for staging, Node B intake, detector run, initial contexts,
leakage audit, freeze and validation (`runner.prepare`, `runner.validate_freeze`,
`runner.question`, `runner.isolation_checks`, `runner.write_new`). The ~30-line per-case
loop of `runner.run` is DUPLICATED here (not imported) because the 06B-J runner is frozen and
must not be modified, and its loop hardcodes `runner.CFG`, `workflow_v34.Planner` and arms B/C.

Write-once: every output goes through `write_new`; a new run needs a new --out directory.
A crashed case is recorded (HARNESS_EXCEPTION) and counted; it is never retried.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest import mock

import case_manager as cm
from dacn import investigation as inv
from dacn.config import AppConfig
from investigation_v3 import audit, workflow_v34
from evaluation.task06b_j import leakage, questions, runner
from evaluation.task07a import variants

ROOT = runner.ROOT
RUNNER_VERSION = "task07a-ablation-v1"
HOLDOUT_MANIFEST = ROOT / "evaluation/task06b_j/results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json"
SMOKE_MANIFEST = ROOT / "evaluation/task06b_j/results/dev/staging_smoke_cases_v1.json"
HARNESS_FILES = ["evaluation/task07a/variants.py", "evaluation/task07a/ablation.py",
                 "evaluation/task07a/metrics.py"]
TRACK = "RAW_PE_E2E"
KIND = "DEV_DIAGNOSTIC"


def harness_hashes() -> Dict[str, str]:
    return {m: runner.file_sha(ROOT / m) for m in HARNESS_FILES}


def _filtered_manifest(src: Path, classes, limit: Optional[int] = None) -> Dict[str, Any]:
    man = runner.read(src)
    cases = [c for c in man["cases"] if c.get("accessibility_class", None) in classes] if classes else list(man["cases"])
    if limit is not None:
        cases = cases[:limit]
    out = dict(man, cases=cases)
    try:
        name = src.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        name = str(src)
    out["task07a_filter"] = {"source_manifest": name, "source_sha256": runner.file_sha(src),
                             "classes": list(classes) if classes else None, "limit": limit,
                             "aliases": [c["alias"] for c in cases]}
    return out


def prepare(variant: str, seed: int, out: Path, *, manifest: Path = HOLDOUT_MANIFEST, smoke: bool = False,
            runtime_root: Path = runner.RUNTIME, ollama_info: Optional[Dict[str, Any]] = None,
            signer_lookup: bool = True) -> Dict[str, Any]:
    if out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out}")
    cfg, _ = variants.make_cfg(variant, seed)
    classes = None if smoke else variants.VARIANTS[variant]["classes"]
    filtered = _filtered_manifest(manifest, classes, limit=1 if smoke else None)
    with tempfile.TemporaryDirectory(prefix="t07a-") as tmp:
        mpath = Path(tmp) / "cases_manifest_filtered.json"
        mpath.write_text(json.dumps(filtered, indent=2), encoding="utf-8")
        # runner.CFG is patched only so freeze.json records THIS variant's AgentConfig;
        # initial_contexts() reads only context budgets, which are identical across variants.
        with mock.patch.object(runner, "CFG", cfg):
            freeze = runner.prepare(mpath, out, mode=KIND if not smoke else "DEV_SMOKE_07A",
                                    runtime_root=runtime_root, ollama_info=ollama_info,
                                    signer_lookup=signer_lookup)
    desc = variants.describe(variant, seed)
    desc.update(track=TRACK, evaluation_kind=KIND, smoke=smoke, confirmatory="NOT_RUN",
                cohort_note=("DEV smoke case outside the 07A cohort" if smoke else
                             "06B-J holdout cohort reused as DEV_DIAGNOSTIC (owner D1); never confirmatory again"),
                cohort_aliases=filtered["task07a_filter"]["aliases"], manifest_filter=filtered["task07a_filter"],
                runner_version=RUNNER_VERSION, harness_sha256=harness_hashes(),
                freeze_sha256=runner.file_sha(out / "freeze.json"))
    vsha = runner.write_new(out / "variant.json", desc)
    runner.write_new(out / "variant_lock.json", {"variant_json_sha256": vsha})
    return {"freeze": freeze, "variant": desc}


def validate_variant(out: Path) -> Dict[str, Any]:
    lock = runner.read(out / "variant_lock.json")
    if runner.file_sha(out / "variant.json") != lock["variant_json_sha256"]:
        raise ValueError("VARIANT_DRIFT: variant.json changed after prepare")
    v = runner.read(out / "variant.json")
    if v["harness_sha256"] != harness_hashes():
        raise ValueError("HARNESS_DRIFT")
    if runner.file_sha(out / "freeze.json") != v["freeze_sha256"]:
        raise ValueError("FREEZE_DRIFT")
    cfg, dec = variants.make_cfg(v["variant"], v["seed"])
    if asdict(cfg) != v["agent_config"] or asdict(dec) != v["decoding"]:
        raise ValueError("VARIANT_CONFIG_DRIFT")
    return v


def _planner(v: Dict[str, Any]):
    cfg, dec = variants.make_cfg(v["variant"], v["seed"])
    if v["planner"] == "ANALYSIS_FIRST":
        return variants.AnalysisFirstPlanner(cfg, dec)
    return variants.V34Planner(cfg, dec)


def run(out: Path, *, authorized_by: Optional[str] = None,
        planner_factory: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    is_mock = planner_factory is not None
    if not is_mock and not authorized_by:
        raise PermissionError("Owner authorization string required for a live Qwen run")
    f = runner.validate_freeze(out, allow_mock=is_mock)
    v = validate_variant(out)
    cfg, _ = variants.make_cfg(v["variant"], v["seed"])
    evaluator_manifest = {c["alias"]: c for c in runner.read(out / "EVALUATOR_ONLY" / "cases_manifest.json")["cases"]}
    done = []
    for row in runner.read(out / "cases.json"):
        alias = row["alias"]
        dest = out / f"{alias}_C.json"
        if dest.exists():
            continue  # already recorded (incl. failures); never re-run
        q = row.get("question") or questions.QUESTIONS[row["question_id"]]
        path = Path(row["case_paths"]["C"])
        state = cm.read_json(path)
        initial = runner.read(out / row["initial_file"])
        if state != initial:
            raise ValueError("STATE_CHANGED_WITHOUT_SAVED_TRACE_NO_RETRY")
        if runner.file_sha(Path(state["target_ref"]["observed"]["path"])) != row["sha256"]:
            raise ValueError("TARGET_DRIFT")
        config = AppConfig.from_home(Path(row["homes"]["C"]))
        reg, orch = inv.build_detector_backend(config, include_imports=True)
        events: List[Dict[str, Any]] = []
        policy = audit.attach(orch, events)
        planner = planner_factory(alias) if is_mock else _planner(v)
        oracle_record: List[Dict[str, Any]] = []
        try:
            with runner.question(q):
                if v["oracle"]:
                    lits = variants.load_relevant(evaluator_manifest[alias].get("reference_EVALUATOR_ONLY"))
                    with variants.oracle_pages(lits, oracle_record):
                        report = workflow_v34.run(path, cfg, reg, orch, policy, planner=planner,
                                                  tool_enabled=True, events=events)
                else:
                    report = workflow_v34.run(path, cfg, reg, orch, policy, planner=planner,
                                              tool_enabled=True, events=events)
        except Exception as exc:  # recorded and counted in the denominator; never retried
            report = {"status": "HARNESS_EXCEPTION", "failure": f"{type(exc).__name__}: {exc}",
                      "traceback": traceback.format_exc(), "turns": [], "final": None,
                      "initial_state": initial, "final_state": cm.read_json(path), "events": events,
                      "latency_s": None, "tool_attempts": None, "retrieval_attempts": None}
        report.update(arm="C", alias=alias, question_id=row["question_id"], question=q,
                      end_to_end_latency_s=(report["latency_s"] + row["static_latency_s"])
                      if report.get("latency_s") is not None else None,
                      authorized_by=authorized_by, runner_version=RUNNER_VERSION, variant=v["variant"],
                      seed=v["seed"], evaluation_kind=KIND, track=TRACK, oracle_variant=v["oracle"],
                      planner_kind_07a="MOCK_LLM" if is_mock else "LOCAL_QWEN")
        if report["status"] != "HARNESS_EXCEPTION":
            report["isolation_checks"] = runner.isolation_checks(report, initial, "C", q)
        runner.write_new(dest, report)
        lk = runner.read(out / "EVALUATOR_ONLY" / f"{alias}_leakage.json")
        hits = [dict(h, turn=t["iteration"]) for t in report.get("turns", [])
                for h in leakage.scan_facts(t["context"]["facts"], lk["tokens"])]
        runner.write_new(out / "EVALUATOR_ONLY" / f"{alias}_C_leakage_all_turns.json",
                         {"summary": leakage.summarize(hits), "hits": hits})
        if v["oracle"]:
            runner.write_new(out / "EVALUATOR_ONLY" / f"{alias}_C_oracle.json",
                             {"label": "ORACLE_DIAGNOSTIC", "per_turn": oracle_record})
        passed = (report.get("isolation_checks") or {}).get("passed")
        done.append((alias, report["status"], passed))
        print(alias, v["variant"], v["seed"], report["status"], report.get("failure"), "isolation", passed, flush=True)
    return {"mode": f["mode"], "variant": v["variant"], "seed": v["seed"],
            "planner": "MOCK_LLM" if is_mock else "LOCAL_QWEN", "runs": done}


def smoke_gate(out: Path) -> Dict[str, Any]:
    """G1 (V1) / G2 (V2) checks on the smoke trace. Deterministic; no semantic judgment."""
    v = runner.read(out / "variant.json")
    rows = []
    for p in sorted(out.glob("*_C.json")):
        r = runner.read(p)
        turns = r.get("turns", [])
        rows.append({
            "alias": r["alias"], "status": r["status"], "failure": r.get("failure"), "turns": len(turns),
            "validation_errors": [t.get("validation_error") for t in turns if t.get("validation_error")],
            "turn_errors": [t.get("error") for t in turns if t.get("error")],
            "done_reasons": [(t.get("meta") or {}).get("done_reason") for t in turns],
            "thinking_chars": [(t.get("meta") or {}).get("thinking_chars") for t in turns],
            "analysis_first": [(t.get("meta") or {}).get("analysis_first") for t in turns],
            "analysis_parse": [(t.get("meta") or {}).get("analysis_parse") for t in turns],
            "proposal_parsed": [t.get("proposal") is not None for t in turns],
            "prompt_plus_output": [((t.get("meta") or {}).get("prompt_eval_count") or 0)
                                   + ((t.get("meta") or {}).get("eval_count") or 0) for t in turns]})
    ok = bool(rows)
    for x in rows:
        answered = [i for i, e in enumerate(x["done_reasons"]) if e is not None]
        ok &= bool(x["turns"]) and all(x["proposal_parsed"]) and "length" not in x["done_reasons"]
        ok &= not any("empty content" in str(e) for e in x["turn_errors"] + [x["failure"]])
        ok &= len(answered) == x["turns"]
        if v["variant"] == "V1":
            ok &= all((c or 0) > 0 for c in x["thinking_chars"])
        if v["variant"] == "V2":
            ok &= all(a is True for a in x["analysis_first"])
    return {"gate": {"V1": "G1", "V2": "G2"}.get(v["variant"], "N/A"), "variant": v["variant"],
            "result": "PASS" if ok else "FAIL", "num_ctx": v["decoding"]["num_ctx"], "rows": rows,
            "kind": "DETERMINISTIC_GATE_CHECK_NOT_SEMANTIC"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 07A diagnostic ablation harness (arm C, DEV_DIAGNOSTIC)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--variant", choices=sorted(variants.VARIANTS), required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--authorized-by", required=True)
    s = sub.add_parser("smoke")
    s.add_argument("--variant", choices=("V1", "V2"), required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--authorized-by", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        res = prepare(a.variant, a.seed, a.out)
        print(json.dumps({"ollama": res["freeze"]["ollama"], "cohort": res["variant"]["cohort_aliases"]}, indent=2))
    elif a.cmd == "run":
        print(json.dumps(run(a.out, authorized_by=a.authorized_by), indent=2))
    else:
        seed = variants.VARIANTS[a.variant]["seeds"][0]
        prepare(a.variant, seed, a.out, manifest=SMOKE_MANIFEST, smoke=True)
        run(a.out, authorized_by=a.authorized_by)
        gate = smoke_gate(a.out)
        runner.write_new(a.out / "smoke_gate.json", gate)
        print(json.dumps({k: gate[k] for k in ("gate", "variant", "result")}, indent=2))


if __name__ == "__main__":
    main()
