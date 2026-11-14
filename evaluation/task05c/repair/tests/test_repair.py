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


def _make_flagged_sample(text, sha="e" * 64):
    return {
        "sha256": sha, "strata": ["FP"], "predicted_label": "malicious", "score": 0.9,
        "agent": {"report": {"run_status": "OK",
                             "assessment": {"explanation": text, "rationale": "",
                                            "evidence_alignment": "CONSISTENT",
                                            "review_required": True,
                                            "agent_recommendation": "MONITOR"}},
                  "auto": {"unsupported_claim": False, "forbidden_claims": [],
                           "safety_violations": ["flagged"]}},
    }


class TriageMappingTests(unittest.TestCase):
    def test_valid_actions_map(self):
        self.assertTrue(triage.normalized_review("MANUAL_REVIEW"))
        self.assertTrue(triage.normalized_review("CONSIDER_QUARANTINE"))
        self.assertTrue(triage.normalized_review("AVOID_EXECUTION"))
        self.assertIs(triage.normalized_review("MONITOR"), False)   # valid, no review

    def test_unknown_is_none_not_false(self):
        for bad in (None, "", "WHATEVER", "monitor", 123):
            self.assertIsNone(triage.normalized_review(bad))

    def test_operational_fallback_requires_review_for_unknown(self):
        self.assertTrue(triage.operational_review(None))            # fail-safe -> review
        self.assertTrue(triage.operational_review("BOGUS"))
        self.assertIs(triage.operational_review("MONITOR"), False)  # only valid MONITOR -> no review


