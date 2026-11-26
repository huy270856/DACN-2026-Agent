"""Deterministic pipeline/cost metrics and an evaluator-side coverage diagnostic.

These are DETERMINISTIC facts read from frozen run artifacts - not semantic judgments.
The coverage diagnostic uses a small API-family lexicon to find committed import entries
relevant to the fixed network/process question that the Agent never had visible. A lexicon
hit is a heuristic relevance flag, not evidence of malice and not a semantic grade.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List

IMPORTS_FACET = "static.pe_imports_detail"
NETWORK_LIBS = ("ws2_32.dll", "wsock32.dll", "wininet.dll", "winhttp.dll", "iphlpapi.dll",
                "dnsapi.dll", "urlmon.dll", "netapi32.dll", "mswsock.dll")
PROCESS_PREFIXES = ("createprocess", "openprocess", "terminateprocess", "virtualallocex",
                    "writeprocessmemory", "readprocessmemory", "createremotethread",
                    "shellexecute", "winexec", "ntcreateprocess", "ntopenprocess")
LEXICON_VERSION = "task06b-j-relevance-lexicon-v1"


def relevant(entry: Dict[str, Any]) -> str | None:
    lib = str(entry.get("library") or "").lower()
    sym = str(entry.get("symbol") or "").lower()
    if lib in NETWORK_LIBS:
        return "NETWORK_LIBRARY"
    if sym.startswith(PROCESS_PREFIXES):
        return "PROCESS_API"
    return None


def coverage_diagnostic(r: Dict[str, Any]) -> Dict[str, Any] | None:
    state = r.get("final_state") or {}
    committed = [e for e in state.get("evidence", []) if e.get("facet") == IMPORTS_FACET and e.get("status") == "SUCCESS"]
    if not committed:
        return None
    ev = committed[-1]
    entries = (ev.get("value") or {}).get("entries", [])
    turns = [t for t in r.get("turns", []) if t.get("context")]
    seen = set()
    for t in turns:
        for e in t["context"]["facts"].get("evidence", []):
            if e["evidence_id"] == ev["evidence_id"]:
                seen |= {x.get("entry_index") for x in (e.get("value") or {}).get("entries", [])}
    hits = [{"entry_index": i, "library": x.get("library"), "symbol": x.get("symbol"), "family": relevant(x)}
            for i, x in enumerate(entries) if relevant(x)]
    unseen = [h for h in hits if h["entry_index"] not in seen]
    value = ev.get("value") or {}
    return {"lexicon": LEXICON_VERSION, "evidence_id": ev["evidence_id"],
            "provider_total_entries": value.get("total_entries"), "committed_entries": len(entries),
            "ever_visible_entries": len(seen), "relevant_committed": len(hits),
            "relevant_never_visible": len(unseen), "relevant_never_visible_entries": unseen,
            "retrieval_reads": r.get("retrieval_attempts", 0),
            "provider_truncated": value.get("truncated")}


def run_metrics(r: Dict[str, Any]) -> Dict[str, Any]:
    if "turns" not in r:  # static template arm
        return {"arm_kind": "STATIC", "llm_calls": 0, "latency_s": r.get("latency_s")}
    ev = r.get("events", [])[r.get("agent_event_start", 0):]
    stages = [e.get("stage") for e in ev]
    d4 = [e["decision"]["outcome"] for e in ev if e.get("stage") == "D4" and "decision" in e]
    v = r.get("verification") or {}
    actions = [(t.get("proposal") or {}).get("action") for t in r["turns"]]
    return {"arm_kind": "AGENT", "status": r.get("status"), "final_present": r.get("final") is not None,
            "failure": r.get("failure"), "llm_calls": len(r["turns"]),
            "tool_proposed": "TOOL_CALL" in actions, "d4_outcomes": d4,
            "d9_commits": stages.count("D9_COMMITTED"), "retrieval_reads": r.get("retrieval_attempts", 0),
            "repairs": r.get("repair_attempts", 0), "no_tool_decision": "TOOL_CALL" not in actions,
            "structural_final_accepted": r.get("final") is not None,
            "rule_screen_flagged": bool(r.get("has_suspected_or_consistency_flags")),
            "clean_by_rule_screen": r.get("status") == "FINISHED",
            "grounding_flags": v.get("flags", []),
            "effective_action": (r.get("effective_recommendation") or {}).get("action"),
            "latency_s": r.get("latency_s"), "end_to_end_latency_s": r.get("end_to_end_latency_s"),
            "prompt_tokens": r.get("prompt_tokens"), "output_tokens": r.get("output_tokens"),
            "coverage": coverage_diagnostic(r)}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """All rows in the denominator; incomplete runs are counted, never dropped."""
    agent = [x for x in rows if x["arm_kind"] == "AGENT"]
    lat = [x["latency_s"] for x in agent if x.get("latency_s") is not None]
    n = len(agent)
    return {"n": n,
            "final_present": sum(x["final_present"] for x in agent),
            "rule_screen_flagged": sum(x["rule_screen_flagged"] for x in agent),
            "clean_by_rule_screen": sum(x["clean_by_rule_screen"] for x in agent),
            "incomplete": sum(not x["final_present"] for x in agent),
            "tool_proposed": sum(x["tool_proposed"] for x in agent),
            "d9_commits": sum(x["d9_commits"] for x in agent),
            "retrieval_reads": sum(x["retrieval_reads"] for x in agent),
            "llm_calls": sum(x["llm_calls"] for x in agent),
            "latency_mean_s": round(mean(lat), 2) if lat else None,
            "latency_median_s": round(median(lat), 2) if lat else None,
            "prompt_tokens": sum(x.get("prompt_tokens") or 0 for x in agent),
            "output_tokens": sum(x.get("output_tokens") or 0 for x in agent)}


def from_mapping(mapping_path: Path, spec_root: Path) -> Dict[str, Any]:
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    rows = []
    for m in mapping["items"]:
        if m["is_probe"]:
            continue
        r = json.loads((spec_root / m["source"]).read_text(encoding="utf-8"))
        rows.append(dict(run_metrics(r), item_id=m["item_id"], arm=m["arm"], variant=m.get("variant"),
                         sample_sha256=m["sample_sha256"]))
    return {"kind": "DETERMINISTIC_PIPELINE_METRICS_NOT_SEMANTIC", "rows": rows}


def main(argv=None):
    import argparse
    from collections import defaultdict
    ap = argparse.ArgumentParser(description="Deterministic pipeline metrics for a 06B-J package")
    ap.add_argument("--mapping", type=Path, required=True)
    ap.add_argument("--spec-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {a.out}")
    doc = from_mapping(a.mapping, a.spec_root)
    groups = defaultdict(list)
    for r in doc["rows"]:
        groups[r["variant"] or r["arm"]].append(r)
    doc["summary_by_group"] = {g: summarize(rows) for g, rows in groups.items()}
    a.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(doc["summary_by_group"], indent=2))


if __name__ == "__main__":
    main()
