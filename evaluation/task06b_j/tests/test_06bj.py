"""TASK 06B-J infrastructure tests (unit + deterministic; MOCK_JUDGE is test-only, never a result)."""
import copy
import json
from pathlib import Path

import pytest

from evaluation.task06b_j import analysis, blind_package, judge_adapter, pipeline_metrics, rubric
from evaluation.task06b_j.score_validation import JUDGMENT_SCHEMA, validate

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "evaluation/task06b_j/results/dev/calibration_spec_v1.json"
TRACERT_E = ROOT / "evaluation/task06b/results/r2_debug_v34/00_E.json"


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    out = tmp_path_factory.mktemp("pkg") / "p"
    blind_package.build(SPEC, out, "test-seed", "TEST-PKG")
    return out


def _view(pkg, name):
    return json.loads((pkg / f"grader/items_{name}.json").read_text(encoding="utf-8"))


def _fill(view, kind="MOCK_JUDGE_TEST_ONLY", pass_id="p1", score=1):
    """A complete, schema-valid judgment file used only to exercise validation/analysis code."""
    js = []
    for it in view["items"]:
        ev = it["agent_visible_evidence"]["evidence"][0]["evidence_id"]
        crit = {}
        for name, rule in it["applicability"].items():
            if rule == rubric.NA:
                crit[name] = {"score": rubric.NA, "rationale": "", "evidence_ids": []}
            elif rule == "NOT_ASSESSABLE_INCOMPLETE":
                crit[name] = {"score": rubric.NX, "rationale": "no final report", "evidence_ids": []}
            else:
                crit[name] = {"score": score, "rationale": "test rationale", "evidence_ids": [ev]}
        claims = [{"claim_id": c["claim_id"], "verdict": "SUPPORTED", "tags": [], "evidence_ids": [ev],
                   "rationale": "test"} for c in it["report"]["claims"]]
        js.append({"item_id": it["item_id"], "criteria": crit, "claims": claims, "additional_claims": []})
    return {"schema_version": JUDGMENT_SCHEMA, "rubric_id": view["rubric_id"], "rubric_sha256": view["rubric_sha256"],
            "package_id": view["package_id"], "view": view["view"],
            "evaluator": {"kind": kind, "evaluator_id": "unit-test"}, "pass_id": pass_id,
            "created_utc": "2026-11-26T00:00:00Z", "judgments": js}


# ----------------------------------------------------------------------------- rubric
def test_applicability_rules_are_fixed_by_view_and_state():
    static = rubric.applicability("common", {"has_final": True, "tool_available": False, "tool_evidence_committed": False})
    assert set(static) == {"R1_factual_support", "R2_evidence_attribution", "R7_uncertainty_limitations",
                           "R8_decision_quality_safety", "R9_investigation_planning"}
    incomplete = rubric.applicability("common", {"has_final": False, "tool_available": False, "tool_evidence_committed": False})
    assert incomplete["R8_decision_quality_safety"] == "REQUIRED"
    assert incomplete["R1_factual_support"] == "NOT_ASSESSABLE_INCOMPLETE"
    b = rubric.applicability("investigation", {"has_final": True, "tool_available": False, "tool_evidence_committed": False})
    assert b["R3_tool_decision_quality"] == rubric.NA and b["R6_incremental_value"] == "REQUIRED"
    c_abstain = rubric.applicability("investigation", {"has_final": True, "tool_available": True, "tool_evidence_committed": False})
    assert c_abstain["R3_tool_decision_quality"] == "REQUIRED" and c_abstain["R5_evidence_consumption"] == rubric.NA
    assert -1 in rubric.CRITERIA["R6_incremental_value"]["scale"]


def test_rubric_hash_is_stable():
    assert rubric.rubric_sha256() == rubric.rubric_sha256()


# ----------------------------------------------------------------------------- package
def test_package_blinded_and_no_scores(pkg):
    for name in ("common", "investigation"):
        text = (pkg / f"grader/items_{name}.json").read_text(encoding="utf-8")
        assert blind_package.leakage_scan(json.loads(text)) == []
        assert "variant" not in text and "deterministic_checker" not in text
    man = json.loads((pkg / "package_manifest.json").read_text(encoding="utf-8"))
    assert man["counts"] == {"common": 19, "investigation": 16, "probes": 4}
    assert man["scores"].startswith("NONE")


def test_package_refuses_overwrite_and_is_deterministic(pkg, tmp_path):
    with pytest.raises(FileExistsError):
        blind_package.build(SPEC, pkg, "test-seed", "TEST-PKG")
    other = tmp_path / "again"
    blind_package.build(SPEC, other, "test-seed", "TEST-PKG")
    a = [i["item_id"] for i in _view(pkg, "common")["items"]]
    b = [i["item_id"] for i in _view(other, "common")["items"]]
    assert a == b


def test_leakage_scan_detects_arm_and_label_tokens():
    assert blind_package.leakage_scan({"x": "arm AGENT_TOOL_ENABLED"}) == ["AGENT_TOOL_ENABLED"]
    assert "true_label" in blind_package.leakage_scan({"true_label": "benign"})


def test_reference_sheet_marks_unseen_import_entries(pkg):
    items = _view(pkg, "common")["items"]
    mapping = {m["item_id"]: m for m in json.loads((pkg / "EVALUATOR_ONLY/mapping.json").read_text(encoding="utf-8"))["items"]}
    item = next(i for i in items if mapping[i["item_id"]]["variant"] == "dev-v3.4-debug"
                and mapping[i["item_id"]]["sample_sha256"].startswith("415e"))
    imp = next(e for e in item["reference_evidence"]["evidence"] if e["facet"] == "static.pe_imports_detail")
    assert imp["entry_indices_visible_to_agent"] == list(range(16))
    assert len(imp["value"]["entries"]) == 64


