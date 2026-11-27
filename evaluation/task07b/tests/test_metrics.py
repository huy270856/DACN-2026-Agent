"""TASK 07B metrics: exercised on committed DEV_DEBUG r3 traces (mechanism only, not results)."""
import json
from pathlib import Path

import pytest

from evaluation.task07b import metrics as M

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT / "evaluation/task07b/results/dev_debug"
MAP = {"IN_INITIAL_TOOL_PROJECTION": M.RP, "REACHABLE_BY_BOUNDED_RETRIEVAL": M.RP, "INACCESSIBLE_UNDER_LIMITS": M.RP,
       "NOT_STATIC_ANSWERABLE": M.NS, "INITIAL_EVIDENCE_SUFFICIENT": M.IS}


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    if not (DEV / "V4_s42_r3").exists():
        pytest.skip("DEV r3 traces not present")
    src = json.loads((ROOT / "evaluation/task06b_j/results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json").read_text(encoding="utf-8"))
    for c in src["cases"]:
        c["accessibility_class"] = MAP[c["accessibility_class"]]
    base = tmp_path_factory.mktemp("m")
    man = base / "man.json"
    man.write_text(json.dumps(src), encoding="utf-8")
    view = base / "view"
    view.mkdir()
    import shutil
    for g in ("V4_s42_r3", "V4_NOQ_s42_r3"):
        shutil.copytree(DEV / g, view / g)
    return M.collect(view, man)


def test_full_denominators_and_fields(doc):
    for g in ("V4_s42_r3", "V4_NOQ_s42_r3"):
        s = doc["groups"][g]["summary"]
        assert s["n_runs"] == 20 and s["M10_final_present"]["d"] == 20
        assert s["M1_relevant_seen"]["d"] == 12 and s["M2_unnecessary_tool"]["d"] == 8
        assert s["M9_answer_status_fit"]["d"] == 8
        assert s["M1_relevant_seen_within_v3"]["d"] + s["M1_relevant_seen_beyond_v3"]["d"] == s["M1_relevant_seen"]["d"]
        assert s["M5_structural_self_corroboration"]["n"] == 0
        assert doc["groups"][g]["missing_runs"] == []
    assert isinstance(doc["groups"]["V4_s42_r3"]["summary"]["M8_query_hit"], dict)


def test_run_without_final_fails_good_metrics():
    case = {"accessibility_class": M.RP, "reference_EVALUATOR_ONLY": {"relevant_entries": ["A.dll!X"]}}
    r = {"schema_version": "investigation-v4.0", "alias": "s", "status": "INVESTIGATION_INCOMPLETE", "final": None,
         "turns": [{"error": "Ollama returned empty content", "error_payload": {"thinking": "x"}}],
         "trusted_metadata": {"viewed_literals": {"0": "A.dll!X"}, "resolved_sources": [{"literal": "A.dll!X"}]},
         "failure": "Ollama returned empty content"}
    row = M.run_row(r, case, 12288)
    assert row["M1_relevant_seen"] and not row["M1b_relevant_cited"] and not row["M10_final_present"]
    assert row["truncations"] == 1 and not row["infra_error"]
    infra = dict(r, failure="Ollama inference failed: URLError: x", turns=[])
    assert M.run_row(infra, case, 12288)["infra_error"]


def test_m4_independent_of_verifier_exemptions():
    case = {"accessibility_class": M.RA, "reference_EVALUATOR_ONLY": {"relevant_entries": []}}
    final = {"answer": "No import name starting with socket was found by the prefix query.", "findings": []}
    r = {"schema_version": "investigation-v4.0", "alias": "s", "status": "FINISHED", "final": final, "turns": [],
         "trusted_metadata": {}, "verification": {"flags": []}}
    row = M.run_row(r, case, 12288)
    assert row["M4_absence_sentences"]  # counted by the 07A screen even though the verifier exempts it


def test_base_v34_trace_shape():
    case = {"accessibility_class": M.RP, "reference_EVALUATOR_ONLY": {"relevant_entries": ["KERNEL32.dll!WriteFile"]}}
    r = {"schema_version": "investigation-v3.4", "alias": "s", "status": "FINISHED_FLAGGED",
         "final": {"assessment": {"explanation": "x", "claims": []}},
         "turns": [{"proposal": {"action": "TOOL_CALL"}, "context": {"facts": {"evidence": [
             {"facet": "static.pe_imports_detail", "value": {"entries": [{"library": "KERNEL32.dll", "symbol": "WriteFile", "ordinal": None}]}}]}}}],
         "trusted_metadata": {"resolved_import_refs": [{"library": "KERNEL32.dll", "symbol": "WriteFile", "ordinal": None}]},
         "verification": {"flags": ["prediction_used_as_own_corroboration"]}}
    row = M.run_row(r, case, 8192)
    assert row["engine"] == "v3.4" and row["M1_relevant_seen"] and row["M1b_relevant_cited"]
    assert row["M5_structural_self_corroboration"] and row["M2_tool_proposed"] and row["M9_answer_status_fit"] is None


