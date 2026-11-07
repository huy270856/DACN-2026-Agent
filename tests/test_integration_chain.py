"""End-to-end INTEGRATION tests for the D.0 orchestrator chain.

Proven flow (real D5/D6 subprocess execution on Windows):

    D2 Registry -> D3 Input Validator -> [MOCK admission standing in for D4/D8]
      -> D5/D6 Executor -> D5->D7 adapter -> D7 Result Validator
      -> D9 Case Bridge -> Node C CaseManager

IMPORTANT / honesty constraints enforced here:
  * D4 (Policy) and D8 (Trust & Approval) are NOT implemented. This module
    fabricates a policy_decision and an HMAC signing key purely as MOCKS,
    clearly labelled ``MOCK_...``. They are not a real policy engine or a
    protected signer and must never be read as one.
  * The feature provider is tests/fixtures/ember_mock_adapter.py, a BENIGN mock
    that emits a placeholder zero vector. No real EMBER extraction or LightGBM
    inference happens; no suspect PE is ever executed. Only a harmless synthetic
    file is read.
  * These tests require Windows (D5/D6 use Win32 locked handles + Job Objects).

Covered scenarios: full success chain, provider mismatch (D3), stale revision
(D3 and D9), target-changed-after-collection (D5), policy DENIED not executed
nor recorded as success, artifact tampering (D5->D7 adapter), replay / duplicate
run (Node C), concurrent writer (D9 optimistic lock), and audit-ledger crash
recovery (D9 reconcile).
"""
import copy
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bc_contracts as bc
import case_manager as cm
import case_state as cs
from orchestrator.input_validator import validate_tool_call, ValidationError
from orchestrator.result_validator import ResultValidationError
from orchestrator import execution_adapter
from orchestrator.case_bridge import CaseBridge, StaleRevisionError

EMBER_ADAPTER = ROOT / "tests" / "fixtures" / "ember_mock_adapter.py"

# --- MOCKS standing in for unimplemented D4/D8 (clearly labelled) ----------------
MOCK_TRUSTED_KEY = secrets.token_bytes(32)  # MOCK D8 signer key; NOT a protected key store.


def MOCK_admission_policy(call):
    """MOCK of D4+D8: unconditionally ALLOW, bound to this call. NOT a real policy."""
    return {
        "schema_version": "d0-v1",
        "decision_id": "POL-MOCK-0001",
        "call_id": call["call_id"],
        "case_id": call["case_id"],
        "expected_revision": call["expected_revision"],
        "outcome": "ALLOW",
        "reason_code": "static_readonly_allowed",
        "reasons": ["MOCK admission: no real D4 policy engine exists"],
        "effective_limits": {
            "timeout_ms": 30000,
            "max_output_bytes": 262144,
            "max_artifact_bytes": 1048576,
            "max_concurrency": 1,
        },
        "policy_version": "policy-MOCK",
        "evaluated_at": "2026-11-07T00:00:00Z",
    }


