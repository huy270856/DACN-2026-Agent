"""TASK 06A — deterministic grounding verifier (evidence <-> claim binding).

Given an assessment's prose + cited evidence ids and the REAL static projection
the agent was shown, flag claims that the evidence does not support. This is the
deterministic defence against the documented v1 failures:

  * fabricated import / library names ("MFC imports", "CRM imports",
    "ExitProcess / MoveFileA") that are not in the evidence sheet,
  * "high entropy / packed" asserted when 0 sections have entropy >= 7,
  * runtime-behaviour claims (connects to C2, injects, executes ...) that are
    impossible to observe from a static feature record.

It is intentionally CONSERVATIVE: it only flags specifics it can positively
contradict or that are impossible static-only, so a correct, well-grounded report
is not penalised. It works on BOTH v1 free text and v2 structured output, so the
same yard-stick measures both branches.

The verifier never calls an LLM and never trusts model text as instructions.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence, Set

# A small lexicon of Windows APIs commonly cited in malware write-ups. We only use
# it to catch a *specific* named API asserted as an import when it is absent from
# the evidence — never to require any of them to be present.
_API_LEXICON = {
    "virtualalloc", "virtualallocex", "virtualprotect", "writeprocessmemory",
    "readprocessmemory", "createremotethread", "createthread", "loadlibrarya",
    "loadlibraryw", "loadlibrary", "getprocaddress", "exitprocess", "terminateprocess",
    "createprocessa", "createprocessw", "winexec", "shellexecutea", "shellexecutew",
    "movefilea", "movefilew", "copyfilea", "copyfilew", "deletefilea", "deletefilew",
    "createfilea", "createfilew", "writefile", "readfile", "regsetvaluea", "regsetvaluew",
    "regcreatekeya", "regopenkeya", "regopenkeyexa", "wsastartup", "wsasocketa",
    "socket", "connect", "send", "recv", "internetopena", "internetopenurla",
    "httpsendrequesta", "urldownloadtofilea", "cryptencrypt", "cryptdecrypt",
    "setwindowshookexa", "getasynckeystate", "adjusttokenprivileges", "openprocess",
    "ntunmapviewofsection", "zwunmapviewofsection", "isdebuggerpresent",
}

# Named frameworks/libraries that showed up as fabricated specifics in v1 audits.
_LIBRARY_HINTS = {"mfc", "crm", "atl", "qt", ".net", "dotnet", "vcl", "wxwidgets"}

# Runtime-behaviour verbs/nouns that cannot be observed from a static feature record.
_BEHAVIOUR_PATTERNS = re.compile(
    r"\b(connect(?:s|ed|ing)?\s+to|command[-\s]?and[-\s]?control|\bc2\b|beacon|"
    r"exfiltrat|inject(?:s|ed|ing|ion)?\s+(?:code|into|a\s+process)|"
    r"was\s+executed|when\s+executed|at\s+runtime|dropped\s+a?\s*file|"
    r"spawns?\s+a?\s*process|established?\s+a?\s*connection|sends?\s+data\s+to)\b",
    re.IGNORECASE)

_HIGH_ENTROPY_PATTERN = re.compile(
    r"\b(high[-\s]?entropy|packed|packer|encrypted\s+section|obfuscat)", re.IGNORECASE)

# Negations that turn a high-entropy mention into a correct "there is none" statement.
_NEGATION = re.compile(r"(no|not|without|zero|0|lacks?|absence of|aren'?t|isn'?t)\s*$",
                       re.IGNORECASE)


def _affirmative_entropy_claim(text: str) -> bool:
    """True only if high-entropy/packing is asserted (not negated)."""
    for m in _HIGH_ENTROPY_PATTERN.finditer(text):
        preceding = text[max(0, m.start() - 16):m.start()]
        if not _NEGATION.search(preceding.strip()):
            return True
    return False


def build_evidence_index(projection: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract the concrete facts actually present in the projection."""
    import_funcs: Set[str] = set()
    libraries: Set[str] = set()
    section_names: Set[str] = set()
    high_entropy_count = None  # missing/truncated is UNKNOWN, never zero
    wx_count = 0
    url_count = registry_count = mz_count = 0
    evidence_ids: Set[str] = set()

    for ev in projection.get("observations", []):
        evidence_ids.add(ev.get("evidence_id"))
        facet = ev.get("facet")
        val = ev.get("value") or {}
        if facet == "static.imports_summary":
            for lib in val.get("libraries", []) or []:
                libraries.add(str(lib).lower())
            for s in val.get("sampled_imports", []) or []:
                # "LIB.dll:FuncName"
                if ":" in s:
                    lib, fn = s.split(":", 1)
                    libraries.add(lib.lower())
                    import_funcs.add(fn.lower())
                else:
                    import_funcs.add(str(s).lower())
        elif facet == "static.sections":
            for s in val.get("sections", []) or []:
                if s.get("name"):
                    section_names.add(str(s["name"]).lower())
            count = val.get("high_entropy_section_count_ge7")
            high_entropy_count = int(count) if count is not None else None
            wx_count = int(val.get("writable_and_executable_section_count", 0) or 0)
        elif facet == "static.strings_summary":
            url_count = int(val.get("url_occurrences", 0) or 0)
            registry_count = int(val.get("registry_key_occurrences", 0) or 0)
            mz_count = int(val.get("embedded_MZ_occurrences", 0) or 0)

    return {
        "evidence_ids": {e for e in evidence_ids if e},
        "import_funcs": import_funcs,
        "libraries": libraries,
        "section_names": section_names,
        "high_entropy_count": high_entropy_count,
        "wx_count": wx_count,
        "url_count": url_count,
        "registry_count": registry_count,
        "mz_count": mz_count,
        "imports_present": bool(import_funcs or libraries),
    }


