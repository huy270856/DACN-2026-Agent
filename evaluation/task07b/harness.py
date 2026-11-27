"""TASK 07B evaluation harness: prepare / run / smoke for arms BASE, V4_NOQ, V4.

* BASE   = frozen investigation v3.4 tool-enabled (TASK 07A V0 config) via `workflow_v34.run`.
* V4_NOQ = investigation v4 contract/projector/workflow, full table, READ_TABLE by offset only.
* V4     = investigation v4 slice 1 with LIST_IMPORT_INDEX + QUERY_IMPORTS.

Reuses the frozen 06B-J runner for staging / Node B / detector / leakage / freeze (imported,
not modified) and 07A's `V34Planner`. Every output is write-once (`runner.write_new`).
A crashed case is recorded as HARNESS_EXCEPTION and counted; it is never retried.
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
from agent.config import AgentConfig
from agent.planner import DecodingOptions
from dacn import investigation as inv
from dacn.config import AppConfig
from investigation_v3 import audit, workflow_v34
from evaluation.task06b_j import leakage, questions, runner
from evaluation.task07a.variants import V34Planner
from investigation_v4 import workflow as v4w
from investigation_v4.config import V4Config

ROOT = runner.ROOT
RUNNER_VERSION = "task07b-harness-v1"
TRACK = "RAW_PE_E2E"
DEV_MANIFEST = ROOT / "evaluation/task06b_j/results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json"
V4_SOURCES = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "investigation_v4").glob("*.py")) + [
    "investigation_v4/ordinal_table.json", "d0/schemas/pe-imports-table-input-v1.schema.json",
    "d0/schemas/pe-imports-table-output-v1.schema.json", "dacn/investigation.py"]
HARNESS_FILES = ["evaluation/task07b/harness.py", "evaluation/task07b/metrics.py", "evaluation/task07b/cohort_audit.py"]

# BASE = 07A V0 (= task06b_j.runner.CFG); V4 arms share one budget/decoding config.
V4_AGENT = dict(max_iterations=8, max_tool_calls=1, max_context_chars=24000, num_predict=3072,
                inference_timeout_s=90, wall_clock_s=420, max_tokens=160000)
ARMS: Dict[str, Dict[str, Any]] = {
    "BASE": {"engine": "v3.4", "agent": dict(max_iterations=5, max_tool_calls=1, max_context_chars=24000,
                                             num_predict=2048, inference_timeout_s=90, wall_clock_s=180),
             "decoding": {"num_ctx": 8192}, "v4": None},
    "V4_NOQ": {"engine": "v4", "agent": dict(V4_AGENT), "decoding": {"num_ctx": 12288},
               "v4": {"retrieval_mode": "READ_TABLE"}},
    "V4": {"engine": "v4", "agent": dict(V4_AGENT), "decoding": {"num_ctx": 12288},
           "v4": {"retrieval_mode": "QUERY"}},
}
SEEDS = (42, 7)
V4_REGION_PREFIXES = ("viewed_imports", "import_index", "coverage.dlls_viewed", "coverage.queries_run")


def make(arm: str, seed: int):
    spec = ARMS[arm]
    cfg = AgentConfig(**spec["agent"])
    dec = DecodingOptions(seed=seed, **spec["decoding"])
    v4 = V4Config(**spec["v4"]) if spec["v4"] is not None else None
    return cfg, dec, v4


def file_hashes(paths) -> Dict[str, str]:
    return {p: runner.file_sha(ROOT / p) for p in paths}


def scan_v4(facts: Dict[str, Any], tokens) -> List[Dict[str, Any]]:
    """06B-J leakage scan; import-derived regions of v4 facts are PE_DERIVED_STATIC, not metadata."""
    hits = leakage.scan_facts(facts, tokens)
    for h in hits:
        if h["classification"] == "ACCIDENTAL_METADATA" and h["location"].startswith(V4_REGION_PREFIXES):
            h["classification"] = "PE_DERIVED_STATIC"
            h["facet"] = "static.pe_imports_table"
    return hits


def _manifest_view(src: Path, aliases: Optional[List[str]]) -> Dict[str, Any]:
    man = runner.read(src)
    cases = [c for c in man["cases"] if aliases is None or c["alias"] in aliases]
    if aliases is not None and len(cases) != len(aliases):
        raise ValueError("ALIAS_NOT_IN_MANIFEST")
    try:
        name = src.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        name = str(src)
    return dict(man, cases=cases, task07b_filter={"source_manifest": name, "source_sha256": runner.file_sha(src),
                                                  "aliases": [c["alias"] for c in cases]})


def prepare(arm: str, seed: int, out: Path, *, manifest: Path, kind: str, aliases: Optional[List[str]] = None,
            runtime_root: Path = runner.RUNTIME, ollama_info=None, signer_lookup=True) -> Dict[str, Any]:
    if out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out}")
    if seed not in SEEDS:
        raise ValueError("SEED_NOT_IN_PROTOCOL")
    cfg, dec, v4 = make(arm, seed)
    view = _manifest_view(manifest, aliases)
    with tempfile.TemporaryDirectory(prefix="t07b-") as tmp:
        mpath = Path(tmp) / "cases_manifest_view.json"
        mpath.write_text(json.dumps(view, indent=2), encoding="utf-8")
        with mock.patch.object(runner, "CFG", cfg):
            freeze = runner.prepare(mpath, out, mode=kind, runtime_root=runtime_root, ollama_info=ollama_info,
                                    signer_lookup=signer_lookup)
    desc = {"arm": arm, "seed": seed, "engine": ARMS[arm]["engine"], "agent_config": asdict(cfg),
            "decoding": asdict(dec), "v4_config": asdict(v4) if v4 else None, "track": TRACK,
            "evaluation_kind": kind, "confirmatory": "NOT_RUN", "cohort_aliases": view["task07b_filter"]["aliases"],
            "manifest_filter": view["task07b_filter"], "runner_version": RUNNER_VERSION,
            "v4_source_sha256": file_hashes(V4_SOURCES), "harness_sha256": file_hashes(HARNESS_FILES),
            "freeze_sha256": runner.file_sha(out / "freeze.json")}
    sha = runner.write_new(out / "arm.json", desc)
    runner.write_new(out / "arm_lock.json", {"arm_json_sha256": sha})
    return {"freeze": freeze, "arm": desc}


def validate_arm(out: Path) -> Dict[str, Any]:
    if runner.file_sha(out / "arm.json") != runner.read(out / "arm_lock.json")["arm_json_sha256"]:
        raise ValueError("ARM_DRIFT: arm.json changed after prepare")
    a = runner.read(out / "arm.json")
    if a["v4_source_sha256"] != file_hashes(V4_SOURCES):
        raise ValueError("V4_SOURCE_DRIFT")
    if a["harness_sha256"] != file_hashes(HARNESS_FILES):
        raise ValueError("HARNESS_DRIFT")
    if runner.file_sha(out / "freeze.json") != a["freeze_sha256"]:
        raise ValueError("FREEZE_DRIFT")
    cfg, dec, v4 = make(a["arm"], a["seed"])
    if asdict(cfg) != a["agent_config"] or asdict(dec) != a["decoding"] or (asdict(v4) if v4 else None) != a["v4_config"]:
        raise ValueError("ARM_CONFIG_DRIFT")
    return a


def isolation_v4(report: Dict[str, Any], initial: Dict[str, Any], q: str) -> Dict[str, Any]:
    turns = report.get("turns", [])
    final_ids = {e["evidence_id"] for e in report["final_state"]["evidence"]}
    mapped = set((report.get("trusted_metadata") or {}).get("handle_map", {}).values())
    checks = {"same_initial_state": report["initial_state"] == initial,
              "question_in_every_turn": all(t["context"]["facts"]["question"] == q for t in turns),
              "handles_map_to_own_casestate": mapped <= final_ids,
              "no_evaluator_only_in_prompt": all("EVALUATOR_ONLY" not in t["context"]["user"] for t in turns),
              "detector_not_citable": all(e.get("kind") != "static.pe_malware_prediction"
                                          for t in turns for e in t["context"]["facts"]["evidence"])}
    checks["passed"] = all(checks.values())
    return checks


def run(out: Path, *, authorized_by: Optional[str] = None,
        planner_factory: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    is_mock = planner_factory is not None
    if not is_mock and not authorized_by:
        raise PermissionError("Owner authorization string required for a live Qwen run")
    f = runner.validate_freeze(out, allow_mock=is_mock)
    a = validate_arm(out)
    cfg, dec, v4 = make(a["arm"], a["seed"])
    done = []
    for row in runner.read(out / "cases.json"):
        alias = row["alias"]
        dest = out / f"{alias}_{a['arm']}.json"
        if dest.exists():
            continue
        q = row.get("question") or questions.QUESTIONS[row["question_id"]]
        path = Path(row["case_paths"]["C"])
        state = cm.read_json(path)
        initial = runner.read(out / row["initial_file"])
        if state != initial:
            raise ValueError("STATE_CHANGED_WITHOUT_SAVED_TRACE_NO_RETRY")
        if runner.file_sha(Path(state["target_ref"]["observed"]["path"])) != row["sha256"]:
            raise ValueError("TARGET_DRIFT")
        config = AppConfig.from_home(Path(row["homes"]["C"]))
        events: List[Dict[str, Any]] = []
        try:
            if a["engine"] == "v3.4":
                reg, orch = inv.build_detector_backend(config, include_imports=True)
                policy = audit.attach(orch, events)
                planner = planner_factory(alias) if is_mock else V34Planner(cfg, dec)
                with runner.question(q):
                    report = workflow_v34.run(path, cfg, reg, orch, policy, planner=planner, tool_enabled=True,
                                              events=events)
            else:
                reg, orch = inv.build_detector_backend(config, include_imports_table=True)
                policy = audit.attach(orch, events)
                planner = planner_factory(alias) if is_mock else v4w.V4Planner(cfg, dec)
                report = v4w.run(path, cfg, v4, reg, orch, policy, question=q, planner=planner, decoding=dec,
                                 events=events)
        except Exception as exc:  # recorded, counted, never retried
            report = {"status": "HARNESS_EXCEPTION", "failure": f"{type(exc).__name__}: {exc}",
                      "traceback": traceback.format_exc(), "turns": [], "final": None, "initial_state": initial,
                      "final_state": cm.read_json(path), "events": events, "latency_s": None}
        report.update(arm=a["arm"], alias=alias, question_id=row["question_id"], question=q, seed=a["seed"],
                      authorized_by=authorized_by, runner_version=RUNNER_VERSION, evaluation_kind=a["evaluation_kind"],
                      track=TRACK, planner_kind_07b="MOCK_LLM" if is_mock else "LOCAL_QWEN",
                      end_to_end_latency_s=(report["latency_s"] + row["static_latency_s"])
                      if report.get("latency_s") is not None else None)
        if report["status"] != "HARNESS_EXCEPTION":
            report["isolation_checks"] = (runner.isolation_checks(report, initial, "C", q) if a["engine"] == "v3.4"
                                          else isolation_v4(report, initial, q))
        runner.write_new(dest, report)
        lk = runner.read(out / "EVALUATOR_ONLY" / f"{alias}_leakage.json")
        scan = leakage.scan_facts if a["engine"] == "v3.4" else scan_v4
        hits = [dict(h, turn=t["iteration"]) for t in report.get("turns", []) for h in scan(t["context"]["facts"], lk["tokens"])]
        runner.write_new(out / "EVALUATOR_ONLY" / f"{alias}_{a['arm']}_leakage_all_turns.json",
                         {"summary": leakage.summarize(hits), "hits": hits})
        passed = (report.get("isolation_checks") or {}).get("passed")
        done.append((alias, report["status"], passed))
        print(alias, a["arm"], a["seed"], report["status"], (report.get("failure") or "")[:120], "isolation", passed,
              flush=True)
    return {"mode": f["mode"], "arm": a["arm"], "seed": a["seed"], "planner": "MOCK_LLM" if is_mock else "LOCAL_QWEN",
            "runs": done}


# ----------------------------------------------------------------------------- G3 smoke gate
def g3_gate(out: Path, relevant: List[str], num_ctx: int) -> Dict[str, Any]:
    """Deterministic G3 checks on a V4 smoke trace (not semantic grading)."""
    from evaluation.task07a.variants import parse_literal
    keys = {parse_literal(x) for x in relevant}
    a = runner.read(out / "arm.json")
    rows = []
    for p in sorted(out.glob(f"*_{a['arm']}.json")):
        r = runner.read(p)
        turns = r.get("turns", [])
        metas = [t.get("meta") or {} for t in turns]
        qres = [t.get("query_result") for t in turns if t.get("query_result")]

        def k(e):
            return (e["library"].lower(), e["symbol"] if e["symbol"] is not None else "#" + str(e["ordinal"]))
        query_hit = any(k(e) in keys for q in qres for e in q["entries"])
        cited = [s for s in (r.get("trusted_metadata") or {}).get("resolved_sources", []) if s.get("literal")]
        cited_hit = any((s["literal"].split("!")[0].lower(), s["literal"].split("!", 1)[1]) in keys for s in cited)
        ev = [e for e in r["final_state"]["evidence"] if e["facet"] == "static.pe_imports_table" and e["status"] == "SUCCESS"]
        checks = {
            "analyzer_committed_d9": bool(ev) and any(e.get("stage") == "D9_COMMITTED" for e in r.get("events", [])),
            "query_saw_relevant": query_hit,
            "final_valid": r.get("final") is not None,
            "final_cites_relevant": cited_hit,
            "no_truncation": all(m.get("done_reason") != "length" for m in metas) and not any(
                t.get("error_payload") for t in turns),
            "analysis_first_every_turn": bool(turns) and all(t.get("analysis_first") for t in turns),
            "prompt_below_0_8_num_ctx": all((m.get("prompt_eval_count") or 0) < 0.8 * num_ctx for m in metas),
            "no_overflow": all((m.get("prompt_eval_count") or 0) + (m.get("eval_count") or 0) < 0.95 * num_ctx for m in metas),
            "isolation": (r.get("isolation_checks") or {}).get("passed") is True}
        rows.append({"alias": r["alias"], "status": r["status"], "failure": r.get("failure"), "checks": checks,
                     "max_prompt_tokens": max([m.get("prompt_eval_count") or 0 for m in metas] or [0]),
                     "actions": [t.get("action") or t.get("stage") for t in turns]})
    ok = bool(rows) and all(all(x["checks"].values()) for x in rows)
    return {"gate": "G3", "result": "PASS" if ok else "FAIL", "rows": rows, "num_ctx": num_ctx,
            "kind": "DETERMINISTIC_GATE_CHECK_NOT_SEMANTIC"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASK 07B harness (BASE / V4_NOQ / V4)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--arm", choices=sorted(ARMS), required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--kind", choices=("DEV_DEBUG", "DEV_SMOKE_G3", "DEV_EVALUATION_FRESH_COHORT"), required=True)
    p.add_argument("--aliases", nargs="*", default=None)
    r = sub.add_parser("run")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--authorized-by", required=True)
    g = sub.add_parser("g3")
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--manifest", type=Path, default=DEV_MANIFEST)
    x = ap.parse_args(argv)
    if x.cmd == "prepare":
        res = prepare(x.arm, x.seed, x.out, manifest=x.manifest, kind=x.kind, aliases=x.aliases)
        print(json.dumps({"ollama": res["freeze"]["ollama"].get("status"), "cohort": res["arm"]["cohort_aliases"]}))
    elif x.cmd == "run":
        print(json.dumps(run(x.out, authorized_by=x.authorized_by), indent=1))
    else:
        a = runner.read(x.out / "arm.json")
        man = {c["alias"]: c for c in runner.read(x.manifest)["cases"]}
        from evaluation.task07a.variants import load_relevant
        rel = [l for al in a["cohort_aliases"] for l in load_relevant(man[al].get("reference_EVALUATOR_ONLY"))]
        gate = g3_gate(x.out, rel, a["decoding"]["num_ctx"])
        runner.write_new(x.out / "g3_gate.json", gate)
        print(json.dumps({"gate": gate["gate"], "result": gate["result"],
                          "rows": [{k: v for k, v in row.items() if k != "actions"} for row in gate["rows"]]}, indent=1))


if __name__ == "__main__":
    main()
