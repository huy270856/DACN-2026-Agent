"""TASK 06B-J blind grading package builder (evaluation-only; never in the Agent decision path).

Input: an item spec (JSON list) naming frozen run artifacts. Output (new directory only):
  grader/items_common.json         - every arm: report + Agent-visible evidence + reference sheet
  grader/items_investigation.json  - Agent arms only: same + action/tool/retrieval trace
  EVALUATOR_ONLY/mapping.json      - item_id -> arm/source/sha (+ deterministic checker flags)
  EVALUATOR_ONLY/calibration_key.json (only if the spec carries developer expectations/probes)
  package_manifest.json            - rubric id/hash, seed, input SHA-256s, output SHA-256s

Blinding: arm names, run names, contract versions, planner kind, statuses, checker flags and
ground-truth labels never enter grader files (enforced by leakage_scan). Report text is kept
verbatim, so stylistic differences between arms and any path the Agent itself saw and quoted
remain visible - a documented, unavoidable limitation. Nothing is scored here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from evaluation.task06b_j import rubric

PACKAGE_SCHEMA = "task06b-j-package-v1"
IMPORTS_FACET = "static.pe_imports_detail"
PRED_FACET = "static.pe_malware_prediction"
PRED_KEYS = ("predicted_label", "raw_score", "threshold", "score_is_calibrated_probability", "model_id")

# Tokens that would reveal arm identity, pipeline version, checker output or ground truth.
FORBIDDEN_TOKENS = (
    "STATIC_ONLY", "AGENT_NO_TOOL", "AGENT_TOOL_ENABLED", "STATIC_TEMPLATE", "true_label",
    "EVALUATOR_ONLY", "label_basis", "FINISHED_FLAGGED", "INVESTIGATION_INCOMPLETE",
    "prediction_used_as_own_corroboration", "suspected_unverified", "investigation-v3",
    "planner_kind", "LOCAL_QWEN", "MOCK_LLM", "r2_debug", "repair_dev", "dev_v1", "dev_v2",
    "SYNTHETIC", "calibration_key", "DEV_CALIBRATION", "dev-probe", "expected_verdict",
)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def _read(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_new(path: Path, obj: Any) -> str:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8")
    path.write_bytes(raw)
    return sha256_bytes(raw)


def _blind_id(seed: str, *parts: str, prefix: str) -> str:
    return prefix + sha256_bytes("|".join((seed,) + parts).encode("utf-8"))[:10]


# ----------------------------------------------------------------------------- evidence views
def _evidence_entry(e: Dict[str, Any]) -> Dict[str, Any]:
    value = copy.deepcopy(e.get("value"))
    if e.get("facet") == PRED_FACET and isinstance(value, dict):
        value = {k: value.get(k) for k in PRED_KEYS if k in value}
    out = {"evidence_id": e["evidence_id"], "facet": e.get("facet"), "status": e.get("status"),
           "value": value}
    for k in ("phase", "coverage", "limitations", "projection_truncated"):
        if k in e:
            out[k] = copy.deepcopy(e[k])
    return out


def _final_turn(report: Dict[str, Any]) -> Dict[str, Any]:
    final = report.get("final")
    for t in reversed(report.get("turns", [])):
        if final is not None and t.get("proposal") == final:
            return t
    return report["turns"][-1] if report.get("turns") else {}


def agent_visible_sheet(report: Dict[str, Any]) -> Dict[str, Any]:
    """Exactly what the Agent was shown in the turn that produced (or ended without) its final."""
    facts = (_final_turn(report).get("context") or {}).get("facts") or {}
    return {"origin": "AGENT_PROMPT_FACTS_AT_FINAL_TURN",
            "question": facts.get("question"),
            "evidence": [_evidence_entry(e) for e in facts.get("evidence", [])],
            "omitted_evidence_ids": facts.get("omitted_evidence_ids", []),
            "unknowns": copy.deepcopy(facts.get("unknowns", []))}


def reference_sheet(state: Dict[str, Any], visible: Dict[str, Any]) -> Dict[str, Any]:
    """Full committed CaseState evidence, each marked with whether/what the Agent saw."""
    vis = {e["evidence_id"]: e for e in visible.get("evidence", [])}
    rows = []
    for e in state.get("evidence", []):
        if e.get("status") != "SUCCESS":
            continue
        row = _evidence_entry(e)
        seen = vis.get(e["evidence_id"])
        row["visible_to_agent"] = seen is not None
        if e.get("facet") == IMPORTS_FACET and isinstance(e.get("value"), dict):
            entries = e["value"].get("entries", [])
            row["value"] = dict(row["value"], entries=[dict(x, entry_index=i) for i, x in enumerate(entries)])
            shown = {x.get("entry_index") for x in ((seen or {}).get("value") or {}).get("entries", [])}
            row["entry_indices_visible_to_agent"] = sorted(i for i in shown if i is not None)
        rows.append(row)
    return {"origin": "COMMITTED_CASESTATE_EVALUATOR_REFERENCE",
            "note": "Reference for checking claims; entries not visible to the Agent cannot support its "
                    "claims but CAN contradict them.", "evidence": rows}


# ----------------------------------------------------------------------------- report views
def _static_report(a: Dict[str, Any]) -> Dict[str, Any]:
    pred = a["model_prediction"]
    rec = a.get("recommendation") or {}
    return {"has_final": True,
            "prediction_shown": {k: pred.get(k) for k in PRED_KEYS if k in pred},
            "explanation": a.get("explanation"),
            "recommendation": rec.get("action"), "recommendation_text": rec.get("explanation"),
            "uncertainty_notes": [], "claims": [], "free_text": {}}


def _agent_report(r: Dict[str, Any]) -> Dict[str, Any]:
    final = r.get("final")
    if not final:
        return {"has_final": False,
                "no_final_note": "The Agent produced no accepted final assessment; the system fell back "
                                 "to human MANUAL_REVIEW.", "claims": []}
    a = final["assessment"]
    resolved = (r.get("trusted_metadata") or {}).get("resolved_import_refs", [])
    claims = []
    for i, c in enumerate(a.get("claims", [])):
        claims.append({"claim_id": f"C{i + 1}", "kind": c.get("kind"), "text": c.get("text"),
                       "evidence_ids": list(c.get("evidence_ids", [])),
                       "import_refs_resolved": [
                           {k: x[k] for k in ("evidence_id", "entry_index", "resolved_import")}
                           for x in resolved if x.get("claim_index") == i]})
    out = {"has_final": True,
           "explanation": a.get("explanation"), "recommendation": a.get("recommendation"),
           "alignment": a.get("alignment"), "confidence_in_assessment": a.get("confidence_in_assessment"),
           "supporting_evidence_ids": a.get("supporting_evidence_ids", []),
           "contradicting_evidence_ids": a.get("contradicting_evidence_ids", []),
           "uncertainty_notes": a.get("uncertainty_notes", []), "claims": claims,
           "free_text": {k: final.get(k) for k in ("reason", "change_explanation", "stop_reason") if final.get(k)}}
    if final.get("import_bindings"):
        out["model_declared_import_bindings"] = copy.deepcopy(final["import_bindings"])
    return out


def trace_view(r: Dict[str, Any]) -> Dict[str, Any]:
    steps = []
    for t in r.get("turns", []):
        p = t.get("proposal") or {}
        step = {"step": t.get("iteration"), "action": p.get("action"), "model_reason": p.get("reason")}
        if t.get("validation_error") or t.get("error"):
            step["rejected"] = (t.get("validation_error") or t.get("error"))[:300]
        if "post_execution" in t:
            pe = t["post_execution"]
            step["tool_result"] = {"outcome": pe.get("outcome"), "new_evidence_ids": pe.get("new_evidence_ids")}
        if "retrieved_page" in t:
            pg = t["retrieved_page"]
            step["read_page"] = {"evidence_id": pg.get("evidence_id"), "offset": pg.get("offset"),
                                 "entries": len(pg.get("entries", []))}
        steps.append(step)
    facts0 = (r["turns"][0].get("context") or {}).get("facts", {}) if r.get("turns") else {}
    return {"tool_available": bool(facts0.get("available_tools")),
            "tools_offered": [x.get("tool_id") for x in facts0.get("available_tools", [])],
            "steps": steps, "llm_calls": len(r.get("turns", [])),
            "tool_calls": r.get("tool_attempts", 0), "evidence_reads": r.get("retrieval_attempts", 0)}


def _tool_committed(r: Dict[str, Any]) -> bool:
    return any(h.get("outcome") == "SUCCESS" and h.get("new_evidence_ids") for h in r.get("history", []))


def deterministic_flags(r: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluator-only copy of the existing rule screen output (never shown to graders)."""
    v = r.get("verification") or {}
    return {"status": r.get("status"), "failure": r.get("failure"),
            "grounding_flags": v.get("flags", []), "claim_flags": v.get("claim_flags", []),
            "consistency_flags": (v.get("consistency") or {}).get("flags", []),
            "effective_action": (r.get("effective_recommendation") or {}).get("action")}


