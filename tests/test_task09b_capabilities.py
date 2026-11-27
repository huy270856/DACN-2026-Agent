"""Fact collection failures must never turn into live support."""
import unittest
from unittest.mock import patch

from response.prevention.capabilities import collect_capabilities


class CapabilitiesTests(unittest.TestCase):
    def test_non_windows_is_unsupported_without_registry_access(self):
        with patch("response.prevention.capabilities.os.name", "posix"), patch(
                "response.prevention.capabilities._registry") as registry:
            result = collect_capabilities()
        registry.assert_not_called()
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertFalse(result["live_supported"])

    def probe(self, admin=False, service="STOPPED", manufacturer="ASUS"):
        with patch("response.prevention.capabilities._registry", return_value={"SystemManufacturer": manufacturer}), patch(
                "response.prevention.capabilities._admin_token", return_value=admin), patch(
                "response.prevention.capabilities._appidsvc", return_value=service):
            return collect_capabilities()

    def test_insufficient_privileges_explicit_and_no_writes(self):
        result = self.probe()
        self.assertEqual(result["reason_code"], "INSUFFICIENT_PRIVILEGES_FOR_LIVE_POLICY_MANAGEMENT")
        self.assertEqual(result["policy_writes"], 0)
        self.assertEqual(result["service_writes"], 0)

    def test_admin_and_vm_hint_are_not_approval(self):
        result = self.probe(admin=True, service="RUNNING", manufacturer="VMware")
        self.assertEqual(result["vm_hint"], "VIRTUALIZATION_HINT_NOT_APPROVAL")
        self.assertEqual(result["approved_vm"], "NOT_ESTABLISHED")
        self.assertFalse(result["live_supported"])
        self.assertIn("RECOVERY_NOT_REHEARSED", result["blockers"])

    def test_read_failures_are_unknown_not_false_facts(self):
        with patch("response.prevention.capabilities._registry", side_effect=PermissionError), patch(
                "response.prevention.capabilities._admin_token", side_effect=PermissionError), patch(
                "response.prevention.capabilities._appidsvc", side_effect=PermissionError):
            result = collect_capabilities()
        self.assertIsNone(result["os"])
        self.assertIsNone(result["token_is_administrator"])
        self.assertEqual(result["appidsvc_status"], "UNKNOWN")
        self.assertEqual(len(result["errors"]), 4)
        self.assertFalse(result["live_supported"])

    def test_powershell_refusal_is_reported_without_retry_bypass(self):
        from response.prevention.__main__ import powershell_capabilities
        from subprocess import CompletedProcess
        with patch("response.prevention.__main__.subprocess.run", return_value=CompletedProcess(
                args=[], returncode=1, stdout="", stderr="UnauthorizedAccess")) as run:
            result = powershell_capabilities()
        self.assertEqual(result["reason_code"], "POWERSHELL_SCRIPT_EXECUTION_DENIED")
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("-ExecutionPolicy", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
