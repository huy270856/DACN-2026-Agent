"""Predeclared investigation question categories for the 06B-J controlled evaluation.

Fixed BEFORE any Agent inference. Assignment is a seeded, balanced rotation over eligible
cases and does NOT use model output. Answerability (where relevant committed import
entries sit) is computed evaluator-side from a static parse and stored EVALUATOR_ONLY as a
stratum; it never reaches the Agent and is not used to choose questions.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, List

QUESTIONS_VERSION = "task06b-j-questions-v1"

QUESTIONS = {
    "Q_NET": "Which declared DLL/API imports, if any, indicate network-related capability (for example "
             "sockets, name resolution, HTTP or ICMP)? What remains unknown?",
    "Q_FILE": "Which declared DLL/API imports, if any, indicate file-system capability (creating, reading, "
              "writing, moving or deleting files)? What remains unknown?",
    "Q_PROC": "Which declared DLL/API imports, if any, indicate process-related capability (creating, opening "
              "or terminating processes, or accessing another process's memory)? What remains unknown?",
    "Q_RUNTIME_LIMIT": "Does this file actually communicate over the network when it runs? State what static "
                       "evidence can and cannot establish about this.",
    "Q_NO_TOOL": "What kind of PE image is this (executable or DLL, architecture) and what did the static "
                 "detector predict? What remains unknown?",
}

# Category intent (evaluator-only documentation; not shown to the Agent).
CATEGORY_INTENT = {
    "Q_NET": "imports-answerable; retrieval may matter if relevant entries lie beyond the first page",
    "Q_FILE": "imports-answerable",
    "Q_PROC": "imports-answerable",
    "Q_RUNTIME_LIMIT": "static evidence cannot answer; correct behaviour is to state the limit",
    "Q_NO_TOOL": "answerable from initial evidence; no analyzer necessary",
}

NETWORK_LIBS = ("ws2_32.dll", "wsock32.dll", "wininet.dll", "winhttp.dll", "iphlpapi.dll", "dnsapi.dll",
                "urlmon.dll", "mswsock.dll", "netapi32.dll")
FILE_PREFIXES = ("createfile", "readfile", "writefile", "deletefile", "movefile", "copyfile", "findfirstfile",
                 "findnextfile", "setfileattributes", "getfileattributes", "createdirectory", "removedirectory",
                 "replacefile", "setendoffile", "_wfopen", "fopen", "_open", "_wopen")
PROCESS_PREFIXES = ("createprocess", "openprocess", "terminateprocess", "virtualallocex", "writeprocessmemory",
                    "readprocessmemory", "createremotethread", "shellexecute", "winexec", "ntcreateprocess",
                    "ntopenprocess", "getexitcodeprocess")
LEXICON = {"Q_NET": ("lib", NETWORK_LIBS), "Q_FILE": ("sym", FILE_PREFIXES), "Q_PROC": ("sym", PROCESS_PREFIXES)}

PAGE = 16          # default visible slice after the tool (repair_context)
COMMIT_CAP = 64    # analyzer commits at most 64 entries


def questions_sha256() -> str:
    return hashlib.sha256(json.dumps(QUESTIONS, sort_keys=True).encode("utf-8")).hexdigest()


def relevant_positions(qid: str, entries: List[Dict[str, Any]]) -> List[int]:
    if qid not in LEXICON:
        return []
    mode, lex = LEXICON[qid]
    out = []
    for i, e in enumerate(entries):
        lib, sym = str(e.get("library") or "").lower(), str(e.get("symbol") or "").lower()
        if (mode == "lib" and lib in lex) or (mode == "sym" and sym.startswith(lex)):
            out.append(i)
    return out


def answerability(qid: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Stratum for analysis only. entries = full declared imports in file order (static parse)."""
    if qid == "Q_RUNTIME_LIMIT":
        return {"stratum": "NOT_ANSWERABLE_STATICALLY"}
    if qid == "Q_NO_TOOL":
        return {"stratum": "ANSWERABLE_FROM_INITIAL_EVIDENCE"}
    pos = relevant_positions(qid, entries)
    if not pos:  # evaluator parses the COMPLETE declared import table
        stratum = "NO_RELEVANT_DECLARED_IMPORTS"
    elif min(pos) < PAGE:
        stratum = "RELEVANT_IN_FIRST_VISIBLE_PAGE"
    elif min(pos) < COMMIT_CAP:
        stratum = "RELEVANT_ONLY_AFTER_RETRIEVAL"
    else:
        stratum = "RELEVANT_ONLY_BEYOND_COMMIT_CAP"
    return {"stratum": stratum, "relevant_positions": pos[:40], "n_relevant": len(pos),
            "declared_entries": len(entries)}


def assign(case_aliases: List[str], seed: str) -> Dict[str, str]:
    """Balanced round-robin over a seeded shuffle; independent of any model output."""
    order = sorted(case_aliases)
    random.Random(seed).shuffle(order)
    cats = list(QUESTIONS)
    return {alias: cats[i % len(cats)] for i, alias in enumerate(order)}
