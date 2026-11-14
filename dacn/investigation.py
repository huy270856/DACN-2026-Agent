"""TASK 05B: real detector integration + investigation report ("phiếu điều tra").

Wires the TASK 05A LightGBM detector into the D1-D9 stack as a trusted, read-only
provider, runs a real static prediction, commits it to Node C, then lets the local
Qwen agent assess the committed evidence and emits a Vietnamese investigation
report. No mock analyzer is used on this path.

Three clearly separated results (never conflated):
  A. static_prediction  - authoritative LightGBM output (label/score/threshold/model).
  B. agent_assessment   - evidence-alignment + reasoning from the SLM (never overrides A).
  C. recommendation     - a SUGGESTION only; execution_status is always NOT_EXECUTED.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import case_manager as cm

from .config import AppConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "research" / "independent_static_ml" / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "model_lightgbm.txt"
MANIFEST_PATH = ARTIFACT_DIR / "model_manifest.json"
ADAPTER_SCRIPT = REPO_ROOT / "research" / "independent_static_ml" / "d5_adapter.py"

TOOL_ID = "static.pe_malware_predict"
TOOL_VERSION = "0.1.0"
PROVIDER_ID = "dacn_lightgbm"
ADAPTER_ID = "dacn_lightgbm_adapter"
CAPABILITY = "static.pe_prediction"
PREDICTION_FACET = "static.pe_malware_prediction"


class DetectorUnavailableError(Exception):
    """The TASK 05A model artifact is missing, unreadable, or digest-mismatched."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_model_manifest() -> Dict[str, Any]:
    """Load + verify the TASK 05A model artifact. Fail closed (no mock fallback)."""
    if not MODEL_PATH.exists():
        raise DetectorUnavailableError(
            f"model artifact not found: {MODEL_PATH} "
            f"(train it via research.independent_static_ml.train_lightgbm)")
    if not MANIFEST_PATH.exists():
        raise DetectorUnavailableError(f"model manifest not found: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    computed = _sha256_file(MODEL_PATH)
    if computed != manifest.get("model_sha256"):
        raise DetectorUnavailableError(
            f"model digest mismatch: file={computed} manifest={manifest.get('model_sha256')}")
    if int(manifest.get("feature_count", 0)) != 2381:
        raise DetectorUnavailableError("model manifest feature_count must be 2381")
    return manifest


def _tool_spec(provider: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "d0-v1", "tool_id": TOOL_ID, "tool_version": TOOL_VERSION,
        "capability": CAPABILITY,
        "description": "Real EMBER v2 + LightGBM static PE malware prediction (read-only)",
        "input_schema_id": "pe-predict-input-v1", "output_schema_id": "static-prediction-v1",
        "provider": provider,
        "effects": {"reads_target": True, "executes_foreign_code": False,
                    "writes_filesystem": False, "mutates_target": False,
                    "requires_human_approval": False, "cleanup_required": False},
        "limits": {"timeout_ms": 120000, "max_output_bytes": 262144,
                   "max_artifact_bytes": 1048576, "max_concurrency": 1},
        "supported_targets": ["FILE"], "enabled": True,
    }


def build_detector_backend(config: AppConfig, manifest: Optional[Dict[str, Any]] = None):
    """Assemble D2/D3/D4/D5/D7/D8/D9 with the REAL detector as the only tool.

    Windows-only (imports the D5 executor). The model artifact, its digest, id and
    threshold are fixed in app code and pinned; the agent can propose calling the
    tool but can inject no adapter/command/model/policy.
    """
    from orchestrator.registry import ToolRegistry
    from orchestrator.policy_engine import PolicyEngine, PolicyConfig
    from orchestrator.trust import TrustedSigner, InMemoryKeyProvider
    from orchestrator.provider_install import ProviderInstallation
    from orchestrator.case_bridge import CaseBridge
    from orchestrator.core import Orchestrator
    from orchestrator.executor import PinnedAdapter
    from orchestrator.pe_prediction_result import pe_prediction_result_from_execution

    config.ensure_dirs()
    manifest = manifest or load_model_manifest()
    model_id = manifest["model_id"]
    model_sha = manifest["model_sha256"]
    threshold = manifest["threshold_selection"]["primary_threshold"]

    interpreter = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
    script = str(ADAPTER_SCRIPT.resolve())
    model_path = str(MODEL_PATH.resolve())
    # Fixed, trusted command. Model path + digest + id + threshold are installer-owned.
    command = (interpreter, "-I", script,
               "--model", model_path, "--expected-model-sha256", model_sha,
               "--model-id", model_id, "--threshold", repr(float(threshold)))
    # All code/data-bearing absolute paths are pinned so D5 verifies their digests.
    pins = [[p, _sha256_file(Path(p))] for p in (interpreter, script, model_path)]
    adapter = PinnedAdapter(PROVIDER_ID, TOOL_VERSION, ADAPTER_ID, command,
                            tuple((p, s) for p, s in pins))

    registry = ToolRegistry()
    registry.register_tool(_tool_spec(adapter.provider()))
    installation = ProviderInstallation()
    installation.install(provider_id=PROVIDER_ID, version=TOOL_VERSION,
                         adapter_id=ADAPTER_ID, command=command, pins=pins)
    policy = PolicyEngine(PolicyConfig(
        tool_allowlist=frozenset({(TOOL_ID, TOOL_VERSION, PROVIDER_ID)}),
        budget_caps={"timeout_ms": 120000, "max_output_bytes": 262144,
                     "max_artifact_bytes": 1048576, "max_concurrency": 1}))
    normalizer = partial(pe_prediction_result_from_execution,
                         expected_model_id=model_id, expected_model_sha256=model_sha)
    orch = Orchestrator(registry=registry, policy=policy,
                        signer=TrustedSigner(InMemoryKeyProvider()),
                        installation=installation,
                        bridge=CaseBridge(audit_ledger_root=config.ledgers_dir),
                        artifact_root=config.artifacts_dir, run_ledger_path=config.run_ledger_path,
                        result_adapters={TOOL_ID: normalizer})
    return registry, orch


def _prediction_tool_call(case_id: str, revision: int, target_ref: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "d0-v1",
        "call_id": "CALL-predict-" + uuid.uuid4().hex[:16],
        "case_id": case_id, "expected_revision": revision,
        "tool_id": TOOL_ID, "tool_version": TOOL_VERSION, "provider_id": PROVIDER_ID,
        "target_ref": copy.deepcopy(target_ref), "arguments": {"feature_version": 2},
        "reason": "TASK 05B deterministic static prediction",
        "requested_by": "workflow", "requested_at": datetime.now(timezone.utc).isoformat(),
        "budget": {"timeout_ms": 120000, "max_output_bytes": 262144},
    }


def run_static_prediction(config: AppConfig, orch, case_file: Path, state: Mapping[str, Any]):
    """Run the real detector through D1-D9 and commit its result to Node C."""
    call = _prediction_tool_call(state["case_id"], state.get("revision", 1), state["target_ref"])
    return orch.run_tool_call(call, case_file)


def read_prediction_evidence(state: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the committed static prediction evidence (evidence_id + value) or None."""
    best = None
    for e in state.get("evidence", []):
        if e.get("facet") == PREDICTION_FACET and e.get("status") == "SUCCESS" and e.get("value"):
            best = {"evidence_id": e.get("evidence_id"), "value": e.get("value")}
    return best


def _facet_evidence(state: Mapping[str, Any], facet: str):
    for e in state.get("evidence", []):
        if e.get("facet") == facet and e.get("status") == "SUCCESS":
            return {"evidence_id": e.get("evidence_id"), "value": e.get("value")}
    return None


# --------------------------------------------------------------------------- #
# Deterministic recommendation (grounded in the authoritative static label).
# The agent may also suggest one; this is the trusted, reproducible baseline.
# Execution is NEVER performed in the MVP.
# --------------------------------------------------------------------------- #
def derive_recommendation(static_label: str, alignment: Optional[str]) -> Dict[str, Any]:
    if static_label == "malicious":
        action, priority = "CONSIDER_QUARANTINE", "HIGH"
        explanation = ("Mô hình tĩnh LightGBM phân loại MALICIOUS. Đề xuất cách ly để xem xét "
                       "và phân tích thêm; chưa thực thi biện pháp nào.")
    elif static_label == "benign":
        action, priority = "MONITOR", "LOW"
        explanation = ("Mô hình tĩnh phân loại BENIGN. Đề xuất theo dõi; phân tích chỉ dựa trên "
                       "đặc trưng tĩnh, không quan sát hành vi runtime.")
    else:
        action, priority = "MANUAL_REVIEW", "MEDIUM"
        explanation = "Không có nhãn tĩnh rõ ràng; đề xuất rà soát thủ công."
    if alignment == "CONFLICT":
        action, priority = "MANUAL_REVIEW", "HIGH"
        explanation = ("Agent báo CONFLICT giữa dự đoán tĩnh và bằng chứng quan sát; "
                       "ưu tiên rà soát thủ công của con người.")
    return {
        "action": action, "priority": priority, "explanation": explanation,
        "requires_human_decision": True, "execution_status": "NOT_EXECUTED",
        "note": "Đây chỉ là ĐỀ XUẤT. Hệ thống không tự cách ly/xoá/kill tiến trình.",
    }


def _extract_agent_assessment(agent_report: Mapping[str, Any],
                              static_label: str) -> Dict[str, Any]:
    """Build the agent_assessment block from the SLM report.

    Prefers the model's own structured `assessment` (alignment/recommendation/
    explanation) when present and valid; otherwise reports INSUFFICIENT_EVIDENCE
    with the model's rationale, never fabricating an alignment.
    """
    assessment = (agent_report or {}).get("agent_assessment")
    valid_alignment = {"CONSISTENT", "CONFLICT", "INSUFFICIENT_EVIDENCE"}
    if isinstance(assessment, dict) and assessment.get("alignment") in valid_alignment:
        alignment = assessment["alignment"]
        review_required = bool(assessment.get("review_required", alignment != "CONSISTENT"))
        explanation = assessment.get("explanation") or agent_report.get("rationale", "")
        agent_reco = assessment.get("recommendation")
    else:
        alignment = "INSUFFICIENT_EVIDENCE"
        review_required = True
        explanation = (agent_report or {}).get("rationale", "") or (
            "Agent không cung cấp đánh giá alignment có cấu trúc.")
        agent_reco = None
    return {
        "evidence_alignment": alignment,
        "review_required": review_required,
        "reasoning_summary": explanation,
        "agent_own_verdict": (agent_report or {}).get("verdict"),
        "agent_suggested_recommendation": agent_reco,
        "evidence_references": list((agent_report or {}).get("evidence_cited", [])),
        "limitations": list((agent_report or {}).get("limitations", [])),
        "does_not_override_static_label": True,
        "planner_kind": (agent_report or {}).get("planner_kind"),
    }


def build_investigation_report(state: Mapping[str, Any], *, prediction_ev: Optional[Dict[str, Any]],
                               prediction_record, agent_report: Optional[Mapping[str, Any]],
                               model_manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Assemble the structured investigation report (phiếu điều tra) JSON."""
    tref = state.get("target_ref") or {}
    sha_ev = _facet_evidence(state, "sha256")
    fmt_ev = _facet_evidence(state, "format")
    fmt = fmt_ev["value"] if fmt_ev else None

    pred = prediction_ev["value"] if prediction_ev else None
    static_label = (pred or {}).get("predicted_label") or "UNKNOWN"

    if pred is not None:
        static_prediction = {
            "status": "AVAILABLE",
            "evidence_id": prediction_ev["evidence_id"],
            "predicted_label": pred["predicted_label"],
            "predicted_class": pred["predicted_class"],
            "raw_score": pred["raw_score"],
            "threshold": pred["threshold"],
            "score_is_calibrated_probability": pred["score_is_calibrated_probability"],
            "model_id": pred["model_id"],
            "model_sha256": pred["model_sha256"],
            "feature_version": pred["feature_version"],
            "feature_count": pred["feature_count"],
            "extractor": pred["extractor"],
            "parser_status": pred["parser_status"],
            "limitations": pred.get("limitations", []),
        }
    else:
        static_prediction = {
            "status": "UNAVAILABLE",
            "reason": f"detector did not commit a prediction "
                      f"(run outcome={getattr(prediction_record, 'outcome', None)}, "
                      f"reason_code={getattr(prediction_record, 'reason_code', None)})",
        }

    alignment = None
    agent_block = None
    if agent_report is not None:
        agent_block = _extract_agent_assessment(agent_report, static_label)
        alignment = agent_block["evidence_alignment"]

    recommendation = derive_recommendation(
        static_label if pred is not None else "UNKNOWN", alignment)

    overall = "COMPLETED" if pred is not None else "BLOCKED_DETECTOR"
    return {
        "schema_version": "investigation-report-v1",
        "schema_status": "PROPOSED additive report (TASK 05B); not owner-approved; "
                         "does not modify D0 contracts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall,
        "case": {
            "case_id": state["case_id"],
            "revision": state.get("revision", 1),
            "target_type": state["target_type"],
            "target_verified_sha256": (tref.get("verified_digest") or {}).get("value"),
            "sha256_evidence_id": sha_ev["evidence_id"] if sha_ev else None,
            "format": (fmt or {}).get("format") if isinstance(fmt, dict) else None,
        },
        "static_prediction": static_prediction,
        "agent_assessment": agent_block,
        "recommendation": recommendation,
        "evidence_used": [
            {"evidence_id": e.get("evidence_id"), "facet": e.get("facet"),
             "status": e.get("status")}
            for e in state.get("evidence", []) if e.get("status") == "SUCCESS"],
        "unverified_items": [
            "Hành vi runtime (dynamic) chưa được quan sát (chỉ phân tích tĩnh).",
            "Raw PE inference trên mẫu malicious chưa được kiểm chứng trong môi trường này "
            "(xem giới hạn TASK 05A).",
        ] + ([] if pred is not None else ["Dự đoán tĩnh không khả dụng cho mục tiêu này."]),
        "model_provenance": {
            "model_id": model_manifest.get("model_id"),
            "model_sha256": model_manifest.get("model_sha256"),
            "dataset": model_manifest.get("dataset", {}).get("name"),
            "feature_version": model_manifest.get("feature_version"),
        },
        "notes": [
            "Nhãn tĩnh (LightGBM) là kết quả phân loại có thẩm quyền; Agent KHÔNG ghi đè.",
            "Raw score KHÔNG phải xác suất đã hiệu chỉnh (uncalibrated).",
            "Chưa thực thi bất kỳ biện pháp xử lý nào (execution_status = NOT_EXECUTED).",
        ],
    }


def render_report_markdown(report: Mapping[str, Any]) -> str:
    """Render the phiếu điều tra as readable Vietnamese Markdown."""
    c = report["case"]
    sp = report["static_prediction"]
    ag = report.get("agent_assessment")
    rc = report["recommendation"]
    mp = report["model_provenance"]
    lines = []
    lines.append("# PHIẾU ĐIỀU TRA MÃ ĐỘC (TASK 05B)")
    lines.append("")
    lines.append(f"- **Trạng thái tổng thể:** {report['overall_status']}")
    lines.append(f"- **Thời điểm:** {report['generated_at']}")
    lines.append("")
    lines.append("## 1. Mục tiêu")
    lines.append(f"- Case ID: `{c['case_id']}` (revision {c['revision']})")
    lines.append(f"- Loại mục tiêu: {c['target_type']}")
    lines.append(f"- SHA-256: `{c['target_verified_sha256']}`")
    lines.append(f"- Định dạng: {c.get('format')}")
    lines.append("")
    lines.append("## 2. Kết quả mô hình tĩnh (LightGBM — có thẩm quyền)")
    if sp["status"] == "AVAILABLE":
        lines.append(f"- **Nhãn:** {sp['predicted_label'].upper()} (class {sp['predicted_class']})")
        lines.append(f"- Raw score: {sp['raw_score']:.6f} · Threshold: {sp['threshold']:.6f} "
                     f"(score ≥ threshold ⇒ malicious)")
        lines.append(f"- Score đã calibrate: {sp['score_is_calibrated_probability']} "
                     f"(raw score, KHÔNG phải xác suất)")
        lines.append(f"- Model: `{sp['model_id']}`")
        lines.append(f"- Model SHA-256: `{sp['model_sha256']}`")
        lines.append(f"- Feature: EMBER v{sp['feature_version']} ({sp['feature_count']} chiều), "
                     f"extractor {sp['extractor']['name']} {sp['extractor']['version']} "
                     f"(LIEF {sp['extractor']['lief_version']})")
        lines.append(f"- Parser status: {sp['parser_status']}")
        lines.append(f"- Evidence ID: `{sp['evidence_id']}`")
    else:
        lines.append(f"- KHÔNG khả dụng: {sp.get('reason')}")
    lines.append("")
    lines.append("## 3. Đánh giá của Agent (Qwen3.5-4B — không ghi đè nhãn tĩnh)")
    if ag is not None:
        lines.append(f"- **Evidence alignment:** {ag['evidence_alignment']}")
        lines.append(f"- Cần review: {ag['review_required']}")
        lines.append(f"- Planner: {ag.get('planner_kind')}")
        lines.append(f"- Tóm tắt lập luận: {ag['reasoning_summary']}")
        if ag.get("agent_own_verdict"):
            lines.append(f"- (Verdict riêng của agent, phi thẩm quyền: {ag['agent_own_verdict']})")
    else:
        lines.append("- Không có đánh giá của Agent (agent không chạy hoặc không khả dụng).")
    lines.append("")
    lines.append("## 4. Bằng chứng sử dụng")
    if ag and ag.get("evidence_references"):
        for r in ag["evidence_references"]:
            lines.append(f"- `{r}`")
    for e in report["evidence_used"]:
        lines.append(f"- `{e['evidence_id']}` — {e['facet']} ({e['status']})")
    lines.append("")
    lines.append("## 5. Giải thích & giới hạn")
    for lim in (sp.get("limitations", []) if sp["status"] == "AVAILABLE" else []):
        lines.append(f"- {lim}")
    if ag:
        for lim in ag.get("limitations", []):
            lines.append(f"- {lim}")
    lines.append("")
    lines.append("## 6. Vấn đề chưa xác minh")
    for u in report["unverified_items"]:
        lines.append(f"- {u}")
    lines.append("")
    lines.append("## 7. Khuyến nghị xử lý (chỉ là đề xuất)")
    lines.append(f"- **Hành động đề xuất:** {rc['action']} · Ưu tiên: {rc['priority']}")
    lines.append(f"- Giải thích: {rc['explanation']}")
    lines.append(f"- Cần con người quyết định: {rc['requires_human_decision']}")
    if ag and ag.get("agent_suggested_recommendation"):
        lines.append(f"- (Agent đề xuất thêm: {ag['agent_suggested_recommendation']})")
    lines.append("")
    lines.append("## 8. Ghi chú")
    lines.append(f"- **Chưa thực thi biện pháp xử lý nào** (execution_status = "
                 f"{rc['execution_status']}).")
    for n in report["notes"]:
        lines.append(f"- {n}")
    lines.append(f"- Model provenance: `{mp.get('model_id')}` / dataset {mp.get('dataset')}.")
    lines.append("")
    return "\n".join(lines)


def write_reports(report: Mapping[str, Any], config: AppConfig) -> Dict[str, str]:
    """Persist the phiếu điều tra as JSON + Markdown under the case report dir."""
    out_dir = Path(config.artifacts_dir) / "investigation_reports" / report["case"]["case_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "investigation_report.json"
    md_path = out_dir / "investigation_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_report_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
