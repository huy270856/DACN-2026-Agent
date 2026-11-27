"""TASK 07B: read-only query service over COMMITTED `static.pe_imports_table` evidence.

Never runs an analyzer, never opens a file, never creates evidence. Inputs are typed and
bounded; matching is literal (case-insensitive equality / prefix), never regex or wildcard.
Binding (case, revision, target SHA, value SHA) is filled by trusted code from the state.
Blocks of the same DLL (imports + delay_imports) are MERGED for DLL queries and coverage.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

from d0.validate import digest

from .imports_table_tool import FACET

PAGE_SIZE = 16
PREFIX_CHARS = re.compile(r"[A-Za-z0-9_?@$]{3,64}")  # input validation only, not user-supplied regex
BY = ("DLL", "SYMBOL_PREFIX")


class QueryError(ValueError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def table_evidence(state: Dict[str, Any]) -> Dict[str, Any]:
    ok = [e for e in state.get("evidence", []) if e.get("facet") == FACET and e.get("status") == "SUCCESS"]
    if not ok:
        raise QueryError("QUERY_NO_COMMITTED_TABLE", "no committed imports table")
    ev = ok[-1]
    if not ev.get("tool_run_id") or (ev.get("value") or {}).get("schema_version") != "pe-imports-table-output-v1":
        raise QueryError("QUERY_NO_COMMITTED_TABLE", "evidence is not a committed analyzer table")
    target = state["target_ref"]["verified_digest"]["value"]
    if ev["value"]["target_sha256"] != target:
        raise QueryError("QUERY_TARGET_MISMATCH", "table bound to a different target")
    return ev


def binding(state: Dict[str, Any], ev: Dict[str, Any]) -> Dict[str, Any]:
    return {"case_id": state["case_id"], "case_revision": state["revision"],
            "target_sha256": state["target_ref"]["verified_digest"]["value"],
            "evidence_id": ev["evidence_id"], "value_sha256": digest(ev["value"]),
            "tool_run_id": ev["tool_run_id"]}


def check_binding(state: Dict[str, Any], expected: Optional[Dict[str, Any]]) -> None:
    """Reject a stale or foreign binding (e.g. case/revision/SHA changed since it was issued)."""
    if expected is None:
        return
    now = binding(state, table_evidence(state))
    for k in ("case_id", "case_revision", "target_sha256", "evidence_id", "value_sha256"):
        if expected.get(k) != now[k]:
            raise QueryError("QUERY_BINDING_MISMATCH", k)


def entry_view(value: Dict[str, Any], index: int) -> Dict[str, Any]:
    lib_idx, symbol, ordinal, delay, resolved = value["entries"][index]
    return {"index": index, "library": value["libraries"][lib_idx]["name"], "symbol": symbol,
            "ordinal": ordinal, "resolved_symbol": resolved, "delay": delay}


def literal(view: Dict[str, Any]) -> str:
    return view["library"] + "!" + (view["symbol"] if view["symbol"] is not None else "#" + str(view["ordinal"]))


def dll_summary(value: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-DLL totals (blocks merged case-insensitively), in first-appearance order."""
    out: Dict[str, Dict[str, Any]] = {}
    for lib in value["libraries"]:
        key = lib["name"].lower()
        d = out.setdefault(key, {"dll": lib["name"], "declared_count": 0, "returned_count": 0, "blocks": 0,
                                 "has_delay_block": False})
        d["declared_count"] += lib["declared_count"]
        d["returned_count"] += lib["returned_count"]
        d["blocks"] += 1
        d["has_delay_block"] |= lib["delay"]
    return list(out.values())


def dll_indices(value: Dict[str, Any], dll: str) -> List[int]:
    key = dll.lower()
    blocks = {i for i, lib in enumerate(value["libraries"]) if lib["name"].lower() == key}
    return [i for i, e in enumerate(value["entries"]) if e[0] in blocks]


def _wrap(state, ev, **body):
    return {**binding(state, ev), **body, "trust_level": "UNTRUSTED_CONTENT", "new_evidence_created": False}


def list_import_index(state: Dict[str, Any]) -> Dict[str, Any]:
    ev = table_evidence(state)
    v = ev["value"]
    return _wrap(state, ev, kind="IMPORT_INDEX", total_entries=v["total_entries"],
                 returned_entries=v["returned_entries"], truncated=v["truncated"],
                 truncation_reason=v["truncation_reason"], dlls=dll_summary(v))


def _page(n: int, page: Any):
    if type(page) is not int or page < 0:
        raise QueryError("QUERY_BAD_PAGE", "page must be a non-negative integer")
    start = page * PAGE_SIZE
    if n and start >= n:
        raise QueryError("QUERY_PAGE_OUT_OF_RANGE", f"page {page} beyond {n} matches")
    nxt = page + 1 if start + PAGE_SIZE < n else None
    return start, nxt


def query_imports(state: Dict[str, Any], by: Any, value: Any, page: Any = 0,
                  expected_binding: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    check_binding(state, expected_binding)
    ev = table_evidence(state)
    v = ev["value"]
    if by not in BY:
        raise QueryError("QUERY_BAD_BY", "by must be DLL or SYMBOL_PREFIX")
    if not isinstance(value, str):
        raise QueryError("QUERY_BAD_VALUE", "value must be a string")
    if by == "DLL":
        names = {lib["name"].lower() for lib in v["libraries"]}
        if not 1 <= len(value) <= 128 or value.lower() not in names:
            raise QueryError("QUERY_UNKNOWN_DLL", "value must equal a DLL name from the import index")
        matches = dll_indices(v, value)
    else:
        if not PREFIX_CHARS.fullmatch(value):
            raise QueryError("QUERY_BAD_PREFIX", "prefix must be 3-64 chars of [A-Za-z0-9_?@$]")
        p = value.lower()
        matches = [i for i, e in enumerate(v["entries"])
                   if (e[1] is not None and e[1].lower().startswith(p))
                   or (e[4] is not None and e[4].lower().startswith(p))]
    start, nxt = _page(len(matches), page)
    return _wrap(state, ev, kind="IMPORT_QUERY", by=by, value=value, page=page, total_matches=len(matches),
                 next_page=nxt, entries=[entry_view(v, i) for i in matches[start:start + PAGE_SIZE]],
                 table_truncated=v["truncated"])


def read_table(state: Dict[str, Any], offset: Any, expected_binding: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """V4_NOQ ablation only: 16 entries by offset over the full table (no index, no query)."""
    check_binding(state, expected_binding)
    ev = table_evidence(state)
    v = ev["value"]
    n = len(v["entries"])
    if type(offset) is not int or offset < 0 or offset % PAGE_SIZE or (n and offset >= n):
        raise QueryError("READ_BAD_OFFSET", "offset must be a multiple of 16 within the table")
    return _wrap(state, ev, kind="TABLE_READ", offset=offset, returned_entries=n, total_entries=v["total_entries"],
                 next_offset=offset + PAGE_SIZE if offset + PAGE_SIZE < n else None,
                 entries=[entry_view(v, i) for i in range(offset, min(n, offset + PAGE_SIZE))],
                 table_truncated=v["truncated"])


def coverage(value: Dict[str, Any], viewed: set) -> List[Dict[str, Any]]:
    """Trusted per-DLL coverage (merged blocks): how many returned entries have been shown."""
    out = []
    for d in dll_summary(value):
        idx = dll_indices(value, d["dll"])
        out.append({"dll": d["dll"], "viewed": sum(i in viewed for i in idx), "count": d["declared_count"],
                    "returned": len(idx)})
    return out


def snapshot(obj):
    return copy.deepcopy(obj)
