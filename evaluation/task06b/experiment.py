"""Frozen paired RAW_PE_E2E DEV; no malware download/execution, no overwritten runs."""
import argparse
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import time
import urllib.request

from agent.config import AgentConfig
from dacn.config import AppConfig
from dacn import investigation as inv
import case_manager as cm
from investigation_v3 import application, workflow, audit, context, schema
from investigation_v3.imports_tool import TOOL_ID, FACET, file_sha
from evaluation.task06a.experiment import write_new, read

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "evaluation/task06b/runtime"
CANDIDATES = ["where.exe", "whoami.exe", "certutil.exe", "schtasks.exe", "curl.exe", "wevtutil.exe",
              "tasklist.exe", "reg.exe", "netstat.exe", "hostname.exe", "route.exe", "tracert.exe",
              "findstr.exe", "fc.exe", "compact.exe", "more.com", "sort.exe", "auditpol.exe",
              "bcdedit.exe", "bitsadmin.exe", "makecab.exe", "chcp.com", "dsregcmd.exe", "esentutl.exe", "expand.exe"]


def ollama(route):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open("http://127.0.0.1:11434/api/" + route, timeout=5) as r:
        return json.load(r)


def sources():
    paths = [p for folder in ("investigation_v3", "agent", "dacn", "orchestrator", "d0", "evaluation/task06b")
             for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"}
             and "runtime" not in p.parts and "results" not in p.parts and "tests" not in p.parts
             and p.name != "REPORT.md"]
    return {p.relative_to(ROOT).as_posix(): file_sha(p) for p in sorted(paths)}


def discover():
    old, exclusions = set(), {}
    for folder in ("evaluation/task05c", "evaluation/task05d", "evaluation/task06a"):
        for p in (ROOT / folder).rglob("*.json"):
            old.update(re.findall(r"\b[0-9a-f]{64}\b", p.read_text(encoding="utf-8")))
            exclusions[p.relative_to(ROOT).as_posix()] = file_sha(p)
    selected, skipped = [], []
    for name in CANDIDATES:
        path = Path("C:/Windows/System32") / name
        if not path.exists():
            skipped.append({"filename": name, "reason": "missing"}); continue
        sha = file_sha(path)
        if sha in old:
            skipped.append({"filename": name, "reason": "historical SHA overlap"}); continue
        if path.stat().st_size > 8 * 1024 * 1024:
            skipped.append({"filename": name, "reason": "size limit"}); continue
        quoted = str(path).replace("'", "''")
        command = "$s=Get-AuthenticodeSignature -LiteralPath '" + quoted + "'; @{status=[string]$s.Status;subject=[string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress"
        info = json.loads(subprocess.check_output(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], text=True, timeout=30))
        if info["status"] != "Valid" or "Microsoft" not in info["subject"]:
            skipped.append({"filename": name, "reason": "not Microsoft VALID"}); continue
        selected.append({"filename": name, "source": str(path), "sha256": sha, "size_bytes": path.stat().st_size,
                         "signature": info, "true_label_EVALUATOR_ONLY": "benign", "label_basis": "OS provenance + valid Microsoft signature"})
        old.add(sha)
        if len(selected) == 6: break
    if len(selected) < 6:
        raise ValueError("Insufficient fresh approved benign PE candidates")
    return selected, skipped, exclusions


