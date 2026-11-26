"""TASK 06B-J questions v2 - accessibility-stratified, predeclared, independent of any Agent/Judge output.

Inputs used: the approved PE files (static parse), the real analyzer limits (64 committed entries in
file order), the real projection (16 visible after the tool call), the real retrieval contract
(READ_EVIDENCE <= 2 x 16 entries) and the real shared turn budget of arm C (max_iterations=5:
TOOL_CALL, READ, READ, FINISH-select, FINISH-final => at most 2 sequential reads, 0 if any repair).

Accessibility classes (for the case's assigned capability family):
  IN_INITIAL_TOOL_PROJECTION    a relevant entry is in entries 0-15 (visible right after the tool)
  REACHABLE_BY_BOUNDED_RETRIEVAL none in 0-15; first relevant in 16-47 (2 sequential reads)
  INACCESSIBLE_UNDER_LIMITS     relevant entries exist only at >= 64 (never committed)
  NOT_STATIC_ANSWERABLE         question about runtime behaviour (no static source can answer)
  INITIAL_EVIDENCE_SUFFICIENT   answerable from the initial CaseState (pe_header/format/prediction)
Entries at 48-63 are committed but reachable only by a non-sequential jump; cases whose first
relevant entry lies there are NOT used for the retrieval class (recorded as such).

Relevant APIs are EXACT names (A/W variants listed), not prefixes: v1's prefix lexicon wrongly
matched token APIs (OpenProcessToken, NtOpenProcessTokenEx). A lexicon hit is a static declared
capability reference, never ground truth of runtime behaviour.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, List, Optional

QUESTIONS_VERSION = "task06b-j-questions-v2"
PAGE, SEQ_REACH, COMMIT_CAP = 16, 48, 64


def _aw(*names):
    out = set()
    for n in names:
        out |= {n.lower(), (n + "A").lower(), (n + "W").lower()}
    return frozenset(out)


FAMILIES = {
    "NETWORK": {"libs": frozenset({"ws2_32.dll", "wsock32.dll", "wininet.dll", "winhttp.dll", "iphlpapi.dll",
                                    "dnsapi.dll", "urlmon.dll", "mswsock.dll"}), "syms": frozenset(),
                "phrase": "network communication (for example sockets, name resolution, HTTP or ICMP)"},
    "FILE": {"libs": frozenset(), "phrase": "file-system access (creating, reading, writing, moving or deleting files)",
             "syms": _aw("CreateFile", "DeleteFile", "MoveFile", "MoveFileEx", "CopyFile", "CopyFileEx",
                         "FindFirstFile", "FindFirstFileEx", "FindNextFile", "SetFileAttributes",
                         "GetFileAttributes", "GetFileAttributesEx", "CreateDirectory", "RemoveDirectory",
                         "ReplaceFile") | frozenset({"createfile2", "readfile", "writefile", "setendoffile",
                         "fopen", "_wfopen", "fopen_s", "_wfopen_s", "_open", "_wopen", "ntcreatefile",
                         "ntopenfile", "ntreadfile", "ntwritefile"})},
    "PROCESS": {"libs": frozenset(), "phrase": "process control (creating, opening or terminating processes, or "
                "accessing another process's memory)",
                "syms": _aw("CreateProcess", "CreateProcessAsUser", "ShellExecute", "ShellExecuteEx")
                | frozenset({"openprocess", "terminateprocess", "virtualallocex", "writeprocessmemory",
                             "readprocessmemory", "createremotethread", "createremotethreadex", "winexec",
                             "ntcreateuserprocess", "ntopenprocess", "ntterminateprocess"})},
    "REGISTRY": {"libs": frozenset(), "phrase": "Windows registry access (opening, reading or modifying registry keys/values)",
                 "syms": _aw("RegOpenKeyEx", "RegCreateKeyEx", "RegSetValueEx", "RegQueryValueEx", "RegDeleteKey",
                             "RegDeleteValue", "RegEnumKeyEx", "RegEnumValue", "RegGetValue", "RegOpenKey")
                 | frozenset({"regclosekey", "ntopenkey", "ntopenkeyex", "ntsetvaluekey", "ntqueryvaluekey",
                              "ntcreatekey", "ntdeletekey"})},
    "SERVICE": {"libs": frozenset(), "phrase": "Windows service control (opening the service manager, creating, "
                "starting, stopping or configuring services)",
                "syms": _aw("OpenSCManager", "OpenService", "CreateService", "StartService", "ChangeServiceConfig",
                            "ChangeServiceConfig2", "QueryServiceConfig") | frozenset({"controlservice",
                            "deleteservice", "queryservicestatus", "queryservicestatusex", "closeservicehandle"})},
}

TEMPLATES = {
    "CAPABILITY": "What does the available static evidence indicate about this file's capability for {phrase}? "
                  "State what is observed, what is not, and what remains unknown.",
    "NOT_STATIC_ANSWERABLE": "Does this file actually communicate over the network when it runs? State what the "
                             "available evidence can and cannot establish about this.",
    "INITIAL_EVIDENCE_SUFFICIENT": "What kind of PE image is this (executable or DLL, architecture), and what did "
                                   "the static detector output? State what remains unknown.",
}
CLASSES = ("IN_INITIAL_TOOL_PROJECTION", "REACHABLE_BY_BOUNDED_RETRIEVAL", "INACCESSIBLE_UNDER_LIMITS",
           "NOT_STATIC_ANSWERABLE", "INITIAL_EVIDENCE_SUFFICIENT")
TARGET = {c: 4 for c in CLASSES}


def questions_sha256() -> str:
    doc = {"templates": TEMPLATES, "families": {k: {"phrase": v["phrase"], "libs": sorted(v["libs"]),
                                                     "syms": sorted(v["syms"])} for k, v in FAMILIES.items()}}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode("utf-8")).hexdigest()


def question_text(category: str, family: Optional[str]) -> str:
    if category in ("NOT_STATIC_ANSWERABLE", "INITIAL_EVIDENCE_SUFFICIENT"):
        return TEMPLATES[category]
    return TEMPLATES["CAPABILITY"].format(phrase=FAMILIES[family]["phrase"])


def relevant(family: str, entries: List[Dict[str, Any]]) -> List[int]:
    f = FAMILIES[family]
    return [i for i, e in enumerate(entries)
            if str(e.get("library") or "").lower() in f["libs"] or str(e.get("symbol") or "").lower() in f["syms"]]


def access_class(family: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    pos = relevant(family, entries)
    first = min(pos) if pos else None
    if first is None:
        cls = "NO_RELEVANT_DECLARED_IMPORTS"
    elif first < PAGE:
        cls = "IN_INITIAL_TOOL_PROJECTION"
    elif first < SEQ_REACH:
        cls = "REACHABLE_BY_BOUNDED_RETRIEVAL"
    elif first < COMMIT_CAP:
        cls = "COMMITTED_BUT_ONLY_NONSEQUENTIAL_READ"
    else:
        cls = "INACCESSIBLE_UNDER_LIMITS"
    return {"family": family, "class": cls, "relevant_indices": pos,
            "relevant_entries": [f"{entries[i]['library']}!{entries[i]['symbol'] or '#' + str(entries[i]['ordinal'])}"
                                 for i in pos[:12]],
            "in_projection": [i for i in pos if i < PAGE],
            "reachable_sequential": [i for i in pos if PAGE <= i < SEQ_REACH],
            "committed_nonsequential": [i for i in pos if SEQ_REACH <= i < COMMIT_CAP],
            "inaccessible": [i for i in pos if i >= COMMIT_CAP]}


def assign(profiles: Dict[str, List[Dict[str, Any]]], seed: str) -> Dict[str, Any]:
    """profiles: alias -> full declared import entries (file order). Deterministic backtracking that
    fills the three import-accessibility classes first (only feasible family options), then the two
    family-independent classes. Returns assignment + feasibility report. Never reads model output."""
    rng = random.Random(seed)
    aliases = sorted(profiles)
    rng.shuffle(aliases)
    fams = sorted(FAMILIES)
    options = {a: {} for a in aliases}
    for a in aliases:
        order = fams[:]
        random.Random(seed + a).shuffle(order)
        for f in order:
            ac = access_class(f, profiles[a])
            if ac["class"] in CLASSES[:3]:
                options[a].setdefault(ac["class"], (f, ac))
    import_classes = list(CLASSES[:3])
    feasible = {c: sum(1 for a in aliases if c in options[a]) for c in import_classes}
    # Predeclared shortfall rule: if fewer than 4 samples can serve IN_INITIAL_TOOL_PROJECTION, the
    # shortfall goes to REACHABLE_BY_BOUNDED_RETRIEVAL (the class that tests the central hypothesis);
    # the two family-independent classes keep 4 each.
    target = dict(TARGET)
    short = max(0, TARGET["IN_INITIAL_TOOL_PROJECTION"] - feasible["IN_INITIAL_TOOL_PROJECTION"])
    target["IN_INITIAL_TOOL_PROJECTION"] -= short
    target["REACHABLE_BY_BOUNDED_RETRIEVAL"] += short
    best: Dict[str, Any] = {}

    def search(i, counts, chosen):
        nonlocal best
        if sum(counts.values()) > sum(best.get("counts", {}).values()) if best else True:
            best = {"counts": dict(counts), "chosen": dict(chosen)}
        if all(counts[c] == target[c] for c in import_classes):
            return True
        if i == len(aliases):
            return False
        a = aliases[i]
        for c in import_classes:
            if c in options[a] and counts[c] < target[c]:
                counts[c] += 1; chosen[a] = (c, *options[a][c])
                if search(i + 1, counts, chosen):
                    return True
                counts[c] -= 1; del chosen[a]
        return search(i + 1, counts, chosen)

    search(0, {c: 0 for c in import_classes}, {})
    chosen = dict(best["chosen"])
    rest = [a for a in aliases if a not in chosen]
    for k, a in enumerate(rest):
        c = "NOT_STATIC_ANSWERABLE" if k < target["NOT_STATIC_ANSWERABLE"] else "INITIAL_EVIDENCE_SUFFICIENT"
        chosen[a] = (c, None, None)
    counts = {c: sum(1 for v in chosen.values() if v[0] == c) for c in CLASSES}
    return {"assignment": chosen, "counts": counts, "requested_target": TARGET, "feasible_target": target,
            "shortfall_rule": f"{short} case(s) moved IN_INITIAL_TOOL_PROJECTION -> REACHABLE_BY_BOUNDED_RETRIEVAL",
            "samples_with_option": feasible, "requested_target_met": counts == TARGET,
            "feasible_target_met": counts == target}
