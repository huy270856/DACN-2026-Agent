"""Tests for the deterministic D1 WorkflowEngine."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from d0.validate import validate
from orchestrator.workflow import WorkflowEngine

SNAP = {"case_id": "CASE-" + "a" * 32, "revision": 1}


class WorkflowEngineTests(unittest.TestCase):
    def setUp(self):
        self.wf = WorkflowEngine()

    def _decide(self, **kw):
        d = self.wf.decide(SNAP, **kw)
        validate("workflow_decision", d)
        return d

    def test_unknown_goes_static_first(self):
        d = self._decide(phase="REPUTATION", reputation="UNKNOWN")
        self.assertEqual(d["next_step"], "STATIC_ANALYSIS")

    def test_unavailable_is_not_benign(self):
        d = self._decide(phase="REPUTATION", reputation="UNAVAILABLE")
        self.assertEqual(d["next_step"], "STATIC_ANALYSIS")

    def test_known_benign_fresh_to_assessment(self):
        d = self._decide(phase="REPUTATION", reputation="KNOWN_BENIGN",
                         reputation_fresh_and_consistent=True)
        self.assertEqual(d["next_step"], "FINAL_ASSESSMENT")

    def test_known_benign_stale_still_static(self):
        d = self._decide(phase="REPUTATION", reputation="KNOWN_BENIGN",
                         reputation_fresh_and_consistent=False)
        self.assertEqual(d["next_step"], "STATIC_ANALYSIS")

    def test_static_sufficient_to_assessment(self):
        d = self._decide(phase="STATIC", reputation="UNKNOWN", static_sufficient=True)
        self.assertEqual(d["next_step"], "FINAL_ASSESSMENT")

    def test_dynamic_needed_vm_ready(self):
        d = self._decide(phase="STATIC", reputation="UNKNOWN",
                         dynamic_needed=True, vm_ready=True)
        self.assertEqual(d["next_step"], "DYNAMIC_ANALYSIS")

    def test_dynamic_needed_vm_unavailable_goes_human(self):
        d = self._decide(phase="STATIC", reputation="UNKNOWN",
                         dynamic_needed=True, vm_ready=False)
        self.assertEqual(d["next_step"], "HUMAN_REVIEW")

    def test_conflict_reputation_static_first(self):
        d = self._decide(phase="INTAKE", reputation="CONFLICT")
        self.assertEqual(d["next_step"], "STATIC_ANALYSIS")

    def test_unknown_reputation_value_rejected(self):
        with self.assertRaises(ValueError):
            self.wf.decide(SNAP, phase="STATIC", reputation="DEFINITELY_SAFE")


if __name__ == "__main__":
    unittest.main()
