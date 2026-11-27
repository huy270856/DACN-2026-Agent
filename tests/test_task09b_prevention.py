"""TASK09B adversarial contract tests. All rule changes are in-memory MOCK."""
import hashlib
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from response.prevention import BlockRequest, Prevention


class PreventionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task09b-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = bytearray(128)
        self.data[:2] = b"MZ"
        self.data[60:64] = (64).to_bytes(4, "little")
        self.data[64:68] = b"PE\0\0"
        self.file = self.root / "fixture.exe"
        self.file.write_bytes(self.data)
        self.request = BlockRequest("r1", "case1", 1, "fixture.exe", hashlib.sha256(self.data).hexdigest())
        self.engine = Prevention(self.root, mode="mock", authorize=lambda r, op: True)

    def plan_apply(self):
        self.assertEqual(self.engine.plan_block(self.request)["status"], "PLANNED")
        self.assertEqual(self.engine.apply_block(self.request)["status"], "MOCK_APPLIED")

    def test_default_dry_run_never_mutates(self):
        engine = Prevention(self.root, authorize=lambda r, op: True)
        before = self.file.read_bytes()
        self.assertEqual(engine.plan_block(self.request)["status"], "PLANNED")
        for op in (engine.apply_block, engine.verify_block, engine.rollback_block):
            self.assertEqual(op(self.request)["reason_code"], "LIVE_BLOCKED_DRY_RUN_ONLY")
        self.assertEqual(engine.rules, {})
        self.assertEqual(before, self.file.read_bytes())

    def test_mock_lifecycle_and_unrelated_rule_preserved(self):
        self.engine.rules["unrelated"] = {"external": True}
        self.plan_apply()
        result = self.engine.verify_block(self.request)
        self.assertEqual(result["status"], "MOCK_VERIFIED")
        self.assertFalse(result["live_execution_verified"])
        self.assertEqual(self.engine.rollback_block(self.request)["status"], "MOCK_ROLLED_BACK")
        self.assertEqual(self.engine.rules, {"unrelated": {"external": True}})

    def test_duplicate_apply_does_not_reapply(self):
        self.plan_apply()
        self.assertEqual(self.engine.apply_block(self.request)["reason_code"], "DUPLICATE_APPLY_USE_VERIFY")
        self.assertEqual(len(self.engine.rules), 1)

    def test_request_id_rebinding_rejected(self):
        self.engine.plan_block(self.request)
        result = self.engine.plan_block(replace(self.request, case_revision=2))
        self.assertEqual(result["reason_code"], "DUPLICATE_REQUEST_CONFLICT")

    def test_plan_return_cannot_be_mutated_to_change_saved_plan(self):
        result = self.engine.plan_block(self.request)
        result["plan"]["identity"]["sha256"] = "0" * 64
        self.assertEqual(self.engine.apply_block(self.request)["status"], "MOCK_APPLIED")

    def test_identity_changed_after_plan(self):
        self.engine.plan_block(self.request)
        self.file.write_bytes(self.data + b"changed")
        self.assertEqual(self.engine.apply_block(self.request)["reason_code"], "TARGET_HASH_MISMATCH")
        self.assertEqual(self.engine.rules, {})

    def test_mutating_apply_result_cannot_change_rule_or_audit(self):
        self.engine.plan_block(self.request)
        result = self.engine.apply_block(self.request)
        result["identity_before"]["sha256"] = "0" * 64
        self.assertEqual(self.engine.verify_block(self.request)["status"], "MOCK_VERIFIED")
        self.assertEqual(self.engine.audit[1]["identity_before"]["sha256"], self.request.target_sha256)

    def test_deleted_target_does_not_prevent_recovery(self):
        self.plan_apply()
        self.file.unlink()
        self.assertEqual(self.engine.verify_block(self.request)["status"], "REJECTED")
        self.assertEqual(self.engine.rollback_block(self.request)["status"], "MOCK_ROLLED_BACK")

    def test_policy_drift_rejected(self):
        self.engine.plan_block(self.request)
        self.engine.rules["concurrent"] = {"unknown": True}
        self.assertEqual(self.engine.apply_block(self.request)["reason_code"], "POLICY_STATE_CHANGED_REPLAN_REQUIRED")
        self.assertEqual(len(self.engine.rules), 1)

    def test_authorization_denied_by_default(self):
        engine = Prevention(self.root, mode="mock")
        engine.plan_block(self.request)
        self.assertEqual(engine.apply_block(self.request)["reason_code"], "MOCK_HARNESS_AUTHORIZATION_DENIED")
        self.assertEqual(engine.rules, {})

    def test_rollback_needs_separate_authorization(self):
        self.engine.authorize = lambda r, op: op != "rollback_block"
        self.plan_apply()
        self.assertEqual(self.engine.rollback_block(self.request)["status"], "REJECTED")
        self.assertEqual(len(self.engine.rules), 1)

    def test_missing_plan(self):
        self.assertEqual(self.engine.apply_block(self.request)["reason_code"], "PLAN_REQUIRED")

    def test_apply_failure_audited_without_rule_change(self):
        self.engine.plan_block(self.request)
        self.engine.fail_next = "apply"
        self.assertEqual(self.engine.apply_block(self.request)["reason_code"], "INJECTED_APPLY_FAILURE_NO_CHANGE")
        self.assertEqual(self.engine.rules, {})
        self.assertEqual(self.engine.audit[-1]["status"], "REJECTED")

    def test_rollback_failure_retains_rule_and_retry_works(self):
        self.plan_apply()
        self.engine.fail_next = "rollback"
        self.assertEqual(self.engine.rollback_block(self.request)["reason_code"], "INJECTED_ROLLBACK_FAILURE_RULE_RETAINED")
        self.assertEqual(len(self.engine.rules), 1)
        self.assertEqual(self.engine.rollback_block(self.request)["status"], "MOCK_ROLLED_BACK")
        self.assertEqual(self.engine.rollback_block(self.request)["reason_code"], "DUPLICATE_ROLLBACK_NO_CHANGE")

    def test_rollback_refuses_changed_owned_rule(self):
        self.plan_apply()
        key = next(iter(self.engine.rules))
        self.engine.rules[key] = {"foreign": True}
        self.assertEqual(self.engine.rollback_block(self.request)["reason_code"], "OWNED_RULE_CHANGED_REQUIRES_REVIEW")
        self.assertIn(key, self.engine.rules)

    def test_traversal_absolute_and_ads_rejected(self):
        for path in ("../outside.exe", str(self.file.absolute()), "fixture.exe:stream", "\\outside.exe", "NUL.exe"):
            with self.subTest(path=path):
                engine = Prevention(self.root)
                result = engine.plan_block(replace(self.request, target_ref=path))
                self.assertEqual(result["reason_code"], "TARGET_OUTSIDE_LAB")

    def test_non_pe_rejected(self):
        self.file.write_bytes(b"hello")
        request = replace(self.request, target_sha256=hashlib.sha256(b"hello").hexdigest())
        self.assertEqual(self.engine.plan_block(request)["reason_code"], "NOT_PE_HEADER")

    def test_permission_failure_is_rejection(self):
        from unittest.mock import patch
        with patch.object(Path, "open", side_effect=PermissionError("fixture-only injection")):
            result = self.engine.plan_block(self.request)
        self.assertEqual(result["reason_code"], "PermissionError")
        self.assertEqual(self.engine.rules, {})

    def test_reparse_rejected_without_creating_system_links(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=stat_mode(), st_file_attributes=0x400)):
            self.assertEqual(self.engine.plan_block(self.request)["reason_code"], "REPARSE_POINT_REJECTED")

    def test_bad_revision_rejected(self):
        self.assertEqual(self.engine.plan_block(replace(self.request, case_revision=True))["reason_code"], "INVALID_REQUEST")

    def test_malformed_request_returns_rejection_without_crashing(self):
        for request in ({"approved": True}, None, replace(self.request, target_ref=123)):
            with self.subTest(request=request):
                self.assertEqual(self.engine.plan_block(request)["status"], "REJECTED")
                self.assertEqual(self.engine.apply_block(request)["status"], "REJECTED")
        self.assertEqual(self.engine.rules, {})

    def test_live_mode_cannot_be_enabled_by_caller(self):
        from response.prevention import PrototypeError
        with self.assertRaisesRegex(PrototypeError, "MODE_UNSUPPORTED"):
            Prevention(self.root, mode="live", authorize=lambda r, op: True)

    def test_returned_receipt_cannot_clear_duplicate_history(self):
        self.engine.plan_block(self.request)
        applied = self.engine.apply_block(self.request)
        applied.clear()
        rolled_back = self.engine.rollback_block(self.request)
        rolled_back.clear()
        self.assertEqual(self.engine.apply_block(self.request)["reason_code"], "DUPLICATE_APPLY_USE_VERIFY")
        self.assertEqual(self.engine.rollback_block(self.request)["reason_code"], "DUPLICATE_ROLLBACK_NO_CHANGE")

    @unittest.skipUnless(os.name == "nt", "Windows file-sharing integration only")
    def test_windows_real_locked_fixture_rejects_without_mutation(self):
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        create = api.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        close = api.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL
        handle = create(str(self.file), 0x80000000, 0, None, 3, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            self.fail("Could not open lab fixture for real Windows sharing test")
        try:
            result = self.engine.plan_block(self.request)
            self.assertEqual(result["status"], "REJECTED")
            self.assertEqual(result["reason_code"], "PermissionError")
            self.assertEqual(self.engine.rules, {})
        finally:
            close(handle)

    def test_probe_unsupported_and_permission_failure(self):
        from unittest.mock import patch
        from response.prevention.__main__ import powershell_capabilities as capabilities
        with patch("response.prevention.__main__.os.name", "posix"):
            self.assertEqual(capabilities()["reason_code"], "WINDOWS_REQUIRED")
        with patch("response.prevention.__main__.subprocess.run", side_effect=PermissionError):
            self.assertEqual(capabilities()["reason_code"], "PermissionError")


def stat_mode():
    import stat
    return stat.S_IFREG


if __name__ == "__main__":
    unittest.main()
