"""Post-hoc artifact audit; no inference, no semantic scoring or historical overwrite.

Run: python -m evaluation.task06b.tests.audit_results
Located outside frozen inference sources; hashes of this evaluator are recorded.
"""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

from d0.validate import validate, verify_receipt_result, digest
from evaluation.task06a.experiment import read, write_new
from investigation_v3.imports_tool import file_sha, FACET, TOOL_ID

ROOT = Path(__file__).resolve().parents[3]
NETWORK_LIBS = {"ws2_32.dll", "wininet.dll", "winhttp.dll", "dnsapi.dll", "iphlpapi.dll"}
PROCESS_APIS = {"OpenProcess", "CreateProcessW", "CreateProcessA", "OpenProcessToken", "GetTokenInformation",
                "CreateRemoteThread", "ReadProcessMemory", "WriteProcessMemory", "VirtualAllocEx"}


def facts_from_visible(turn):
    return {(x["library"], x["symbol"], x["ordinal"], x["delay"])
            for ev in turn["context"]["facts"]["evidence"] if ev["facet"] == FACET
            for x in (ev.get("value") or {}).get("entries", [])}


def relevant(fact):
    return fact[0].lower() in NETWORK_LIBS or fact[1] in PROCESS_APIS


def run():
    output = ROOT / "evaluation/task06b/results"
    protected = read(ROOT / "evaluation/task06a/results/task06a_r/integrity_before.json")["protected_sha256"]
    changed = [p for p, sha in protected.items() if file_sha(ROOT / p) != sha]
    assert not changed, changed
    subprocess.run(["git", "diff", "--exit-code", "8011eaf", "--", "README.md", "research/independent_static_ml",
                    "evaluation/task05c", "evaluation/task05d", "evaluation/task06a", "agent"], cwd=ROOT, check=True)
    result = {"method": "POST_HOC_ARTIFACT_AUDIT_NO_MODEL_OR_HUMAN_GRADING",
              "audit_source_sha256": file_sha(Path(__file__)), "protected_paths_unchanged": len(protected),
              "versions": {}, "query_relevance_lexicon": "POST_HOC_HEURISTIC_NOT_CONFIRMATORY"}
    all_stdout = []
    for version in ("dev_v1", "dev_v2"):
        out = output / version
        frozen = read(out / "freeze.json")
        snapshot = read(out / "source_snapshot.json")
        assert all(hashlib.sha256(snapshot[p].encode()).hexdigest() == h for p, h in frozen["source_sha256"].items())
        assert all(file_sha(out / p) == h for p, h in frozen["initial_artifacts_sha256"].items())
        cases = read(out / "cases.json")
        rows, model_calls, requests, failed = [], 0, 0, []
        for item in cases:
            i = item["index"]
            b, c = read(out / f"{i:02d}_B.json"), read(out / f"{i:02d}_C.json")
            bf, cf = copy.deepcopy(b["turns"][0]["context"]["facts"]), copy.deepcopy(c["turns"][0]["context"]["facts"])
            bf.pop("available_tools"); cf.pop("available_tools")
            assert bf == cf, "Unpaired initial evidence"
            stages = c["events"][c["agent_event_start"]:]
            call = next(e["call"] for e in stages if e["stage"] == "D1_TOOL_CALL")
            decision = next(e["decision"] for e in stages if e["stage"] == "D4")
            receipt = next(e["receipt"] for e in stages if e["stage"] == "D5_D6_RECEIPT")
            d7 = next(e["result"] for e in stages if e["stage"] == "D7_VALIDATED")
            d9 = next(e["commit"] for e in stages if e["stage"] == "D9_COMMITTED")
            assert call["call_id"] == decision["call_id"] == receipt["call_id"] == d7["call_id"]
            assert decision["outcome"] == "ALLOW" and receipt["outcome"] == d7["status"] == "SUCCESS"
            assert verify_receipt_result(receipt, d7, call)
            assert d7["receipt_sha256"] == digest(receipt)
            validate("pe-imports-output-v1", d7["observations"][0]["value"])
            new_id = c["history"][0]["new_evidence_ids"][0]
            committed = next(e for e in c["final_state"]["evidence"] if e["evidence_id"] == new_id)
            assert committed["value"] == d7["observations"][0]["value"]
            assert committed["tool_run_id"] == receipt["run_id"] == d9["tool_run_id"]
            assert committed["value"]["target_sha256"] == item["sha256"]
            assert d9["revision"] == c["final_revision"] > c["initial_revision"]
            assert any(e["evidence_id"] == new_id for e in c["turns"][1]["context"]["facts"]["evidence"])
            assert c["turns"][1]["context"]["facts"]["case_revision"] == c["final_revision"]
            ledger = Path(d9["audit_path"])
            ledger_rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            assert any(r["phase"] == "COMMITTED" and r["run_id"] == receipt["run_id"] and r["revision_committed"] == d9["revision"] for r in ledger_rows)
            ledger_copy = out / "audit_ledgers" / f"{i:02d}_D9.jsonl"
            ledger_copy.parent.mkdir(exist_ok=True)
            if not ledger_copy.exists(): ledger_copy.write_bytes(ledger.read_bytes())
            assert ledger_copy.read_bytes() == ledger.read_bytes()
            stdout = out / "provider_stdout" / (receipt["run_id"] + ".json")
            raw_stdout = Path(item["config_home"]) / "artifacts" / receipt["run_id"] / "stdout.bin"
            assert stdout.read_bytes() == raw_stdout.read_bytes()
            assert read(stdout) == committed["value"]
            all_stdout.append({"path": stdout.relative_to(ROOT).as_posix(), "sha256": file_sha(stdout),
                               "digest_stage": "POST_HOC_EXPORT_CHECK_NOT_AN_ORIGINAL_D6_STREAM_DIGEST"})
            for arm, r in (("B", b), ("C", c)):
                model_calls += len(r["turns"])
                requests += r["tool_attempts"]
                if r["status"] not in {"FINISHED", "MORE_EVIDENCE_REQUIRED"}:
                    failed.append({"index": i, "arm": arm, "errors": [t.get("error") for t in r["turns"] if t.get("error")]})
            initial = facts_from_visible(c["turns"][0])
            new_visible = facts_from_visible(c["turns"][1]) - initial
            uses = c.get("verification", {}).get("literal_new_fact_uses", [])
            claims = (c.get("final") or {}).get("assessment", {}).get("claims", [])
            observed_uses = [u for u in uses if any(cl["kind"] == "OBSERVED" and u["evidence_id"] in cl["evidence_ids"]
                              and u["library"].lower() in cl["text"].lower() and u["symbol"].lower() in cl["text"].lower() for cl in claims)]
            rows.append({"index": i, "B_status": b["status"], "C_status": c["status"],
                         "B_latency_s": b["end_to_end_latency_s"], "C_latency_s": c["end_to_end_latency_s"],
                         "D5_D6_ms": receipt["resources"]["duration_ms"],
                         "committed_import_facts": len(committed["value"]["entries"]),
                         "new_visible_literal_import_facts": len(new_visible),
                         "heuristic_query_relevant_visible_facts": sum(relevant(f) for f in new_visible),
                         "verified_literal_new_uses": len(uses), "also_mentioned_in_observed_claim": len(observed_uses),
                         "assessment_changed_self_report": (c.get("final") or {}).get("assessment_changed"),
                         "semantic_update_quality": "PENDING", "revision_before": c["initial_revision"], "revision_after": c["final_revision"]})
        resumes = []
        for p in out.glob("*_resume.json"):
            r = read(p)
            assert r["tool_attempts"] == 0 and r["status"] == "FINISHED"
            assert r["initial_revision"] == r["final_revision"]
            model_calls += len(r["turns"])
            resumes.append({"file": p.name, "status": r["status"], "tool_attempts": 0, "revision": r["final_revision"]})
        result["versions"][version] = {"cases": rows, "model_calls_including_resume": model_calls,
            "analyzer_attempts": requests, "B_statuses": dict(Counter(r["B_status"] for r in rows)),
            "C_statuses": dict(Counter(r["C_status"] for r in rows)), "failures": failed,
            "B_e2e_mean_s": statistics.mean(r["B_latency_s"] for r in rows),
            "C_e2e_mean_s": statistics.mean(r["C_latency_s"] for r in rows),
            "D5_D6_mean_ms": statistics.mean(r["D5_D6_ms"] for r in rows), "no_tool_resumes": resumes}
    probe = read(ROOT / "evaluation/task05c/repair/results/agreement_bias.json")["dev_probe"]["samples"]
    old_prefixes = {r["sha256"][:12] for r in probe}
    latest = read(output / "dev_v2/manifest_EVALUATOR_ONLY.json")
    overlap = [r["sha256"] for r in latest["dev"] + latest["reserve_NOT_EVALUATED"] if r["sha256"][:12] in old_prefixes]
    assert not overlap
    result["old_16_probe_sha_prefix_overlap"] = overlap
    result["provider_stdout_export_checks"] = all_stdout
    write_new(output / "artifact_audit.json", result)
    c = read(output / "dev_v2/01_C.json")
    md = "# Live curl investigation — rendered from saved trace, no new inference\n\n"
    md += f"Case `{c['case_id']}`, revision {c['initial_revision']} → {c['final_revision']}.\n\n"
    md += "Raw final (LLM, bao gồm các lỗi đã được verifier flag):\n\n```json\n" + json.dumps(c["final"], ensure_ascii=False, indent=2) + "\n```\n\n"
    md += "Trusted verification / effective decision:\n\n```json\n" + json.dumps(c["verification"], ensure_ascii=False, indent=2) + "\n```\n"
    md += "\nLiteral binding không chứng minh semantic relevance hoặc malware. Human grading PENDING.\n"
    target = output / "dev_v2/01_final_report.md"
    with target.open("x", encoding="utf-8") as f: f.write(md)
    print(json.dumps({k: {p: v for p, v in value.items() if p not in ("cases", "failures")} for k,value in result["versions"].items()}, indent=2))


if __name__ == "__main__": run()
