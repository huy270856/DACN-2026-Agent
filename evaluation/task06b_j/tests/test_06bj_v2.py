"""06B-J rubric v2 / questions v2 / two-pass calibration infrastructure tests (MOCK_JUDGE only)."""
import copy
import json
from pathlib import Path

import pytest

from evaluation.task06b_j import analysis, blind_package, judge_kit, questions_v2 as q2, rubric, rubric_v2, rubrics
from evaluation.task06b_j.score_validation import validate

ROOT = Path(__file__).resolve().parents[3]
SPEC2 = ROOT / "evaluation/task06b_j/results/dev/calibration_spec_v2.json"
V1_DIR = ROOT / "evaluation/task06b_j/results/dev/judge_cal_v1"
V1_PKG = ROOT / "evaluation/task06b_j/results/dev/calibration_package_v1"


@pytest.fixture(scope="module")
def pkgs(tmp_path_factory):
    base = tmp_path_factory.mktemp("v2")
    out = {}
    for p in (1, 2):
        d = base / f"p{p}"
        blind_package.build(SPEC2, d, f"seed-{p}", f"TEST-V2-P{p}", rubric_v2.RUBRIC_ID)
        out[p] = d
    return out


def _view(pkg, name):
    return json.loads((pkg / f"grader/items_{name}.json").read_text(encoding="utf-8"))


def fill_v2(view, *, verdict="SUPPORTED", access=None, score=1):
    js = []
    for it in view["items"]:
        ev = it["agent_visible_evidence"]["evidence"][0]["evidence_id"]
        crit = {}
        for name, rule in it["applicability"].items():
            if rule == rubric.NA:
                crit[name] = {"score": rubric.NA, "rationale": "", "evidence_ids": []}
            elif rule == "NOT_ASSESSABLE_INCOMPLETE":
                crit[name] = {"score": rubric.NX, "rationale": "no final", "evidence_ids": []}
            else:
                crit[name] = {"score": score, "rationale": "test", "evidence_ids": [ev]}
        claims = []
        for c in it["report"]["claims"]:
            cv = {"claim_id": c["claim_id"], "verdict": verdict, "tags": [], "evidence_ids": [ev], "rationale": "t"}
            if access:
                cv["evidence_access"] = access
            claims.append(cv)
        js.append({"item_id": it["item_id"], "criteria": crit, "claims": claims, "additional_claims": []})
    return {"schema_version": "task06b-j-judgments-v1", "rubric_id": view["rubric_id"], "rubric_sha256": view["rubric_sha256"],
            "package_id": view["package_id"], "view": view["view"],
            "evaluator": {"kind": "MOCK_JUDGE_TEST_ONLY", "evaluator_id": "unit"}, "pass_id": view["package_id"],
            "created_utc": "2026-11-26T00:00:00Z", "judgments": js}


# ----------------------------------------------------------------------------- rubric v2
def test_v1_preserved_and_v2_distinct():
    assert rubric.RUBRIC_ID == "task06b-j-rubric-v1" and rubric_v2.RUBRIC_ID == "task06b-j-rubric-v2"
    assert rubric.rubric_sha256() == "9fa271b8ccbbc6902f7b3e2c7e032c9719fc425a1632f6c8fad5fe4bf963d057"
    assert rubric.rubric_sha256() != rubric_v2.rubric_sha256()
    assert rubrics.get(rubric.RUBRIC_ID) is rubric and rubrics.get(rubric_v2.RUBRIC_ID) is rubric_v2


def test_locked_v1_judgments_still_valid_under_current_validator():
    for track, view in (("A", "common"), ("B", "investigation")):
        j = json.loads((V1_DIR / f"track{track}_pass1/judgments.json").read_text(encoding="utf-8"))
        v = json.loads((V1_PKG / f"grader/items_{view}.json").read_text(encoding="utf-8"))
        assert validate(j, v) == []


