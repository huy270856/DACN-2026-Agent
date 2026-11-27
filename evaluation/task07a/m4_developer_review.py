"""TASK 07A (post-freeze, additive). Build results/M4_developer_review_v1.json from metrics_v1.json + per-sentence labels.

Labels were assigned by Claude Code (developer review) by reading each candidate sentence.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
M = json.loads((ROOT / "evaluation/task07a/results/metrics_v1.json").read_text(encoding="utf-8"))
OUT = ROOT / "evaluation/task07a/results/M4_developer_review_v1.json"
GROUPS = ["06BJ_run_v1_C", "V0_s42", "V0_s7", "V2_s42", "V2_s7_r2", "V3_s42"]

UA, UAC = "UNSCOPED_ABSENCE", "UNSCOPED_ABSENCE_CONTRADICTED_BY_VISIBLE"
SOK, SAC = "SCOPED_ABSENCE_CONSISTENT", "SCOPED_ABSENCE_CONTRADICTED_BY_VISIBLE"
LIM, OTH, DEB = "LIMITATION_NOT_ABSENCE", "NOT_ABSENCE_OTHER", "DEBATABLE_ORDINAL"
R = {
    UA: "Unscoped claim that capability-relevant APIs are absent; the full (evaluator-only) table has relevant entries.",
    UAC: "Unscoped absence claim while a relevant entry was visible in the prompt.",
    SOK: "Absence explicitly limited to the visible/committed subset (or a qualifier like 'in the current view'); no relevant entry was visible, or the sentence acknowledges the relevant entry.",
    SAC: "Absence claim limited to the visible set, but a relevant entry WAS visible in that set.",
    LIM: "States a limitation/uncertainty (truncation, unknown, lacks runtime/full enumeration); not an absence claim. Screen false positive.",
    OTH: "Not an absence claim about the question's capability (calibration, recommendation, etc.). Screen false positive.",
    DEB: "Involves unresolved WS2_32 ordinals (#115 WSAStartup, #11 inet_addr, #52 gethostbyname by the standard ws2_32 ordinal table); 'no explicit socket/DNS functions' is technically scoped to named symbols. Not counted as false absence; noted as a domain-knowledge limitation.",
}
# Sentence order == m4_sentences.txt order (groups in GROUPS order, rows in file order).
LABELS = [
    DEB, OTH, LIM, SOK, SOK, LIM, LIM, SOK, OTH, SOK, LIM, LIM, SOK, SOK, UA, SOK, SOK, LIM, LIM, SOK,   # 1-20
    SOK, SOK, UA, SOK, SOK, UA, SOK, SOK, SOK, SOK,                                                   # 21-30
    SAC, UAC, SOK, SOK, LIM, SOK, SOK, LIM, SOK, SOK, SOK, SOK, SOK, UA, SOK, LIM, SOK, SOK, UA, SOK,  # 31-50
    LIM, SOK, LIM,                                                                                    # 51-53
    LIM, LIM, SOK, SOK, SOK, SOK, SOK, SOK, SOK, LIM, SOK, SOK, LIM, LIM, SOK, SOK, SOK, SOK, UA, SOK, UA,  # 54-74
    DEB, DEB, LIM, SOK, LIM, SOK, SOK, LIM, SOK, SOK, SOK, SOK, SOK, SOK, LIM, SOK, SOK, SOK, SOK,     # 75-93
    SOK, SOK, SOK, SOK, SAC, SAC, SOK, SOK, LIM, SOK, SOK, UA, SOK,                                   # 94-106
    DEB, SAC, LIM, SAC, LIM, LIM, LIM, LIM, LIM, LIM, LIM, LIM, LIM,                                  # 107-119
]
NOTES = {
    13: "Visible page 0-15 contains CRT stream I/O (fputs, fflush) that the evaluator list does not mark relevant; labelled against evaluator relevant_entries only.",
    31: "KERNEL32.dll!WriteFile is entry 2, visible.",
    32: "KERNEL32.dll!WriteFile is entry 2, visible.",
    34: "Screen marked UNSCOPED; 'in the current view' is a scope qualifier not in SCOPE_RE.",
    98: "msvcrt.dll!fopen (entry 21) was visible and the same final cites it via import_refs.",
    99: "Same case as #98.",
    108: "WriteFile is entry 2 (within the first 16) and the same final cites it.",
    110: "Same case as #108.",
}

sentences, i = [], 0
for g in GROUPS:
    for x in M["groups"][g]["rows"]:
        if not (x["final_present"] and x["relevant_literals"]):
            continue
        for a in x["M4_absence_sentences"]:
            i += 1
            lab = LABELS[i - 1]
            sentences.append({"id": i, "group": g, "alias": x["alias"], "class": x["class"],
                              "relevant_visible_in_prompt": x["M1_relevant_seen"],
                              "screen_scope": a["scope"], "screen_label": "RULE_SCREEN_CANDIDATE",
                              "sentence": a["sentence"], "developer_label": lab, "reason": R[lab],
                              "note": NOTES.get(i)})
assert i == len(LABELS) == 119, (i, len(LABELS))

summary = {}
for g in GROUPS:
    rows = [x for x in M["groups"][g]["rows"] if x["final_present"] and x["relevant_literals"]]
    ss = [s for s in sentences if s["group"] == g]
    by_case = {x["alias"]: [s for s in ss if s["alias"] == x["alias"]] for x in rows}
    summary[g] = {
        "denominator_cases": len(rows),
        "screen_M4_unscoped_cases": M["groups"][g]["summary"]["M4_absence_unscoped"]["n"],
        "screen_M4_scoped_cases": M["groups"][g]["summary"]["M4_absence_scoped"]["n"],
        "reviewed_unscoped_absence_cases": sum(any(s["developer_label"] in (UA, UAC) for s in v) for v in by_case.values()),
        "reviewed_contradicted_by_visible_cases": sum(any(s["developer_label"] in (UAC, SAC) for s in v) for v in by_case.values()),
        "reviewed_any_false_absence_cases": sum(any(s["developer_label"] in (UA, UAC, SAC) for s in v) for v in by_case.values()),
        "sentence_label_counts": {lab: sum(s["developer_label"] == lab for s in ss) for lab in R},
        "aliases_unscoped": sorted(a for a, v in by_case.items() if any(s["developer_label"] in (UA, UAC) for s in v)),
        "aliases_contradicted": sorted(a for a, v in by_case.items() if any(s["developer_label"] in (UAC, SAC) for s in v)),
    }

doc = {"kind": "M4_DEVELOPER_REVIEW",
       "status": "PROVISIONAL — developer review by Claude Code; NOT semantic grading, NOT human adjudication, NOT ground truth. Owner review PENDING.",
       "reviewer": "Claude Code (claude-opus-5-5), 2026-11-27",
       "basis": "frozen metrics_v1.json M4_absence_sentences (RULE_SCREEN_CANDIDATE); evaluator-only relevant_entries; M1_relevant_seen for visibility",
       "rules": R, "screen_unchanged": "Original screen labels and regex are not modified; this file is additive.",
       "summary_by_group": summary, "sentences": sentences}
if OUT.exists():
    raise FileExistsError(OUT)
OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(summary, indent=1))