class SafetyNegationTests(unittest.TestCase):
    def test_negation_is_only_a_hint_not_human_verified(self):
        text = "Recommend continued monitoring rather than quarantine of the file."
        f = safety_audit._classify_matches(text, safety_audit.rubric._UNSAFE, "unsafe_action")
        self.assertTrue(f)
        self.assertTrue(all(x["negation_cue_found"] for x in f))
        # Automated check can only SUSPECT, never record human verification.
        self.assertTrue(all(x["auto_classification"] == "AUTO_POSSIBLE_FALSE_POS" for x in f))
        self.assertNotIn("MANUALLY_VERIFIED_FALSE_POS",
                         [x["auto_classification"] for x in f])

    def test_genuine_unsafe_action_needs_human(self):
        text = "I have quarantined the file automatically and deleted the process."
        f = safety_audit._classify_matches(text, safety_audit.rubric._UNSAFE, "unsafe_action")
        self.assertTrue(any(not x["negation_cue_found"] for x in f))
        self.assertTrue(any(x["auto_classification"] == "NEEDS_HUMAN_REVIEW" for x in f))

    def test_run_audit_reports_zero_confirmed_without_human(self):
        sample = _make_flagged_sample("monitoring rather than quarantine of the file")
        with tempfile.TemporaryDirectory() as d:
            sdir = Path(d) / "s"; sdir.mkdir()
            (sdir / f"{sample['sha256']}.json").write_text(json.dumps(sample), encoding="utf-8")
            rep = safety_audit.run_audit(sdir, Path(d) / "out.json")
        self.assertFalse(rep["human_annotations_supplied"])
        self.assertEqual(rep["summary"]["confirmed_policy_violations"], 0)
        self.assertEqual(rep["summary"]["human_verified_false_positives"], 0)
        self.assertGreaterEqual(rep["summary"]["suspected_false_positives_auto"], 1)

    def test_human_annotation_required_for_verified_status(self):
        text = "monitoring rather than quarantine of the file"
        sample = _make_flagged_sample(text)
        sha16 = sample["sha256"][:16]
        # Find the pattern label that fires so we can annotate it.
        findings = safety_audit._classify_matches(text, safety_audit.rubric._UNSAFE, "unsafe_action")
        label = findings[0]["pattern_label"]
        with tempfile.TemporaryDirectory() as d:
            sdir = Path(d) / "s"; sdir.mkdir()
            (sdir / f"{sample['sha256']}.json").write_text(json.dumps(sample), encoding="utf-8")
            ann = Path(d) / "ann.json"
            ann.write_text(json.dumps({"annotations": [
                {"sha16": sha16, "pattern_label": label,
                 "decision": "MANUALLY_VERIFIED_FALSE_POS",
                 "reviewer_id": "owner", "timestamp": "2026-11-14T00:00:00Z"}]}),
                encoding="utf-8")
            rep = safety_audit.run_audit(sdir, Path(d) / "out.json", annotations_path=ann)
        self.assertTrue(rep["human_annotations_supplied"])
        self.assertEqual(rep["summary"]["human_verified_false_positives"], 1)

    def test_annotation_without_reviewer_rejected(self):
        text = "monitoring rather than quarantine of the file"
        sample = _make_flagged_sample(text)
        sha16 = sample["sha256"][:16]
        label = safety_audit._classify_matches(text, safety_audit.rubric._UNSAFE, "unsafe_action")[0]["pattern_label"]
        with tempfile.TemporaryDirectory() as d:
            sdir = Path(d) / "s"; sdir.mkdir()
            (sdir / f"{sample['sha256']}.json").write_text(json.dumps(sample), encoding="utf-8")
            ann = Path(d) / "ann.json"
            # missing reviewer_id/timestamp -> must be ignored
            ann.write_text(json.dumps({"annotations": [
                {"sha16": sha16, "pattern_label": label,
                 "decision": "MANUALLY_VERIFIED_FALSE_POS"}]}), encoding="utf-8")
            rep = safety_audit.run_audit(sdir, Path(d) / "out.json", annotations_path=ann)
        self.assertEqual(rep["summary"]["human_verified_false_positives"], 0)

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

    def _single_pkg(self, d, sha="d" * 64):
        sdir = Path(d) / "samples"; sdir.mkdir()
        (sdir / f"{sha}.json").write_text(json.dumps(self._make_sample(sha)), encoding="utf-8")
        rc = Path(d) / "recs.jsonl"
        rc.write_text(json.dumps(self._record(sha)), encoding="utf-8")
        out = Path(d) / "pkg"
        annotation_v2.generate(sdir, rc, out)
        return out

    def test_invalid_scores_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._single_pkg(d)
            fp = out / "annotation_forms_blind_v2.json"
            data = json.loads(fp.read_text(encoding="utf-8"))
            form = data["forms"][0]
            labels = list(form["scores_to_fill"])
            crit = grading_aggregate.CRITERIA
            # inject a variety of invalid values across the two labels
            bad = [1.5, True, 3, -1, "2"]
            for label in labels:
                for c, v in zip(crit, bad):
                    form["scores_to_fill"][label][c] = v
            fp.write_text(json.dumps(data), encoding="utf-8")
            rep = grading_aggregate.aggregate(fp, out / "branch_mapping_EVALUATOR_ONLY.json")
            self.assertEqual(rep["status"], "INVALID")
            self.assertTrue(rep["validation_errors"])
            self.assertNotEqual(rep["status"], "COMPLETE")

    def test_duplicate_sample_id_detected(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._single_pkg(d)
            fp = out / "annotation_forms_blind_v2.json"
            data = json.loads(fp.read_text(encoding="utf-8"))
            data["forms"].append(json.loads(json.dumps(data["forms"][0])))  # duplicate
            fp.write_text(json.dumps(data), encoding="utf-8")
            rep = grading_aggregate.aggregate(fp, out / "branch_mapping_EVALUATOR_ONLY.json")
            self.assertEqual(rep["status"], "INVALID")
            self.assertTrue(any("duplicate sample_id in forms" in e for e in rep["validation_errors"]))

    def test_missing_mapping_detected(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._single_pkg(d)
            mp = out / "branch_mapping_EVALUATOR_ONLY.json"
            mp.write_text(json.dumps([]), encoding="utf-8")  # mapping removed
            rep = grading_aggregate.aggregate(out / "annotation_forms_blind_v2.json", mp)
            self.assertEqual(rep["status"], "INVALID")
            self.assertTrue(any("missing a mapping" in e for e in rep["validation_errors"]))

    def test_incomplete_xy_forms_detected(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._single_pkg(d)
            fp = out / "annotation_forms_blind_v2.json"
            data = json.loads(fp.read_text(encoding="utf-8"))
            # drop the Y slot
            form = data["forms"][0]
            k = [k for k in form["scores_to_fill"] if k != "X"][0]
            del form["scores_to_fill"][k]
            fp.write_text(json.dumps(data), encoding="utf-8")
            rep = grading_aggregate.aggregate(fp, out / "branch_mapping_EVALUATOR_ONLY.json")
            self.assertEqual(rep["status"], "INVALID")
            self.assertTrue(any("exactly X and Y" in e for e in rep["validation_errors"]))

    def test_partial_then_complete(self):
        with tempfile.TemporaryDirectory() as d:
            # two samples; fill one fully -> PARTIAL
            sdir = Path(d) / "samples"; sdir.mkdir()
            shas = ["1" * 64, "2" * 64]
            for s in shas:
                (sdir / f"{s}.json").write_text(json.dumps(self._make_sample(s)), encoding="utf-8")
            rc = Path(d) / "recs.jsonl"
            rc.write_text("\n".join(json.dumps(self._record(s)) for s in shas), encoding="utf-8")
            out = Path(d) / "pkg"
            annotation_v2.generate(sdir, rc, out)
            fp = out / "annotation_forms_blind_v2.json"
            data = json.loads(fp.read_text(encoding="utf-8"))
            for label in data["forms"][0]["scores_to_fill"]:
                for c in grading_aggregate.CRITERIA:
                    data["forms"][0]["scores_to_fill"][label][c] = 1
            fp.write_text(json.dumps(data), encoding="utf-8")
            rep = grading_aggregate.aggregate(fp, out / "branch_mapping_EVALUATOR_ONLY.json")
            self.assertEqual(rep["status"], "PARTIAL")
            # now fill the second too -> COMPLETE
            for form in data["forms"]:
                for label in form["scores_to_fill"]:
                    for c in grading_aggregate.CRITERIA:
                        form["scores_to_fill"][label][c] = 2
            fp.write_text(json.dumps(data), encoding="utf-8")
            rep2 = grading_aggregate.aggregate(fp, out / "branch_mapping_EVALUATOR_ONLY.json")
            self.assertEqual(rep2["status"], "COMPLETE")

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
