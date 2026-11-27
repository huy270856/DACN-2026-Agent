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


# Conservative exemption (review Medium-3): WHITELIST of narrow sentence shapes + DENY list of broad words.
# Narrow prefix shape: "no ... (import|entry|symbol|name|function|API)s ... (starting with|prefix|named|matching) VALUE"
NARROW_PREFIX_RE = re.compile(
    r"\b(?:no|none|zero|not)\b.{0,80}?\b(?:imports?|entr(?:y|ies)|symbols?|names?|functions?|apis?)\b.{0,40}?"
    r"\b(?:starting with|start with|with (?:the )?prefix|prefix(?:ed)?(?: by| with)?|named|matching|match(?:es|ed)?)"
    r"\s+['\"`]?([A-Za-z0-9_?@$]{3,64})", re.I)
# Narrow DLL shape: "... in/from X.dll"
NARROW_DLL_RE = re.compile(r"\b(?:in|from)\s+['\"`]?([A-Za-z0-9_.\-]+\.dll)\b", re.I)
BROAD_RE = re.compile(
    r"\b(?:network\w*|file[- ]system|files?|process(?:es)?|registry|services?|capabilit(?:y|ies)|communicat\w*|"
    r"internet|persisten\w*|inject\w*|crypt\w*|encrypt\w*|download\w*|upload\w*|remote\w*|malicious|malware|"
    r"suspicious|evasi\w*|privilege\w*|keylog\w*|exfiltrat\w*|execut\w*|memory|thread\w*|hook\w*|debug\w*|"
    r"security|sensitive|dangerous|harmful|behaviou?r\w*|related|relevant|(?:apis?|functions?|imports?)\s+for)\b",
    re.I)


def _covered(sentence: str, table_value: Dict[str, Any], viewed: set, query_log: List[Dict[str, Any]]) -> bool:
    """An absence sentence is exempt ONLY if: the table is not truncated; it contains no broad word
    (capability families, intent words like malicious/injection/persistence, "APIs for ..."); and it
    has a narrow shape whose captured VALUE is a query whose matches were all viewed (incl. zero
    matches), or whose captured DLL had all its returned entries viewed. Everything else stays flagged."""
    if table_value["truncated"] or BROAD_RE.search(sentence):
        return False
    seen: Dict[str, Dict[str, Any]] = {}
    for q in query_log:
        rec = seen.setdefault(q["value"].lower(), {"total": q["total_matches"], "idx": set()})
        rec["idx"] |= set(q["indices"])
    m = NARROW_PREFIX_RE.search(sentence)
    if m and m.group(1).lower() in seen:
        rec = seen[m.group(1).lower()]
        if len(rec["idx"]) >= rec["total"]:
            return True
    d = NARROW_DLL_RE.search(sentence)
    if d:
        names = {x["dll"].lower(): x["dll"] for x in query.dll_summary(table_value)}
        name = names.get(d.group(1).lower())
        if name and set(query.dll_indices(table_value, name)) <= viewed:
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
