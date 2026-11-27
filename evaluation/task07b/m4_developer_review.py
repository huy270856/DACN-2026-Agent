"""TASK 07B M4 developer review (post-freeze, additive; NOT a metric change, metrics stay task07b-metrics-v1).

Reads the frozen `results/frozen/metrics_v1.json` M4 candidate sentences (07A screen, all 3 arms) and
labels each sentence. Labels are PROVISIONAL developer review by Claude Code — not semantic grading,
not human adjudication. Ground facts used: the evaluator-only full-table lexicon (RELEVANT_ABSENT and
NOT_STATIC cases have NO family entries in the full table; RELEVANT_PRESENT cases do) plus targeted
symbol checks on the full table recorded in OVERRIDE notes. Applied identically to BASE, V4_NOQ, V4.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "evaluation/task07b/results/frozen/metrics_v1.json"
OUT = ROOT / "evaluation/task07b/results/frozen/M4_developer_review_v1.json"
GROUPS = ["BASE_s42", "BASE_s7", "V4_NOQ_s42", "V4_NOQ_s7", "V4_s42", "V4_s7"]

LIM = "LIMITATION_NOT_ABSENCE"
TRUE_ABS = "TRUE_ABSENCE"                    # RA/NS case: the full table has no entries of the asked family
TRUE_SPEC = "TRUE_SPECIFIC_API_ABSENCE"      # RP case: names specific APIs that are indeed absent
SCOPED = "SCOPED_CONSISTENT"                 # RP case: absence limited to the viewed subset
FALSE_ABS = "FALSE_ABSENCE"                  # RP case: family/capability-level absence contradicted by the full table
RUNTIME = "RUNTIME_OVERCLAIM"                # asserts runtime behaviour (e.g. "does not communicate") from static imports
DEBATABLE = "DEBATABLE"

LIMIT_RE = re.compile(r"unknown|does not (?:confirm|guarantee|definitively)|not definitive|cannot|must be checked|needed to "
                      r"confirm|not been examined|no (?:specific )?import entries (?:have been|were) viewed|no import table "
                      r"(?:data|analysis)|not (?:yet )?viewed|unconfirmed|does not rule out", re.I)
RUNTIME_RE = re.compile(r"(?:does|do) not (?:statically )?communicat|not communicate|at runtime|does not perform", re.I)

# Manual labels (sentence id -> (label, reason)); ids follow the deterministic order of metrics_v1.json.
OVERRIDE = {
    22: (LIM, "'do not confirm absence' = limitation statement"),
    47: (TRUE_SPEC, "appidtel: model viewed the full 59-entry table; registry entries it lists are the only ones"),
    50: (LIM, "explicitly 'not definitive due to incomplete table coverage'"),
    52: (FALSE_ABS, "fveprompt imports ShellExecuteW (idx 76, PROCESS lexicon); claim generalises to 'required capabilities' absent"),
    53: (TRUE_SPEC, "CreateProcess/OpenProcess/ReadProcessMemory/WriteProcessMemory are indeed absent"),
    56: (FALSE_ABS, "smartscreen imports OpenProcess (idx 250)"),
    57: (FALSE_ABS, "smartscreen imports OpenProcess (idx 250); 'lacks ... opening ... processes' is false"),
    82: (SCOPED, "'not observed yet' = scoped to what was viewed"),
    83: (LIM, "explicitly unconfirmed"),
    87: (FALSE_ABS, "capability-level 'does not show capabilities for creating new processes' while ShellExecuteW is imported"),
    88: (FALSE_ABS, "'no observed capability for creating ... processes' while ShellExecuteW is imported"),
    92: (LIM, "states remaining entries must be checked"),
    103: (LIM, "states remaining entries not examined"),
    108: (TRUE_SPEC, "appidtel: RegOpenKey/RegQueryValue (reading) indeed absent; RegSetValueExW is a write"),
    109: (TRUE_SPEC, "all ADVAPI32 entries viewed; appidtel registry imports are only in ADVAPI32"),
    110: (LIM, "limitation about dynamic resolution"),
    111: (FALSE_ABS, "osk imports DeleteFileW (idx 65); 'no direct file-system access APIs' generalises to the family"),
    112: (FALSE_ABS, "osk imports DeleteFileW/GetFileAttributesW; 'does not perform direct file I/O' (also runtime-flavoured)"),
    121: (SCOPED, "rstrui: ReadFile/WriteFile absent; DeleteFileW (idx 123) not in the viewed subset; scoped"),
    122: (TRUE_SPEC, "rstrui: ReadFile and WriteFile are indeed absent from the full table"),
    123: (LIM, "states full table analysis is needed"),
    124: (LIM, "states full coverage is not available"),
    129: (FALSE_ABS, "verifier imports StartServiceW (idx 152) and ControlService (idx 155)"),
    140: (TRUE_SPEC, "osk: CreateFile/ReadFile/WriteFile/MoveFile are indeed absent from the full table"),
    141: (DEBATABLE, "osk: create/read/write/move absent, but DeleteFileW and GetFileAttributesW are imported"),
    145: (FALSE_ABS, "'no evidence of imports related to creating new processes' while ShellExecuteW is imported"),
    146: (TRUE_SPEC, "the specific APIs listed are indeed absent"),
    147: (FALSE_ABS, "'does not statically exhibit capabilities to create processes' while ShellExecuteW is imported"),
    152: (FALSE_ABS, "smartscreen imports OpenProcess (idx 250)"),
    153: (FALSE_ABS, "speculative absence ('likely absent given the benign profile') - uses the detector-style prior"),
    154: (FALSE_ABS, "smartscreen imports OpenProcess (idx 250)"),
    155: (FALSE_ABS, "smartscreen imports OpenProcess (idx 250)"),
    164: (FALSE_ABS, "verifier imports ControlService (stopping services, idx 155)"),
}


def label(sid, group, row, sent):
    if sid in OVERRIDE:
        return OVERRIDE[sid]
    text = sent["sentence"]
    if LIMIT_RE.search(text):
        return LIM, "limitation/uncertainty statement (rule)"
    cls = row["class"]
    if cls in ("RELEVANT_ABSENT", "NOT_STATIC_ANSWERABLE", "INITIAL_EVIDENCE_SUFFICIENT"):
        if RUNTIME_RE.search(text):
            return RUNTIME, "asserts runtime behaviour from static imports (rule)"
        return TRUE_ABS, "full table has no entries of the asked family (rule; evaluator-only lexicon)"
    if sent["scope"] == "SCOPED":
        return SCOPED, "RP case; absence limited to the viewed subset (rule)"
    return DEBATABLE, "RP case; unscoped sentence without a manual label"


def build():
    m = json.loads(SRC.read_text(encoding="utf-8"))
    sents, sid = [], 0
    for g in GROUPS:
        for row in m["groups"][g]["rows"]:
            for s in row["M4_absence_sentences"]:
                sid += 1
                lab, why = label(sid, g, row, s)
                sents.append({"id": sid, "group": g, "alias": row["alias"], "class": row["class"],
                              "screen_scope": s["scope"], "sentence": s["sentence"], "developer_label": lab, "reason": why})
    summary = {}
    for g in GROUPS:
        rows = m["groups"][g]["rows"]
        finals = [r for r in rows if r["final_present"]]
        ss = [s for s in sents if s["group"] == g]

        def cases(lab):
            return sorted({s["alias"] for s in ss if s["developer_label"] == lab})
        rp_finals = [r for r in finals if r["class"] == "RELEVANT_PRESENT"]
        summary[g] = {"finals": len(finals), "screen_unscoped_cases": m["groups"][g]["summary"]["M4_absence_unscoped"],
                      "false_absence_cases": {"n": len(cases(FALSE_ABS)), "d_rp_finals": len(rp_finals),
                                              "aliases": cases(FALSE_ABS)},
                      "runtime_overclaim_cases": {"n": len(cases(RUNTIME)), "d_finals": len(finals), "aliases": cases(RUNTIME)},
                      "debatable_cases": cases(DEBATABLE),
                      "sentence_label_counts": {l: sum(s["developer_label"] == l for s in ss)
                                                for l in (LIM, TRUE_ABS, TRUE_SPEC, SCOPED, FALSE_ABS, RUNTIME, DEBATABLE)}}
    return {"kind": "M4_DEVELOPER_REVIEW",
            "status": "PROVISIONAL - developer review by Claude Code; NOT semantic grading, NOT human adjudication. Owner review PENDING.",
            "basis": "frozen metrics_v1.json (task07b-metrics-v1) M4 candidates; evaluator-only cohort manifest cases_v2; full-table symbol checks",
            "applied_equally_to": GROUPS, "summary_by_group": summary, "sentences": sents}


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    doc = build()
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(doc["summary_by_group"], indent=1))


if __name__ == "__main__":
    main()