def _tokens(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_.]{2,}", text or "")


def check_grounding(text: str, cited_ids: Sequence[str],
                    projection: Mapping[str, Any]) -> Dict[str, Any]:
    """Return grounding flags for one assessment. Lower is better.

    All lists are the specific offending items so a reviewer can audit each flag.
    """
    idx = build_evidence_index(projection)
    text = text or ""
    low_tokens = {t.lower() for t in _tokens(text)}

    # 1. Cited ids that do not exist in the projection.
    invalid_ids = [c for c in cited_ids if c not in idx["evidence_ids"]]

    # 2. Specific Windows APIs asserted but absent from the evidence imports.
    unsupported_apis = sorted(
        {t for t in low_tokens
         if t in _API_LEXICON and t not in idx["import_funcs"]})

    # 3. Named frameworks/libraries asserted but absent from the evidence libraries.
    unsupported_libraries = sorted(
        {h for h in _LIBRARY_HINTS
         if h in low_tokens and not any(h in lib for lib in idx["libraries"])})

    # 4. High-entropy / packing asserted while NO section has entropy >= 7.
    entropy_unsupported = _affirmative_entropy_claim(text) and idx["high_entropy_count"] == 0

    # 5. Runtime-behaviour claims impossible from a static record.
    behaviour_claims = sorted({m.group(0).lower() for m in _BEHAVIOUR_PATTERNS.finditer(text)})

    unsupported_specifics = (len(unsupported_apis) + len(unsupported_libraries)
                             + (1 if entropy_unsupported else 0))

    return {
        "invalid_evidence_ids": invalid_ids,
        "citation_valid": not invalid_ids,
        "unsupported_apis": unsupported_apis,
        "unsupported_libraries": unsupported_libraries,
        "entropy_claim_unsupported": entropy_unsupported,
        "runtime_behaviour_claims": behaviour_claims,
        "unsupported_specifics_count": unsupported_specifics,
        "grounded": unsupported_specifics == 0 and not invalid_ids and not behaviour_claims,
    }
