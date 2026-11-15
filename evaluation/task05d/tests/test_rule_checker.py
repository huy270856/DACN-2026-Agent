"""Tests for the RULE-BASED heuristic checker (TASK 05D-J); NOT an LLM, NOT human grading.

Verifies: scores are only 0/1/2/null, blind (no mapping/GT needed to score), symmetric
across X/Y (no branch favouritism), the rubric-fidelity rules (unverifiable ref != 0,
limitations field credited, omission != mischaracterisation), flagging, metadata, and
that aggregation uses the mapping only afterwards.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from evaluation.task05d import rule_checker as J

CRIT = J.CRIT


def _form(label="X", expl="", cited=None, sheet_ids=None, lims=None, reco="MONITOR",
          pred_label="benign", score=0.01, thr=0.83):
    sheet = [{"evidence_id": e, "facet": "static.x", "value": {}} for e in (sheet_ids or [])]
    return {"report_label": label, "explanation": expl,
            "cited_evidence_refs": cited or [], "evidence_sheet": sheet,
            "limitations": lims or [], "recommendation": reco,
            "static_prediction": {"predicted_label": pred_label, "raw_score": score,
                                  "threshold": thr, "score_is_calibrated_probability": False}}


class ScoreRangeTests(unittest.TestCase):
    def test_scores_only_0_1_2_or_null(self):
        f = _form(expl="imports and sections consistent; raw score uncalibrated",
                  cited=["EV-a"], sheet_ids=["EV-a"], lims=["static only", "uncalibrated"])
        j = J.judge_form(f)
        for c in CRIT:
            self.assertIn(j["scores"][c], (0, 1, 2, None))

    def test_empty_explanation_is_null_not_zero(self):
        j = J.judge_form(_form(expl="", lims=[]))
        self.assertIsNone(j["scores"]["A2_claims_supported"])
        self.assertIn("A2_claims_supported", j["insufficient_basis"])


class BlindAndSymmetryTests(unittest.TestCase):
    def test_scoring_is_label_independent(self):
        content = dict(expl="imports/sections grounded; raw score uncalibrated",
                       cited=["EV-a"], sheet_ids=["EV-a"], lims=["static only", "no dynamic"])
        jx = J.judge_form(_form(label="X", **content))
        jy = J.judge_form(_form(label="Y", **content))
        self.assertEqual(jx["scores"], jy["scores"])  # no favouritism by label

    def test_judge_needs_no_mapping(self):
        # judge_form must not require any branch mapping / ground truth
        j = J.judge_form(_form(expl="sections grounded", cited=["EV-a"], sheet_ids=["EV-a"]))
        self.assertIsInstance(j["scores"]["A2_claims_supported"], int)


class RubricFidelityTests(unittest.TestCase):
    def test_A2_unverifiable_ref_is_1_not_0(self):
        # cites a ref not in the provided sheet (e.g. omitted prediction obs) -> 1, not 0
        j = J.judge_form(_form(expl="imports and sections grounded",
                               cited=["EV-a", "EV-missing"], sheet_ids=["EV-a"]))
        self.assertEqual(j["scores"]["A2_claims_supported"], 1)

    def test_A2_forbidden_claim_is_0(self):
        j = J.judge_form(_form(expl="when executed it connects to the c2 server and sends data",
                               cited=["EV-a"], sheet_ids=["EV-a"]))
        self.assertEqual(j["scores"]["A2_claims_supported"], 0)

    def test_A2_all_valid_grounded_is_2(self):
        j = J.judge_form(_form(expl="sections and imports grounded",
                               cited=["EV-a"], sheet_ids=["EV-a"]))
        self.assertEqual(j["scores"]["A2_claims_supported"], 2)

    def test_B1_uncalibrated_is_2_omission_is_1_miscalib_is_0(self):
        self.assertEqual(J.judge_form(_form(expl="raw score is uncalibrated"))["scores"]["B1_score_vs_truth_distinction"], 2)
        self.assertEqual(J.judge_form(_form(expl="evidence consistent with the prediction"))["scores"]["B1_score_vs_truth_distinction"], 1)
        self.assertEqual(J.judge_form(_form(expl="this is malware with high probability of infection"))["scores"]["B1_score_vs_truth_distinction"], 0)

    def test_C1_credits_limitations_field(self):
        j = J.judge_form(_form(expl="factual observations only",
                               lims=["static only", "uncalibrated", "replay"]))
        self.assertEqual(j["scores"]["C1_uncertainty"], 2)

    def test_D1_recommendation_appropriateness(self):
        self.assertEqual(J.judge_form(_form(pred_label="benign", reco="MONITOR"))["scores"]["D1_recommendation_appropriate"], 2)
        self.assertEqual(J.judge_form(_form(pred_label="malicious", score=0.99, reco="MONITOR"))["scores"]["D1_recommendation_appropriate"], 1)
        self.assertEqual(J.judge_form(_form(pred_label="benign", reco="CONSIDER_QUARANTINE"))["scores"]["D1_recommendation_appropriate"], 1)
        self.assertEqual(J.judge_form(_form(pred_label="malicious", score=0.99, reco="CONSIDER_QUARANTINE"))["scores"]["D1_recommendation_appropriate"], 2)


class EndToEndTests(unittest.TestCase):
    def _pkg(self, d):
        forms = {"rubric_version": "task05c-rubric-v1", "scoring_guidance": {},
                 "forms": [{"sample_id": "S-1",
                            "forms": [_form("X", expl="raw score uncalibrated; sections grounded",
                                            cited=["EV-a"], sheet_ids=["EV-a"], lims=["static only", "x"]),
                                      _form("Y", expl="evidence consistent with prediction",
                                            cited=["EV-a", "EV-miss"], sheet_ids=["EV-a"], lims=["x"])]}]}
        fp = Path(d) / "forms.json"; fp.write_text(json.dumps(forms), encoding="utf-8")
        mp = Path(d) / "map.json"
        mp.write_text(json.dumps([{"sample_id": "S-1", "X_is": "STATIC_ONLY", "Y_is": "STATIC_PLUS_AGENT"}]),
                      encoding="utf-8")
        return fp, mp

    def test_run_metadata_and_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            fp, mp = self._pkg(d)
            out = Path(d) / "aij"
            res = J.run(fp, out, mp)
            self.assertEqual(res["graded_forms"], 2)
            for name in ("pilot_ai_scores.json", "pilot_ai_reasoning.json",
                         "pilot_ai_summary.md", "human_review_queue.json"):
                self.assertTrue((out / name).exists())
            scores = json.loads((out / "pilot_ai_scores.json").read_text(encoding="utf-8"))
            self.assertEqual(scores["evaluation_type"], "RULE_BASED_HEURISTIC_PROVISIONAL")
            self.assertFalse(scores["human_verified"])
            for k in ("judge_model", "judge_version", "rubric_version", "timestamp",
                      "source_manifest_hash"):
                self.assertIn(k, scores)
            # aggregation used the mapping (evaluator step)
            self.assertIn("STATIC_ONLY", res["aggregate"])
            self.assertIn("STATIC_PLUS_AGENT", res["aggregate"])

    def test_not_called_human_grading(self):
        with tempfile.TemporaryDirectory() as d:
            fp, mp = self._pkg(d)
            res = J.run(fp, Path(d) / "aij", mp)
            self.assertFalse(res["meta"]["human_verified"])
            self.assertEqual(res["meta"]["evaluation_type"], "RULE_BASED_HEURISTIC_PROVISIONAL")


if __name__ == "__main__":
    unittest.main()
