"""TASK 07C-R: offline deterministic trusted re-render of frozen 07B V4 (investigation-v4.0) traces.

DEV_DIAGNOSTIC, deterministic replay (no Qwen). Reads 07B traces read-only; writes a NEW directory.
Each model-written sentence is quoted verbatim (model-authored) or moved to "Nội dung bị loại" when it matches
the 07C NEGATION_RE / ABSENCE_RE. Coverage comes from the trusted trace. Nothing is created or rewritten.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from evaluation.task07a.metrics import SENT_SPLIT
from evaluation.task07a.variants import load_relevant, parse_literal
from investigation_v4.verifier import ABSENCE_RE, NEGATION_RE

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "evaluation/task07b/results/frozen"
MANIFEST = ROOT / "evaluation/task07b/results/cohort/cases_v2_EVALUATOR_ONLY.json"
OUT = ROOT / "evaluation/task07c/results/rerender_07b"
VERSION = "task07c-r-rerender-v1"


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in SENT_SPLIT.split(text or "") if s.strip()]


def _drop_reason(s: str):
    if NEGATION_RE.search(s):
        return "câu dạng phủ định/vắng mặt (NEGATION_RE)"
    if ABSENCE_RE.search(s):
        return "câu khẳng định vắng mặt (ABSENCE_RE)"
    return None


def split_final(final: Dict[str, Any]) -> Dict[str, Any]:
    kept, dropped = [], []
    for s in _sentences(final.get("answer", "")):
        (dropped if _drop_reason(s) else kept).append({"where": "answer", "sentence": s, "reason": _drop_reason(s)})
    for i, f in enumerate(final.get("findings", [])):
        for s in _sentences(f.get("text", "")):
            item = {"where": f"findings[{i}]", "kind": f.get("kind"), "sentence": s, "sources": f.get("sources", []),
                    "reason": _drop_reason(s)}
            (dropped if item["reason"] else kept).append(item)
    return {"kept": kept, "dropped": dropped}


def render(r: Dict[str, Any], parts: Dict[str, Any]) -> str:
    tm = r.get("trusted_metadata") or {}
    lit = {s["handle"]: s.get("literal") or s.get("evidence_id") for s in tm.get("resolved_sources", [])}
    out = ["# Báo cáo dựng lại tất định (TASK 07C-R, từ trace frozen 07B investigation-v4.0)", "",
           f"**Câu hỏi:** {r.get('question')}", "",
           f"**Trạng thái trả lời (model chọn):** {(r.get('final') or {}).get('answer_status')}", "",
           "## Nội dung được giữ (nguyên văn do model viết)"]
    if not parts["kept"]:
        out.append("- (không còn câu nào)")
    for k in parts["kept"]:
        src = ", ".join(f"{h} = {lit.get(h, h)}" for h in k.get("sources", []))
        tag = f"[{k['kind']}] " if k.get("kind") else ""
        out.append(f"- {tag}\"{k['sentence']}\"" + (f" — nguồn: {src}" if src else "") + " *(model-authored)*")
    out += ["", "## Nội dung bị loại (không phải dữ kiện)"]
    out += [f"- \"{d['sentence']}\" — lý do: {d['reason']}" for d in parts["dropped"]] or ["- (không có)"]
    out += ["", "## Phạm vi đã xem (trusted trace)"]
    viewed = tm.get("viewed_literals", {})
    out.append(f"- Đã hiển thị cho model {len(viewed)} entry import; mọi entry khác: CHƯA xem.")
    for t in r.get("turns", []):
        q = t.get("query_result")
        if q and t.get("action") == "QUERY_IMPORTS":
            out.append(f"- Query {q.get('by')} `{q.get('value')}` trang {q.get('page')}: {len(q.get('entries', []))}/"
                       f"{q.get('total_matches')} match")
    out += ["", "_Import khai báo là capability tĩnh, không phải hành vi runtime._"]
    return "\n".join(out)


def run_row(r: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
    keys = {parse_literal(x) for x in load_relevant(case.get("reference_EVALUATOR_ONLY") or {})}
    final = r.get("final")
    if final is None:
        return {"alias": r["alias"], "class": case["accessibility_class"], "final": False, "m1b_render": False,
                "m1b_trace": False, "dropped": 0, "kept_presence": 0, "m4_render_unscoped": False}
    parts = split_final(final)
    kept_findings = {k["where"] for k in parts["kept"] if k["where"].startswith("findings[")}
    tm = r.get("trusted_metadata") or {}

    def key(l):
        lib, _, s = l.partition("!")
        return (lib.lower(), s)
    cited_all = {key(s["literal"]) for s in tm.get("resolved_sources", []) if s.get("literal")}
    cited_kept = {key(s["literal"]) for s in tm.get("resolved_sources", []) if s.get("literal")
                  and s.get("cited_in") in kept_findings}
    presence = [k for k in parts["kept"] if k.get("kind") != "LIMITATION"]
    return {"alias": r["alias"], "class": case["accessibility_class"], "final": True,
            "m1b_trace": bool(keys & cited_all), "m1b_render": bool(keys & cited_kept),
            "dropped": len(parts["dropped"]), "kept_presence": len(presence),
            "m4_render_unscoped": any(ABSENCE_RE.search(k["sentence"]) for k in parts["kept"]),
            "parts": parts, "report": render(r, parts)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {a.out}")
    man = {c["alias"]: c for c in json.loads(MANIFEST.read_text(encoding="utf-8"))["cases"]}
    summary = {"kind": "DEV_DIAGNOSTIC", "track": "DETERMINISTIC_REPLAY_OFFLINE", "version": VERSION,
               "source": "evaluation/task07b/results/frozen/V4_s{42,7} (read-only)", "groups": {}}
    a.out.mkdir(parents=True)
    for g in ("V4_s42", "V4_s7"):
        rows = []
        (a.out / g).mkdir()
        for alias in sorted(man):
            r = json.loads((SRC / g / f"{alias}_V4.json").read_text(encoding="utf-8"))
            row = run_row(r, man[alias])
            if row.get("report"):
                (a.out / g / f"{alias}_report.md").write_text(row["report"], encoding="utf-8")
            rows.append({k: v for k, v in row.items() if k != "report"})
        rp = [x for x in rows if x["class"] == "RELEVANT_PRESENT"]
        summary["groups"][g] = {
            "M1b_render": {"n": sum(x["m1b_render"] for x in rp), "d": len(rp)},
            "M1b_trace": {"n": sum(x["m1b_trace"] for x in rp), "d": len(rp)},
            "M4_render_unscoped": {"n": sum(x["m4_render_unscoped"] for x in rows), "d": len(rows),
                                   "note": "satisfied by construction (ABSENCE_RE sentences are dropped)"},
            "runs_with_presence_sentence": {"n": sum(x["kept_presence"] > 0 for x in rows), "d": len(rows)},
            "dropped_per_run": [x["dropped"] for x in rows], "rows": rows}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({g: {k: v for k, v in s.items() if k not in ("rows",)} for g, s in summary["groups"].items()},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
