"""Re-check inherited allegations against saved sheets, original records and prompts.

No model inference, no grading. Old artifacts are read only.
"""
import hashlib
import json
from pathlib import Path
from agent.config import AgentConfig
from agent.context import build_context
from evaluation.task05c.agent_replay import build_replay_state
from evaluation.task05c.evidence_projection import project_record, prediction_observation
from evaluation.task06a.experiment import ROOT, digest, read, write_new


def main():
    pilot = ROOT / "evaluation/task05d/results/pilot_package"
    forms = read(pilot / "annotation_forms_blind_v2.json")["forms"]
    mapping = {r["sample_id"]: r for r in read(pilot / "branch_mapping_EVALUATOR_ONLY.json")}
    records_path = Path("D:/datasets/ember2018-cache/task05c_audit_records.jsonl")
    records = {r["sha256"]: r for r in (json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines())}
    anon = {"S-" + hashlib.sha256(("anon:" + s).encode()).hexdigest()[:10]: s for s in records}
    targets = {"S-7c2ea2e8f0": ["crm"], "S-37cfb6694f": ["mfc"],
               "S-bf43ef03ff": ["exitprocess", "movefilea"], "S-5327b8b93a": []}
    results = []
    for sample in forms:
        sid = sample["sample_id"]
        if sid not in targets:
            continue
        sha = anon[sid]
        record = records[sha]
        form = next(f for f in sample["forms"] if mapping[sid][f["report_label"] + "_is"] == "STATIC_PLUS_AGENT")
        projection = project_record(record)
        state = build_replay_state(sha, projection, prediction_observation(sha, form["static_prediction"]))
        ctx = build_context(state, [], AgentConfig(), [])
        sheet_ids = {e["evidence_id"] for e in form["evidence_sheet"]}
        def imports_text(observations):
            return json.dumps([e["value"] for e in observations if e["facet"] == "static.imports_summary"]).lower()
        original = json.dumps(record.get("imports", {})).lower()
        sheet = imports_text(form["evidence_sheet"])
        rendered = imports_text(ctx["facts"]["evidence"])
        results.append({"sample_id": sid, "sha256": sha, "explanation": form["explanation"],
                        "name_presence": {name: {"original_import_record": name in original,
                                                 "evidence_sheet": name in sheet,
                                                 "reconstructed_prompt_value": name in rendered}
                                          for name in targets[sid]},
                        "entropy_ge7_count": next(e["value"]["high_entropy_section_count_ge7"]
                                                  for e in projection["observations"] if e["facet"] == "static.sections"),
                        "sheet_missing_cited_ids": sorted(set(form["cited_evidence_refs"]) - sheet_ids),
                        "state_missing_cited_ids": sorted(set(form["cited_evidence_refs"]) - {e["evidence_id"] for e in state["evidence"]}),
                        "note": "Reconstructed current frozen v1 context, not a saved historical HTTP payload; no semantic grade assigned"})
    write_new(ROOT / "evaluation/task06a/results/legacy_reaudit.json", {
        "kind": "SOURCE_ARTIFACT_REAUDIT_NO_INFERENCE_NO_GRADING", "records_cache_sha256": digest(records_path),
        "forms_sha256": digest(pilot / "annotation_forms_blind_v2.json"),
        "analysis_source_sha256": digest(Path(__file__)), "findings": results})
    print(json.dumps(results, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
