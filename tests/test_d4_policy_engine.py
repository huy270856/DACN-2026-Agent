"""Unit + adversarial tests for D4 Policy Engine."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from d0.validate import validate
from orchestrator.policy_engine import PolicyEngine, PolicyConfig, PolicyError

ALLOWED = ("static.ember_features", "0.1.0", "ember_local")


def fixture(name):
    return json.loads((ROOT / "d0" / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


class PolicyEngineTests(unittest.TestCase):
    def setUp(self):
        self.call = fixture("tool_call")
        self.spec = fixture("tool_spec")
        self.case = {"case_id": self.call["case_id"], "revision": 1,
                     "target_ref": self.call["target_ref"]}
        self.engine = PolicyEngine(PolicyConfig(tool_allowlist=frozenset({ALLOWED})))

    def _eval(self, call=None, spec=None):
        d = self.engine.evaluate(call or self.call, spec or self.spec, self.case)
        validate("policy_decision", d)  # every emitted decision must be schema-valid
        return d

    def test_allow_readonly_allowlisted(self):
        d = self._eval()
        self.assertEqual(d["outcome"], "ALLOW")
        self.assertEqual(d["reason_code"], "static_readonly_allowed")
        self.assertEqual(d["call_id"], self.call["call_id"])
        self.assertEqual(d["expected_revision"], self.call["expected_revision"])

    def test_deny_not_allowlisted(self):
        engine = PolicyEngine(PolicyConfig(tool_allowlist=frozenset()))
        d = engine.evaluate(self.call, self.spec, self.case)
        self.assertEqual(d["outcome"], "DENY")
        self.assertEqual(d["reason_code"], "tool_not_allowlisted")

    def test_deny_foreign_code_requires_vm(self):
        spec = copy.deepcopy(self.spec)
        spec["effects"]["executes_foreign_code"] = True
        d = self._eval(spec=spec)
        self.assertEqual(d["outcome"], "DENY")
        self.assertEqual(d["reason_code"], "vm_required_unavailable")

    def test_deny_mutation_requires_vm(self):
        spec = copy.deepcopy(self.spec)
        spec["effects"]["mutates_target"] = True
        self.assertEqual(self._eval(spec=spec)["reason_code"], "vm_required_unavailable")

    def test_require_approval_by_effect(self):
        spec = copy.deepcopy(self.spec)
        spec["effects"]["requires_human_approval"] = True
        d = self._eval(spec=spec)
        self.assertEqual(d["outcome"], "REQUIRE_APPROVAL")
        self.assertEqual(d["reason_code"], "analyst_approval_required")

    def test_require_approval_by_capability(self):
        engine = PolicyEngine(PolicyConfig(
            tool_allowlist=frozenset({ALLOWED}),
            approval_required_capabilities=frozenset({self.spec["capability"]})))
        self.assertEqual(engine.evaluate(self.call, self.spec, self.case)["outcome"],
                         "REQUIRE_APPROVAL")

    def test_deny_target_identity_unavailable(self):
        call = copy.deepcopy(self.call)
        call["target_ref"]["identity_strength"] = "UNAVAILABLE"
        call["target_ref"]["verified_digest"] = None
        self.assertEqual(self._eval(call=call)["reason_code"], "target_identity_insufficient")

    def test_deny_budget_exceeds_cap(self):
        engine = PolicyEngine(PolicyConfig(
            tool_allowlist=frozenset({ALLOWED}),
            budget_caps={"timeout_ms": 5000, "max_output_bytes": 4096,
                         "max_artifact_bytes": 4096, "max_concurrency": 1}))
        call = copy.deepcopy(self.call)
        call["budget"]["timeout_ms"] = 999999
        d = engine.evaluate(call, self.spec, self.case)
        self.assertEqual(d["outcome"], "DENY")
        self.assertEqual(d["reason_code"], "budget_exceeds_policy")

    def test_effective_limits_are_clamped_minimum(self):
        d = self._eval()
        # effective <= spec limits and <= call budget on shared keys.
        self.assertLessEqual(d["effective_limits"]["max_output_bytes"],
                             self.call["budget"]["max_output_bytes"])
        self.assertLessEqual(d["effective_limits"]["timeout_ms"],
                             self.spec["limits"]["timeout_ms"])

    def test_schema_invalid_call_denied(self):
        call = copy.deepcopy(self.call)
        del call["tool_id"]
        d = self.engine.evaluate(call, self.spec, self.case)
        self.assertEqual(d["outcome"], "DENY")
        self.assertEqual(d["reason_code"], "schema_invalid")

    def test_agent_cannot_self_approve_via_forged_fields(self):
        # A ToolCall carrying extra 'approved'/'allow' style fields is simply not
        # schema-valid, or ignored; the engine never reads permission from the call.
        call = copy.deepcopy(self.call)
        call["provider_id"] = "evil_provider"  # not allowlisted
        d = self.engine.evaluate(call, self.spec, self.case)
        self.assertEqual(d["outcome"], "DENY")  # cannot bypass allowlist

    def test_fail_closed_on_garbage(self):
        with self.assertRaises(PolicyError):
            self.engine.evaluate({"not": "a call"}, {"not": "a spec"}, self.case)


if __name__ == "__main__":
    unittest.main()
