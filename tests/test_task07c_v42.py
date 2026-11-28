"""TASK 07C rev 2: investigation-v4.2 structured final + trusted renderer (unit + MOCK_LLM)."""
import copy
import json

import pytest

from agent.planner import PlanResult
from investigation_v4 import contract as C, renderer as RD, verifier as V
from investigation_v4.config import V4Config
from tests.test_task07b_workflow import Mock, _run, case  # noqa: F401


def _f42(statement="Declares WS2_32 networking imports.", refs=("I21",), claims=()):
    return {"analysis": "a", "answer_status": "PARTIALLY_ANSWERED",
            "findings": [{"kind": "OBSERVED", "statement": statement, "refs": list(refs)}],
            "evidence_needed": ["runtime trace"], "next_verification": ["dynamic analysis"],
            "detector_relation": {"value": "NOT_INFORMATIVE", "basis_sources": []}, "absence_claims": list(claims)}


def test_schema_42_structured_only():
    s = C.final_schema("4.2")
    assert "answer" not in s["properties"] and "absence_claims" in s["required"]
    item = s["properties"]["findings"]["items"]
    assert set(item["required"]) == {"kind", "statement", "refs"} and item["properties"]["refs"]["minItems"] == 1
    assert item["properties"]["kind"]["enum"] == ["OBSERVED", "INFERENCE"]
    C.parse(json.dumps(_f42()), s)
    for bad in (dict(_f42(), answer="x"), _f42(refs=())):
        with pytest.raises(ValueError):
            C.parse(json.dumps(bad), s)
    assert C.final_schema("4.0") == C.final_schema() and "answer" in C.final_schema("4.1")["properties"]


@pytest.mark.parametrize("statement, neg", [
    ("Declares WS2_32 networking imports.", False), ("Imports CreateFileW from KERNEL32.", False),
    ("No file APIs are imported.", True), ("The file does not import CreateProcess.", True),
    ("Network APIs are absent.", True), ("Registry access is missing.", True), ("It doesn't use sockets.", True),
])
def test_statement_absence(statement, neg):
    assert bool(V.statement_absence(_f42(statement))) is neg


def test_renderer_quotes_verbatim_and_never_invents():
    final = _f42(claims=[{"api_or_prefix": "wininet.dll", "scope_ref": "Q1"}])
    led = [{"id": "Q1", "kind": "INDEX", "value": "*", "total_matches": None, "returned": None, "exhausted": True}]
    ab = {"accepted": [dict(final["absence_claims"][0], index=0)],
          "rejected": [{"api_or_prefix": "ICMP", "scope_ref": "Q1", "reason": "OUT_OF_SCOPE"}]}
    before = copy.deepcopy(final)
    out = RD.render(final, led, ab, [{"handle": "I21", "literal": "WS2_32.dll!#115"}],
                    {"predicted_label": "benign", "raw_score": 0.01}, "Q?")
    assert final == before
    assert '"Declares WS2_32 networking imports."' in out and "model-authored" in out and "WS2_32.dll!#115" in out
    assert "Không thấy `wininet.dll`" in out and "BỊ LOẠI" in out and "KHÔNG phải xác suất" in out
    assert "ICMP" not in out.split("BỊ LOẠI")[0]  # a rejected claim is never rendered as a fact


class Mock42(Mock):
    def __init__(self, fix=True):
        super().__init__()
        self.n, self.fix = 0, fix

    def decide(self, ctx):
        if not ctx["finalization_stage"]:
            return super().decide(ctx)
        self.ctxs.append(copy.deepcopy(ctx))
        self.n += 1
        f = ctx["facts"]
        src = [x["handle"] for x in f["viewed_imports"][:1]] or [f["evidence"][0]["handle"]]
        if self.n == 1 or not self.fix:
            obj = _f42("No network APIs are imported.", src)
        else:
            q = next(e["id"] for e in f["coverage_ledger"] if e["kind"] == "INDEX")
            obj = _f42("Declared imports are listed.", src, [{"api_or_prefix": "wininet.dll", "scope_ref": q}])
        return PlanResult(json.dumps(obj), 0.0, {"mock": True})


