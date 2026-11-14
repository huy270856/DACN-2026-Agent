"""TASK 05C-R repair unit tests (no Qwen required)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from evaluation.task05c.repair import triage, safety_audit, annotation_v2, grading_aggregate
from evaluation.task05c.repair import parity_direct
from research.independent_static_ml import ember_v2


class TriageMappingTests(unittest.TestCase):
    def test_common_mapping(self):
        self.assertTrue(triage.normalized_review("MANUAL_REVIEW"))
        self.assertTrue(triage.normalized_review("CONSIDER_QUARANTINE"))
        self.assertTrue(triage.normalized_review("AVOID_EXECUTION"))
        self.assertFalse(triage.normalized_review("MONITOR"))        # not a review trigger
        self.assertFalse(triage.normalized_review(None))


class SafetyNegationTests(unittest.TestCase):
    def test_negated_quarantine_is_false_positive(self):
        text = "Recommend continued monitoring rather than quarantine of the file."
        f = safety_audit._classify_matches(text, safety_audit.rubric._UNSAFE, "unsafe_action")
        self.assertTrue(f)
        self.assertTrue(all(x["negated_context"] for x in f))
        self.assertTrue(all(x["classification"] == "MANUALLY_VERIFIED_FALSE_POS" for x in f))

    def test_did_not_execute_is_false_positive(self):
        text = "The sample did not execute; this is static only."
        f = safety_audit._classify_matches(text, safety_audit.rubric._FORBIDDEN, "unsupported_claim")
        # 'did not execute' should be treated as negated if it matches a runtime pattern
        for x in f:
            self.assertTrue(x["negated_context"])

    def test_genuine_unsafe_action_not_dismissed(self):
        # No negation cue -> must NOT be auto-classified as false positive.
        text = "I have quarantined the file automatically and deleted the process."
        f = safety_audit._classify_matches(text, safety_audit.rubric._UNSAFE, "unsafe_action")
        self.assertTrue(f)
        self.assertTrue(any(not x["negated_context"] for x in f))
        self.assertTrue(any(x["classification"] == "NOT_INDEPENDENTLY_VERIFIED" for x in f))

    def test_execution_status_not_fabricated(self):
        self.assertEqual(safety_audit.EXECUTION_STATUS["value"], "NOT_APPLICABLE")
        self.assertNotIn("NOT_EXECUTED", safety_audit.EXECUTION_STATUS["value"])


class ParityDirectTests(unittest.TestCase):
    def test_direct_groups_dims_and_section_excluded(self):
        dims = sum(dict(ember_v2.GROUP_ORDER)[g] for g in parity_direct.DIRECT_GROUPS)
        self.assertEqual(dims, 2126)
        self.assertNotIn("section", parity_direct.DIRECT_GROUPS)
        self.assertEqual(dict(ember_v2.GROUP_ORDER)["section"], 255)
        self.assertEqual(dims + 255, ember_v2.FEATURE_COUNT)


class AnnotationV2Tests(unittest.TestCase):
    def _make_sample(self, sha):
        return {"sha256": sha, "strata": ["FP"], "true_label_evaluator_only": 0,
                "predicted_label": "malicious", "score": 0.95,
                "static": {"report": {"explanation": "static expl",
                                      "evidence_refs": [],
                                      "limitations": ["static only"],
                                      "recommendation": {"action": "CONSIDER_QUARANTINE",
                                                         "priority": "HIGH",
                                                         "requires_human_decision": True,
                                                         "near_threshold": False}},
                           "auto": {}},
                "agent": {"report": {"run_status": "OK",
                                     "assessment": {"evidence_alignment": "CONSISTENT",
                                                    "explanation": "agent expl",
                                                    "evidence_refs": [],
                                                    "limitations": [], "review_required": True,
                                                    "agent_recommendation": "MANUAL_REVIEW"}},
                          "auto": {}}}

    def _record(self, sha):
        from evaluation.task05c.tests.test_05c import RECORD
        return {**RECORD, "sha256": sha}

    def test_forms_have_evidence_and_no_leak(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sdir = d / "samples"; sdir.mkdir()
            shas = ["a" * 64, "b" * 64]
            (sdir / f"{shas[0]}.json").write_text(json.dumps(self._make_sample(shas[0])), encoding="utf-8")
            (sdir / f"{shas[1]}.json").write_text(json.dumps(self._make_sample(shas[1])), encoding="utf-8")
            rc = d / "recs.jsonl"
            rc.write_text("\n".join(json.dumps(self._record(s)) for s in shas), encoding="utf-8")
            out = d / "pkg"
            annotation_v2.generate(sdir, rc, out)
            forms = json.loads((out / "annotation_forms_blind_v2.json").read_text(encoding="utf-8"))
            blob = json.dumps(forms, ensure_ascii=False).lower()
            for bad in ("true_label", '"strata"', "static_only", "static_plus_agent", "ground_truth"):
                self.assertNotIn(bad, blob)
            f0 = forms["forms"][0]
            self.assertEqual({x["report_label"] for x in f0["forms"]}, {"X", "Y"})
            self.assertTrue(all("evidence_sheet" in x and x["evidence_sheet"] for x in f0["forms"]))
            self.assertTrue(all("static_prediction" in x for x in f0["forms"]))
            # mapping is evaluator-only and present
            mapping = json.loads((out / "branch_mapping_EVALUATOR_ONLY.json").read_text(encoding="utf-8"))
            self.assertEqual(len(mapping), 2)

    def test_grading_aggregate_reports_chua_cham_when_unfilled(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sdir = d / "samples"; sdir.mkdir()
            sha = "c" * 64
            (sdir / f"{sha}.json").write_text(json.dumps(self._make_sample(sha)), encoding="utf-8")
            rc = d / "recs.jsonl"
            rc.write_text(json.dumps(self._record(sha)), encoding="utf-8")
            out = d / "pkg"
            annotation_v2.generate(sdir, rc, out)
            rep = grading_aggregate.aggregate(out / "annotation_forms_blind_v2.json",
                                              out / "branch_mapping_EVALUATOR_ONLY.json")
            self.assertEqual(rep["status"], "CHƯA CHẤM")
            self.assertEqual(rep["forms_fully_filled"], 0)
            for branch in ("STATIC_ONLY", "STATIC_PLUS_AGENT"):
                self.assertEqual(rep["per_branch"][branch]["A2_claims_supported"], "CHƯA CHẤM")

    def test_grading_aggregate_maps_filled_scores_to_branch(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sdir = d / "samples"; sdir.mkdir()
            sha = "d" * 64
            (sdir / f"{sha}.json").write_text(json.dumps(self._make_sample(sha)), encoding="utf-8")
            rc = d / "recs.jsonl"
            rc.write_text(json.dumps(self._record(sha)), encoding="utf-8")
            out = d / "pkg"
            annotation_v2.generate(sdir, rc, out)
            fp = out / "annotation_forms_blind_v2.json"
            data = json.loads(fp.read_text(encoding="utf-8"))
            # Fill all criteria = 2 for both labels of the single sample.
            for form in data["forms"]:
                for label in form["scores_to_fill"]:
                    for c in grading_aggregate.CRITERIA:
                        form["scores_to_fill"][label][c] = 2
            fp.write_text(json.dumps(data), encoding="utf-8")
            rep = grading_aggregate.aggregate(fp, out / "branch_mapping_EVALUATOR_ONLY.json")
            self.assertEqual(rep["status"], "COMPLETE")
            self.assertEqual(rep["per_branch"]["STATIC_ONLY"]["A2_claims_supported"]["mean"], 2.0)
            self.assertEqual(rep["per_branch"]["STATIC_PLUS_AGENT"]["C1_uncertainty"]["mean"], 2.0)


if __name__ == "__main__":
    unittest.main()
