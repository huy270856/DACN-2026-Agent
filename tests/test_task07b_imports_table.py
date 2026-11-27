"""TASK 07B S2: static.pe_imports_table adapter, D7 validator, install and backend wiring.

Unit + real-adapter integration on benign System32 PEs already used by earlier tests (never
a 07B cohort file; no malicious samples). No model inference.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest

import case_manager as cm
from agent.config import AgentConfig
from dacn import application as app, investigation as inv
from investigation_v3 import audit, import_adapter as v3_adapter
from investigation_v4 import imports_table_adapter as A, imports_table_tool as T
from investigation_v4.controller import ToolBinding, V4Controller
from orchestrator.result_validator import ResultValidationError

WHOAMI = Path("C:/Windows/System32/whoami.exe")
TRACERT = Path("C:/Windows/System32/tracert.exe")
BINDING = ToolBinding(T.TOOL_ID, T.FACET, T.ARGUMENTS)


def need(p):
    if not p.exists():
        pytest.skip("Windows benign PE required")


# ----------------------------------------------------------------------------- adapter
def test_invalid_pe_and_size_budget():
    with pytest.raises(ValueError, match="Invalid PE"):
        A.inspect_bytes(b"not PE")
    with pytest.raises(ValueError, match="8 MiB"):
        A.inspect_bytes(b"MZ" + b"0" * A.MAX_BYTES)


def test_real_table_deterministic_ordered_and_consistent(monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail("network forbidden"))
    need(WHOAMI)
    a, b = A.inspect_file(WHOAMI), A.inspect_file(WHOAMI)
    assert a == b
    assert a["target_sha256"] == hashlib.sha256(WHOAMI.read_bytes()).hexdigest()
    assert a["returned_entries"] == a["total_entries"] == len(a["entries"]) and not a["truncated"]
    T.check_payload(a)
    # Same declaration order as the frozen v3 analyzer for its first 64 entries.
    v3 = v3_adapter.inspect_file(WHOAMI)["entries"]
    mine = [{"library": a["libraries"][e[0]]["name"], "symbol": e[1], "ordinal": e[2], "delay": e[3]}
            for e in a["entries"][:64]]
    assert mine == v3


def test_ordinal_resolution_ws2_32_annotation_only():
    need(TRACERT)
    p = A.inspect_file(TRACERT)
    res = [e for e in p["entries"] if e[4] is not None]
    assert res and p["resolution_source"].startswith("ordinal-table-ws2_32-v1")
    table, lookup, _ = T.pinned_table()
    for e in res:
        assert e[1] is None and e[2] is not None  # original symbol stays null
        assert p["libraries"][e[0]]["name"].lower() == "ws2_32.dll"
        assert e[4] == lookup["ws2_32.dll"][e[2]]
    # Non-ws2_32 ordinals are never resolved.
    assert all(e[4] is None for e in p["entries"] if e[2] is not None
               and p["libraries"][e[0]]["name"].lower() != "ws2_32.dll")


def _blocks(n_entries, name_len=20, libs=3):
    per = n_entries // libs
    out = []
    for i in range(libs):
        k = per if i < libs - 1 else n_entries - per * (libs - 1)
        out.append((f"LIB{i}.dll", False, [("S" * (name_len - 6) + f"{j:06d}", None) for j in range(k)]))
    return out


def _payload(blocks, monkeypatch, **kw):
    total = sum(len(b[2]) for b in blocks)
    monkeypatch.setattr(A, "parse_table", lambda data: (blocks, total, "LIEF test"))
    return A.inspect_bytes(b"MZ" + b"\0" * 100, **kw)


def test_truncation_at_max_entries(monkeypatch):
    p = _payload(_blocks(1500), monkeypatch)
    assert p["returned_entries"] == 1024 and p["total_entries"] == 1500
    assert p["truncated"] and p["truncation_reason"] == "MAX_ENTRIES"
    assert sum(l["declared_count"] for l in p["libraries"]) == 1500
    assert p["libraries"][-1]["returned_count"] < p["libraries"][-1]["declared_count"]
    T.check_payload(p)
    assert len(A.encode(p)) <= A.OUTPUT_BUDGET


def test_boundary_1024_longest_names_controlled_reduction(monkeypatch):
    # 1024 entries with the longest allowed symbol (160) cannot fit; adapter reduces deterministically.
    p = _payload(_blocks(1024, name_len=160), monkeypatch)
    assert p["truncated"] and p["truncation_reason"] == "OUTPUT_BYTES"
    assert 0 < p["returned_entries"] < 1024
    assert len(A.encode(p)) <= A.OUTPUT_BUDGET < T.LIMITS["max_output_bytes"]
    T.check_payload(p)
    assert any("Output byte budget" in x for x in p["limitations"])
    q = _payload(_blocks(1024, name_len=160), monkeypatch)
    assert q == p  # deterministic


def test_1024_typical_names_fit_without_reduction(monkeypatch):
    p = _payload(_blocks(1024, name_len=30, libs=40), monkeypatch)
    assert not p["truncated"] and p["truncation_reason"] is None and len(A.encode(p)) <= A.OUTPUT_BUDGET


def test_name_budgets_enforced():
    class E:
        def __init__(self, name): self.is_ordinal, self.ordinal, self.name = False, 0, name

    class L:
        def __init__(self, name, entries): self.name, self.entries = name, entries

    class B:
        def __init__(self, libs): self.imports, self.delay_imports = libs, []
    import lief
    orig = lief.PE.parse
    try:
        lief.PE.parse = lambda data: B([L("x" * 129, [])])
        with pytest.raises(ValueError, match="library exceeds"):
            A.parse_table(b"MZ" + b"\0" * 100)
        lief.PE.parse = lambda data: B([L("a.dll", [E("s" * 161)])])
        with pytest.raises(ValueError, match="symbol exceeds"):
            A.parse_table(b"MZ" + b"\0" * 100)
    finally:
        lief.PE.parse = orig


# ----------------------------------------------------------------------------- D7 cross-field rules
def _good():
    need(TRACERT)
    return A.inspect_file(TRACERT)


@pytest.mark.parametrize("mutate, msg", [
    (lambda p: p.update(returned_entries=p["returned_entries"] - 1), "returned/total"),
    (lambda p: p.update(truncated=True), "truncated flag"),
    (lambda p: p.update(truncation_reason="MAX_ENTRIES"), "truncation_reason without"),
    (lambda p: p["libraries"][0].update(declared_count=p["libraries"][0]["declared_count"] + 1), "sum to total"),
    (lambda p: p["libraries"][1].update(first_index=p["libraries"][1]["first_index"] + 1), "tile"),
    (lambda p: p["entries"][0].__setitem__(0, 1), "library/delay"),
    (lambda p: p["entries"][0].__setitem__(2, 7), "exactly one symbol or ordinal"),
    (lambda p: p.update(ordinal_table_sha256="0" * 64), "pinned table"),
    (lambda p: next(e for e in p["entries"] if e[4]).__setitem__(4, "Evil"), "resolved_symbol differs"),
    (lambda p: p.update(resolution_source=None), "resolution_source"),
])
def test_check_payload_rejects_each_rule(mutate, msg):
    p = copy.deepcopy(_good())
    mutate(p)
    with pytest.raises(ValueError, match=msg):
        T.check_payload(p)


def test_resolution_on_unlisted_library_rejected():
    p = copy.deepcopy(_good())
    e = next(e for e in p["entries"] if e[4])
    p["libraries"][e[0]]["name"] = "WSOCK32.dll"  # not in the pinned allowlist
    with pytest.raises(ValueError, match="resolved_symbol differs"):
        T.check_payload(p)


def test_output_schema_shape():
    from d0.validate import validate, ContractError
    p = copy.deepcopy(_good())
    validate("pe-imports-table-output-v1", p)
    bad = copy.deepcopy(p)
    bad["entries"][0].append("extra")
    with pytest.raises(ContractError):
        validate("pe-imports-table-output-v1", bad)
    with pytest.raises(ContractError):
        validate("pe-imports-table-input-v1", {"max_entries": 64})


# ----------------------------------------------------------------------------- real D1-D9
@pytest.fixture
def v4case(tmp_path):
    need(WHOAMI)
    cfg = AppConfig_from(tmp_path)
    intake = app.intake_file(str(WHOAMI), cfg)
    path = cm.case_path(cfg.cases_dir, intake["case_id"])
    registry, orch = inv.build_detector_backend(cfg, include_imports_table=True)
    events = []
    policy = audit.attach(orch, events)
    state = cm.read_json(path)
    ctl = V4Controller(registry, orch, AgentConfig(), state, policy, [BINDING])
    return cfg, path, registry, orch, events, policy, state, ctl


def AppConfig_from(tmp_path):
    from dacn.config import AppConfig
    return AppConfig.from_home(tmp_path / "home")


def run_table(fx):
    cfg, path, registry, orch, events, policy, state, ctl = fx
    spec = ctl.available_tools(state)[0]
    proposal = ctl.tool_proposal(spec, state, "need declared imports")
    ctl.validate(proposal, state)
    return ctl.run_tool(proposal, state, path)


def test_backend_default_unchanged(tmp_path):
    from dacn.config import AppConfig
    reg0, _ = inv.build_detector_backend(AppConfig.from_home(tmp_path / "a"))
    reg1, _ = inv.build_detector_backend(AppConfig.from_home(tmp_path / "b"), include_imports=True)
    assert all(s["tool_id"] != T.TOOL_ID for s in reg0.list_tools() + reg1.list_tools())


def test_real_d1_d9_commit(v4case):
    cfg, path, registry, orch, events, policy, initial, ctl = v4case
    assert [s["tool_id"] for s in ctl.available_tools(initial)] == [T.TOOL_ID]
    record = run_table(v4case)
    assert record.outcome == "SUCCESS", record
    after = cm.validate_case(cm.read_json(path))
    assert after["revision"] > initial["revision"]
    ev = next(e for e in after["evidence"] if e["facet"] == T.FACET)
    assert ev["status"] == "SUCCESS" and ev["trust_level"] == "UNTRUSTED_CONTENT"
    assert ev["value"]["target_sha256"] == initial["target_ref"]["verified_digest"]["value"]
    assert ev["value"]["returned_entries"] == ev["value"]["total_entries"]
    assert [e["stage"] for e in events] == ["D4", "D5_D6_RECEIPT", "D7_VALIDATED", "D9_COMMITTED"]
    # Committed tool is never offered again; duplicate call rejected.
    assert ctl.available_tools(after) == []
    fresh = V4Controller(registry, orch, AgentConfig(), after, policy, [BINDING])
    assert fresh.available_tools(after) == []


def test_d4_default_deny_without_explicit_allowlist(v4case, monkeypatch):
    cfg, path, registry, orch, events, policy, state, ctl = v4case
    from orchestrator.policy_engine import PolicyConfig, PolicyEngine
    cfg_no = PolicyConfig(tool_allowlist=frozenset(), budget_caps={"timeout_ms": 120000, "max_output_bytes": 262144,
                                                                    "max_artifact_bytes": 1048576, "max_concurrency": 1})
    deny = PolicyEngine(cfg_no)
    spec = registry.get_tool(T.TOOL_ID, T.VERSION)
    tool = {"tool_id": T.TOOL_ID, "tool_version": T.VERSION, "provider_id": spec["provider"]["id"], "arguments": T.ARGUMENTS}
    assert deny.evaluate(ctl._build_toolcall(tool, state), spec, state)["outcome"] == "DENY"
    ctl_deny = V4Controller(registry, orch, AgentConfig(), state, deny, [BINDING])
    assert ctl_deny.available_tools(state) == []


@pytest.mark.parametrize("mutation", ["sha", "count", "resolved", "table"])
def test_normalize_rejects_tampered_payload(v4case, mutation):
    assert run_table(v4case).outcome == "SUCCESS"
    events, state, ctl, registry = v4case[4], v4case[6], v4case[7], v4case[2]
    d7 = next(e for e in events if e["stage"] == "D7_VALIDATED")
    receipt = next(e["receipt"] for e in events if e["stage"] == "D5_D6_RECEIPT")
    spec = registry.get_tool(T.TOOL_ID, T.VERSION)
    call = ctl._build_toolcall(ctl.tool_proposal(spec, state, "x")["tool"], state)
    call.update(call_id=receipt["call_id"])
    payload = copy.deepcopy(d7["result"]["observations"][0]["value"])
    if mutation == "sha":
        payload["target_sha256"] = "0" * 64
    elif mutation == "count":
        payload["returned_entries"] -= 1
    elif mutation == "resolved":
        e = next((e for e in payload["entries"] if e[2] is not None), None)
        if e is None:
            payload["entries"][0][4] = "Forged"
        else:
            e[4] = "Forged"
    else:
        payload["ordinal_table_version"] = "other"
    with pytest.raises(ResultValidationError):
        T.normalize(payload, receipt, call, spec)


def test_spec_effects_limits_and_pins():
    from orchestrator.registry import ToolRegistry
    from orchestrator.provider_install import ProviderInstallation
    reg, inst = ToolRegistry(), ProviderInstallation()
    spec = T.install(reg, inst)
    e = spec["effects"]
    assert not e["executes_foreign_code"] and not e["writes_filesystem"] and not e["requires_human_approval"]
    assert spec["limits"]["max_output_bytes"] == 131072 <= 262144
    rec = repr(inst.__dict__)
    assert "ordinal_table.json" in rec and "imports_table_adapter.py" in rec