# ----------------------------------------------------------------------------- validation
def test_valid_judgments_pass(pkg):
    for name in ("common", "investigation"):
        v = _view(pkg, name)
        assert validate(_fill(v), v) == []


def test_incomplete_or_autofilled_judgments_rejected(pkg):
    v = _view(pkg, "common")
    j = _fill(v); j["judgments"].pop()
    assert any("incomplete coverage" in e for e in validate(j, v))
    j = _fill(v)
    req = next(x for x in j["judgments"] if x["criteria"]["R1_factual_support"]["score"] == 1)
    req["criteria"]["R1_factual_support"] = {"score": rubric.NA, "rationale": "x", "evidence_ids": []}
    assert any("not allowed" in e for e in validate(j, v))
    j = _fill(v)
    inc = next(x for x in j["judgments"] if x["criteria"]["R1_factual_support"]["score"] == rubric.NX)
    inc["criteria"]["R1_factual_support"]["score"] = 0
    assert any("incomplete report" in e for e in validate(j, v))
    j = _fill(v)
    req = next(x for x in j["judgments"] if x["criteria"]["R1_factual_support"]["score"] == 1)
    req["criteria"]["R1_factual_support"]["evidence_ids"] = []
    assert any("needs evidence_ids" in e for e in validate(j, v))
    j = _fill(v)
    withc = next(x for x in j["judgments"] if x["claims"])
    withc["claims"] = withc["claims"][1:]
    assert any("missing claim verdicts" in e for e in validate(j, v))
    j = _fill(v); j["rubric_sha256"] = "0" * 64
    assert validate(j, v)


def test_llm_judge_requires_provenance(pkg):
    v = _view(pkg, "common")
    errs = validate(_fill(v, kind="LLM_JUDGE"), v)
    assert any("LLM provenance" in e for e in errs)


# ----------------------------------------------------------------------------- judge adapter
def test_judge_blocked_without_transport(pkg, tmp_path):
    with pytest.raises(judge_adapter.JudgeUnavailable):
        judge_adapter.run(pkg / "grader/items_common.json", tmp_path / "j", transport=None, provider=None,
                          evaluator_id="x", pass_id="p")


def _provider():
    return {"provider": "mock", "model": "mock", "model_version_or_digest": "mock", "inference_method": "test"}


def test_judge_records_raw_calls_and_rejects_malformed(pkg, tmp_path):
    v = _view(pkg, "common")
    canned = {j["item_id"]: j for j in _fill(v)["judgments"]}
    ok = lambda req: {"text": json.dumps(canned[req["item_id"]]), "meta": {"mock": True}}
    res = judge_adapter.run(pkg / "grader/items_common.json", tmp_path / "ok", transport=ok, provider=_provider(),
                            evaluator_id="mock", pass_id="p1", kind="MOCK_JUDGE_TEST_ONLY")
    assert res["status"] == "COMPLETE_VALID"
    assert len((tmp_path / "ok/raw_calls.jsonl").read_text(encoding="utf-8").splitlines()) == len(v["items"])
    first = v["items"][0]["item_id"]
    bad = lambda req: {"text": "not json" if req["item_id"] == first else json.dumps(canned[req["item_id"]])}
    res = judge_adapter.run(pkg / "grader/items_common.json", tmp_path / "bad", transport=bad, provider=_provider(),
                            evaluator_id="mock", pass_id="p1", kind="MOCK_JUDGE_TEST_ONLY")
    assert res["status"] == "INCOMPLETE_REJECTED"
    assert not (tmp_path / "bad/judgments.json").exists()


# ----------------------------------------------------------------------------- analysis
def test_lock_then_analyze_never_imputes(pkg, tmp_path):
    views = {"common": pkg / "grader/items_common.json", "investigation": pkg / "grader/items_investigation.json"}
    files = []
    for name, p in views.items():
        f = tmp_path / f"{name}.json"
        f.write_text(json.dumps(_fill(_view(pkg, name))), encoding="utf-8")
        files.append(f)
    lock = tmp_path / "lock.json"
    analysis.lock(files, views, lock)
    with pytest.raises(FileExistsError):
        analysis.lock(files, views, lock)
    rep = analysis.analyze(lock, pkg / "EVALUATOR_ONLY/mapping.json")
    ev = next(iter(rep["evaluators"].values()))
    inc = ev["per_arm"]["B[dev-v3.3-no-tool]"]["R1_factual_support"]
    assert inc["n_assessable"] == 0 and inc["NOT_ASSESSABLE"] == 3 and inc["mean"] is None
    assert all("probe" not in k for k in ev["per_arm"])
    assert ev["paired"] == {}  # DEV variants never form arm pairs
    files[0].write_text(files[0].read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError):
        analysis.analyze(lock, pkg / "EVALUATOR_ONLY/mapping.json")


# ----------------------------------------------------------------------------- deterministic metrics
def test_coverage_diagnostic_on_frozen_tracert_trace():
    r = json.loads(TRACERT_E.read_text(encoding="utf-8"))
    cov = pipeline_metrics.coverage_diagnostic(r)
    assert cov["committed_entries"] == 64 and cov["ever_visible_entries"] == 16
    assert cov["relevant_committed"] == 15 and cov["relevant_never_visible"] == 15
    m = pipeline_metrics.run_metrics(r)
    assert m["tool_proposed"] and m["d9_commits"] == 1 and m["rule_screen_flagged"]
