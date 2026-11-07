"""Unit + adversarial tests for D8 Trust & Approval."""
import copy
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bc_contracts as bc
import case_manager as cm
import case_state as cs
from d0.validate import validate, digest
from orchestrator.trust import (
    ApprovalService, ApprovalExpiredError, ApprovalMismatchError,
    AuthenticationError, DpapiKeyProvider, InMemoryKeyProvider, KeyCustodyError,
    LocalOsAuthenticator, MockSigner, StaticAuthenticator, TrustedSigner,
    os_account_name,
)


def make_file_context(path="C:\\samples\\fixture.exe", digest_hex="a" * 64):
    return {
        "schema_version": "context-v1", "collector_version": "1.2.0",
        "collection_id": "COL-D8", "target_type": "FILE", "target": {"path": path},
        "status": "SUCCESS",
        "facets": {
            "file_identity": {"status": "SUCCESS", "value": {
                "device": 1, "inode": 2, "size_bytes": 1024, "mtime_ns": 123}},
            "file_unchanged_during_collection": {"status": "SUCCESS", "value": True},
            "sha256": {"status": "SUCCESS", "value": digest_hex}},
        "errors": [], "limitations": [],
    }


class SignerTests(unittest.TestCase):
    def test_inmemory_keys_are_real_and_32_bytes(self):
        kp = InMemoryKeyProvider()
        self.assertEqual(len(kp.tool_key()), 32)
        self.assertNotEqual(kp.tool_key(), kp.approval_key())

    def test_trusted_signer_produces_verifiable_tool_proof(self):
        kp = InMemoryKeyProvider()
        signer = TrustedSigner(kp)
        payload = {"tool_run_id": "RUN-abc", "tool": "x"}
        proof = signer.sign_tool_result("CASE-" + "a" * 32, payload)
        self.assertEqual(proof["role"], "tool")
        self.assertIn("mac", proof)
        self.assertEqual(signer.trusted_keys(), {"tool": kp.tool_key()})

    def test_mock_signer_is_flagged(self):
        self.assertTrue(getattr(MockSigner(), "is_mock", False))

    @unittest.skipUnless(os.name == "nt", "Token-based identity is Windows-specific")
    def test_analyst_identity_not_env_spoofable(self):
        # Setting USERNAME must NOT change the authenticated subject on Windows,
        # because the identity comes from the process token (GetUserNameW).
        real = os_account_name()
        old = os.environ.get("USERNAME")
        try:
            os.environ["USERNAME"] = "HACKER-SPOOF"
            subject, method = LocalOsAuthenticator().authenticate()
            self.assertNotEqual(subject, "HACKER-SPOOF")
            self.assertEqual(subject, real)
            self.assertEqual(method, "local_os_account")
        finally:
            if old is None:
                os.environ.pop("USERNAME", None)
            else:
                os.environ["USERNAME"] = old

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_dpapi_key_provider_roundtrip(self):
        tmp = Path(tempfile.mkdtemp(prefix="d8-dpapi-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        kp1 = DpapiKeyProvider(tmp / "key.bin")
        tk, ak = kp1.tool_key(), kp1.approval_key()
        self.assertEqual(len(tk), 32)
        # Reload from the protected file -> identical keys.
        kp2 = DpapiKeyProvider(tmp / "key.bin")
        self.assertEqual(kp2.tool_key(), tk)
        self.assertEqual(kp2.approval_key(), ak)


class ApprovalServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d8-approval-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.svc = ApprovalService(ttl_seconds=120)
        self.kp = InMemoryKeyProvider()
        ctx = make_file_context()
        self.target_ref = bc.target_ref_from_context(ctx)
        self.state = cs.build_case_state(ctx)
        self.case_path = cs.save_case_state(self.state, self.tmp)
        self.snapshot = {"case_id": self.state["case_id"], "revision": 1,
                         "target_ref": self.target_ref}
        self.auth = StaticAuthenticator("ANALYST-01")

    def _request(self):
        return self.svc.create_request(
            self.snapshot, action_id="ACT-1", action_type="QUARANTINE_FILE",
            target_ref=self.target_ref, effect_summary="Quarantine the sample",
            risk="HIGH", reason="Confirmed malicious")

    def test_request_is_schema_valid_pending(self):
        req = self._request()
        validate("approval_request", req)
        self.assertEqual(req["status"], "PENDING")
        self.assertEqual(req["expected_revision"], 1)

    def test_decision_subject_comes_from_authenticator(self):
        event = self.svc.record_decision(self._request(), "APPROVED",
                                         StaticAuthenticator("REAL-ANALYST"))
        validate("approval_event", event)
        self.assertEqual(event["authenticated_subject"], "REAL-ANALYST")

    def _drive_to_investigating(self):
        cm.apply_update(self.case_path, "action", {
            "event_id": "EV-1", "action": "START_INVESTIGATION", "actor": "test"})

    def test_authorize_and_commit_response_end_to_end(self):
        self._drive_to_investigating()
        snap = {"case_id": self.state["case_id"], "revision": cm.read_json(self.case_path)["revision"],
                "target_ref": self.target_ref}
        req = self.svc.create_request(
            snap, action_id="ACT-9", action_type="QUARANTINE_FILE",
            target_ref=self.target_ref, effect_summary="Quarantine", risk="HIGH",
            reason="malicious")
        event = self.svc.record_decision(req, "APPROVED", self.auth)
        authz = self.svc.authorize_response(
            snap, {"status": "APPROVED", "description": "Quarantine sample",
                   "approver": "AGENT-SUPPLIED-IGNORED"}, req, event, self.kp)
        # D8 overwrote the Agent-supplied approver with the authenticated subject.
        self.assertEqual(authz["payload"]["approver"], "ANALYST-01")
        self.assertTrue(authz["payload"]["human_approved"])
        result = cm.apply_update(self.case_path, "response", authz["payload"],
                                 authorization=authz["authorization"],
                                 trusted_keys=authz["trusted_keys"])
        self.assertEqual(result["response_count"], 1)

    def test_forged_action_digest_rejected(self):
        req = self._request()
        event = self.svc.record_decision(req, "APPROVED", self.auth)
        tampered = copy.deepcopy(event)
        tampered["action_digest_sha256"] = "f" * 64
        with self.assertRaises(ApprovalMismatchError):
            self.svc.authorize_response(self.snapshot, {"status": "APPROVED",
                "description": "x"}, req, tampered, self.kp)

    def test_rejected_decision_not_authorized(self):
        req = self._request()
        event = self.svc.record_decision(req, "REJECTED", self.auth)
        with self.assertRaises(ApprovalMismatchError):
            self.svc.authorize_response(self.snapshot, {"status": "REJECTED",
                "description": "x"}, req, event, self.kp)

    def test_expired_approval_rejected(self):
        req = self.svc.create_request(
            self.snapshot, action_id="ACT-2", action_type="ISOLATE_HOST",
            target_ref=self.target_ref, effect_summary="Isolate", risk="CRITICAL",
            reason="spreading")
        event = self.svc.record_decision(req, "APPROVED", self.auth)
        expired = copy.deepcopy(event)
        past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        expired["expires_at"] = past
        with self.assertRaises(ApprovalExpiredError):
            self.svc.authorize_response(self.snapshot, {"status": "APPROVED",
                "description": "x"}, req, expired, self.kp)

    def test_revision_changed_since_approval_rejected(self):
        req = self._request()
        event = self.svc.record_decision(req, "APPROVED", self.auth)
        stale_snapshot = {"case_id": self.state["case_id"], "revision": 5,
                          "target_ref": self.target_ref}
        with self.assertRaises(ApprovalMismatchError):
            self.svc.authorize_response(stale_snapshot, {"status": "APPROVED",
                "description": "x"}, req, event, self.kp)


if __name__ == "__main__":
    unittest.main()
