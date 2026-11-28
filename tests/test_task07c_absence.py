"""TASK 07C: coverage ledger, investigation-v4.1 absence_claims, coverage summary (unit + MOCK_LLM)."""
import copy
import json

import pytest

from agent.planner import PlanResult
from investigation_v4 import contract as C, ledger as L, verifier as V
from investigation_v4.config import V4Config
from tests.test_task07b_query_projector import _payload
from tests.test_task07b_workflow import CFG, Mock, _final, _run, case  # noqa: F401 (fixture)


def _led(v):
    qlog = [{"by": "SYMBOL_PREFIX", "value": "socket", "page": 0, "total_matches": 0, "indices": []},
            {"by": "DLL", "value": "WS2_32.dll", "page": 0, "total_matches": 3, "indices": [21, 22, 23]},
            {"by": "SYMBOL_PREFIX", "value": "Get", "page": 0, "total_matches": 21, "indices": list(range(16))}]
    return L.build(qlog, True, v)


def test_ledger_ids_exhaustion_and_summary():
    v = _payload()
    led = _led(v)
    assert [(e["id"], e["kind"], e["exhausted"]) for e in led] == [
        ("Q1", "INDEX", True), ("Q2", "SYMBOL_PREFIX", True), ("Q3", "DLL", True), ("Q4", "SYMBOL_PREFIX", False)]
    s = L.summary(led)
    assert "Q4 SYMBOL_PREFIX Get (NOT exhausted (16/21 returned))" in s and "NOT covered" in s
    assert L.build([], False, v) == [] and "nothing" in L.summary([])


def test_contract_41_backward_compatible():
    assert C.final_schema() == C.final_schema("4.0") and "absence_claims" not in C.final_schema()
    s = C.final_schema("4.1")
    assert "absence_claims" in s["required"] and list(s["properties"])[0] == "analysis"
    with pytest.raises(ValueError):
        C.final_schema("9")
    with pytest.raises(ValueError):
        V4Config(contract_version="5")


@pytest.mark.parametrize("claim, ok, reason", [
    ({"api_or_prefix": "socket", "scope_ref": "Q2"}, True, None),
    ({"api_or_prefix": "socketpair", "scope_ref": "Q2"}, True, None),           # inside exhausted prefix scope
    ({"api_or_prefix": "connect", "scope_ref": "Q2"}, False, "OUT_OF_SCOPE"),
    ({"api_or_prefix": "GetTickCount", "scope_ref": "Q4"}, False, "SCOPE_NOT_EXHAUSTED"),
    ({"api_or_prefix": "send", "scope_ref": "Q3"}, True, None),                 # WS2_32 fully returned, no send*
    ({"api_or_prefix": "WSAStartup", "scope_ref": "Q3"}, False, "CONTRADICTED"),  # resolved #115 = WSAStartup
    ({"api_or_prefix": "advapi32.dll", "scope_ref": "Q1"}, True, None),
    ({"api_or_prefix": "msvcrt.dll", "scope_ref": "Q1"}, False, "CONTRADICTED"),
    ({"api_or_prefix": "CreateFileW", "scope_ref": "Q1"}, False, "OUT_OF_SCOPE"),
    ({"api_or_prefix": "socket", "scope_ref": "Q9"}, False, "UNKNOWN_SCOPE_REF"),
])
def test_absence_claim_rules(claim, ok, reason):
    v = _payload()
    obj = dict(_final(["I21"], text="Declared WS2_32 ordinal imports were observed."), absence_claims=[claim])
    ab = V.check_absence_claims(obj, _led(v), v)
    if ok:
        assert ab["accepted"] and not ab["rejected"]
    else:
        assert ab["rejected"] and ab["rejected"][0]["reason"].startswith(reason)


def test_free_text_absence_rejected_without_editing_text():
    v = _payload()
    obj = dict(_final(["I21"], text="The file has no network APIs."), absence_claims=[])
    before = copy.deepcopy(obj)
    ab = V.check_absence_claims(obj, _led(v), v)
    assert ab["free_text_absence_rejected"] == ["The file has no network APIs."] and obj == before
    narrow = dict(_final(["I21"], text="No import name starting with socket was found."), absence_claims=[])
    assert V.check_absence_claims(narrow, _led(v), v)["free_text_absence_rejected"] == []  # existing whitelist kept


class Mock41(Mock):
    """MOCK_LLM: final with a free-text absence, then (on repair) a structured claim."""

    def __init__(self, fix=True):
        super().__init__()
        self.finals = 0
        self.fix = fix

    def decide(self, ctx):
        if not ctx["finalization_stage"]:
            return super().decide(ctx)
        self.ctxs.append(copy.deepcopy(ctx))
        self.finals += 1
        f = ctx["facts"]
        src = [x["handle"] for x in f["viewed_imports"][:1]] or [f["evidence"][0]["handle"]]
        if self.finals == 1 or not self.fix:
            obj = dict(_final(src, text="The file has no network APIs."), absence_claims=[])
        else:
            q = next(e["id"] for e in f["coverage_ledger"] if e["kind"] == "INDEX")
            obj = dict(_final(src, text="Declared imports are listed."),
                       absence_claims=[{"api_or_prefix": "wininet.dll", "scope_ref": q}])
        return PlanResult(json.dumps(obj), 0.0, {"mock": True})


def test_e2e_v41_repair_then_accept(case):
    m = Mock41()
    r = _run(case, m, V4Config(contract_version="4.1"))
    assert r["schema_version"] == "investigation-v4.1" and r["final"] is not None
    finals = [t for t in r["turns"] if t["stage"] in ("FINAL", "FORCED_FINAL")]
    assert len(finals) == 2 and finals[1]["is_repair"]
    assert "ABSENCE_REJECTED" in finals[1]["context"]["facts"]["repair_feedback"]["error"]
    assert finals[0]["context"]["facts"]["coverage_summary"].startswith("Covered:")
    assert "coverage_ledger" not in r["turns"][0]["context"]["facts"]  # only at final stage
    ab = r["verification"]["absence_claims"]
    assert len(ab["accepted"]) == 1 and not ab["rejected"] and not ab["free_text_absence_rejected"]
    assert "ABSENCE RULE" in finals[0]["context"]["system"]


def test_e2e_v41_rejection_recorded_after_failed_repair(case):
    r = _run(case, Mock41(fix=False), V4Config(contract_version="4.1"))
    assert "free_text_absence_rejected" in r["verification"]["flags"] and r["status"] == "FINISHED_FLAGGED"
    assert r["final"]["answer"]  # model text preserved, not rewritten
    assert r["effective_recommendation"]["action"] == "MANUAL_REVIEW"


def test_e2e_v40_default_unchanged(case):
    r = _run(case, Mock())
    assert r["schema_version"] == "investigation-v4.0" and "absence_claims" not in (r["verification"] or {})
    assert all("coverage_ledger" not in t["context"]["facts"] for t in r["turns"])