# ----------------------------------------------------------------------------- probes
def apply_probe(report_view: Dict[str, Any], probe: Dict[str, Any]) -> Dict[str, Any]:
    """Developer-constructed calibration probe: append one claim to a copy of a real report."""
    out = copy.deepcopy(report_view)
    out["claims"].append({"claim_id": f"C{len(out['claims']) + 1}", "kind": probe["kind"],
                          "text": probe["text"], "evidence_ids": list(probe["evidence_ids"]),
                          "import_refs_resolved": []})
    return out


# ----------------------------------------------------------------------------- leakage
def leakage_scan(obj: Any) -> List[str]:
    text = json.dumps(obj, ensure_ascii=False)
    return [t for t in FORBIDDEN_TOKENS if t.lower() in text.lower()]


# ----------------------------------------------------------------------------- build
def build(spec_path: Path, out_dir: Path, seed: str, package_id: str) -> Dict[str, Any]:
    if out_dir.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out_dir} exists")
    spec = _read(spec_path)
    root = spec_path.parent
    inputs, common, invest, mapping, key = {}, [], [], [], []
    for s in spec["items"]:
        src = (root / s["source"]).resolve()
        inputs[s["source"]] = sha256_file(src)
        r = _read(src)
        sample_alias = _blind_id(seed, s["sample_sha256"], prefix="S-")
        item_id = _blind_id(seed, s["sample_sha256"], s["arm"], s.get("variant", ""),
                            json.dumps(s.get("probe"), sort_keys=True), prefix="J-")
        if s["arm"] == "A":
            init_src = (root / s["initial_state"]).resolve()
            inputs[s["initial_state"]] = sha256_file(init_src)
            state = _read(init_src)
            visible = {"origin": "REPORT_INPUT_INITIAL_CASESTATE", "question": r.get("question"),
                       "evidence": [_evidence_entry(e) for e in state["evidence"] if e.get("status") == "SUCCESS"],
                       "omitted_evidence_ids": [], "unknowns": []}
            report = _static_report(r)
            flags = {"status": "STATIC_TEMPLATE"}
            trace, committed = None, False
        else:
            state = r.get("final_state") or r.get("initial_state")
            visible = agent_visible_sheet(r)
            report = _agent_report(r)
            flags = deterministic_flags(r)
            trace, committed = trace_view(r), _tool_committed(r)
        if s.get("probe"):
            report = apply_probe(report, s["probe"])
        ref = reference_sheet(state, visible)
        base = {"item_id": item_id, "sample": sample_alias, "report": report,
                "agent_visible_evidence": visible, "reference_evidence": ref}
        app_c = rubric.applicability("common", {"has_final": report["has_final"], "tool_available": False,
                                                "tool_evidence_committed": False})
        common.append(dict(base, applicability=app_c))
        if s["arm"] != "A":
            props = {"has_final": report["has_final"], "tool_available": trace["tool_available"],
                     "tool_evidence_committed": committed}
            invest.append(dict(base, trace=trace, applicability=rubric.applicability("investigation", props)))
        mapping.append({"item_id": item_id, "sample": sample_alias, "sample_sha256": s["sample_sha256"],
                        "arm": s["arm"], "variant": s.get("variant"), "source": s["source"],
                        "source_sha256": inputs[s["source"]], "deterministic_checker": flags,
                        "tool_evidence_committed": committed, "is_probe": bool(s.get("probe"))})
        if s.get("expectation") or s.get("probe"):
            key.append({"item_id": item_id, "expectation": s.get("expectation"),
                        "probe": s.get("probe"), "status": "DEVELOPER_EXPECTATION_NOT_GROUND_TRUTH"})
    order = lambda x: _blind_id(seed, "order", x["item_id"], prefix="")
    common.sort(key=order); invest.sort(key=order)
    instructions = {
        "rubric_id": rubric.RUBRIC_ID, "rubric_sha256": rubric.rubric_sha256(),
        "instructions": [
            "Score each item independently using RUBRIC.md; do not compare items to each other.",
            "The static detector prediction is a MODEL OUTPUT, not ground truth; its raw score is not a probability.",
            "agent_visible_evidence is what the report author saw; reference_evidence is the full committed "
            "evidence (entries the author did not see cannot support its claims but can contradict them).",
            "Give a verdict for every listed claim and list any additional material claim found in free text.",
            "Use NOT_ASSESSABLE when the material shown does not allow a decision; never guess.",
            "Some items may be constructed check items; grade them like any other item.",
        ]}
    leaks = leakage_scan(common) + leakage_scan(invest) + leakage_scan(instructions)
    if leaks:
        raise ValueError(f"LEAKAGE_DETECTED: {sorted(set(leaks))}")
    out_dir.mkdir(parents=True)
    outputs = {
        "grader/items_common.json": _write_new(out_dir / "grader/items_common.json",
            dict(instructions, schema_version=PACKAGE_SCHEMA, package_id=package_id, view="common", items=common)),
        "grader/items_investigation.json": _write_new(out_dir / "grader/items_investigation.json",
            dict(instructions, schema_version=PACKAGE_SCHEMA, package_id=package_id, view="investigation", items=invest)),
        "EVALUATOR_ONLY/mapping.json": _write_new(out_dir / "EVALUATOR_ONLY/mapping.json",
            {"package_id": package_id, "seed": seed, "items": mapping}),
    }
    if key:
        outputs["EVALUATOR_ONLY/calibration_key.json"] = _write_new(out_dir / "EVALUATOR_ONLY/calibration_key.json",
            {"package_id": package_id, "note": spec.get("calibration_note"), "items": key})
    manifest = {"schema_version": PACKAGE_SCHEMA, "package_id": package_id, "track": spec.get("track"),
                "confirmatory": spec.get("confirmatory", "NOT_RUN"), "seed": seed,
                "rubric_id": rubric.RUBRIC_ID, "rubric_sha256": rubric.rubric_sha256(),
                "spec_sha256": sha256_file(spec_path), "input_sha256": inputs, "output_sha256": outputs,
                "counts": {"common": len(common), "investigation": len(invest),
                           "probes": sum(m["is_probe"] for m in mapping)},
                "leakage_scan": "PASS", "scores": "NONE (package contains no scores)"}
    _write_new(out_dir / "package_manifest.json", manifest)
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build a TASK 06B-J blind grading package")
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--package-id", required=True)
    a = ap.parse_args(argv)
    print(json.dumps(build(a.spec, a.out, a.seed, a.package_id), indent=2))


if __name__ == "__main__":
    main()
