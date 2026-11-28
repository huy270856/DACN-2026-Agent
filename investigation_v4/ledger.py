"""TASK 07C: deterministic coverage ledger (trusted; the model never writes it).

One entry per distinct executed request: Q<k> for each (by, value) QUERY_IMPORTS (pages merged)
and for LIST_IMPORT_INDEX. `exhausted` = every match of that request has been returned to the model.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def build(query_log: List[Dict[str, Any]], index_listed: bool,
          table_value: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if index_listed and table_value is not None:
        out.append({"id": None, "kind": "INDEX", "value": "*", "total_matches": None, "returned": None,
                    "exhausted": not table_value["truncated"]})
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for q in query_log:
        k = (q["by"], q["value"].lower())
        e = by_key.get(k)
        if e is None:
            e = {"id": None, "kind": q["by"], "value": q["value"], "total_matches": q["total_matches"], "_idx": set()}
            by_key[k] = e
            out.append(e)
        e["_idx"] |= set(q["indices"])
    for i, e in enumerate(out, 1):
        e["id"] = f"Q{i}"
        if e["kind"] != "INDEX":
            e["returned"] = len(e["_idx"])
            e["exhausted"] = e["returned"] >= e["total_matches"] and not (table_value or {}).get("truncated", False)
            e["indices"] = sorted(e.pop("_idx"))
    return out


def summary(entries: List[Dict[str, Any]]) -> str:
    if not entries:
        return "Covered: nothing (no index listed, no query run)."
    parts = []
    for e in entries:
        what = "import index" if e["kind"] == "INDEX" else f"{e['kind']} {e['value']}"
        state = "exhausted" if e["exhausted"] else f"NOT exhausted ({e['returned']}/{e['total_matches']} returned)"
        parts.append(f"{e['id']} {what} ({state})")
    return "Covered: " + "; ".join(parts) + ". Everything else in the import table: NOT covered."
