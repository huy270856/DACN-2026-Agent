"""TASK 05D tests: sample discovery, grading import/validation, inter-rater, runner."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from evaluation.task05d import sample_discovery as disc
from evaluation.task05d import grading_import as gi
from evaluation.task05d import validation_runner as vr

BENIGN_PE = r"C:\Windows\System32\notepad.exe"
CRIT = ["A2_claims_supported", "B1_score_vs_truth_distinction",
        "B2_no_feature_importance_from_score", "C1_uncertainty", "D1_recommendation_appropriate"]


def _annotation(reviewer, items, rubric="task05c-rubric-v1"):
    return {"schema_version": "task05d-annotations-v1", "reviewer_id": reviewer,
            "rubric_version": rubric, "exported_at": "2026-11-15T00:00:00Z",
            "source_forms": "x.json", "annotations": items}


def _full_scores(val=2):
    return {c: val for c in CRIT}


class DiscoveryTests(unittest.TestCase):
    def test_non_pe_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "notpe.txt"
            p.write_bytes(b"this is not a PE file" * 10)
            self.assertIsNone(disc.pe_metadata(p))

    def test_sha256_consistency(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.bin"
            p.write_bytes(b"abc123" * 1000)
            self.assertEqual(disc.sha256_file(p), hashlib.sha256(p.read_bytes()).hexdigest())

    @unittest.skipUnless(os.name == "nt" and os.path.exists(BENIGN_PE), "needs Windows + PE")
    def test_real_pe_metadata_and_signature(self):
        meta = disc.pe_metadata(Path(BENIGN_PE))
        self.assertIsNotNone(meta)
        self.assertIn(meta["kind"], ("EXE", "DLL"))
        self.assertIn(meta["pe_format"], ("PE32", "PE32+"))
        sig = disc.signature_status(Path(BENIGN_PE))
        self.assertIn(sig["signature"], ("VALID", "INVALID", "UNAVAILABLE", "NOT_CHECKED"))

    @unittest.skipUnless(os.name == "nt" and os.path.exists(BENIGN_PE), "needs Windows + PE")
    def test_discover_builds_manifest_with_provenance(self):
        m = disc.discover([Path(BENIGN_PE)], target_min=1, check_signature=False)
        self.assertEqual(m["n_selected"], 1)
        s = m["samples"][0]
        for k in ("sha256", "pe_format", "signature_status", "provenance", "label",
                  "label_confidence", "track"):
            self.assertIn(k, s)
        self.assertEqual(s["track"], "RAW_PE_E2E")

    def test_public_manifest_strips_local_path(self):
        m = {"schema_version": "x", "samples": [{"local_path": "C:/secret/x.exe", "sha256": "a"}],
             "skipped": []}
        with tempfile.TemporaryDirectory() as d:
            full = Path(d) / "full.json"; pub = Path(d) / "pub.json"
            disc.write_manifest(m, full, pub)
            pubdata = json.loads(pub.read_text(encoding="utf-8"))
            self.assertNotIn("local_path", pubdata["samples"][0])
            self.assertIn("local_path", json.loads(full.read_text(encoding="utf-8"))["samples"][0])


class GradingImportTests(unittest.TestCase):
    def _write(self, d, obj, name):
        p = Path(d) / name
        p.write_text(json.dumps(obj), encoding="utf-8")
        return p

    def test_invalid_scores_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            bad = _annotation("r1", [{"sample_id": "S1", "blind_label": "X",
                                      "scores": {**_full_scores(), "A2_claims_supported": 1.5}}])
            p = self._write(d, bad, "a.json")
            reviews, errors = gi.load_reviews([p])
            self.assertTrue(any("invalid score" in e for e in errors))

    def test_bool_and_out_of_range_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            bad = _annotation("r1", [{"sample_id": "S1", "blind_label": "X",
                                      "scores": {**_full_scores(), "B1_score_vs_truth_distinction": True,
                                                 "C1_uncertainty": 3}}])
            p = self._write(d, bad, "a.json")
            _, errors = gi.load_reviews([p])
            self.assertEqual(sum("invalid score" in e for e in errors), 2)

    def test_duplicate_reviewer_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._write(d, _annotation("r1", []), "a.json")
            b = self._write(d, _annotation("r1", []), "b.json")
            _, errors = gi.load_reviews([a, b])
            self.assertTrue(any("duplicate reviewer_id" in e for e in errors))

    def test_duplicate_sample_annotation_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = _annotation("r1", [{"sample_id": "S1", "blind_label": "X", "scores": _full_scores()},
                                   {"sample_id": "S1", "blind_label": "X", "scores": _full_scores()}])
            p = self._write(d, a, "a.json")
            _, errors = gi.load_reviews([p])
            self.assertTrue(any("duplicate annotation" in e for e in errors))

    def test_bad_blind_label_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = _annotation("r1", [{"sample_id": "S1", "blind_label": "Z", "scores": _full_scores()}])
            p = self._write(d, a, "a.json")
            _, errors = gi.load_reviews([p])
            self.assertTrue(any("bad blind_label" in e for e in errors))

    def test_partial_vs_complete_status(self):
        expected = {("S1", "X"), ("S1", "Y")}
        with tempfile.TemporaryDirectory() as d:
            # reviewer fills only X -> PARTIAL
            a = _annotation("r1", [{"sample_id": "S1", "blind_label": "X", "scores": _full_scores()}])
            p = self._write(d, a, "a.json")
            reviews, errors = gi.load_reviews([p])
            self.assertFalse(errors)
            rep = gi.aggregate(reviews, expected_items=expected)
            self.assertEqual(rep["per_reviewer"]["r1"]["status"], "PARTIAL")
            # fill both -> COMPLETE
            a2 = _annotation("r1", [{"sample_id": "S1", "blind_label": "X", "scores": _full_scores()},
                                    {"sample_id": "S1", "blind_label": "Y", "scores": _full_scores()}])
            reviews2, _ = gi.load_reviews([self._write(d, a2, "a2.json")])
            rep2 = gi.aggregate(reviews2, expected_items=expected)
            self.assertEqual(rep2["per_reviewer"]["r1"]["status"], "COMPLETE")
            self.assertEqual(rep2["overall_status"], "COMPLETE")

    def test_inter_rater_two_reviewers(self):
        items1 = [{"sample_id": "S1", "blind_label": "X", "scores": _full_scores(2)},
                  {"sample_id": "S1", "blind_label": "Y", "scores": _full_scores(1)}]
        items2 = [{"sample_id": "S1", "blind_label": "X", "scores": _full_scores(2)},
                  {"sample_id": "S1", "blind_label": "Y", "scores": _full_scores(0)}]  # disagree on Y
        with tempfile.TemporaryDirectory() as d:
            p1 = self._write(d, _annotation("r1", items1), "r1.json")
            p2 = self._write(d, _annotation("r2", items2), "r2.json")
            reviews, errors = gi.load_reviews([p1, p2])
            self.assertFalse(errors)
            rep = gi.aggregate(reviews)
            self.assertIn("r1|r2", rep["inter_rater_agreement"])
            self.assertGreater(rep["n_disagreements"], 0)
            # disagreement is recorded, not auto-resolved
            self.assertTrue(all("scores" in dz for dz in rep["disagreements_for_adjudication"]))

    def test_no_llm_or_autofill(self):
        # aggregate never invents scores: empty reviewer -> CHƯA CHẤM
        reviews, _ = gi.load_reviews([self._write(tempfile.mkdtemp(), _annotation("r1", []), "a.json")])
        rep = gi.aggregate(reviews)
        self.assertEqual(rep["overall_status"], "CHƯA CHẤM")


class RunnerAggregateTests(unittest.TestCase):
    def _row(self, label, score, align="CONSISTENT", status="AVAILABLE", lat_s=1.0, lat_a=6.0):
        return {"sample_id": "RPE-x", "filename": "x.exe", "pe_format": "PE32+", "kind": "EXE",
                "machine": "AMD64", "size_bytes": 1000, "signature_status": "VALID", "label": "benign",
                "static_only": {"overall_status": "COMPLETED", "report_written": True, "latency_s": lat_s},
                "static_plus_agent": {"overall_status": "COMPLETED", "report_written": True,
                                      "latency_s": lat_a, "planner_kind": "LOCAL_QWEN",
                                      "evidence_alignment": align, "review_required": True,
                                      "agent_completed": True},
                "prediction": {"status": status, "predicted_label": label, "raw_score": score,
                               "threshold": 0.83, "parser_status": "OK", "evidence_id": "EV-1"}}

    def test_aggregate_counts_fp_and_latency_no_prf(self):
        rows = [self._row("benign", 0.01), self._row("benign", 0.2),
                self._row("malicious", 0.9)]  # one FP within set
        agg = vr.aggregate(rows, {"samples": [{"model_id": "m"}]})
        self.assertEqual(agg["benign_set_false_positive_count"], 1)
        self.assertEqual(agg["detector_inference_success"]["k"], 3)
        self.assertAlmostEqual(agg["latency"]["agent_overhead_mean_s"], 5.0)
        # benign-only set: no precision/recall/f1
        blob = json.dumps(agg).lower()
        for k in ("precision", "recall", "f1"):
            self.assertNotIn(f'"{k}"', blob)
        self.assertEqual(len(agg["anomalies_predicted_malicious"]), 1)


@unittest.skipUnless(
    (Path(ROOT) / "evaluation/task05c/results/audit_manifest.json").exists()
    and Path("D:/datasets/ember2018-cache/task05c_audit_records.jsonl").exists(),
    "pilot needs locked 05C data + records cache")
class PilotTests(unittest.TestCase):
    def test_pilot_balanced_no_leak(self):
        from evaluation.task05d import pilot
        with tempfile.TemporaryDirectory() as d:
            res = pilot.build(
                Path(ROOT) / "evaluation/task05c/results/audit_manifest.json",
                Path(ROOT) / "evaluation/task05c/results/samples",
                Path("D:/datasets/ember2018-cache/task05c_audit_records.jsonl"),
                Path(d), n_per=2)
            self.assertEqual(res["n_selected"], 10)
            data = json.loads((Path(d) / "annotation_forms_blind_v2.json").read_text(encoding="utf-8"))
            self.assertIn("rubric_version", data)
            blob = json.dumps(data).lower()
            for bad in ("strata", "true_label", "static_only", "static_plus_agent"):
                self.assertNotIn(bad, blob)


if __name__ == "__main__":
    unittest.main()
