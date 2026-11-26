"""06B-J runner / staging / leakage / Claude-judge kit tests.

Runner tests use MOCK_LLM planners with the REAL Node B, LightGBM detector and D1-D9 path on a
benign System32 PE that was already used in 05D/06B tests (never a holdout candidate).
MOCK outputs are never evaluation results.
"""
import copy
import json
from pathlib import Path

import pytest

from agent.planner import PlanResult
from evaluation.task06b_j import analysis, blind_package, judge_kit, leakage, pipeline_metrics, questions, rubric, runner
from evaluation.task06b_j.score_validation import validate
from evaluation.task06b_j.tests.test_06bj import SPEC, _fill, _view, pkg  # noqa: F401  (fixture reuse)
from evaluation.task06b.tests.test_v34 import final as v34_final

ROOT = Path(__file__).resolve().parents[3]
PE_A = Path("C:/Windows/System32/whoami.exe")
PE_B = Path("C:/Windows/System32/where.exe")
TRACERT_E = ROOT / "evaluation/task06b/results/r2_debug_v34/00_E.json"


# ----------------------------------------------------------------------------- staging / leakage
def test_neutral_staging_preserves_sha(tmp_path):
    if not PE_A.exists():
        pytest.skip("Windows PE required")
    st = runner.stage(PE_A, tmp_path / "t", "sample_0001")
    assert st["sha256_before"] == st["sha256_after"] == runner.file_sha(PE_A)
    assert Path(st["staged_path"]).name == "sample_0001.exe"
    with pytest.raises(FileExistsError):
        runner.stage(PE_A, tmp_path / "t", "sample_0001")


def test_leakage_detects_original_path_in_unstaged_historical_prompt():
    r = json.loads(TRACERT_E.read_text(encoding="utf-8"))
    facts = r["turns"][0]["context"]["facts"]
    toks = leakage.identity_tokens(Path("C:/Windows/System32/tracert.exe"),
                                   version={"OriginalFilename": "tracert.exe", "FileDescription": "TCP/IP Traceroute Command"})
    hits = leakage.scan_facts(facts, toks)
    s = leakage.summarize(hits)
    assert s["status"] == "FAIL_ACCIDENTAL_IDENTITY_LEAK"
    assert any(h["classification"] == "ACCIDENTAL_METADATA" and "unknowns" in h["location"] for h in hits)


def test_leakage_separates_pe_derived_residual_from_accidental():
    facts = {"question": "q", "unknowns": [], "evidence": [
        {"evidence_id": "EV-1", "facet": "static.pe_imports_detail",
         "value": {"entries": [{"library": "ulib.dll", "symbol": "x"}]}}]}
    toks = [{"token": "ulib", "source": "test", "kind": "PROGRAM_IDENTITY"}]
    hits = leakage.scan_facts(facts, toks)
    assert hits and hits[0]["classification"] == "PE_DERIVED_STATIC"
    assert leakage.summarize(hits)["status"] != "FAIL_ACCIDENTAL_IDENTITY_LEAK"


def test_question_assignment_balanced_and_deterministic():
    aliases = [f"sample_{i:04d}" for i in range(1, 21)]
    a, b = questions.assign(aliases, "s"), questions.assign(aliases, "s")
    assert a == b
    counts = {q: list(a.values()).count(q) for q in questions.QUESTIONS}
    assert set(counts.values()) == {4}


def test_answerability_strata():
    entries = [{"library": "kernel32.dll", "symbol": f"F{i}"} for i in range(20)] + [{"library": "WS2_32.dll", "symbol": "send"}]
    assert questions.answerability("Q_NET", entries)["stratum"] == "RELEVANT_ONLY_AFTER_RETRIEVAL"
    assert questions.answerability("Q_FILE", entries)["stratum"] == "NO_RELEVANT_DECLARED_IMPORTS"
    assert questions.answerability("Q_RUNTIME_LIMIT", entries)["stratum"] == "NOT_ANSWERABLE_STATICALLY"


# ----------------------------------------------------------------------------- runner (MOCK_LLM)
class MockPlanner:
    is_mock = True

    def __init__(self):
        self.contexts = []

    def decide(self, ctx):
        self.contexts.append(copy.deepcopy(ctx))
        f = ctx["facts"]
        head = {"action": "FINISH", "case_id": f["case_id"], "case_revision": f["case_revision"],
                "reason": "mock", "evidence_refs": []}
        if f["available_tools"] and not any(h.get("tool_id") for h in f["history"]):
            t = f["available_tools"][0]
            head.update(action="TOOL_CALL", tool={k: t[k] for k in ("tool_id", "tool_version", "provider_id")})
            head["tool"]["arguments"] = {"max_entries": 64}
            return PlanResult(json.dumps(head), 0, {"mock": True})
        if not ctx.get("finalization_stage"):
            return PlanResult(json.dumps(head), 0, {"mock": True})
        return PlanResult(json.dumps(v34_final(ctx)), 0, {"mock": True})