def test_missing_trace_stays_in_denominator(tmp_path):
    case = {"alias": "sample_0001", "sha256": "a" * 64, "accessibility_class": M.RP,
            "reference_EVALUATOR_ONLY": {"relevant_entries": ["A.dll!X"], "beyond_v3_reach": True}}
    case2 = dict(case, alias="sample_0002", accessibility_class=M.NS, reference_EVALUATOR_ONLY={})
    man = tmp_path / "m.json"
    man.write_text(json.dumps({"cases": [case, case2]}), encoding="utf-8")
    d = tmp_path / "res" / "V4_s42"
    d.mkdir(parents=True)
    (d / "arm.json").write_text(json.dumps({"arm": "V4", "seed": 42, "engine": "v4", "decoding": {"num_ctx": 12288},
                                            "v4_config": {"retrieval_mode": "QUERY"},
                                            "cohort_aliases": ["sample_0001", "sample_0002"]}), encoding="utf-8")
    doc = M.collect(tmp_path / "res", man)
    s = doc["groups"]["V4_s42"]["summary"]
    assert doc["groups"]["V4_s42"]["missing_runs"] == ["sample_0001", "sample_0002"]
    assert s["n_runs"] == 2 and s["M10_final_present"] == {"n": 0, "d": 2}
    assert s["M1b_relevant_cited"]["d"] == 1 and s["M8_query_hit"]["d"] == 1 and s["M8_query_hit"]["n"] == 0
    assert s["M9_answer_status_fit"]["d"] == 1 and s["M9_answer_status_fit"]["n"] == 0
    assert s["M7_integrity"]["missing_traces"] == 2


def test_noq_read_hit_not_reported_as_m8(doc):
    s = doc["groups"]["V4_NOQ_s42_r3"]["summary"]
    assert s["M8_query_hit"] == "NOT_APPLICABLE" and isinstance(s["M8_read_hit_reference"], dict)
    assert isinstance(doc["groups"]["V4_s42_r3"]["summary"]["M8_query_hit"], dict)


def test_m4_rate_noise_and_latency_ratio():
    def g(n, d, lat):
        return {"summary": {"M4_absence_unscoped": M._rate(n, d), "M4_absence_scoped": M._rate(0, d),
                            "M6_cost": {"latency_median_s": lat}, **{k: {"n": 0, "d": 1} for k in M.KEY if k not in M.RATE_KEYS}}}
    groups = {"V4_s42": g(1, 10, 60.0), "V4_s7": g(3, 12, 66.0), "BASE_s42": g(4, 20, 20.0), "BASE_s7": g(4, 20, 30.0)}
    for k in ("M8_query_hit", "M9_answer_status_fit"):
        for x in ("V4_s42", "V4_s7"):
            groups[x]["summary"][k] = {"n": 0, "d": 1}
    nz = M.noise(groups)
    assert nz["V4"]["M4_absence_unscoped_rate"] == round(abs(0.1 - 0.25), 4)
    assert "M4_absence_unscoped" not in nz["V4"]
    assert M.latency_ratios(groups) == {"V4/BASE_s42": 3.0, "V4/BASE_s7": 2.2}


def test_broken_runs_never_improve_m2():
    ok_case = {"accessibility_class": M.IS, "reference_EVALUATOR_ONLY": {}}
    broken = {"schema_version": "investigation-v4.0", "alias": "s", "status": "INFRA_INTERRUPTED", "final": None,
              "turns": [], "failure": "STATE_CHANGED_WITHOUT_SAVED_TRACE_NO_RETRY"}
    good = dict(broken, status="FINISHED", failure=None,
                final={"answer_status": "ANSWERED", "answer": "x", "findings": []}, trusted_metadata={})
    rows = [M.run_row(broken, ok_case, 12288), M.run_row(good, ok_case, 12288),
            M.missing_row("m", ok_case, "v4", "QUERY")]
    assert [r["M2_correct_no_tool"] for r in rows] == [False, True, False]
    s = M.summarize(rows)
    assert s["M2_correct_no_tool"] == {"n": 1, "d": 3, "aliases": ["s"]} and s["M2_broken_runs"] == 2
