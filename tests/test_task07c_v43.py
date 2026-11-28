"""TASK 07C rev 3: investigation-v4.3 two-step final (F1 presence / F2 decision+absence+unresolved). Unit + MOCK_LLM."""
import copy
import json

import pytest

from agent.planner import PlanResult
from investigation_v4 import contract as C, renderer as RD
from investigation_v4.config import V4Config
from tests.test_task07b_workflow import Mock, _run, case  # noqa: F401


def test_schemas():
    f1, f2 = C.f1_schema(), C.f2_schema()
    assert list(f1["properties"]) == ["analysis", "findings"] and f1["properties"]["findings"]["minItems"] == 0
    assert list(f2["properties"])[0] == "analysis" and "findings" not in f2["properties"] and "answer" not in f2["properties"]
    assert f2["properties"]["unresolved"]["items"]["properties"]["reason"]["enum"] == C.UNRESOLVED_REASONS
    assert C.final_schema("4.2") == C.final_schema("4.2")  # earlier contracts untouched
    V4Config(contract_version="4.3")


def _f1(statements):
    return {"analysis": "a", "findings": [{"kind": "OBSERVED", "statement": s, "refs": r} for s, r in statements]}


def _f2(claims=(), unresolved=(("runtime network use", "NOT_STATIC_DETERMINABLE"),)):
    return {"analysis": "b", "answer_status": "PARTIALLY_ANSWERED", "evidence_needed": [], "next_verification": [],
            "detector_relation": {"value": "NOT_INFORMATIVE", "basis_sources": []}, "absence_claims": list(claims),
            "unresolved": [{"topic": t, "reason": r} for t, r in unresolved]}


class Mock43(Mock):
    def __init__(self, f1_first_negated=False, f2_bad_claim=False):
        super().__init__()
        self.f1n = f1_first_negated
        self.f2b = f2_bad_claim
        self.steps = []

    def decide(self, ctx):
        if not ctx["finalization_stage"]:
            return super().decide(ctx)
        f = ctx["facts"]
        self.ctxs.append(copy.deepcopy(ctx))
        if "findings" in ctx["schema"]["properties"]:          # F1
            self.steps.append("F1")
            src = [x["handle"] for x in f["viewed_imports"][:1]] or [f["evidence"][0]["handle"]]
            if self.f1n and self.steps.count("F1") == 1:
                return PlanResult(json.dumps(_f1([("No network APIs are imported.", src)])), 0.0, {})
            return PlanResult(json.dumps(_f1([("Declared imports are listed.", src)])), 0.0, {})
        self.steps.append("F2")
        assert "f1_findings" in f and "coverage_ledger" in f
        q = next(e["id"] for e in f["coverage_ledger"] if e["kind"] == "INDEX")
        bad = self.f2b and self.steps.count("F2") == 1
        claim = {"api_or_prefix": "connect" if bad else "wininet.dll", "scope_ref": q}
        return PlanResult(json.dumps(_f2([claim])), 0.0, {})


def test_e2e_two_steps_render(case):
    m = Mock43()
    r = _run(case, m, V4Config(contract_version="4.3"))
    assert r["schema_version"] == "investigation-v4.3" and m.steps == ["F1", "F2"]
    assert [t["final_step"] for t in r["turns"] if t["final_step"]] == ["F1", "F2"]
    assert r["final"]["findings"][0]["statement"] == "Declared imports are listed."
    assert len(r["verification"]["absence_claims"]["accepted"]) == 1
    rep = r["rendered_report"]
    assert "Câu hỏi còn mở" in rep and '"runtime network use"' in rep and "NOT_STATIC_DETERMINABLE" in rep
    assert "Không thấy `wininet.dll`" in rep


def test_f1_repair_then_p1_and_f2_claim_repair(case):
    m = Mock43(f1_first_negated=True, f2_bad_claim=True)
    r = _run(case, m, V4Config(contract_version="4.3"))
    assert m.steps == ["F1", "F1", "F2", "F2"] and r["step_repairs"] == {"F1": True, "F2": True}
    assert r["final"] is not None and len(r["verification"]["absence_claims"]["accepted"]) == 1


def test_f1_negated_after_repair_is_dropped(case):
    class Neg(Mock43):
        def decide(self, ctx):
            if ctx["finalization_stage"] and "findings" in ctx["schema"]["properties"]:
                self.steps.append("F1")
                src = [ctx["facts"]["evidence"][0]["handle"]]
                return PlanResult(json.dumps(_f1([("Nothing is imported for HTTP.", src), ("PE32+ x64 image.", src)])), 0.0, {})
            return super().decide(ctx)
    r = _run(case, Neg(), V4Config(contract_version="4.3"))
    assert r["rendered_dropped_statements"] == ["Nothing is imported for HTTP."]
    head = r["rendered_report"].split("## Nội dung bị loại")[0]
    assert "Nothing is imported" not in head and '"PE32+ x64 image."' in head


def test_v43_metrics_rendered_answer():
    from evaluation.task07b import metrics as M
    case_ = {"accessibility_class": M.RA, "reference_EVALUATOR_ONLY": {"relevant_entries": []}}
    final = dict(_f2(unresolved=()), findings=[])
    r = {"schema_version": "investigation-v4.3", "alias": "s", "status": "FINISHED", "final": final, "turns": [],
         "trusted_metadata": {"resolved_sources": []},
         "verification": {"flags": [], "absence_claims": {"accepted": [{"api_or_prefix": "x.dll"}], "rejected": []}}}
    assert M.run_row(r, case_, 12288)["rendered_answer"] is True
    final2 = dict(_f2(unresolved=()), findings=[])
    r2 = dict(r, final=final2, verification={"flags": [], "absence_claims": {"accepted": [], "rejected": []}})
    assert M.run_row(r2, case_, 12288)["rendered_answer"] is False
    assert M.summarize([M.run_row(r, case_, 12288), M.run_row(r2, case_, 12288)])["rendered_answer_rate"] == {"n": 1, "d": 2}