@pytest.fixture(scope="module")
def mock_run(tmp_path_factory):
    if not (PE_A.exists() and PE_B.exists()):
        pytest.skip("Windows PE required")
    base = tmp_path_factory.mktemp("runner")
    cases = base / "cases.json"
    cases.write_text(json.dumps({"cases": [
        {"alias": "sample_0001", "source": str(PE_A), "sha256": runner.file_sha(PE_A), "question_id": "Q_NET"},
        {"alias": "sample_0002", "source": str(PE_B), "sha256": runner.file_sha(PE_B), "question_id": "QV2_TEST",
         "question_text": "What does the available static evidence indicate about this file's capability for file-system access?"}]}),
        encoding="utf-8")
    out = base / "run"
    runner.prepare(cases, out, mode="DEV_SMOKE", runtime_root=base / "runtime",
                   ollama_info={"status": "MOCK_TEST_NOT_QUERIED"}, signer_lookup=False)
    planners = {}
    res = runner.run(out, planner_factory=lambda arm: planners.setdefault(arm + str(len(planners)), MockPlanner()))
    return out, cases, base, res


def test_three_arm_initial_equivalence(mock_run):
    out = mock_run[0]
    for row in runner.read(out / "cases.json"):
        init = runner.read(out / row["initial_file"])
        a = runner.read(out / f"{row['alias']}_A.json")
        b = runner.read(out / f"{row['alias']}_B.json")
        c = runner.read(out / f"{row['alias']}_C.json")
        assert b["initial_state"] == c["initial_state"] == init
        pred = [e for e in init["evidence"] if e["facet"] == "static.pe_malware_prediction"][0]["value"]
        assert a["model_prediction"]["raw_score"] == pred["raw_score"] == b["model_prediction"]["raw_score"] == c["model_prediction"]["raw_score"]
        expected_q = questions.QUESTIONS.get(row["question_id"]) or "What does the available static evidence indicate about this file's capability for file-system access?"
        assert a["question"] == b["question"] == c["question"] == row["question"] == expected_q
        assert all(t["context"]["facts"]["question"] == expected_q for t in b["turns"] + c["turns"])
        assert row["case_paths"]["B"] != row["case_paths"]["C"] and row["homes"]["B"] != row["homes"]["C"]
        assert init["target_ref"]["verified_digest"]["value"] == row["sha256"]


def test_no_tool_arm_isolation_and_no_post_tool_leak(mock_run):
    out = mock_run[0]
    for row in runner.read(out / "cases.json"):
        b = runner.read(out / f"{row['alias']}_B.json")
        c = runner.read(out / f"{row['alias']}_C.json")
        assert b["isolation_checks"]["passed"], b["isolation_checks"]
        assert c["isolation_checks"]["passed"], c["isolation_checks"]
        assert b["tool_attempts"] == 0 and b["retrieval_attempts"] == 0
        assert c["tool_attempts"] == 1 and c["final_revision"] > c["initial_revision"]
        c_new = {e["evidence_id"] for e in c["final_state"]["evidence"]} - {e["evidence_id"] for e in c["initial_state"]["evidence"]}
        b_seen = {e["evidence_id"] for t in b["turns"] for e in t["context"]["facts"]["evidence"]}
        assert c_new and not (c_new & b_seen)
        assert b["planner_kind"] == "MOCK_LLM"


def test_staged_paths_hide_original_identity(mock_run):
    out = mock_run[0]
    for row in runner.read(out / "cases.json"):
        init = runner.read(out / row["initial_file"])
        text = json.dumps(init).lower()
        assert "whoami" not in text and "where.exe" not in text and "system32" not in text
        lk = runner.read(out / "EVALUATOR_ONLY" / f"{row['alias']}_leakage.json")
        assert all(v["summary"]["accidental_program_identity_hits"] == 0 for v in lk["initial_context"].values())


