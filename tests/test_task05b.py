"""TASK 05B tests: real detector integration, D7 prediction binding, report.

Layers are kept distinct (as the task requires):
  * pure unit  - schema + D7 normalizer binding + report builder (no Windows, no model);
  * real model integration - detector through D1-D9 on a real benign PE (Windows + artifact);
  * live LLM - the full Qwen E2E, skipped unless explicitly enabled.
No mock analyzer is used on the real-model path.
"""
import copy
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from d0.validate import SCHEMAS, canonical_json_bytes, digest, validate, ContractError
from orchestrator.result_validator import ResultValidationError
from orchestrator.pe_prediction_result import (normalize_pe_prediction_result,
                                               PREDICTION_FACET)
from dacn import investigation as inv

BENIGN_PE = r"C:\Windows\System32\notepad.exe"
MODEL_PRESENT = inv.MODEL_PATH.exists()
GOOD_MODEL_SHA = "a" * 64
GOOD_MODEL_ID = "test-model-1"


def fixture(name):
    return json.loads((ROOT / "d0" / "fixtures" / f"{name}.json").read_text(encoding="utf8"))


def _prediction_payload(target_sha, *, label="malicious", cls=1,
                        model_id=GOOD_MODEL_ID, model_sha=GOOD_MODEL_SHA):
    return {
        "schema_version": "static-prediction-v1", "feature_version": 2,
        "feature_count": 2381,
        "extractor": {"name": "dacn-independent-ember-v2", "version": "0.1.0",
                      "lief_version": "0.15.1"},
        "target_sha256": target_sha, "model_id": model_id, "model_sha256": model_sha,
        "threshold": 0.83, "raw_score": 0.97,
        "score_is_calibrated_probability": False,
        "predicted_label": label, "predicted_class": cls, "parser_status": "OK",
        "limitations": ["Raw LightGBM score; NOT a calibrated probability."],
    }


def _pred_fixtures():
    call, spec, receipt = fixture("tool_call"), fixture("tool_spec"), fixture("execution_receipt")
    call["tool_id"] = spec["tool_id"] = receipt["tool_id"] = "static.pe_malware_predict"
    spec["input_schema_id"] = "pe-predict-input-v1"
    spec["output_schema_id"] = "static-prediction-v1"
    spec["capability"] = "static.pe_prediction"
    call["arguments"] = {"feature_version": 2}
    receipt["arguments_sha256"] = digest(call["arguments"])
    sha = call["target_ref"]["verified_digest"]["value"]
    payload = _prediction_payload(sha)
    receipt["outcome"] = "SUCCESS"
    receipt["resources"]["output_bytes"] = len(canonical_json_bytes(payload))
    call["budget"]["max_output_bytes"] = 32768
    return payload, receipt, call, spec, sha


class SchemaTests(unittest.TestCase):
    def test_schemas_registered_and_additive(self):
        self.assertIn("static-prediction-v1", SCHEMAS)
        self.assertIn("pe-predict-input-v1", SCHEMAS)
        # EMBER feature contract is untouched (additive requirement).
        self.assertEqual(SCHEMAS["ember-output-v1"]["properties"]["feature_count"]["const"], 2381)

    def test_prediction_payload_validates(self):
        validate("static-prediction-v1", _prediction_payload("b" * 64))

    def test_bad_label_rejected(self):
        p = _prediction_payload("b" * 64)
        p["predicted_label"] = "definitely_evil"
        with self.assertRaises(ContractError):
            validate("static-prediction-v1", p)

    def test_calibrated_flag_must_be_false(self):
        p = _prediction_payload("b" * 64)
        p["score_is_calibrated_probability"] = True
        with self.assertRaises(ContractError):
            validate("static-prediction-v1", p)