def prepare(out):
    if out.exists(): raise ValueError("Use a new experiment version")
    mm = inv.load_model_manifest()
    cfg = AgentConfig(max_iterations=3, max_tool_calls=1, max_context_chars=24000, num_predict=2048,
                      inference_timeout_s=90, wall_clock_s=180)
    tags = ollama("tags")
    model = next(m for m in tags["models"] if m["name"] == cfg.model)
    samples, skipped, exclusions = discover()
    out.mkdir(parents=True)
    cases = []
    for i, item in enumerate(samples[:4]):
        config = AppConfig.from_home(RUNTIME / out.name / str(i))
        started = time.monotonic()
        path, registry, orch, policy, events = application.prepare(config, file=item["source"])
        elapsed = time.monotonic() - started
        initial = cm.validate_case(cm.read_json(path))
        initial_copy = config.home / "initial_case.json"
        initial_copy.write_bytes(path.read_bytes())
        write_new(out / f"{i:02d}_initial_state.json", initial)
        write_new(out / f"{i:02d}_initial_trusted_trace.json", events)
        prediction = inv.read_prediction_evidence(initial)["value"]
        static = {"method": "STATIC_TEMPLATE_06B_V1", "model_prediction": prediction,
                  "explanation": "Static model prediction only. Raw score is uncalibrated. Concrete imports were not collected; do not infer runtime capabilities or behaviour.",
                  "recommendation": inv.derive_recommendation(prediction["predicted_label"], None),
                  "latency_s": elapsed, "prompt_tokens": 0, "output_tokens": 0}
        write_new(out / f"{i:02d}_A.json", static)
        ctx = context.build_context(initial, [], cfg, initial_ids={e["evidence_id"] for e in initial["evidence"]}, history=[])
        from evaluation.task05c.agent_replay import _assert_no_ground_truth
        _assert_no_ground_truth(ctx["system"] + ctx["user"])
        cases.append({"index": i, "sha256": item["sha256"], "config_home": str(config.home),
                      "case_path": str(path), "initial_copy": str(initial_copy),
                      "initial_sha256": file_sha(initial_copy), "static_latency_s": elapsed})
    write_new(out / "cases.json", cases)
    write_new(out / "manifest_EVALUATOR_ONLY.json", {"track": "RAW_PE_E2E_BENIGN_DEV", "selection": CANDIDATES,
               "dev": samples[:4], "reserve_NOT_EVALUATED": samples[4:], "skipped": skipped,
               "historical_sha_overlap": 0, "historical_artifact_sha256": exclusions,
               "blinding": "DEV labels public; reserve not claimed confirmatory holdout"})
    initial_hashes = {p.name: file_sha(p) for p in out.glob("*.json")}
    write_new(out / "freeze.json", {"created_utc": datetime.now(timezone.utc).isoformat(), "base_commit": "8011eaf",
               "source_sha256": sources(), "config": asdict(cfg), "ollama_model": model,
               "ollama_version": ollama("version"), "environment": {"python": platform.python_version(), "platform": platform.platform()},
               "model_sha256": mm["model_sha256"], "threshold": mm["threshold_selection"]["primary_threshold"],
               "adapter_pins": dict(orch._installation.pinned_adapter_for(registry.get_tool(TOOL_ID, "0.1.0")).pins),
               "initial_artifacts_sha256": initial_hashes, "protocol_sha256": file_sha(ROOT / "evaluation/task06b/PROTOCOL.md"),
               "ordering": "B then C for even index; C then B for odd index; B reads immutable initial case copy",
               "prompt_schema_sha256": hashlib.sha256((context.SYSTEM + json.dumps(schema.FORMAT, sort_keys=True)).encode()).hexdigest()})
    print("Frozen 4 DEV cases and 2 unused reserve candidates", flush=True)


def validate(out):
    frozen = read(out / "freeze.json")
    if frozen["source_sha256"] != sources(): raise ValueError("Source drift; use new version, never rebase old freeze")
    for name, expected in frozen["initial_artifacts_sha256"].items():
        if file_sha(out / name) != expected: raise ValueError("Initial data drift")
    if inv.load_model_manifest()["model_sha256"] != frozen["model_sha256"]: raise ValueError("Model drift")
    if any(file_sha(p) != sha for p, sha in frozen["adapter_pins"].items()): raise ValueError("Installed analyzer/parser drift")
    return frozen


def run(out):
    frozen = validate(out)
    cfg = AgentConfig(**frozen["config"])
    model = next(m for m in ollama("tags")["models"] if m["name"] == cfg.model)
    if model["digest"] != frozen["ollama_model"]["digest"] or ollama("version") != frozen["ollama_version"]:
        raise ValueError("Ollama/model drift")
    # Evaluator manifest is hash-checked but never parsed in inference phase.
    for item in read(out / "cases.json"):
        index = item["index"]
        config = AppConfig.from_home(item["config_home"])
        registry, orch = inv.build_detector_backend(config, include_imports=True)
        events = []
        policy = audit.attach(orch, events)
        if file_sha(item["initial_copy"]) != item["initial_sha256"]:
            raise ValueError("Initial CaseState copy drift")
        original = cm.read_json(item["initial_copy"])["target_ref"]["observed"]["path"]
        if file_sha(original) != item["sha256"]:
            raise ValueError("Approved original target changed")
        for arm in (("B", "C") if index % 2 == 0 else ("C", "B")):
            target = out / f"{index:02d}_{arm}.json"
            if target.exists(): continue  # preserve successes AND failures
            path = item["initial_copy"] if arm == "B" else item["case_path"]
            if arm == "C" and file_sha(path) != item["initial_sha256"]:
                raise ValueError("C state changed without saved trace; do not retry or hide partial execution")
            report = workflow.run(path, cfg, registry, orch, policy, tool_enabled=arm == "C", events=events)
            report["end_to_end_latency_s"] = item["static_latency_s"] + report["latency_s"]
            write_new(target, report)
            print(f"{index} {arm} {report['status']} tools={report['tool_attempts']} rev={report['initial_revision']}->{report['final_revision']} {report['latency_s']:.2f}s", flush=True)
        c = read(out / f"{index:02d}_C.json")
        resume = out / f"{index:02d}_resume.json"
        if c["status"] == "FINISHED" and c["tool_attempts"] and not resume.exists():
            report = workflow.run(item["case_path"], cfg, registry, orch, policy, events=events)
            write_new(resume, report)
            print(f"{index} resume {report['status']} tools={report['tool_attempts']}", flush=True)
        # Preserve exact trusted raw artifacts in portable text form, never target.bin.
        for r in config.artifacts_dir.rglob("stdout.bin"):
            target = out / "provider_stdout" / (r.parent.name + ".json")
            if not target.exists():
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(r.read_bytes())
    validate(out)


