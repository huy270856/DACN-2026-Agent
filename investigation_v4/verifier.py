"""TASK 07B deterministic verifier v4. Flags only; never edits or completes model claims.

Trusted code RESOLVES model-selected handles into literal sources for provenance/display; a
valid reference does not prove the evidence entails the claim (semantic grounding PENDING).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from . import query

# Same absence screen as TASK 07A metrics (task07a-metrics-v1) so results stay comparable.
from evaluation.task07a.metrics import ABSENCE_RE, LIMITATION_RE, SENT_SPLIT

NUMERIC_RE = re.compile(r"\bentropy\b|\b\d+(?:\.\d+)?\s*%\s*(?:probability|chance|likelihood)", re.I)
SCORE_PROB_RE = re.compile(r"\b(?:probability|likelihood|chance)\b[^.]{0,60}\b(?:malicious|benign|malware)\b"
                           r"|\b(?:malicious|benign|malware)\b[^.]{0,60}\bprobability\b", re.I)


def _texts(obj: Dict[str, Any]) -> List[str]:
    return [obj.get("answer") or ""] + [f.get("text") or "" for f in obj.get("findings", [])]


def resolve(handle: str, handles, table_value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    r = handles.resolve(handle)
    if r is None:
        return None
    if r["kind"] == "IMPORT_ENTRY":
        if table_value is None or r["index"] >= len(table_value["entries"]):
            return None
        v = query.entry_view(table_value, r["index"])
        return {"handle": handle, "kind": "IMPORT_ENTRY", "index": r["index"], "literal": query.literal(v),
                "resolved_symbol": v["resolved_symbol"]}
    return {"handle": handle, **r}


# Conservative exemption: the sentence must stay within the queried scope.
SCOPE_CUE_RE = re.compile(r"\b(?:quer(?:y|ied|ies)|prefix|starting with|start with|named|match(?:es|ing)?|in [\w.\-]+\.dll)\b", re.I)
BROAD_RE = re.compile(r"\b(?:network|networking|file[- ]system|file|files|process|processes|registry|service|services|"
                      r"capabilit(?:y|ies)|communicat\w*|internet|socket[- ]?level)\b", re.I)


def _covered(sentence: str, table_value: Dict[str, Any], viewed: set, query_log: List[Dict[str, Any]]) -> bool:
    """An absence sentence is in coverage only if (a) the table is not truncated, (b) it names a DLL whose
    returned entries were all viewed, or a query value whose matches were all viewed (incl. zero
    matches), (c) it carries an explicit query/DLL scope cue, and (d) it does not generalise to a whole
    capability family (network/file/process/registry/service/capability...). Broader claims stay flagged."""
    if table_value["truncated"]:
        return False
    low = sentence.lower()
    if not SCOPE_CUE_RE.search(sentence) or BROAD_RE.search(sentence):
        return False
    for d in query.dll_summary(table_value):
        if d["dll"].lower() in low and set(query.dll_indices(table_value, d["dll"])) <= viewed:
            return True
    seen: Dict[tuple, Dict[str, Any]] = {}
    for q in query_log:
        k = (q["by"], q["value"].lower())
        rec = seen.setdefault(k, {"total": q["total_matches"], "idx": set()})
        rec["idx"] |= set(q["indices"])
    for (by, value), rec in seen.items():
        if value in low and len(rec["idx"]) >= rec["total"]:
            return True
    return False


def verify(obj: Dict[str, Any], *, shown_handles: Iterable[str], handles, table_value: Optional[Dict[str, Any]],
           viewed_indices: Iterable[int], query_log: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    shown = set(shown_handles)
    viewed = set(viewed_indices)
    flags: List[str] = []
    finding_flags: List[Dict[str, Any]] = []
    resolved: List[Dict[str, Any]] = []

    def check_sources(srcs, where):
        for h in srcs:
            r = resolve(h, handles, table_value) if h in shown else None
            if r is None:
                finding_flags.append({"where": where, "flag": "source_not_visible", "handle": h})
            else:
                resolved.append(dict(r, cited_in=where))

    for i, f in enumerate(obj.get("findings", [])):
        check_sources(f.get("sources", []), f"findings[{i}]")
        if f.get("kind") == "OBSERVED" and not f.get("sources"):
            finding_flags.append({"where": f"findings[{i}]", "flag": "observed_without_source"})
    rel = obj.get("detector_relation") or {}
    check_sources(rel.get("basis_sources", []), "detector_relation")
    if rel.get("value") in ("AGREES", "CONFLICTS") and not rel.get("basis_sources"):
        flags.append("detector_relation_without_basis")
    # Absence beyond coverage: a capability-negating sentence while the table was not fully viewed.
    full_view = table_value is not None and len(viewed) >= len(table_value["entries"]) and not table_value["truncated"]
    absence = []
    for text in _texts(obj):
        for sent in SENT_SPLIT.split(text):
            if ABSENCE_RE.search(sent) and not LIMITATION_RE.search(sent):
                absence.append(sent.strip())
    uncovered = [a for a in absence if table_value is not None and not full_view
                 and not _covered(a, table_value, viewed, query_log or [])]
    if absence and table_value is None:
        flags.append("absence_claim_without_imports_source_suspected")
    elif uncovered:
        flags.append("absence_beyond_coverage_suspected")
    joined = " ".join(_texts(obj))
    if NUMERIC_RE.search(joined):
        flags.append("numeric_or_entropy_claim_suspected_unverified")
    if SCORE_PROB_RE.search(joined):
        flags.append("score_as_probability_suspected")
    if finding_flags:
        flags.append("finding_flags_present")
    return {"flags": flags, "finding_flags": finding_flags, "resolved_sources": resolved,
            "absence_sentences": absence, "absence_uncovered": uncovered, "has_flags": bool(flags),
            "semantic_grounding": "PENDING_INDEPENDENT_REVIEW"}
