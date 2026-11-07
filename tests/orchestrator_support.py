"""Shared builder for the full real orchestrator stack (Windows execution).

Used by D1 and end-to-end tests. Uses the benign EMBER mock adapter; no mock of
D2/D3/D4/D7/D8/D9 themselves.
"""
import copy
import hashlib
import json
import sys
from pathlib import Path

import bc_contracts as bc
import case_state as cs
from orchestrator.registry import ToolRegistry
from orchestrator.policy_engine import PolicyEngine, PolicyConfig
from orchestrator.provider_install import ProviderInstallation
from orchestrator.trust import TrustedSigner, InMemoryKeyProvider
from orchestrator.case_bridge import CaseBridge
from orchestrator.core import Orchestrator

ROOT = Path(__file__).resolve().parents[1]
EMBER_ADAPTER = ROOT / "tests" / "fixtures" / "ember_mock_adapter.py"
IDENTITY = ("static.ember_features", "0.1.0", "ember_mock")


def fixture(name):
    return json.loads((ROOT / "d0" / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


def build_stack(tmp: Path):
    from orchestrator.executor import PinnedAdapter

    target = tmp / "sample.bin"
    target.write_bytes(b"MZ benign orchestrator fixture\x00" * 40)
    info = target.stat()
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    ctx = {
        "schema_version": "context-v1", "collector_version": "1.2.0",
        "collection_id": "COL-ORCH", "target_type": "FILE",
        "target": {"path": str(target)}, "status": "SUCCESS",
        "facets": {
            "file_identity": {"status": "SUCCESS", "value": {
                "device": info.st_dev, "inode": info.st_ino,
                "size_bytes": info.st_size, "mtime_ns": info.st_mtime_ns}},
            "file_unchanged_during_collection": {"status": "SUCCESS", "value": True},
            "sha256": {"status": "SUCCESS", "value": sha}},
        "errors": [], "limitations": []}
    target_ref = bc.target_ref_from_context(ctx)
    state = cs.build_case_state(ctx)
    case_path = cs.save_case_state(state, tmp)

    interpreter = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
    script = str(EMBER_ADAPTER.resolve())
    pins = [[p, hashlib.sha256(Path(p).read_bytes()).hexdigest()] for p in (interpreter, script)]
    adapter = PinnedAdapter("ember_mock", "0.1.0", "ember_mock_adapter",
                            (interpreter, "-I", script), tuple((p, s) for p, s in pins))

    spec = fixture("tool_spec")
    spec["provider"] = adapter.provider()
    spec["tool_version"] = "0.1.0"
    spec["limits"] = {"timeout_ms": 30000, "max_output_bytes": 262144,
                      "max_artifact_bytes": 1048576, "max_concurrency": 1}
    registry = ToolRegistry()
    registry.register_tool(spec)

    installation = ProviderInstallation()
    installation.install(provider_id="ember_mock", version="0.1.0",
                         adapter_id="ember_mock_adapter",
                         command=(interpreter, "-I", script), pins=pins)

    policy = PolicyEngine(PolicyConfig(
        tool_allowlist=frozenset({IDENTITY}),
        budget_caps={"timeout_ms": 30000, "max_output_bytes": 262144,
                     "max_artifact_bytes": 1048576, "max_concurrency": 1}))
    signer = TrustedSigner(InMemoryKeyProvider())
    bridge = CaseBridge(audit_ledger_root=tmp / "ledgers")
    orch = Orchestrator(registry=registry, policy=policy, signer=signer,
                        installation=installation, bridge=bridge,
                        artifact_root=tmp / "artifacts",
                        run_ledger_path=tmp / "run_ledger.jsonl")

    call = fixture("tool_call")
    call.update({
        "call_id": "CALL-orch00000001", "case_id": state["case_id"],
        "expected_revision": 1, "tool_id": "static.ember_features",
        "tool_version": "0.1.0", "provider_id": "ember_mock",
        "target_ref": copy.deepcopy(target_ref),
        "arguments": {"feature_version": 2},
        "budget": {"timeout_ms": 20000, "max_output_bytes": 200000}})

    return {"registry": registry, "policy": policy, "signer": signer,
            "installation": installation, "bridge": bridge, "orch": orch,
            "call": call, "case_path": case_path, "spec": spec, "state": state,
            "target": target, "target_ref": target_ref}
