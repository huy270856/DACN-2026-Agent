"""D1 Orchestrator Core: lifecycle, idempotency, fail-closed, concurrency."""
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
from orchestrator.policy_engine import PolicyEngine, PolicyConfig
from orchestrator.core import IdempotencyConflict


@unittest.skipUnless(os.name == "nt", "D1 drives the Windows D5/D6 executor")
class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        from orchestrator_support import build_stack
        self.tmp = Path(tempfile.mkdtemp(prefix="dacn-d1-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.s = build_stack(self.tmp)
        self.orch = self.s["orch"]
        self.call = self.s["call"]
        self.case_path = self.s["case_path"]

    def test_full_allow_executes_and_commits(self):
        rec = self.orch.run_tool_call(self.call, self.case_path)
        self.assertEqual(rec.phase, "COMMITTED")
        self.assertEqual(rec.outcome, "SUCCESS")
        self.assertIsNotNone(rec.run_id)
        state = cm.read_json(self.case_path)
        self.assertTrue(any(e.get("facet") == "static.ember_features"
                            for e in state["evidence"]))

    def test_tool_unknown_rejected(self):
        call = copy.deepcopy(self.call)
        call["tool_id"] = "does.not.exist"
        rec = self.orch.run_tool_call(call, self.case_path)
        self.assertEqual(rec.outcome, "REJECTED")
        self.assertEqual(rec.reason_code, "TOOL_UNKNOWN")

    def test_policy_deny_notes_case_and_does_not_execute(self):
        # A fresh orchestrator with an empty allowlist denies.
        from orchestrator_support import build_stack
        s2 = build_stack(Path(tempfile.mkdtemp(prefix="dacn-d1b-")))
        self.addCleanup(lambda: shutil.rmtree(s2["case_path"].parent, ignore_errors=True))
        orch = s2["orch"]
        orch._policy = PolicyEngine(PolicyConfig(tool_allowlist=frozenset()))
        rec = orch.run_tool_call(s2["call"], s2["case_path"])
        self.assertEqual(rec.outcome, "DENY")
        self.assertEqual(rec.reason_code, "tool_not_allowlisted")
        state = cm.read_json(s2["case_path"])
        self.assertTrue(any(a["action"] == "NOTE" and "DENIED" in (a.get("reason") or "")
                            for a in state["action_history"]))
        # No tool run was recorded for the denied tool.
        self.assertFalse(any(r.get("tool") == "static_ember_features"
                             for r in state["tool_runs"]))

    def test_stale_revision_rejected(self):
        call = copy.deepcopy(self.call)
        call["expected_revision"] = 999
        rec = self.orch.run_tool_call(call, self.case_path)
        self.assertEqual(rec.outcome, "REJECTED")
        self.assertEqual(rec.reason_code, "CASE_REVISION_STALE")

    def test_require_approval_does_not_execute(self):
        self.orch._policy = PolicyEngine(PolicyConfig(
            tool_allowlist=frozenset({("static.ember_features", "0.1.0", "ember_mock")}),
            approval_required_capabilities=frozenset({self.s["spec"]["capability"]}),
            budget_caps={"timeout_ms": 30000, "max_output_bytes": 262144,
                         "max_artifact_bytes": 1048576, "max_concurrency": 1}))
        rec = self.orch.run_tool_call(self.call, self.case_path)
        self.assertEqual(rec.outcome, "REQUIRE_APPROVAL")
        self.assertEqual(rec.phase, "WAITING_APPROVAL")
        self.assertFalse(any(r.get("tool") == "static_ember_features"
                             for r in cm.read_json(self.case_path)["tool_runs"]))

    def test_disabled_provider_rejected(self):
        self.s["registry"].set_provider_availability("ember_mock", False)
        rec = self.orch.run_tool_call(self.call, self.case_path)
        self.assertEqual(rec.outcome, "REJECTED")
        self.assertEqual(rec.reason_code, "PROVIDER_UNAVAILABLE")

    def test_idempotent_replay_returns_same_record(self):
        first = self.orch.run_tool_call(self.call, self.case_path)
        rev_after = cm.read_json(self.case_path)["revision"]
        second = self.orch.run_tool_call(self.call, self.case_path)
        self.assertEqual(second.run_id, first.run_id)
        self.assertEqual(second.revision, first.revision)
        # The idempotent replay did NOT execute or commit again.
        self.assertEqual(cm.read_json(self.case_path)["revision"], rev_after)

    def test_idempotency_conflict_on_changed_payload(self):
        self.orch.run_tool_call(self.call, self.case_path)
        mutated = copy.deepcopy(self.call)
        mutated["reason"] = "A different reason under the same call_id"
        with self.assertRaises(IdempotencyConflict):
            self.orch.run_tool_call(mutated, self.case_path)


if __name__ == "__main__":
    unittest.main()
