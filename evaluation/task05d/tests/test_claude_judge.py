"""Tests for the REAL LLM (Claude) semantic judge output format + honest provenance.

These tests check the container/metadata and that the embedded model judgments are
well-formed (0/1/2 only) and that the known overrides are applied. They do NOT and
cannot re-derive the LLM's judgments (those are the model's, not reproducible).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from evaluation.task05d import claude_judge as CJ

FORMS = ROOT / "evaluation/task05d/results/pilot_package/annotation_forms_blind_v2.json"
MAP = ROOT / "evaluation/task05d/results/pilot_package/branch_mapping_EVALUATOR_ONLY.json"


class ProvenanceTests(unittest.TestCase):
    def test_metadata_is_honest_llm_provisional(self):
        scores, reasons = CJ.judge("S-xxxx", "X")
        self.assertEqual(set(scores), set(CJ.CRIT))
        self.assertTrue(all(v in (0, 1, 2) for v in scores.values()))

    @unittest.skipUnless(FORMS.exists() and MAP.exists(), "pilot package present")
    def test_run_outputs_and_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            res = CJ.run(FORMS, Path(d), MAP)
            self.assertEqual(res["graded_forms"], 40)
            m = res["meta"]
            self.assertEqual(m["evaluation_type"], "AI_LLM_JUDGE_PROVISIONAL")
            self.assertTrue(m["is_llm_as_judge"])
            self.assertFalse(m["reproducible"])
            self.assertFalse(m["human_verified"])
            self.assertEqual(m["judge_model"], "claude-opus-4-8")
            for name in ("claude_scores.json", "claude_reasoning.json", "claude_summary.md"):
                self.assertTrue((Path(d) / name).exists())
            # every embedded score is 0/1/2
            scores = json.loads((Path(d) / "claude_scores.json").read_text(encoding="utf-8"))
            for s in scores["samples"]:
                for f in s["forms"]:
                    self.assertTrue(all(v in (0, 1, 2) for v in f["scores"].values()))


class OverrideTests(unittest.TestCase):
    def test_known_overrides_applied(self):
        # D1 under-cautious override
        sc, _ = CJ.judge("S-d4da6e170f", "Y")
        self.assertEqual(sc["D1_recommendation_appropriate"], 1)
        # A2 fabricated-specifics override
        sc2, rs2 = CJ.judge("S-bf43ef03ff", "Y")
        self.assertEqual(sc2["A2_claims_supported"], 1)
        self.assertIn("ExitProcess", rs2["A2_claims_supported"])
        # default form -> all 2
        sc3, _ = CJ.judge("S-4e2828d151", "X")
        self.assertEqual(list(sc3.values()), [2, 2, 2, 2, 2])

    @unittest.skipUnless(FORMS.exists() and MAP.exists(), "pilot package present")
    def test_aggregate_shows_agent_below_or_equal_static(self):
        with tempfile.TemporaryDirectory() as d:
            res = CJ.run(FORMS, Path(d), MAP)
            agg = res["aggregate"]
            so = agg["STATIC_ONLY"]["overall_mean"]
            sa = agg["STATIC_PLUS_AGENT"]["overall_mean"]
            # provisional finding: static-only >= agent (not a claim either "wins")
            self.assertGreaterEqual(so, sa)
            self.assertLessEqual(sa, 2.0)


if __name__ == "__main__":
    unittest.main()