def test_runner_refuses_overwrite_drift_and_unauthorized_live(mock_run, monkeypatch):
    out, cases, base, _ = mock_run
    with pytest.raises(FileExistsError):
        runner.prepare(cases, out, mode="DEV_SMOKE", runtime_root=base / "runtime2",
                       ollama_info={"status": "MOCK"}, signer_lookup=False)
    before = {p.name: p.read_bytes() for p in out.glob("*_B.json")}
    runner.run(out, planner_factory=lambda arm: MockPlanner())  # existing arms are skipped, not rerun
    assert before == {p.name: p.read_bytes() for p in out.glob("*_B.json")}
    with pytest.raises(PermissionError):
        runner.run(out)
    monkeypatch.setattr(runner, "source_hashes", lambda: {"x": "changed"})
    with pytest.raises(ValueError, match="SOURCE_DRIFT"):
        runner.validate_freeze(out, allow_mock=True)


def test_runner_output_feeds_blind_package(mock_run, tmp_path):
    out = mock_run[0]
    spec = tmp_path / "spec.json"
    runner.spec_for_package(out, spec)
    man = blind_package.build(spec, tmp_path / "pkg", "seed", "MOCK-PKG")
    assert man["counts"] == {"common": 6, "investigation": 4, "probes": 0}
    rows = pipeline_metrics.from_mapping(tmp_path / "pkg/EVALUATOR_ONLY/mapping.json", tmp_path)["rows"]
    agent = [r for r in rows if r["arm_kind"] == "AGENT"]
    assert pipeline_metrics.summarize(agent)["n"] == 4


# ----------------------------------------------------------------------------- judge kit
def _kit(pkg, tmp_path, track="A"):
    kit = tmp_path / f"kit{track}"
    judge_kit.export(pkg, track, kit)
    return kit


def _write_responses(kit, view, *, drop=0, fenced_first=False):
    for k, j in enumerate(_fill(view)["judgments"]):
        if k < drop:
            continue
        text = json.dumps(j)
        if fenced_first and k == drop:
            text = "```json\n" + text + "\n```"
        (kit / "responses" / f"{j['item_id']}.json").write_text(text, encoding="utf-8")


def test_kit_export_refuses_repo_and_contains_no_evaluator_data(pkg, tmp_path):
    with pytest.raises(ValueError, match="KIT_INSIDE_REPOSITORY"):
        judge_kit.export(pkg, "A", ROOT / "evaluation/task06b_j/results/_kit_should_not_exist")
    kit = _kit(pkg, tmp_path)
    blob = "".join(p.read_text(encoding="utf-8") for p in kit.rglob("*") if p.is_file())
    assert blind_package.leakage_scan(blob) == []
    assert "mapping" not in {p.name for p in kit.rglob("*")}
    assert len(list((kit / "items").glob("*.json"))) == 19


def test_kit_import_complete_valid_with_unknown_metadata(pkg, tmp_path):
    kit = _kit(pkg, tmp_path)
    _write_responses(kit, _view(pkg, "common"), fenced_first=True)
    rec = judge_kit.import_responses(kit, pkg, tmp_path / "imp", pass_id="p1")
    assert rec["status"] == "COMPLETE_VALID", rec["problems"][:3]
    doc = json.loads((tmp_path / "imp/judgments.json").read_text(encoding="utf-8"))
    ev = doc["evaluator"]
    assert ev["model"] == "UNKNOWN" and ev["human_verified"] is False and ev["automated_api_inference"] is False
    assert ev["inference_method"] == "INTERACTIVE_LLM_JUDGE_BLIND_BATCH"
    assert len(list((tmp_path / "imp/raw").glob("*.json"))) == 19
    assert any(r.get("fenced") for r in rec["raw_index"])


def test_kit_import_rejects_missing_duplicate_and_tampered(pkg, tmp_path):
    view = _view(pkg, "common")
    kit = _kit(pkg, tmp_path)
    _write_responses(kit, view, drop=1)
    rec = judge_kit.import_responses(kit, pkg, tmp_path / "missing", pass_id="p1")
    assert rec["status"] == "INCOMPLETE_REJECTED" and not (tmp_path / "missing/judgments.json").exists()
    kit2 = tmp_path / "kit2"
    judge_kit.export(pkg, "A", kit2)
    _write_responses(kit2, view)
    first = view["items"][0]["item_id"]
    (kit2 / "responses" / "copy.json").write_text((kit2 / "responses" / f"{first}.json").read_text(encoding="utf-8"), encoding="utf-8")
    rec = judge_kit.import_responses(kit2, pkg, tmp_path / "dup", pass_id="p1")
    assert rec["status"] == "INCOMPLETE_REJECTED"
    kit3 = tmp_path / "kit3"
    judge_kit.export(pkg, "A", kit3)
    _write_responses(kit3, view)
    item = next((kit3 / "items").glob("*.json"))
    item.write_text(item.read_text(encoding="utf-8").replace("benign", "malicious"), encoding="utf-8")
    rec = judge_kit.import_responses(kit3, pkg, tmp_path / "tamper", pass_id="p1")
    assert any(p.get("problem") == "KIT_ITEM_MISSING_OR_MODIFIED" for p in rec["problems"])