class D7BindingTests(unittest.TestCase):
    def _normalize(self, payload, receipt, call, spec, **kw):
        kw.setdefault("expected_model_id", GOOD_MODEL_ID)
        kw.setdefault("expected_model_sha256", GOOD_MODEL_SHA)
        return normalize_pe_prediction_result(payload, receipt, call, spec, **kw)

    def test_success_builds_prediction_observation(self):
        payload, receipt, call, spec, _ = _pred_fixtures()
        result = self._normalize(payload, receipt, call, spec)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["observations"][0]["facet"], PREDICTION_FACET)
        self.assertEqual(result["observations"][0]["trust_level"], "UNTRUSTED_CONTENT")
        self.assertEqual(result["observations"][0]["value"]["predicted_label"], "malicious")

    def test_wrong_target_hash_rejected(self):
        payload, receipt, call, spec, _ = _pred_fixtures()
        payload["target_sha256"] = "c" * 64  # not the verified file
        with self.assertRaises(ResultValidationError) as e:
            self._normalize(payload, receipt, call, spec)
        self.assertEqual(e.exception.code, "TARGET_CHANGED")

    def test_wrong_model_digest_rejected(self):
        payload, receipt, call, spec, _ = _pred_fixtures()
        with self.assertRaises(ResultValidationError) as e:
            self._normalize(payload, receipt, call, spec, expected_model_sha256="d" * 64)
        self.assertEqual(e.exception.code, "RESULT_INVALID")

    def test_failed_outcome_cannot_carry_payload(self):
        payload, receipt, call, spec, _ = _pred_fixtures()
        receipt["outcome"] = "FAILED"
        with self.assertRaises(ResultValidationError):
            self._normalize(payload, receipt, call, spec, error={"code": "provider_failed",
                                                                 "message": "x"})


class ReportBuilderTests(unittest.TestCase):
    def _state(self, with_pred=True):
        state = {
            "case_id": "CASE-" + "0" * 32, "revision": 2, "target_type": "FILE",
            "target_ref": {"verified_digest": {"value": "e" * 64}},
            "evidence": [
                {"evidence_id": "EV-sha", "facet": "sha256", "status": "SUCCESS", "value": "e" * 64},
                {"evidence_id": "EV-fmt", "facet": "format", "status": "SUCCESS",
                 "value": {"format": "PE"}},
            ],
        }
        if with_pred:
            state["evidence"].append({
                "evidence_id": "EV-pred", "facet": PREDICTION_FACET, "status": "SUCCESS",
                "value": _prediction_payload("e" * 64, label="malicious", cls=1)})
        return state

    def _manifest(self):
        return {"model_id": GOOD_MODEL_ID, "model_sha256": GOOD_MODEL_SHA,
                "feature_version": 2, "dataset": {"name": "EMBER2018 feature version 2"}}

    def test_report_with_prediction_and_agent(self):
        state = self._state(True)
        pred_ev = inv.read_prediction_evidence(state)
        agent_report = {"verdict": "INSUFFICIENT_EVIDENCE", "rationale": "structure matches",
                        "evidence_cited": ["EV-pred"], "limitations": [],
                        "planner_kind": "LOCAL_QWEN",
                        "agent_assessment": {"alignment": "CONSISTENT", "review_required": True,
                                             "recommendation": "CONSIDER_QUARANTINE",
                                             "explanation": "consistent"}}
        rep = inv.build_investigation_report(state, prediction_ev=pred_ev,
                                             prediction_record=None, agent_report=agent_report,
                                             model_manifest=self._manifest())
        self.assertEqual(rep["overall_status"], "COMPLETED")
        self.assertEqual(rep["static_prediction"]["predicted_label"], "malicious")
        self.assertEqual(rep["agent_assessment"]["evidence_alignment"], "CONSISTENT")
        self.assertTrue(rep["agent_assessment"]["does_not_override_static_label"])
        # malicious static label -> quarantine suggestion, never executed
        self.assertEqual(rep["recommendation"]["action"], "CONSIDER_QUARANTINE")
        self.assertEqual(rep["recommendation"]["execution_status"], "NOT_EXECUTED")
        self.assertTrue(rep["recommendation"]["requires_human_decision"])
        # markdown renders without error and is Vietnamese
        md = inv.render_report_markdown(rep)
        self.assertIn("PHIẾU ĐIỀU TRA", md)

    def test_report_blocked_when_no_prediction(self):
        state = self._state(with_pred=False)
        rep = inv.build_investigation_report(state, prediction_ev=None, prediction_record=None,
                                             agent_report=None, model_manifest=self._manifest())
        self.assertEqual(rep["overall_status"], "BLOCKED_DETECTOR")
        self.assertEqual(rep["static_prediction"]["status"], "UNAVAILABLE")

    def test_conflict_forces_manual_review(self):
        reco = inv.derive_recommendation("benign", "CONFLICT")
        self.assertEqual(reco["action"], "MANUAL_REVIEW")
        self.assertEqual(reco["priority"], "HIGH")
        self.assertEqual(reco["execution_status"], "NOT_EXECUTED")