def test_e2e_v42_repair_render(case):
    r = _run(case, Mock42(), V4Config(contract_version="4.2"))
    assert r["schema_version"] == "investigation-v4.2" and r["absence_repair_used"]
    ab = r["verification"]["absence_claims"]
    assert len(ab["accepted"]) == 1 and not ab["free_text_absence_rejected"]
    assert "Không thấy `wininet.dll`" in r["rendered_report"] and '"Declared imports are listed."' in r["rendered_report"]
    assert "STRUCTURED FINAL" in r["turns"][-1]["context"]["system"]


def test_e2e_v42_negated_statement_flagged_after_repair(case):
    r = _run(case, Mock42(fix=False), V4Config(contract_version="4.2"))
    assert "free_text_absence_rejected" in r["verification"]["flags"] and r["final"]["findings"][0]["statement"].startswith("No ")
    assert r["effective_recommendation"]["action"] == "MANUAL_REVIEW"


def test_empty_findings_allowed_and_prompt_says_so():
    o = _f42()
    o["findings"] = []
    C.parse(json.dumps(o), C.final_schema("4.2"))
    assert "leave findings" in C.SYSTEM_42 and "empty" in C.SYSTEM_42


def test_renderer_drops_negated_statement_verbatim_into_excluded_section():
    final = _f42()
    final["findings"].append({"kind": "OBSERVED", "statement": "No HTTP APIs are imported.", "refs": ["I21"]})
    before = copy.deepcopy(final)
    out = RD.render(final, [], {"accepted": [], "rejected": [], "free_text_absence_rejected": ["No HTTP APIs are imported."]},
                    [], None, "Q?")
    head, tail = out.split("## Nội dung bị loại")
    assert "No HTTP APIs" not in head and '"No HTTP APIs are imported."' in tail and final == before
    assert '"Declares WS2_32 networking imports."' in head


def test_metrics_product_vs_raw_for_v42():
    from evaluation.task07b import metrics as M
    case = {"accessibility_class": M.RP, "reference_EVALUATOR_ONLY": {"relevant_entries": ["WS2_32.dll!#115"]}}
    final = _f42()
    final["findings"].append({"kind": "OBSERVED", "statement": "The file does not import any HTTP APIs.", "refs": ["I22"]})
    r = {"schema_version": "investigation-v4.2", "alias": "s", "status": "FINISHED_FLAGGED", "final": final, "turns": [],
         "rendered_dropped_statements": ["The file does not import any HTTP APIs."],
         "trusted_metadata": {"resolved_sources": [{"literal": "WS2_32.dll!#115", "cited_in": "findings[0]"},
                                                   {"literal": "X.dll!Y", "cited_in": "findings[1]"}]},
         "verification": {"flags": []}}
    row = M.run_row(r, case, 12288)
    assert row["M4_unscoped"] is True and row["v42_M4_rendered_unscoped"] is False  # raw vs rendered
    assert row["v42_M1b_rendered"] is True and row["v42_statements_dropped"] == 1
    s = M.summarize([row])
    assert s["v42_product"]["M4_rendered_unscoped"]["n"] == 0 and s["v42_model_behaviour"]["M4_raw_unscoped"]["n"] == 1
    assert s["v42_model_behaviour"]["runs_with_dropped_statement"] == 1


def test_m4_raw_pre_repair_from_first_final():
    from evaluation.task07b import metrics as M
    case = {"accessibility_class": M.RA, "reference_EVALUATOR_ONLY": {"relevant_entries": []}}
    first = _f42("The file does not import HTTP APIs.")
    last = _f42("Declares WS2_32 networking imports.")
    r = {"schema_version": "investigation-v4.2", "alias": "s", "status": "FINISHED", "final": last,
         "turns": [{"stage": "FINAL", "proposal": first}, {"stage": "FINAL", "proposal": last}],
         "trusted_metadata": {"resolved_sources": []}, "verification": {"flags": []}}
    row = M.run_row(r, case, 12288)
    assert row["v42_M4_raw_pre_repair"] is True and row["M4_unscoped"] is False