def load_fixture(name):
    return json.loads((ROOT / "d0" / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


@unittest.skipUnless(os.name == "nt", "D5/D6 require Windows locked handles + Job Objects")
class IntegrationChainTests(unittest.TestCase):
    def setUp(self):
        from orchestrator.executor import PinnedAdapter, ToolExecutor
        self.tmp = Path(tempfile.mkdtemp(prefix="dacn-integration-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

        # A harmless synthetic "sample" file (never executed).
        self.target = self.tmp / "sample_có_dấu.bin"
        self.target.write_bytes(b"MZ harmless integration fixture\x00" * 40)
        info = self.target.stat()
        sha = hashlib.sha256(self.target.read_bytes()).hexdigest()

        # Node B context -> Node C case on disk, with STRONG target identity.
        ctx = {
            "schema_version": "context-v1", "collector_version": "1.2.0",
            "collection_id": "COL-INT-0001", "target_type": "FILE",
            "target": {"path": str(self.target)}, "status": "SUCCESS",
            "facets": {
                "file_identity": {"status": "SUCCESS", "value": {
                    "device": info.st_dev, "inode": info.st_ino,
                    "size_bytes": info.st_size, "mtime_ns": info.st_mtime_ns}},
                "file_unchanged_during_collection": {"status": "SUCCESS", "value": True},
                "sha256": {"status": "SUCCESS", "value": sha},
            },
            "errors": [], "limitations": [],
        }
        self.target_ref = bc.target_ref_from_context(ctx)
        self.assertEqual(self.target_ref["identity_strength"], "STRONG")
        self.state = cs.build_case_state(ctx)
        self.case_path = cs.save_case_state(self.state, self.tmp)
        self.case_id = self.state["case_id"]
        self.case_snapshot = {"case_id": self.case_id, "revision": 1,
                              "target_ref": copy.deepcopy(self.target_ref)}

        # D2: a ToolSpec bound to the MOCK ember subprocess provider.
        interpreter = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
        script = str(EMBER_ADAPTER.resolve())
        pins = tuple((p, hashlib.sha256(Path(p).read_bytes()).hexdigest())
                     for p in (interpreter, script))
        self.adapter = PinnedAdapter("ember_mock", "0.1.0", "ember_mock_adapter",
                                     (interpreter, "-I", script), pins)
        self.spec = load_fixture("tool_spec")
        self.spec["provider"] = self.adapter.provider()
        self.spec["tool_version"] = "0.1.0"
        self.spec["limits"] = {"timeout_ms": 30000, "max_output_bytes": 262144,
                               "max_artifact_bytes": 1048576, "max_concurrency": 1}

        # A ToolCall for this case/target.
        self.call = load_fixture("tool_call")
        self.call.update({
            "call_id": "CALL-int00000001", "case_id": self.case_id,
            "expected_revision": 1, "tool_id": "static.ember_features",
            "tool_version": "0.1.0", "provider_id": "ember_mock",
            "target_ref": copy.deepcopy(self.target_ref),
            "arguments": {"feature_version": 2},
            "budget": {"timeout_ms": 20000, "max_output_bytes": 200000},
        })
        self.executor = ToolExecutor(self.tmp / "artifacts")
        self.bridge = CaseBridge(audit_ledger_root=self.tmp / "ledgers")

    # -- helpers ------------------------------------------------------------
    def _d3(self, call=None):
        return validate_tool_call(call or self.call, self.spec, self.case_snapshot,
                                  provider_available=True)

    def _execute(self, policy):
        return self.executor.execute(self.call, self.spec, policy, self.case_snapshot, self.adapter)

    def _to_tool_result(self, output):
        return execution_adapter.ember_result_from_execution(
            output, self.call, self.spec, artifact_root=self.executor.root)

    # -- scenarios ----------------------------------------------------------
    def test_full_success_chain_D2_D3_D5_D7_D9_NodeC(self):
        validated = self._d3()                           # D3
        policy = MOCK_admission_policy(validated)         # MOCK D4/D8 admission
        output = self._execute(policy)                    # D5/D6 real subprocess
        self.assertEqual(output.receipt["outcome"], "SUCCESS")
        tool_result = self._to_tool_result(output)        # D5->D7
        self.assertEqual(tool_result["status"], "SUCCESS")
        self.assertEqual(tool_result["observations"][0]["facet"], "static.ember_features")
        self.assertEqual(tool_result["observations"][0]["trust_level"], "UNTRUSTED_CONTENT")

        result = self.bridge.commit_tool_result(                 # D9 -> Node C
            self.case_path, tool_result, output.receipt,
            trusted_key=MOCK_TRUSTED_KEY, expected_revision=1)
        self.assertGreater(result["revision"], 1)
        self.assertEqual(result["legacy_tool"], "static_ember_features")

        final = cm.read_json(self.case_path)
        self.assertTrue(any(r.get("tool_run_id") == output.receipt["run_id"]
                            for r in final["tool_runs"]))
        self.assertTrue(any(e.get("facet") == "static.ember_features"
                            for e in final["evidence"]))
        # Two-phase ledger trail present.
        ledger = (self.tmp / "ledgers" / self.case_id / "d0_audit_ledger.jsonl")
        phases = [json.loads(x)["phase"] for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertEqual(phases, ["PENDING", "COMMITTED"])

    def test_provider_mismatch_rejected_at_D3(self):
        bad = copy.deepcopy(self.call)
        bad["provider_id"] = "someone_else"
        with self.assertRaises(ValidationError) as ctx:
            self._d3(bad)
        self.assertEqual(ctx.exception.code, "PROVIDER_MISMATCH")

    def test_stale_revision_rejected_at_D3(self):
        bad = copy.deepcopy(self.call)
        bad["expected_revision"] = 999
        with self.assertRaises(ValidationError) as ctx:
            self._d3(bad)
        self.assertEqual(ctx.exception.code, "CASE_REVISION_STALE")

    def test_target_changed_after_collection_rejected_at_D5(self):
        from orchestrator.executor import ExecutionRejected
        self._d3()
        policy = MOCK_admission_policy(self.call)
        self.target.write_bytes(b"this file was modified after collection" * 3)  # tamper on host
        with self.assertRaises(ExecutionRejected) as ctx:
            self._execute(policy)
        self.assertEqual(ctx.exception.code, "TARGET_CHANGED")

    def test_policy_denied_never_executes_and_not_recorded_as_success(self):
        from orchestrator.executor import ExecutionRejected
        denied = MOCK_admission_policy(self.call)
        denied["outcome"] = "DENY"
        denied["reason_code"] = "policy_denied"
        with self.assertRaises(ExecutionRejected) as ctx:
            self._execute(denied)
        self.assertEqual(ctx.exception.code, "POLICY_DENIED")
        # Node C has no tool run for the denied tool, and the denied outcome is
        # never represented as a SUCCESS. (The pre-existing context_collector
        # collection run from case creation is unrelated.)
        state = cm.read_json(self.case_path)
        self.assertFalse(any(r.get("tool") == "static_ember_features"
                             for r in state["tool_runs"]))
        self.assertFalse(any(str(r.get("tool_run_id", "")).startswith("RUN-")
                             for r in state["tool_runs"]))

    def test_artifact_tampering_detected_by_D5_to_D7_adapter(self):
        self._d3()
        output = self._execute(MOCK_admission_policy(self.call))
        self.assertEqual(output.receipt["outcome"], "SUCCESS")
        # Tamper with the captured provider stdout AFTER the receipt recorded its hash.
        (output.run_directory / "stdout.bin").write_bytes(b"tampered provider output")
        with self.assertRaises(ResultValidationError) as ctx:
            self._to_tool_result(output)
        self.assertEqual(ctx.exception.code, "ARTIFACT_INTEGRITY_FAILED")

    def test_replay_duplicate_run_rejected_by_node_c(self):
        self._d3()
        output = self._execute(MOCK_admission_policy(self.call))
        tool_result = self._to_tool_result(output)
        first = self.bridge.commit_tool_result(
            self.case_path, tool_result, output.receipt,
            trusted_key=MOCK_TRUSTED_KEY, expected_revision=1)
        # Replaying the identical ToolResult (same run_id) must be rejected.
        with self.assertRaises(Exception) as ctx:
            self.bridge.commit_tool_result(
                self.case_path, tool_result, output.receipt,
                trusted_key=MOCK_TRUSTED_KEY, expected_revision=first["revision"])
        self.assertIn("Duplicate tool_run_id", str(ctx.exception))

    def test_concurrent_writer_detected_by_D9_optimistic_lock(self):
        self._d3()
        output = self._execute(MOCK_admission_policy(self.call))
        tool_result = self._to_tool_result(output)
        self.bridge.commit_tool_result(                       # writer A: 1 -> higher
            self.case_path, tool_result, output.receipt,
            trusted_key=MOCK_TRUSTED_KEY, expected_revision=1)
        # Writer B still thinks the case is at revision 1 -> stale -> aborts.
        other = copy.deepcopy(tool_result)
        other["run_id"] = "RUN-integration-second-writer"
        receipt2 = copy.deepcopy(output.receipt)
        receipt2["run_id"] = other["run_id"]
        from d0.validate import digest
        other["receipt_sha256"] = digest(receipt2)
        with self.assertRaises(StaleRevisionError):
            self.bridge.commit_tool_result(
                self.case_path, other, receipt2,
                trusted_key=MOCK_TRUSTED_KEY, expected_revision=1)

    def test_audit_ledger_crash_recovery_reconcile(self):
        self._d3()
        output = self._execute(MOCK_admission_policy(self.call))
        tool_result = self._to_tool_result(output)
        self.bridge.commit_tool_result(
            self.case_path, tool_result, output.receipt,
            trusted_key=MOCK_TRUSTED_KEY, expected_revision=1)
        ledger = self.tmp / "ledgers" / self.case_id / "d0_audit_ledger.jsonl"
        # Simulate a crash: a PENDING line for a run that actually committed, with
        # no COMMITTED follow-up (orphaned write-ahead marker).
        orphan = {"audit_id": "AUDIT-orphan", "phase": "PENDING",
                  "run_id": output.receipt["run_id"], "case_id": self.case_id,
                  "raw_tool_result": tool_result, "execution_receipt": output.receipt}
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(orphan) + "\n")
        summary = self.bridge.reconcile_ledger(self.case_path)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["reconciled_committed"], 1)
        tail = json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(tail["phase"], "RECONCILED_COMMITTED")
        self.assertEqual(tail["audit_id"], "AUDIT-orphan")


if __name__ == "__main__":
    unittest.main()
