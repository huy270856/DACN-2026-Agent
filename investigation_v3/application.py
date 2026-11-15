"""App integration; deterministic detector first, supplemental analyzer only on LLM request."""
import json
from pathlib import Path
import uuid

from agent.config import AgentConfig
from dacn import application as app, investigation as inv
import case_manager as cm
from . import audit, workflow
from .import_adapter import MAX_BYTES


def prepare(config, *, file=None, case_id=None):
    if file is not None:
        try:
            if Path(file).stat().st_size > MAX_BYTES:
                raise app.ApplicationError("Multi-step PE exceeds 8 MiB input budget")
        except OSError as exc:
            raise app.ApplicationError("Target metadata unavailable") from exc
    manifest = inv.load_model_manifest()
    if file is not None:
        intake = app.intake_file(file, config)
        if intake["collection_status"] == "FAILED":
            raise app.ApplicationError("Node B intake failed")
        case_id = intake["case_id"]
    path = cm.case_path(config.cases_dir, case_id)
    state = cm.validate_case(cm.read_json(path))
    registry, orch = inv.build_detector_backend(config, manifest, include_imports=True)
    events = []
    policy = audit.attach(orch, events)
    if inv.read_prediction_evidence(state) is None:
        record = inv.run_static_prediction(config, orch, path, state)
        if record.outcome != "SUCCESS":
            raise app.ApplicationError("Detector did not commit a prediction: " + str(record.reason_code))
    return path, registry, orch, policy, events


def investigate(config, *, file=None, case_id=None, agent_config=None, planner=None):
    try:
        path, registry, orch, policy, events = prepare(config, file=file, case_id=case_id)
    except inv.DetectorUnavailableError as exc:
        return {"supported": True, "overall_status": "BLOCKED_DETECTOR", "error": str(exc),
                "report_paths": {}, "report": None}
    cfg = agent_config or AgentConfig(max_iterations=3, max_context_chars=24000)
    report = workflow.run(path, cfg, registry, orch, policy, planner=planner, events=events)
    folder = config.home / "reports"
    folder.mkdir(exist_ok=True)
    target = folder / (report["case_id"] + "-" + uuid.uuid4().hex[:8])
    jp, mp = target.with_suffix(".json"), target.with_suffix(".md")
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    final = report.get("final") or {}
    mp.write_text("# Phiếu điều tra nhiều bước\n\nTrạng thái: " + report["status"]
                  + "\n\nPrediction (raw score không phải xác suất): " + json.dumps(report["model_prediction"], ensure_ascii=False)
                  + "\n\nAssessment và phân biệt bằng chứng cũ/mới:\n\n```json\n" + json.dumps(final, ensure_ascii=False, indent=2)
                  + "\n```\n\nTrusted verification / recommendation (chưa thực thi):\n\n```json\n"
                  + json.dumps(report.get("verification"), ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    with mp.open("a", encoding="utf-8") as stream:
        stream.write("\nEffective recommendation (trusted, không containment):\n\n```json\n"
                     + json.dumps(report["effective_recommendation"], ensure_ascii=False, indent=2) + "\n```\n")
    return {"supported": True, "overall_status": "COMPLETED" if report["status"] == "FINISHED" else report["status"],
            "case_id": report["case_id"], "report_paths": {"json": str(jp), "markdown": str(mp)}, "report": report}
