"""TASK 06B-J controlled 3-arm runner (evaluation harness; Agent source is NOT modified).

A STATIC_ONLY          deterministic template from the frozen detector output (no LLM)
B AGENT_NO_TOOL        workflow_v34.run(tool_enabled=False): no analyzer, no retrieval
C AGENT_TOOL_ENABLED   workflow_v34.run(tool_enabled=True): Controller -> D1-D9 analyzer, bounded retrieval

Per case: one neutral-name staged copy (bytes copied, SHA verified before/after), ONE Node B
intake + ONE detector run (in C's home); B gets a byte-identical clone of that CaseState in a
separate home/artifact root, so A/B/C share target SHA, initial evidence IDs, detector
score/label and question. The per-case question is injected at HARNESS level by patching the
module constant `investigation_v3.context.GOAL` while that case runs; every recorded turn is
checked to carry the assigned question. The Agent source files and their hashes are unchanged.

Outputs are write-once (`write_new`); a new run needs a new output directory. A non-MOCK run
requires a frozen, matching Qwen digest and an explicit owner authorization string.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from unittest import mock

import case_manager as cm
from agent.config import AgentConfig
from dacn import investigation as inv
from dacn.config import AppConfig
from investigation_v3 import application, audit, context as v3context, repair_context, workflow_v34, final_v34
from investigation_v3.workflow import InvestigationController
from evaluation.task06b_j import leakage, questions, rubric

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "evaluation/task06b/runtime"  # gitignored; staged PE copies never leave it
RUNNER_VERSION = "task06b-j-runner-v1"
# Identical to the 06B-R2 v3.4 DEBUG configuration (r2_debug.CFG); not tuned for 06B-J.
CFG = AgentConfig(max_iterations=5, max_tool_calls=1, max_context_chars=24000, num_predict=2048,
                  inference_timeout_s=90, wall_clock_s=180)
AGENT_SOURCES = ["investigation_v3/final_v34.py", "investigation_v3/workflow_v34.py",
                 "investigation_v3/repair_context.py", "investigation_v3/retrieval.py",
                 "investigation_v3/imports_tool.py", "investigation_v3/import_adapter.py",
                 "investigation_v3/grounding.py", "investigation_v3/context.py", "investigation_v3/workflow.py",
                 "investigation_v3/schema.py", "investigation_v3/application.py",
                 "agent/planner.py", "agent/controller.py", "agent/config.py"]
HARNESS_SOURCES = ["evaluation/task06b_j/runner.py", "evaluation/task06b_j/questions.py",
                   "evaluation/task06b_j/leakage.py", "evaluation/task06b_j/rubric.py"]


def file_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path: Path, obj: Any) -> str:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def read(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def source_hashes() -> Dict[str, str]:
    return {m: file_sha(ROOT / m) for m in AGENT_SOURCES + HARNESS_SOURCES}


@contextmanager
def question(text: str):
    """Harness-level question injection; the Agent code reads context.GOAL at call time."""
    with mock.patch.object(v3context, "GOAL", text):
        yield


def probe_ollama() -> Dict[str, Any]:
    from evaluation.task06b.experiment import ollama
    try:
        model = next(m for m in ollama("tags")["models"] if m["name"] == CFG.model)
        return {"status": "AVAILABLE", "model": model, "version": ollama("version")}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}


def stage(src: Path, targets_dir: Path, alias: str) -> Dict[str, Any]:
    """Copy-only neutral staging. PE bytes are never modified or executed."""
    before = file_sha(src)
    dest = targets_dir / f"{alias}.exe"
    if dest.exists():
        raise FileExistsError(f"staged target exists: {dest}")
    targets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    after, src_after = file_sha(dest), file_sha(src)
    if not (before == after == src_after):
        raise ValueError("STAGING_SHA_MISMATCH")
    return {"alias": alias, "staged_path": str(dest), "sha256_before": before, "sha256_after": after}


def static_report(state: Dict[str, Any], q: str, latency: float) -> Dict[str, Any]:
    pred = inv.read_prediction_evidence(state)["value"]
    return {"method": "STATIC_TEMPLATE_06B_R", "arm": "A", "question": q, "model_prediction": pred,
            "explanation": "Static prediction only; raw score uncalibrated; concrete imports unavailable.",
            "recommendation": inv.derive_recommendation(pred["predicted_label"], None), "latency_s": latency}


def initial_contexts(state, reg, orch, policy, q) -> Dict[str, Dict[str, Any]]:
    """Exactly the first-turn facts each Agent arm would receive (no inference)."""
    ids = {e["evidence_id"] for e in state["evidence"]}
    ctl = InvestigationController(reg, orch, CFG, state, policy)
    out = {}
    with question(q):
        for arm, tools in (("B", []), ("C", ctl.available_tools(state))):
            out[arm] = repair_context.build(state, tools, CFG, initial_ids=ids, history=[], pages={},
                                            retrieval_available=False)["facts"]
    return out


def prepare(cases_manifest: Path, out: Path, *, mode: str, runtime_root: Path = RUNTIME,
            ollama_info: Optional[Dict[str, Any]] = None, signer_lookup: bool = True) -> Dict[str, Any]:
    if out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out}")
    man = read(cases_manifest)
    ollama_info = ollama_info if ollama_info is not None else probe_ollama()
    mm = inv.load_model_manifest()
    out.mkdir(parents=True)
    rows = []
    for c in man["cases"]:
        alias, src = c["alias"], Path(c["source"])
        if file_sha(src) != c["sha256"]:
            raise ValueError(f"TARGET_DRIFT {alias}")
        # Hashed run folder: the staged path the Agent sees must not reveal the run's purpose.
        root = runtime_root / ("r" + hashlib.sha256(out.name.encode("utf-8")).hexdigest()[:10]) / alias
        st = stage(src, root / "targets", alias)
        homes = {a: AppConfig.from_home(root / a) for a in ("B", "C")}
        t0 = time.monotonic()
        path, reg, orch, policy, events = application.prepare(homes["C"], file=st["staged_path"])
        static_latency = time.monotonic() - t0
        state = cm.validate_case(cm.read_json(path))
        homes["B"].cases_dir.mkdir(parents=True, exist_ok=True)
        clone = cm.case_path(homes["B"].cases_dir, state["case_id"])
        clone.parent.mkdir(parents=True, exist_ok=True)
        clone.write_bytes(path.read_bytes())
        q = questions.QUESTIONS[c["question_id"]]
        write_new(out / f"{alias}_initial_state.json", state)
        write_new(out / f"{alias}_initial_trusted_trace.json", events)
        write_new(out / f"{alias}_A.json", static_report(state, q, static_latency))
        ctxs = initial_contexts(state, reg, orch, policy, q)
        signer = None
        if signer_lookup:
            signer = leakage.authenticode([src]).get(str(src), {}).get("subject")
        tokens = leakage.identity_tokens(src, signer=signer)
        leak = {arm: (lambda h: {"summary": leakage.summarize(h), "hits": h})(leakage.scan_facts(f, tokens))
                for arm, f in ctxs.items()}
        write_new(out / "EVALUATOR_ONLY" / f"{alias}_leakage.json",
                  {"alias": alias, "original": str(src), "tokens": tokens, "initial_context": leak,
                   "staging": st})
        rows.append({"alias": alias, "sha256": c["sha256"], "question_id": c["question_id"],
                     "question_sha256": hashlib.sha256(q.encode("utf-8")).hexdigest(),
                     "case_id": state["case_id"], "initial_file": f"{alias}_initial_state.json",
                     "case_paths": {"B": str(clone), "C": str(path)},
                     "homes": {a: str(h.home) for a, h in homes.items()}, "static_latency_s": static_latency,
                     "initial_leakage_status": {a: v["summary"]["status"] for a, v in leak.items()}})
        print(alias, c["question_id"], "prepared", rows[-1]["initial_leakage_status"], flush=True)
    write_new(out / "cases.json", rows)
    write_new(out / "EVALUATOR_ONLY" / "cases_manifest.json", man)
    freeze = {"created_utc": datetime.now(timezone.utc).isoformat(), "runner_version": RUNNER_VERSION,
              "mode": mode, "confirmatory": "NOT_RUN", "base_commit": _git_head(),
              "agent_contract": final_v34.VERSION, "system_prompt_sha256": hashlib.sha256(final_v34.SYSTEM.encode()).hexdigest(),
              "source_hashes": source_hashes(), "config": asdict(CFG),
              "questions_version": questions.QUESTIONS_VERSION, "questions_sha256": questions.questions_sha256(),
              "rubric_id": rubric.RUBRIC_ID, "rubric_sha256": rubric.rubric_sha256(),
              "model_sha256": mm["model_sha256"], "threshold": mm["threshold_selection"]["primary_threshold"],
              "ollama": ollama_info, "cases_manifest_sha256": file_sha(cases_manifest),
              "initial_hashes": {p.name: file_sha(p) for p in sorted(out.glob("*.json"))},
              "arm_differences": {
                  "A": "no LLM; fixed template; question recorded but not answered",
                  "B": "same v3.4 prompt/schema; tools=[] and retrieval unavailable; loop bound min(3, max_iterations)",
                  "C": "same v3.4 prompt/schema; one analyzer call max, two 16-entry reads max; loop bound max_iterations",
                  "order": "B then C for even case index, C then B for odd"}}
    write_new(out / "freeze.json", freeze)
    return freeze


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "UNKNOWN"


def validate_freeze(out: Path, *, allow_mock: bool) -> Dict[str, Any]:
    f = read(out / "freeze.json")
    if f["source_hashes"] != source_hashes():
        raise ValueError("SOURCE_DRIFT")
    for name, h in f["initial_hashes"].items():
        if file_sha(out / name) != h:
            raise ValueError(f"INPUT_DRIFT {name}")
    mm = inv.load_model_manifest()
    if mm["model_sha256"] != f["model_sha256"] or mm["threshold_selection"]["primary_threshold"] != f["threshold"]:
        raise ValueError("MODEL_DRIFT")
    if not allow_mock:
        now = probe_ollama()
        if f["ollama"].get("status") != "AVAILABLE" or now.get("status") != "AVAILABLE":
            raise RuntimeError("BLOCKED_OLLAMA_UNAVAILABLE")
        if now["model"]["digest"] != f["ollama"]["model"]["digest"] or now["version"] != f["ollama"]["version"]:
            raise ValueError("QWEN_DRIFT")
    return f


def isolation_checks(report: Dict[str, Any], initial: Dict[str, Any], arm: str, q: str) -> Dict[str, Any]:
    init_ids = {e["evidence_id"] for e in initial["evidence"]}
    turns = report.get("turns", [])
    seen = {e["evidence_id"] for t in turns for e in t["context"]["facts"]["evidence"]}
    agent_events = report.get("events", [])[report.get("agent_event_start", 0):]
    final_ids = {e["evidence_id"] for e in report["final_state"]["evidence"]}
    checks = {"same_initial_state": report["initial_state"] == initial,
              "question_in_every_turn": all(t["context"]["facts"]["question"] == q for t in turns),
              "visible_ids_subset_of_own_casestate": seen <= final_ids}
    if arm == "B":
        checks.update(
            no_tool_offered=all(not t["context"]["facts"]["available_tools"] for t in turns),
            no_retrieval_offered=all(not t["context"]["facts"]["retrieval_available"] for t in turns),
            no_d1_dispatch=not any(str(e.get("stage", "")).startswith(("D1", "D4", "D5", "D7", "D9")) for e in agent_events),
            zero_tool_and_retrieval=report["tool_attempts"] == 0 and report["retrieval_attempts"] == 0,
            casestate_unchanged=final_ids == init_ids and report["final_revision"] == report["initial_revision"],
            only_initial_evidence_visible=seen <= init_ids)
    checks["passed"] = all(checks.values())
    return checks


def run(out: Path, *, planner_factory: Optional[Callable[[str], Any]] = None,
        authorized_by: Optional[str] = None) -> Dict[str, Any]:
    is_mock = planner_factory is not None
    if not is_mock and not authorized_by:
        raise PermissionError("Owner authorization string required for a live Qwen run")
    f = validate_freeze(out, allow_mock=is_mock)
    cases = read(out / "cases.json")
    done = []
    for i, row in enumerate(cases):
        q = questions.QUESTIONS[row["question_id"]]
        for arm in (("B", "C") if i % 2 == 0 else ("C", "B")):
            dest = out / f"{row['alias']}_{arm}.json"
            if dest.exists():
                continue
            path = Path(row["case_paths"][arm])
            state = cm.read_json(path)
            initial = read(out / row["initial_file"])
            if state != initial:
                raise ValueError("STATE_CHANGED_WITHOUT_SAVED_TRACE_NO_RETRY")
            if file_sha(Path(state["target_ref"]["observed"]["path"])) != row["sha256"]:
                raise ValueError("TARGET_DRIFT")
            config = AppConfig.from_home(Path(row["homes"][arm]))
            reg, orch = inv.build_detector_backend(config, include_imports=True)
            events: list = []
            policy = audit.attach(orch, events)
            planner = planner_factory(arm) if is_mock else None
            with question(q):
                report = workflow_v34.run(path, CFG, reg, orch, policy, planner=planner,
                                          tool_enabled=(arm == "C"), events=events)
            report.update(arm=arm, alias=row["alias"], question_id=row["question_id"], question=q,
                          end_to_end_latency_s=report["latency_s"] + row["static_latency_s"],
                          authorized_by=authorized_by, runner_version=RUNNER_VERSION)
            report["isolation_checks"] = isolation_checks(report, initial, arm, q)
            write_new(dest, report)
            lk = read(out / "EVALUATOR_ONLY" / f"{row['alias']}_leakage.json")
            hits = [dict(h, turn=t["iteration"]) for t in report.get("turns", [])
                    for h in leakage.scan_facts(t["context"]["facts"], lk["tokens"])]
            write_new(out / "EVALUATOR_ONLY" / f"{row['alias']}_{arm}_leakage_all_turns.json",
                      {"summary": leakage.summarize(hits), "hits": hits})
            done.append((row["alias"], arm, report["status"], report["isolation_checks"]["passed"]))
            print(row["alias"], arm, report["status"], "isolation", report["isolation_checks"]["passed"], flush=True)
    return {"mode": f["mode"], "planner": "MOCK_LLM" if is_mock else "LOCAL_QWEN", "runs": done}


def spec_for_package(out: Path, spec_path: Path) -> Dict[str, Any]:
    """Item spec for blind_package.build from a completed run (paths relative to spec_path)."""
    rel = lambda p: _relpath(Path(p), spec_path.parent)
    items = []
    for row in read(out / "cases.json"):
        a = out / f"{row['alias']}_A.json"
        items.append({"sample_sha256": row["sha256"], "arm": "A", "source": rel(a),
                      "initial_state": rel(out / row["initial_file"])})
        for arm in ("B", "C"):
            items.append({"sample_sha256": row["sha256"], "arm": arm, "source": rel(out / f"{row['alias']}_{arm}.json")})
    spec = {"track": read(out / "freeze.json")["mode"], "confirmatory": "NOT_RUN", "items": items}
    write_new(spec_path, spec)
    return spec


def _relpath(p: Path, start: Path) -> str:
    import os
    return os.path.relpath(p.resolve(), start.resolve())


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 06B-J 3-arm runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--mode", choices=("CONFIRMATORY", "DEV_SMOKE"), required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--authorized-by", required=True, help="owner authorization note recorded in every output")
    s = sub.add_parser("spec")
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--spec", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        print(json.dumps(prepare(a.cases, a.out, mode=a.mode)["ollama"], indent=2))
    elif a.cmd == "run":
        print(json.dumps(run(a.out, authorized_by=a.authorized_by), indent=2))
    else:
        spec_for_package(a.out, a.spec)


if __name__ == "__main__":
    main()