def test_v2_constructs():
    assert "R9_next_step_planning" in rubric_v2.EXPLORATORY and "R9_next_step_planning" not in rubric_v2.PRIMARY
    assert "SEMANTIC_SELF_CORROBORATION" in rubric_v2.CLAIM_TAGS and "SELF_CORROBORATION" not in rubric_v2.CLAIM_TAGS
    assert "SCOPE_OVERCLAIM" in rubric_v2.CLAIM_TAGS
    app = rubric_v2.applicability("investigation", {"has_final": True, "tool_available": True, "tool_evidence_committed": True})
    assert set(app) == {"R3_tool_decision_quality", "R4_new_evidence_relevance", "R5_new_evidence_consumption", "R6_incremental_value"}
    inc = rubric_v2.applicability("common", {"has_final": False, "tool_available": False, "tool_evidence_committed": False})
    assert inc["R2_evidence_traceability"] == "NOT_ASSESSABLE_INCOMPLETE" and inc["R8_decision_quality_safety"] == "REQUIRED"


def test_v2_requires_evidence_access_for_negative_verdicts(pkgs):
    v = _view(pkgs[1], "common")
    assert validate(fill_v2(v), v) == []
    bad = fill_v2(v, verdict="UNSUPPORTED")
    assert any("evidence_access required" in e for e in validate(bad, v))
    ok = fill_v2(v, verdict="UNSUPPORTED", access="ACCESSIBLE_NOT_RETRIEVED")
    assert validate(ok, v) == []
    wrong = fill_v2(v, verdict="CONTRADICTED", access="SOMEWHERE")
    assert validate(wrong, v)


def test_v2_rejects_v1_tag_and_wrong_rubric_hash(pkgs):
    v = _view(pkgs[1], "common")
    j = fill_v2(v)
    item = next(x for x in j["judgments"] if x["claims"])
    item["claims"][0]["tags"] = ["SELF_CORROBORATION"]
    assert any("unknown tags" in e for e in validate(j, v))
    j = fill_v2(v); j["rubric_sha256"] = rubric.rubric_sha256()
    assert any("rubric" in e for e in validate(j, v))


def test_v2_reference_sheet_states_access_limits(pkgs):
    v = _view(pkgs[1], "common")
    rows = [e for it in v["items"] for e in it["reference_evidence"]["evidence"] if e["facet"] == "static.pe_imports_detail"]
    assert rows and all("access_limits" in r for r in rows)


# ----------------------------------------------------------------------------- two passes
def test_two_passes_are_randomised_and_align_for_self_consistency(pkgs, tmp_path):
    a, b = _view(pkgs[1], "common"), _view(pkgs[2], "common")
    assert not ({i["item_id"] for i in a["items"]} & {i["item_id"] for i in b["items"]})
    files, views = [], {}
    for p, pkg in pkgs.items():
        v = _view(pkg, "common")
        f = tmp_path / f"p{p}.json"
        f.write_text(json.dumps(fill_v2(v)), encoding="utf-8")
        files.append(f)
        views[(v["package_id"], "common")] = pkg / "grader/items_common.json"
    lock = tmp_path / "lock.json"
    analysis.lock(files, views, lock)
    rep = analysis.analyze(lock, [pkg / "EVALUATOR_ONLY/mapping.json" for pkg in pkgs.values()])
    agree = [v for k, v in rep["agreement"].items() if k.endswith("R1_factual_support")]
    assert agree and agree[0]["n"] >= 15 and agree[0]["percent_agreement"] == 1.0


def test_kit_audit_blocks_contamination(pkgs, tmp_path):
    kit = tmp_path / "kit"
    judge_kit.export(pkgs[1], "A", kit)
    assert judge_kit.audit_kit(kit) == []
    (kit / "JUDGE_RUNBOOK.md").write_text("see EVALUATOR_ONLY/mapping.json", encoding="utf-8")
    probs = judge_kit.audit_kit(kit)
    assert any("unexpected file" in p for p in probs) and any("forbidden" in p for p in probs)


def test_v2_kit_prompt_contains_v2_rules(pkgs, tmp_path):
    kit = tmp_path / "kitB"
    judge_kit.export(pkgs[2], "B", kit)
    text = (kit / "JUDGE_PROMPT.md").read_text(encoding="utf-8")
    assert "evidence_access" in text and "SEMANTIC_SELF_CORROBORATION" in text and "Score each criterion only" in text
    assert "expected_verdict" not in text and "expected_tags" not in text and "probe" not in text.lower()


# ----------------------------------------------------------------------------- questions v2
def _e(lib, sym):
    return {"library": lib, "symbol": sym, "ordinal": None}


def test_exact_lexicon_excludes_token_apis():
    entries = [_e("advapi32.dll", "OpenProcessToken"), _e("ntdll.dll", "NtOpenProcessTokenEx"), _e("kernel32.dll", "OpenProcess")]
    assert q2.relevant("PROCESS", entries) == [2]


