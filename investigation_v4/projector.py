"""TASK 07B projector v4: compact, question-centred facts with short trusted handles.

* Non-import evidence gets handles E1..En; import entries get I<index> (declaration index).
  Trusted code keeps the handle -> real-ID map and records it in the trace.
* The detector output is `detector_context`: NOT evidence, has NO handle, cannot be cited.
* Provenance noise (model SHA, extractor, full_detail_ref, repeated limitations, unknowns with
  paths/inodes, raw omitted IDs) is dropped and replaced by one count line.
* Nothing is silently cut: exceeding the character budget raises V4_CONTEXT_BUDGET.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import query
from .imports_table_tool import FACET as TABLE_FACET

PREDICTION_FACET = "static.pe_malware_prediction"
COMPACT_FACETS = {"pe_header": ("pe_kind", "architecture", "is_dll", "executable_image_flag", "classification"),
                  "format": ("format", "pe_kind", "architecture", "is_dll", "structural_valid")}
DETECTOR_NOTE = ("Raw score is NOT a probability. This is context, not evidence; it cannot be cited "
                 "in sources or basis_sources.")


class HandleMap:
    """Run-scoped, stable handle assignment. E-handles in first-seen order; I-handles = index."""

    def __init__(self):
        self.e: Dict[str, str] = {}

    def e_handle(self, evidence_id: str) -> str:
        if evidence_id not in self.e:
            self.e[evidence_id] = f"E{len(self.e) + 1}"
        return self.e[evidence_id]

    @staticmethod
    def i_handle(index: int) -> str:
        return f"I{index}"

    def resolve(self, handle: str) -> Optional[Dict[str, Any]]:
        if handle.startswith("E"):
            for eid, h in self.e.items():
                if h == handle:
                    return {"kind": "EVIDENCE", "evidence_id": eid}
            return None
        if handle.startswith("I") and handle[1:].isdigit() and str(int(handle[1:])) == handle[1:]:
            return {"kind": "IMPORT_ENTRY", "index": int(handle[1:])}
        return None

    def to_trace(self) -> Dict[str, str]:
        return {h: eid for eid, h in self.e.items()}


def detector_context(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pred = next((e for e in reversed(state.get("evidence", []))
                 if e.get("facet") == PREDICTION_FACET and e.get("status") == "SUCCESS"), None)
    if pred is None:
        return None
    v = pred["value"]
    return {"predicted_label": v.get("predicted_label"), "raw_score": v.get("raw_score"),
            "threshold": v.get("threshold"), "note": DETECTOR_NOTE}


def _compact(ev):
    keys = COMPACT_FACETS[ev["facet"]]
    return {k: ev["value"].get(k) for k in keys if isinstance(ev.get("value"), dict) and k in ev["value"]}


def _entry(handle: str, x: Dict[str, Any]) -> Dict[str, Any]:
    """Compact view: symbol XOR ordinal; resolved_symbol/delay only when present (no null noise)."""
    out = {"handle": handle, "dll": x["library"]}
    if x["symbol"] is not None:
        out["symbol"] = x["symbol"]
    else:
        out["ordinal"] = x["ordinal"]
        if x["resolved_symbol"] is not None:
            out["resolved_symbol"] = x["resolved_symbol"]
    if x["delay"]:
        out["delay"] = True
    return out


def build(state: Dict[str, Any], *, question: str, handles: HandleMap, viewed: Dict[int, Dict[str, Any]],
          index_listed: bool, queries_run: List[Dict[str, Any]], queries_left: int, turns_left: int,
          available_actions: List[str], retrieval_mode: str, max_context_chars: int,
          last_result: Optional[Dict[str, Any]] = None, repair_error: Optional[str] = None) -> Dict[str, Any]:
    evidence, omitted = [], 0
    table = None
    for ev in state.get("evidence", []):
        f = ev.get("facet")
        if f in COMPACT_FACETS and ev.get("status") == "SUCCESS":
            evidence.append({"handle": handles.e_handle(ev["evidence_id"]), "kind": f, "value": _compact(ev)})
        elif f == TABLE_FACET and ev.get("status") == "SUCCESS":
            table = ev
        elif f != PREDICTION_FACET:
            omitted += 1
    facts: Dict[str, Any] = {"contract": "investigation-v4.0", "question": question,
                             "detector_context": detector_context(state)}
    cov: Dict[str, Any] = {"analyzer_run": table is not None, "queries_left": queries_left, "turns_left": turns_left}
    if table is not None:
        v = table["value"]
        evidence.append({"handle": handles.e_handle(table["evidence_id"]), "kind": "imports_table",
                         "value": {"total_entries": v["total_entries"], "returned_entries": v["returned_entries"],
                                   "truncated": v["truncated"], "dll_count": len(query.dll_summary(v))}})
        seen = set(viewed)
        if retrieval_mode == "QUERY":
            if index_listed:
                facts["import_index"] = [{"dll": d["dll"], "count": d["declared_count"]} for d in query.dll_summary(v)]
            cov["dlls_viewed"] = [c for c in query.coverage(v, seen) if c["viewed"]] if seen else []
            cov["queries_run"] = [{k: q[k] for k in ("by", "value", "page", "total_matches")} for q in queries_run]
        else:
            cov["viewed_entries"] = len(seen)
            cov["table_entries"] = v["returned_entries"]
            cov["reads_run"] = [q["offset"] for q in queries_run]
    facts["evidence"] = evidence
    facts["omitted"] = f"{omitted} collector facets omitted as not relevant" if omitted else None
    facts["viewed_imports"] = [_entry(handles.i_handle(i), x) for i, x in sorted(viewed.items())]
    facts["coverage"] = cov
    facts["last_result"] = last_result
    facts["available_actions"] = available_actions
    facts["repair_feedback"] = ({"error": repair_error[:600],
                                 "instruction": "One bounded format correction. Use only these same facts."}
                                if repair_error else None)
    text = json.dumps(facts, ensure_ascii=True)
    if len(text) > max_context_chars:
        raise ValueError(f"V4_CONTEXT_BUDGET: {len(text)} > {max_context_chars}")
    return {"user": "UNTRUSTED_CASE_DATA\n" + text + "\nEND_UNTRUSTED_CASE_DATA", "facts": facts,
            "table_evidence_id": table["evidence_id"] if table else None}
