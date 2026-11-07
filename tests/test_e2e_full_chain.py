"""End-to-end TRUSTED chain: Node B/C -> D1 -> D2 -> D3 -> D4 -> D8 -> D5/D6 -> D7 -> D9 -> Node C.

This suite uses the REAL D4 PolicyEngine and REAL D8 TrustedSigner / ApprovalService
(a genuine HMAC key from InMemoryKeyProvider, not a MockSigner). The only test
doubles are the benign EMBER mock analyzer and a StaticAuthenticator standing in
for interactive OS login. No suspect PE is executed; only a harmless file is read.
"""
import copy
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import case_manager as cm
from d0.validate import digest
from orchestrator.core import Orchestrator
from orchestrator.case_bridge import ReceiptIntegrityError
from orchestrator.trust import (ApprovalService, StaticAuthenticator,
                                TrustedSigner, MockSigner)


@unittest.skipUnless(os.name == "nt", "End-to-end chain drives the Windows executor")
class E2ETrustedChainTests(unittest.TestCase):
    def setUp(self):
        from orchestrator_support import build_stack
        self.tmp = Path(tempfile.mkdtemp(prefix="dacn-e2e-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.s = build_stack(self.tmp)
        self.orch = self.s["orch"]
        self.call = self.s["call"]
        self.case_path = self.s["case_path"]

    def test_trusted_full_chain_uses_no_mock_d4_d8(self):
        # Assert the signer in the trusted path is a real TrustedSigner, not a mock.
        self.assertIsInstance(self.s["signer"], TrustedSigner)
        self.assertFalse(getattr(self.s["signer"], "is_mock", False))
        rec = self.orch.run_tool_call(self.call, self.case_path)
        self.assertEqual((rec.phase, rec.outcome), ("COMMITTED", "SUCCESS"))
        state = cm.read_json(self.case_path)
        # Evidence committed and the two-phase audit ledger is consistent.
        self.assertTrue(any(e.get("facet") == "static.ember_features" for e in state["evidence"]))
        ledger = self.tmp / "ledgers" / state["case_id"] / "d0_audit_ledger.jsonl"
        phases = [__import__("json").loads(x)["phase"]
                  for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertEqual(phases, ["PENDING", "COMMITTED"])

    def test_response_approval_authenticated_end_to_end(self):
        # Run a static analysis, then drive an authenticated analyst approval of a
        # response action through REAL D8 and commit it to Node C.
        self.orch.run_tool_call(self.call, self.case_path)
        cm.apply_update(self.case_path, "action",
                        {"event_id": "EV-INV", "action": "START_INVESTIGATION", "actor": "analyst"})
        snap = {"case_id": self.s["state"]["case_id"],
                "revision": cm.read_json(self.case_path)["revision"],
                "target_ref": self.s["target_ref"]}
        svc = ApprovalService(ttl_seconds=120)
        req = svc.create_request(snap, action_id="ACT-Q1", action_type="QUARANTINE_FILE",
                                 target_ref=self.s["target_ref"], effect_summary="Quarantine",
                                 risk="HIGH", reason="confirmed")
        event = svc.record_decision(req, "APPROVED", StaticAuthenticator("ANALYST-REAL"))
        authz = svc.authorize_response(
            snap, {"status": "APPROVED", "description": "Quarantine the sample"},
            req, event, self.s["signer"]._keys)  # real approval key
        result = cm.apply_update(self.case_path, "response", authz["payload"],
                                 authorization=authz["authorization"],
                                 trusted_keys=authz["trusted_keys"])
        self.assertEqual(result["response_count"], 1)
        self.assertEqual(authz["payload"]["approver"], "ANALYST-REAL")

    def test_replayed_approval_proof_rejected(self):
        self.orch.run_tool_call(self.call, self.case_path)
        cm.apply_update(self.case_path, "action",
                        {"event_id": "EV-INV2", "action": "START_INVESTIGATION", "actor": "a"})
        snap = {"case_id": self.s["state"]["case_id"],
                "revision": cm.read_json(self.case_path)["revision"],
                "target_ref": self.s["target_ref"]}
        svc = ApprovalService()
        req = svc.create_request(snap, action_id="ACT-R", action_type="QUARANTINE_FILE",
                                 target_ref=self.s["target_ref"], effect_summary="q",
                                 risk="HIGH", reason="r")
        event = svc.record_decision(req, "APPROVED", StaticAuthenticator("A"))
        authz = svc.authorize_response(snap, {"status": "APPROVED", "description": "x"},
                                       req, event, self.s["signer"]._keys)
        cm.apply_update(self.case_path, "response", authz["payload"],
                        authorization=authz["authorization"], trusted_keys=authz["trusted_keys"])
        # Replaying the SAME signed proof (same nonce) must be rejected by Node C.
        with self.assertRaises(PermissionError):
            cm.apply_update(self.case_path, "response", authz["payload"],
                            authorization=authz["authorization"], trusted_keys=authz["trusted_keys"])

    def test_restart_recovery_idempotent_run_history(self):
        first = self.orch.run_tool_call(self.call, self.case_path)
        rev_after = cm.read_json(self.case_path)["revision"]
        # Simulate a process restart: a brand-new Orchestrator over the SAME durable
        # run ledger must treat the same call as already done (no re-execution).
        orch2 = Orchestrator(
            registry=self.s["registry"], policy=self.s["policy"], signer=self.s["signer"],
            installation=self.s["installation"], bridge=self.s["bridge"],
            artifact_root=self.tmp / "artifacts", run_ledger_path=self.tmp / "run_ledger.jsonl")
        again = orch2.run_tool_call(self.call, self.case_path)
        self.assertEqual(again.run_id, first.run_id)
        self.assertEqual(cm.read_json(self.case_path)["revision"], rev_after)

    def test_forged_receipt_rejected_at_commit(self):
        # Obtain a real result, then tamper the receipt so its digest no longer
        # matches tool_result.receipt_sha256 -> D9 refuses the commit.
        from orchestrator_support import build_stack
        from orchestrator.execution_adapter import ember_result_from_execution
        from orchestrator.executor import ToolExecutor
        s2 = build_stack(Path(tempfile.mkdtemp(prefix="dacn-e2e-forge-")))
        self.addCleanup(lambda: shutil.rmtree(s2["case_path"].parent, ignore_errors=True))
        execu = ToolExecutor(s2["case_path"].parent / "art")
        policy = s2["policy"].evaluate(s2["call"], s2["spec"], {
            "case_id": s2["state"]["case_id"], "revision": 1, "target_ref": s2["target_ref"]})
        output = execu.execute(s2["call"], s2["spec"], policy, {
            "case_id": s2["state"]["case_id"], "revision": 1, "target_ref": s2["target_ref"]},
            s2["installation"].pinned_adapter_for(s2["spec"]))
        tool_result = ember_result_from_execution(output, s2["call"], s2["spec"],
                                                   artifact_root=execu.root)
        tampered_receipt = copy.deepcopy(output.receipt)
        # Keep the receipt schema-valid (finish after start) but change its digest.
        tampered_receipt["finished_at"] = "2099-01-01T00:00:00Z"
        with self.assertRaises(ReceiptIntegrityError):
            s2["bridge"].commit_tool_result(
                s2["case_path"], tool_result, tampered_receipt,
                trusted_key=s2["signer"].tool_key(), expected_revision=1)

    def test_concurrent_second_call_sees_stale_revision(self):
        self.orch.run_tool_call(self.call, self.case_path)  # advances revision
        other = copy.deepcopy(self.call)
        other["call_id"] = "CALL-orch00000002"
        other["expected_revision"] = 1  # stale: case already advanced
        rec = self.orch.run_tool_call(other, self.case_path)
        self.assertEqual(rec.outcome, "REJECTED")
        self.assertEqual(rec.reason_code, "CASE_REVISION_STALE")


if __name__ == "__main__":
    unittest.main()
