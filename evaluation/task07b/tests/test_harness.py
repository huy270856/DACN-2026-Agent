"""TASK 07B harness: MOCK_LLM mechanism tests over the real Node B / detector / D1-D9 path on a
benign System32 PE already used in earlier tests (not a 07B cohort file). Not behaviour evidence."""
import json
from pathlib import Path

import pytest

from evaluation.task06b_j import runner
from evaluation.task06b_j.tests.test_06bj_runner_judge import MockPlanner as V34Mock
from evaluation.task07b import harness as H
from tests.test_task07b_workflow import Mock as V4Mock

PE = Path("C:/Windows/System32/whoami.exe")


def _manifest(path):
    path.write_text(json.dumps({"cases": [{
        "alias": "sample_0001", "source": str(PE), "sha256": runner.file_sha(PE), "question_id": "QV2_TEST",
        "question_text": "What does the available static evidence indicate about this file's capability for process control?",
        "accessibility_class": "RELEVANT_PRESENT", "reference_EVALUATOR_ONLY": {"relevant_entries": []},
        "true_label_EVALUATOR_ONLY": "benign"}]}), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    if not PE.exists():
        pytest.skip("Windows PE required")
    base = tmp_path_factory.mktemp("t07b")
    m = _manifest(base / "m.json")
    common = dict(manifest=m, kind="DEV_DEBUG", runtime_root=base / "rt", ollama_info={"status": "MOCK"},
                  signer_lookup=False)
    out = {}
    for arm in ("BASE", "V4_NOQ", "V4"):
        o = base / f"{arm}_s42"
        H.prepare(arm, 42, o, **common)
        H.run(o, planner_factory=(lambda a: V34Mock()) if arm == "BASE" else (lambda a: V4Mock()))
        out[arm] = o
    return base, out, m


def test_three_arms_write_traces_and_labels(runs):
    base, out, m = runs
    for arm, o in out.items():
        r = runner.read(o / f"sample_0001_{arm}.json")
        assert r["arm"] == arm and r["seed"] == 42 and r["planner_kind_07b"] == "MOCK_LLM"
        assert r["track"] == "RAW_PE_E2E" and r["evaluation_kind"] == "DEV_DEBUG"
        assert r["isolation_checks"]["passed"], r["isolation_checks"]
        assert r["status"] in ("FINISHED", "FINISHED_FLAGGED"), (arm, r.get("failure"))
        assert (o / "EVALUATOR_ONLY" / f"sample_0001_{arm}_leakage_all_turns.json").exists()
    assert runner.read(out["BASE"] / "arm.json")["engine"] == "v3.4"
    v4 = runner.read(out["V4"] / "sample_0001_V4.json")
    assert v4["retrieval_mode"] == "QUERY" and v4["tool_attempts"] == 1
    noq = runner.read(out["V4_NOQ"] / "sample_0001_V4_NOQ.json")
    assert noq["retrieval_mode"] == "READ_TABLE"
    assert all("QUERY_IMPORTS" not in t["context"]["facts"]["available_actions"] for t in noq["turns"])


def test_base_matches_07a_v0_config(runs):
    from evaluation.task07a.variants import make_cfg
    from dataclasses import asdict
    cfg, dec = make_cfg("V0", 42)
    a = runner.read(runs[1]["BASE"] / "arm.json")
    assert a["agent_config"] == asdict(cfg) and a["decoding"] == asdict(dec)


def test_write_once_no_rerun_and_auth(runs):
    o = runs[1]["V4"]
    before = (o / "sample_0001_V4.json").read_bytes()
    H.run(o, planner_factory=lambda a: V4Mock())
    assert (o / "sample_0001_V4.json").read_bytes() == before
    with pytest.raises(PermissionError):
        H.run(o)
    with pytest.raises(FileExistsError):
        H.prepare("V4", 42, o, manifest=runs[2], kind="DEV_DEBUG", ollama_info={"status": "MOCK"}, signer_lookup=False)
    with pytest.raises(ValueError):
        H.prepare("V4", 3, runs[0] / "x", manifest=runs[2], kind="DEV_DEBUG")


def test_drift_detected(runs, monkeypatch):
    o = runs[1]["V4"]
    assert H.validate_arm(o)["arm"] == "V4"
    monkeypatch.setattr(H, "file_hashes", lambda paths: {"x": "y"})
    with pytest.raises(ValueError, match="V4_SOURCE_DRIFT"):
        H.validate_arm(o)


def test_scan_v4_reclassifies_import_regions():
    facts = {"question": "q", "evidence": [], "viewed_imports": [{"handle": "I1", "dll": "ulib.dll", "symbol": "x"}],
             "coverage": {"queries_run": [{"by": "DLL", "value": "ulib.dll"}]}, "omitted": "ulib"}
    hits = H.scan_v4(facts, [{"token": "ulib", "source": "t", "kind": "PROGRAM_IDENTITY"}])
    cls = {h["location"].split(".")[0].split("[")[0]: h["classification"] for h in hits}
    assert cls["viewed_imports"] == "PE_DERIVED_STATIC" and cls["coverage"] == "PE_DERIVED_STATIC"
    assert cls["omitted"] == "ACCIDENTAL_METADATA"


def test_g3_gate_on_mock_trace(runs):
    o = runs[1]["V4"]
    r = runner.read(o / "sample_0001_V4.json")
    q = next(t for t in r["turns"] if t.get("query_result"))["query_result"]["entries"][0]
    lit = q["library"] + "!" + (q["symbol"] if q["symbol"] is not None else "#" + str(q["ordinal"]))
    gate = H.g3_gate(o, [lit], 12288)
    checks = gate["rows"][0]["checks"]
    assert checks["analyzer_committed_d9"] and checks["query_saw_relevant"] and checks["final_valid"]
    assert checks["analysis_first_every_turn"] and checks["isolation"]
    assert H.g3_gate(o, ["NOPE.dll!X"], 12288)["result"] == "FAIL"
