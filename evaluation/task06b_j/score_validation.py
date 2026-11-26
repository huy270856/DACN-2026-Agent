"""Strict validation of a TASK 06B-J judgment file (human or LLM-as-Judge).

A judgment file is rejected - never repaired or auto-filled - if anything is missing or
malformed. Validation checks: schema/rubric/package identity, evaluator provenance, full
item coverage, criterion keys, applicability (NOT_APPLICABLE only where the rubric says so,
a real score or NOT_ASSESSABLE wherever REQUIRED), score ranges, non-empty rationales,
evidence IDs that exist in the item, and a verdict for every listed claim.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from evaluation.task06b_j import rubric

JUDGMENT_SCHEMA = "task06b-j-judgments-v1"
EVALUATOR_KINDS = ("HUMAN", "LLM_JUDGE", "MOCK_JUDGE_TEST_ONLY")
LLM_PROVENANCE_KEYS = ("provider", "model", "model_version_or_digest", "prompt_sha256",
                       "inference_method", "raw_responses_file")


def _item_ids(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {it["item_id"]: it for it in items}


def _known_evidence_ids(item: Dict[str, Any]) -> set:
    ids = {e["evidence_id"] for e in item["agent_visible_evidence"]["evidence"]}
    ids |= {e["evidence_id"] for e in item["reference_evidence"]["evidence"]}
    return ids


def validate(judgments: Dict[str, Any], package_view: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    if judgments.get("schema_version") != JUDGMENT_SCHEMA:
        errs.append(f"bad schema_version {judgments.get('schema_version')!r}")
    for k in ("rubric_id", "rubric_sha256", "package_id", "view"):
        if judgments.get(k) != package_view.get(k):
            errs.append(f"{k} mismatch: {judgments.get(k)!r} != package {package_view.get(k)!r}")
    if judgments.get("rubric_sha256") != rubric.rubric_sha256():
        errs.append("rubric_sha256 does not match the locked rubric in code")
    ev = judgments.get("evaluator") or {}
    if ev.get("kind") not in EVALUATOR_KINDS:
        errs.append(f"evaluator.kind must be one of {EVALUATOR_KINDS}")
    if not ev.get("evaluator_id"):
        errs.append("evaluator.evaluator_id missing")
    if ev.get("kind") == "LLM_JUDGE":
        errs += [f"evaluator.{k} missing (LLM provenance)" for k in LLM_PROVENANCE_KEYS if not ev.get(k)]
        if ev.get("human_verified") is not False:
            errs.append("evaluator.human_verified must be explicitly false for an LLM judge")
    for k in ("pass_id", "created_utc"):
        if not judgments.get(k):
            errs.append(f"{k} missing")

    items = _item_ids(package_view["items"])
    seen = set()
    for j in judgments.get("judgments", []):
        iid = j.get("item_id")
        if iid not in items:
            errs.append(f"unknown item_id {iid!r}"); continue
        if iid in seen:
            errs.append(f"duplicate judgment for {iid}"); continue
        seen.add(iid)
        item = items[iid]
        known = _known_evidence_ids(item)
        crit = j.get("criteria") or {}
        extra = set(crit) - set(item["applicability"])
        if extra:
            errs.append(f"{iid}: criteria not in this view: {sorted(extra)}")
        for name, rule in item["applicability"].items():
            c = crit.get(name)
            if c is None:
                errs.append(f"{iid}: missing criterion {name}"); continue
            score = c.get("score")
            if rule == rubric.NA:
                if score != rubric.NA:
                    errs.append(f"{iid}.{name}: must be {rubric.NA} by rule, got {score!r}")
                continue
            if rule == "NOT_ASSESSABLE_INCOMPLETE":
                if score != rubric.NX:
                    errs.append(f"{iid}.{name}: incomplete report -> must be {rubric.NX}, got {score!r}")
                continue
            scale = rubric.CRITERIA[name]["scale"]
            if score == rubric.NA:
                errs.append(f"{iid}.{name}: {rubric.NA} not allowed where rubric requires a judgment")
            elif score != rubric.NX and (isinstance(score, bool) or score not in scale):
                errs.append(f"{iid}.{name}: score {score!r} outside {scale}")
            if not str(c.get("rationale") or "").strip():
                errs.append(f"{iid}.{name}: empty rationale")
            cited = c.get("evidence_ids") or []
            if set(cited) - known:
                errs.append(f"{iid}.{name}: rationale cites unknown evidence {sorted(set(cited) - known)}")
            if name in rubric.RATIONALE_NEEDS_EVIDENCE and score in scale and not cited:
                errs.append(f"{iid}.{name}: numeric score needs evidence_ids in the rationale")
        # claim level
        claim_ids = {c["claim_id"] for c in item["report"].get("claims", [])}
        got = {}
        for cv in j.get("claims", []):
            cid = cv.get("claim_id")
            if cid in got:
                errs.append(f"{iid}: duplicate claim verdict {cid}")
            got[cid] = cv
            if cid not in claim_ids:
                errs.append(f"{iid}: verdict for unknown claim {cid!r}")
            if cv.get("verdict") not in rubric.CLAIM_VERDICTS:
                errs.append(f"{iid}.{cid}: bad verdict {cv.get('verdict')!r}")
            bad_tags = set(cv.get("tags", [])) - set(rubric.CLAIM_TAGS)
            if bad_tags:
                errs.append(f"{iid}.{cid}: unknown tags {sorted(bad_tags)}")
            if not str(cv.get("rationale") or "").strip():
                errs.append(f"{iid}.{cid}: empty claim rationale")
            if set(cv.get("evidence_ids") or []) - known:
                errs.append(f"{iid}.{cid}: cites unknown evidence")
        missing = claim_ids - set(got)
        if missing and judgments.get("view") == "common":
            errs.append(f"{iid}: missing claim verdicts {sorted(missing)}")
        for k, ac in enumerate(j.get("additional_claims", [])):
            if not ac.get("text") or ac.get("verdict") not in rubric.CLAIM_VERDICTS:
                errs.append(f"{iid}: additional_claims[{k}] needs text and a valid verdict")
    missing_items = set(items) - seen
    if missing_items:
        errs.append(f"incomplete coverage: {len(missing_items)} item(s) not judged")
    return errs


def validate_files(judgment_path: Path, package_view_path: Path) -> List[str]:
    j = json.loads(Path(judgment_path).read_text(encoding="utf-8"))
    p = json.loads(Path(package_view_path).read_text(encoding="utf-8"))
    return validate(j, p)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Validate a 06B-J judgment file against a package view")
    ap.add_argument("--judgments", type=Path, required=True)
    ap.add_argument("--package-view", type=Path, required=True)
    a = ap.parse_args()
    errors = validate_files(a.judgments, a.package_view)
    print(json.dumps({"valid": not errors, "errors": errors}, indent=2, ensure_ascii=False))
    raise SystemExit(0 if not errors else 1)