def test_missing_criterion_and_no_fallback(pkg, tmp_path):
    view = _view(pkg, "common")
    kit = _kit(pkg, tmp_path)
    js = _fill(view)["judgments"]
    js[0]["criteria"].pop("R9_investigation_planning")
    for j in js:
        (kit / "responses" / f"{j['item_id']}.json").write_text(json.dumps(j), encoding="utf-8")
    rec = judge_kit.import_responses(kit, pkg, tmp_path / "imp", pass_id="p1")
    assert rec["status"] == "INCOMPLETE_REJECTED"
    assert any("missing criterion R9_investigation_planning" in str(p) for p in rec["problems"])
    empty = tmp_path / "kitE"
    judge_kit.export(pkg, "A", empty)
    rec = judge_kit.import_responses(empty, pkg, tmp_path / "impE", pass_id="p1")
    assert rec["status"] == "INCOMPLETE_REJECTED" and rec["n_responses"] == 0


def test_llm_judge_must_declare_not_human_verified(pkg):
    view = _view(pkg, "common")
    j = _fill(view, kind="LLM_JUDGE")
    j["evaluator"].update(provider="x", model="UNKNOWN", model_version_or_digest="UNKNOWN", prompt_sha256="x",
                          inference_method="INTERACTIVE_LLM_JUDGE_BLIND_BATCH", raw_responses_file="raw/")
    assert any("human_verified" in e for e in validate(j, view))
    j["evaluator"]["human_verified"] = False
    assert validate(j, view) == []


def test_r6_negative_allowed_only_for_r6_and_averaged(pkg, tmp_path):
    view = _view(pkg, "investigation")
    j = _fill(view)
    target = next(x for x in j["judgments"] if x["criteria"]["R6_incremental_value"]["score"] == 1)
    target["criteria"]["R6_incremental_value"]["score"] = -1
    assert validate(j, view) == []
    bad = copy.deepcopy(j)
    other = next(x for x in bad["judgments"] if x["criteria"].get("R3_tool_decision_quality", {}).get("score") == 1)
    other["criteria"]["R3_tool_decision_quality"]["score"] = -1
    assert any("outside" in e for e in validate(bad, view))
    f = tmp_path / "inv.json"
    f.write_text(json.dumps(j), encoding="utf-8")
    lock = tmp_path / "lock.json"
    analysis.lock([f], {"investigation": pkg / "grader/items_investigation.json"}, lock)
    rep = analysis.analyze(lock, pkg / "EVALUATOR_ONLY/mapping.json")
    means = [v["R6_incremental_value"]["mean"] for v in next(iter(rep["evaluators"].values()))["per_arm"].values()
             if "R6_incremental_value" in v and v["R6_incremental_value"]["mean"] is not None]
    assert any(m < 1 for m in means)


def test_analyze_requires_lock(pkg, tmp_path):
    with pytest.raises(FileNotFoundError):
        analysis.analyze(tmp_path / "no_lock.json", pkg / "EVALUATOR_ONLY/mapping.json")
    bad = _fill(_view(pkg, "common"))
    bad["judgments"].pop()
    f = tmp_path / "bad.json"
    f.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        analysis.lock([f], {"common": pkg / "grader/items_common.json"}, tmp_path / "l.json")
    assert not (tmp_path / "l.json").exists()


def test_pipeline_denominator_includes_incomplete():
    rows = [{"arm_kind": "AGENT", "final_present": False, "rule_screen_flagged": False, "clean_by_rule_screen": False,
             "tool_proposed": False, "d9_commits": 0, "retrieval_reads": 0, "llm_calls": 1, "latency_s": 1.0},
            {"arm_kind": "AGENT", "final_present": True, "rule_screen_flagged": True, "clean_by_rule_screen": False,
             "tool_proposed": True, "d9_commits": 1, "retrieval_reads": 0, "llm_calls": 3, "latency_s": 3.0}]
    s = pipeline_metrics.summarize(rows)
    assert s["n"] == 2 and s["incomplete"] == 1 and s["final_present"] == 1