class DetectorArtifactTests(unittest.TestCase):
    @unittest.skipUnless(MODEL_PRESENT, "TASK 05A model artifact not present")
    def test_manifest_loads_and_digest_matches(self):
        manifest = inv.load_model_manifest()
        self.assertEqual(manifest["feature_count"], 2381)

    def test_missing_model_is_blocker_not_mock(self):
        saved = inv.MODEL_PATH
        try:
            inv.MODEL_PATH = Path("Z:/nonexistent/model.txt")
            with self.assertRaises(inv.DetectorUnavailableError):
                inv.load_model_manifest()
        finally:
            inv.MODEL_PATH = saved


@unittest.skipUnless(os.name == "nt" and MODEL_PRESENT and os.path.exists(BENIGN_PE),
                     "real detector E2E requires Windows + model + a benign PE")
class RealDetectorE2E(unittest.TestCase):
    def _config(self, tag):
        import tempfile
        from dacn.config import AppConfig
        self._tmp = tempfile.mkdtemp(prefix=f"dacn_05b_{tag}_")
        return AppConfig.from_home(self._tmp)

    def test_benign_pe_predicts_and_commits_no_agent(self):
        from dacn import application as app
        cfg = self._config("benign")
        res = app.investigate_real(cfg, file=BENIGN_PE, run_agent=False)
        self.assertEqual(res["overall_status"], "COMPLETED")
        self.assertEqual(res["prediction_outcome"], "SUCCESS")
        sp = res["report"]["static_prediction"]
        self.assertEqual(sp["status"], "AVAILABLE")
        self.assertIn(sp["predicted_label"], ("benign", "malicious"))
        self.assertEqual(sp["feature_count"], 2381)
        # report files exist
        self.assertTrue(Path(res["report_paths"]["json"]).exists())
        self.assertTrue(Path(res["report_paths"]["markdown"]).exists())

    def test_malformed_pe_commits_no_fake_benign(self):
        import case_manager as cm
        from dacn import application as app
        cfg = self._config("malformed")
        # Stage a non-PE file as the target.
        bad = Path(self._tmp) / "not_a_pe.bin"
        bad.write_bytes(b"this is definitely not a PE file" * 4)
        res = app.investigate_real(cfg, file=str(bad), run_agent=False)
        # No prediction should be committed; report is blocked, not a benign verdict.
        self.assertEqual(res["overall_status"], "BLOCKED_DETECTOR")
        self.assertNotEqual(res["prediction_outcome"], "SUCCESS")
        state = cm.validate_case(cm.read_json(cm.case_path(cfg.cases_dir, res["case_id"])))
        self.assertIsNone(inv.read_prediction_evidence(state))


@unittest.skipUnless(os.name == "nt" and MODEL_PRESENT and os.path.exists(BENIGN_PE)
                     and os.environ.get("DACN_AGENT_LIVE") == "1",
                     "Live Qwen E2E requires Windows + model + benign PE + DACN_AGENT_LIVE=1 + Ollama")
class LiveQwenE2E(unittest.TestCase):
    def test_full_real_pipeline_with_qwen(self):
        import tempfile
        from dataclasses import replace
        from dacn.config import AppConfig
        from dacn import application as app
        from agent.config import AgentConfig
        cfg = AppConfig.from_home(tempfile.mkdtemp(prefix="dacn_05b_live_"))
        acfg = replace(AgentConfig.from_env(), max_iterations=3, max_tool_calls=2)
        res = app.investigate_real(cfg, file=BENIGN_PE, agent_config=acfg, run_agent=True)
        self.assertEqual(res["overall_status"], "COMPLETED")
        ag = res["report"]["agent_assessment"]
        self.assertIsNotNone(ag)
        self.assertEqual(ag["planner_kind"], "LOCAL_QWEN")
        self.assertIn(ag["evidence_alignment"], ("CONSISTENT", "CONFLICT", "INSUFFICIENT_EVIDENCE"))
        self.assertTrue(ag["does_not_override_static_label"])


if __name__ == "__main__":
    unittest.main()