def test_access_classes_follow_budget():
    filler = [_e("kernel32.dll", f"F{i}") for i in range(80)]
    def at(i, fam_entry):
        e = list(filler); e[i] = fam_entry; return e
    net = _e("WS2_32.dll", "send")
    assert q2.access_class("NETWORK", at(3, net))["class"] == "IN_INITIAL_TOOL_PROJECTION"
    assert q2.access_class("NETWORK", at(40, net))["class"] == "REACHABLE_BY_BOUNDED_RETRIEVAL"
    assert q2.access_class("NETWORK", at(55, net))["class"] == "COMMITTED_BUT_ONLY_NONSEQUENTIAL_READ"
    assert q2.access_class("NETWORK", at(70, net))["class"] == "INACCESSIBLE_UNDER_LIMITS"


def test_assignment_shortfall_rule_and_determinism():
    filler = [_e("kernel32.dll", f"F{i}") for i in range(80)]
    def prof(pos):
        e = list(filler); e[pos] = _e("WS2_32.dll", "send"); return e
    profiles = {f"s{i:02d}": prof(p) for i, p in enumerate([2, 20, 21, 22, 23, 24, 25, 26, 70, 71, 72, 73] + [79] * 8)}
    r1, r2 = q2.assign(profiles, "x"), q2.assign(profiles, "x")
    assert r1["assignment"] == r2["assignment"]
    assert r1["counts"]["IN_INITIAL_TOOL_PROJECTION"] == 1
    # shortfall 3 -> retrieval target 4 + 3 = 7
    assert r1["counts"]["REACHABLE_BY_BOUNDED_RETRIEVAL"] == 7 and r1["feasible_target_met"]
    assert sum(r1["counts"].values()) == 20


def test_questions_do_not_leak_names_or_force_tools():
    for cat, fam in [("IN_INITIAL_TOOL_PROJECTION", f) for f in q2.FAMILIES] + [("NOT_STATIC_ANSWERABLE", None),
                                                                              ("INITIAL_EVIDENCE_SUFFICIENT", None)]:
        t = q2.question_text(cat, fam).lower()
        assert "import" not in t and "tool" not in t and ".exe" not in t and "system32" not in t


def test_holdout_manifest_v2_shape():
    m = json.loads((ROOT / "evaluation/task06b_j/results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json").read_text(encoding="utf-8"))
    v1 = json.loads((ROOT / "evaluation/task06b_j/results/holdout/candidate_cases_v1_EVALUATOR_ONLY.json").read_text(encoding="utf-8"))
    assert [(c["alias"], c["sha256"]) for c in m["cases"]] == [(c["alias"], c["sha256"]) for c in v1["cases"]]
    assert m["allocation"]["feasible_target_met"] and sum(m["allocation"]["counts"].values()) == 20
    for c in m["cases"]:
        assert c["question_text"] and c["filename_EVALUATOR_ONLY" if False else "program_identity_EVALUATOR_ONLY"]["filename"].split(".")[0].lower() not in c["question_text"].lower()


def test_final_report_aggregates_two_passes_two_tracks(pkgs, tmp_path):
    from evaluation.task06b_j import final_report
    files, views = [], {}
    for p, pkg in pkgs.items():
        for name in ("common", "investigation"):
            v = _view(pkg, name)
            j = fill_v2(v)
            j["pass_id"] = f"conf-P{p}-track{'A' if name == 'common' else 'B'}"
            f = tmp_path / f"p{p}{name}.json"
            f.write_text(json.dumps(j), encoding="utf-8")
            files.append(f)
            views[(v["package_id"], name)] = pkg / f"grader/items_{name}.json"
    lock = tmp_path / "lock.json"
    analysis.lock(files, views, lock)
    det = tmp_path / "det.json"
    det.write_text(json.dumps({"by_arm": {"A": {}}, "by_class": {}}), encoding="utf-8")
    doc = final_report.build(lock, list(pkgs.values()), det)
    assert set(doc["per_pass"]) == {"P1", "P2"}
    assert "R2_evidence_traceability" in doc["self_consistency"] and "R6_incremental_value" in doc["self_consistency"]
    md = final_report.markdown(doc)
    assert "PRIMARY" in md and "EXPLORATORY" in md and "not accuracy" in md