def literal_facts(state):
    return {(e["library"], e["symbol"], e["ordinal"], e["delay"])
            for ev in state["evidence"] if ev.get("facet") == FACET and ev.get("status") == "SUCCESS"
            for e in (ev.get("value") or {}).get("entries", [])}


def summarize(out):
    validate(out)
    rows = []
    for item in read(out / "cases.json"):
        row = {"index": item["index"], "sha256": item["sha256"]}
        for arm in ("A", "B", "C"):
            r = read(out / f"{item['index']:02d}_{arm}.json")
            if arm == "A": row[arm] = {"latency_s": r["latency_s"], "method": r["method"]}; continue
            stages = r["events"][r["agent_event_start"]:]
            new_ids = {ev["evidence_id"] for ev in r["final_state"]["evidence"]} - {ev["evidence_id"] for ev in r["initial_state"]["evidence"]}
            later_visible = {ev["evidence_id"] for t in r["turns"][1:] for ev in t["context"]["facts"]["evidence"]}
            checks = r.get("verification", {})
            row[arm] = {"status": r["status"], "tool_proposals": sum(t.get("proposal", {}).get("action") == "TOOL_CALL" for t in r["turns"]),
                        "controller_valid_tool_proposals": sum(t.get("proposal", {}).get("action") == "TOOL_CALL" and t.get("controller_validated", False) for t in r["turns"]),
                        "tool_attempts": r["tool_attempts"], "D4": [e["decision"]["outcome"] for e in stages if e["stage"] == "D4"],
                        "D5_success": sum(e["stage"] == "D5_D6_RECEIPT" and e["receipt"]["outcome"] == "SUCCESS" for e in stages),
                        "D7_success": sum(e["stage"] == "D7_VALIDATED" and e["result"]["status"] == "SUCCESS" for e in stages),
                        "D9_commits": sum(e["stage"] == "D9_COMMITTED" for e in stages),
                        "revision_increment": r["final_revision"] - r["initial_revision"], "new_ids": sorted(new_ids),
                        "new_ids_visible_next_turn": sorted(new_ids & later_visible),
                        "new_literal_import_facts": len(literal_facts(r["final_state"]) - literal_facts(r["initial_state"])),
                        "literal_new_fact_uses": len(checks.get("literal_new_fact_uses", [])),
                        "unsupported_new_fact_uses_suspected": len(checks.get("unsupported_new_fact_uses_suspected", [])),
                        "consistency_flags": checks.get("consistency", {}).get("flags"),
                        "grounding_screen_flag": not checks.get("grounding_screen", {}).get("grounded", False) if checks else None,
                        "raw_review": (r.get("final") or {}).get("assessment", {}).get("review_required"),
                        "effective_recommendation": checks.get("effective_recommendation"),
                        "latency_s": r["latency_s"], "end_to_end_latency_s": r["end_to_end_latency_s"],
                        "prompt_tokens": r["prompt_tokens"], "output_tokens": r["output_tokens"],
                        "semantic_value": "PENDING_INDEPENDENT_REVIEW"}
        rows.append(row)
    write_new(out / "summary.json", {"track": "RAW_PE_E2E_BENIGN_DEV", "n": len(rows), "cases": rows,
              "human_grading": "PENDING", "confirmatory": "NOT_RUN", "malicious_raw_pe": "BLOCKED_NO_APPROVED_SAMPLES",
              "money_cost": "N/A local inference; latency and tokens measured"})
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("prepare", "run", "summarize"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    {"prepare": prepare, "run": run, "summarize": summarize}[args.action](args.out)
