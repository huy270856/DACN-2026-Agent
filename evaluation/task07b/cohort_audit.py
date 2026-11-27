"""TASK 07B (D5) fresh-cohort audit: evaluator-only, read-only static parsing; never executes targets.

Wraps (imports, does not modify) the frozen 06B-J helpers `pe_profile`, `jaccard`,
`leakage.authenticode/version_strings` and the v2 capability lexicon, but replaces two
weaknesses of `task06b_j.holdout_audit` for this task:
  * exclusion is EXPLICIT: program names AND SHA-256 of 05D, 06B (dev/reserve), 06B-J
    (CANDIDATES_V1, holdout v1/v2, DEV smoke, calibration) and 07A DEV/test PEs, plus every
    System32 program name / SHA found in ANY tracked repository file (no task06b_j skip);
  * accessibility is the v4 model (full table, no 64-entry cap): classes RELEVANT_PRESENT,
    RELEVANT_ABSENT, NOT_STATIC_ANSWERABLE, INITIAL_EVIDENCE_SUFFICIENT.
Stratification rules and targets are fixed here BEFORE any 07B inference on the new cohort.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from evaluation.task06b_j import holdout_audit as ha, leakage, questions_v2 as qv2

ROOT = Path(__file__).resolve().parents[2]
SYSTEM32 = Path("C:/Windows/System32")
AUDIT_VERSION = "task07b-cohort-audit-v1"
SEED = "task07b-cohort-v1"
POOL_SIZE = 120
JACCARD_MAX = 0.85
V3_REACH = 48          # v3.4 BASE can see entries 0-47 at most (first page + 2 reads)
TARGETS = {"RELEVANT_PRESENT": 8, "RELEVANT_ABSENT": 4, "NOT_STATIC_ANSWERABLE": 4, "INITIAL_EVIDENCE_SUFFICIENT": 4}
MIN_BEYOND_V3 = 5      # RELEVANT_PRESENT cases whose first relevant entry index >= 48
FAMILIES = ("FILE", "NETWORK", "PROCESS", "REGISTRY", "SERVICE")
ELIGIBILITY = {"pe": "PE32+ x64 EXE (not DLL)", "signature": "Authenticode Valid, subject contains 'Microsoft'",
               "max_size_bytes": 8 * 1024 * 1024, "min_declared_imports": 1,
               "program_disjoint": "stem / OriginalFilename stem not in the explicit exclusion list",
               "sha_disjoint": "SHA-256 not in any tracked repository file nor of any excluded program on disk",
               "near_duplicate": f"import-set Jaccard < {JACCARD_MAX} vs excluded programs on disk and earlier pool members"}

# Explicit lists (in addition to manifests parsed below).
EXPLICIT_EXCLUDED = {
    "06B-J CANDIDATES_V1": list(ha.CANDIDATES_V1),
    "06B-J/07A DEV smoke + test fixtures": ["tracert.exe", "findstr.exe", "whoami.exe", "where.exe"],
}
SYS32_NAME = re.compile(r"system32[\\/]+([A-Za-z0-9_.\-]+\.(?:exe|com))", re.I)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _tracked(*folders) -> List[str]:
    return subprocess.check_output(["git", "ls-files", *folders], cwd=ROOT, text=True).split()


def excluded_programs() -> Dict[str, str]:
    """lower-case filename -> why excluded. Explicit lists + 05D/06B (via ha.prior_programs) + names
    mentioned with a System32 path in ANY tracked text file."""
    out: Dict[str, str] = {}
    for src, names in EXPLICIT_EXCLUDED.items():
        for n in names:
            out.setdefault(n.lower(), src)
    for n, why in ha.prior_programs().items():
        out.setdefault(n.lower(), why)
    for f in _tracked("evaluation", "research", "docs", "tests", "benchmarks", "examples"):
        if f.endswith((".json", ".jsonl", ".md", ".csv", ".txt", ".py")):
            text = (ROOT / f).read_text(encoding="utf-8", errors="ignore")
            for m in SYS32_NAME.finditer(text):
                out.setdefault(m.group(1).lower(), "tracked:" + f.split("/")[1] if "/" in f else f)
    return out


def tracked_shas() -> set:
    out = set()
    for f in _tracked("evaluation", "research", "docs", "tests", "benchmarks", "examples"):
        if f.endswith((".json", ".jsonl", ".md", ".csv", ".txt", ".xml", ".log")):
            out |= set(re.findall(r"\b[0-9a-f]{64}\b", (ROOT / f).read_text(encoding="utf-8", errors="ignore")))
    return out


def relevant(entries: List[Dict[str, Any]], family: str) -> List[Tuple[int, str]]:
    fam = qv2.FAMILIES[family]
    out = []
    for i, e in enumerate(entries):
        lib = (e["library"] or "").lower()
        sym = (e["symbol"] or "").lower()
        if lib in fam["libs"] or (e["symbol"] is not None and sym in fam["syms"]):
            out.append((i, e["library"] + "!" + (e["symbol"] if e["symbol"] is not None else "#" + str(e["ordinal"]))))
    return out


def _rank(name: str, salt: str = "") -> str:
    return hashlib.sha256((SEED + salt + name.lower()).encode()).hexdigest()


def audit(out: Path, *, system32: Path = SYSTEM32, pool_size: int = POOL_SIZE) -> Dict[str, Any]:
    if out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out}")
    excl = excluded_programs()
    shas = tracked_shas()
    excl_profiles, excl_shas = {}, set()
    for n in sorted(excl):
        p = system32 / n
        if p.exists() and p.suffix.lower() in (".exe", ".com"):
            excl_shas.add(sha256(p))
            prof = ha.pe_profile(p)
            if prof.get("parse") == "OK":
                excl_profiles[n] = prof["import_set"]
    stems = {Path(n).stem for n in excl}
    names = sorted((p.name for p in system32.glob("*.exe")), key=lambda n: _rank(n))
    rows, pool, accepted = [], [], {}
    for n in names:
        if len(pool) >= pool_size:
            break
        p = system32 / n
        row: Dict[str, Any] = {"filename": n, "source": str(p)}
        reasons = []
        if Path(n).stem.lower() in stems:
            reasons.append("EXCLUDED_PROGRAM (" + excl.get(n.lower(), "stem match") + ")")
        size = p.stat().st_size
        if size > ELIGIBILITY["max_size_bytes"]:
            reasons.append("TOO_LARGE")
        if reasons:
            rows.append(dict(row, eligible=False, reasons=reasons))
            continue
        h = sha256(p)
        if h in shas or h in excl_shas:
            reasons.append("SHA_OVERLAP")
        prof = ha.pe_profile(p)
        if prof.get("parse") != "OK" or prof["pe_kind"] != "PE32+" or prof["machine"] != "AMD64" or prof["is_dll"]:
            reasons.append("NOT_PE32PLUS_X64_EXE")
        elif prof["declared_imports"] < 1:
            reasons.append("NO_DECLARED_IMPORTS")
        ver = leakage.version_strings(p) if not reasons else {}
        orig = Path(ver.get("OriginalFilename", n)).stem.lower()
        if orig in stems:
            reasons.append("EXCLUDED_PROGRAM (OriginalFilename " + orig + ")")
        if not reasons:
            near = {k: round(ha.jaccard(prof["import_set"], v), 3) for k, v in excl_profiles.items()}
            hit = {k: v for k, v in near.items() if v >= JACCARD_MAX}
            if hit:
                reasons.append(f"NEAR_DUPLICATE_OF_EXCLUDED {hit}")
            ch = {k: round(ha.jaccard(prof["import_set"], v), 3) for k, v in accepted.items()
                  if ha.jaccard(prof["import_set"], v) >= JACCARD_MAX}
            if ch:
                reasons.append(f"NEAR_DUPLICATE_OF_EARLIER_POOL_MEMBER {ch}")
        if not reasons:
            sig = leakage.authenticode([p]).get(str(p), {"status": "UNKNOWN", "subject": ""})
            if sig.get("status") != "Valid" or "microsoft" not in str(sig.get("subject", "")).lower():
                reasons.append("SIGNATURE_NOT_VALID_MICROSOFT")
        else:
            sig = None
        row.update(sha256=h, size_bytes=size, eligible=not reasons, reasons=reasons)
        if not reasons:
            accepted[n] = prof["import_set"]
            fam = {f: relevant(prof["entries"], f) for f in FAMILIES}
            row.update(version=ver, signature=sig, declared_imports=prof["declared_imports"],
                       family_relevant={f: {"indices": [i for i, _ in v], "literals": [l for _, l in v]}
                                        for f, v in fam.items()})
            pool.append(row)
        rows.append(row)
    doc = {"audit_version": AUDIT_VERSION, "seed": SEED, "created_utc": datetime.now(timezone.utc).isoformat(),
           "track": "RAW_PE_E2E_BENIGN_FRESH_COHORT", "eligibility_rules": ELIGIBILITY,
           "excluded_programs": excl, "excluded_on_disk": sorted(excl_profiles), "pool_size_target": pool_size,
           "n_examined": len(rows), "n_pool": len(pool), "lexicon": qv2.QUESTIONS_VERSION,
           "limitations": ["Benign-only cohort (signed Windows utilities); no malicious, packed, third-party or DLL strata.",
                           "Program independence judged by name/version/import similarity; functional relatedness remains possible.",
                           "Relevant entries are exact-name lexicon hits on the full declared table; a hit is a declared "
                           "capability reference, never ground truth of runtime behaviour."],
           "candidates": rows}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc


def allocate(audit_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic stratification (rules fixed before inference). Each program used once."""
    pool = sorted((r for r in audit_doc["candidates"] if r["eligible"]), key=lambda r: _rank(r["filename"], "alloc"))
    used, cases, notes = set(), [], []

    def take(cands, k, cls):
        got = []
        fams_seen: Dict[str, int] = {}
        # round-robin over families for variety: prefer the least-used family first
        while len(got) < k and cands:
            cands.sort(key=lambda c: (fams_seen.get(c[1], 0), _rank(c[0]["filename"] + c[1], cls)))
            r, f = cands.pop(0)
            if r["filename"] in used:
                continue
            used.add(r["filename"])
            fams_seen[f] = fams_seen.get(f, 0) + 1
            got.append((r, f))
            cands[:] = [c for c in cands if c[0]["filename"] not in used]
        return got

    present = [(r, f) for r in pool for f in FAMILIES if r["family_relevant"][f]["indices"]]
    beyond = [(r, f) for r, f in present if r["family_relevant"][f]["indices"][0] >= V3_REACH]
    rp = take(list(beyond), MIN_BEYOND_V3, "RP_BEYOND")
    if len(rp) < MIN_BEYOND_V3:
        notes.append(f"Only {len(rp)} RELEVANT_PRESENT cases with first relevant index >= {V3_REACH} available "
                     f"(target {MIN_BEYOND_V3}); using what exists (recorded before inference).")
    rp += take([c for c in present if c[0]["filename"] not in used], TARGETS["RELEVANT_PRESENT"] - len(rp), "RP_ANY")
    absent = [(r, f) for r in pool for f in FAMILIES if not r["family_relevant"][f]["indices"]]
    ra = take(absent, TARGETS["RELEVANT_ABSENT"], "RA")
    rest = [(r, "-") for r in pool if r["filename"] not in used]
    ns = take(list(rest), TARGETS["NOT_STATIC_ANSWERABLE"], "NS")
    rest = [(r, "-") for r in pool if r["filename"] not in used]
    isuf = take(list(rest), TARGETS["INITIAL_EVIDENCE_SUFFICIENT"], "IS")
    for cls, got in (("RELEVANT_PRESENT", rp), ("RELEVANT_ABSENT", ra), ("NOT_STATIC_ANSWERABLE", ns),
                     ("INITIAL_EVIDENCE_SUFFICIENT", isuf)):
        if len(got) < TARGETS[cls]:
            notes.append(f"{cls}: {len(got)}/{TARGETS[cls]} available")
        for r, f in got:
            cases.append(_case(r, cls, f if f != "-" else None))
    order = sorted(cases, key=lambda c: _rank(c["source"], "alias"))
    for i, c in enumerate(order, 1):
        c["alias"] = f"sample_{i:04d}"
    return {"cases": order, "notes": notes}


def _case(r: Dict[str, Any], cls: str, family: Optional[str]) -> Dict[str, Any]:
    if cls in ("RELEVANT_PRESENT", "RELEVANT_ABSENT"):
        q = qv2.TEMPLATES["CAPABILITY"].format(phrase=qv2.FAMILIES[family]["phrase"])
        fr = r["family_relevant"][family]
        ref = {"relevant_entries": fr["literals"], "relevant_indices": fr["indices"],
               "first_relevant_index": fr["indices"][0] if fr["indices"] else None,
               "beyond_v3_reach": bool(fr["indices"]) and fr["indices"][0] >= V3_REACH,
               "declared_entries": r["declared_imports"],
               "answer": (f"Declared {family} references in the full import table: {len(fr['indices'])}" if fr["indices"]
                          else f"No declared {family} references in the full import table; dynamically resolved APIs remain possible")}
        qid = f"Q07B_{cls}_{family}"
    else:
        q = qv2.TEMPLATES[cls]
        ref = ({"answer": "UNANSWERABLE statically: declared imports can at most show a declared capability, never runtime communication",
                "network_relevant_entries": r["family_relevant"]["NETWORK"]["literals"]}
               if cls == "NOT_STATIC_ANSWERABLE" else
               {"answer": "PE kind/arch from static parse; detector output = whatever the frozen initial CaseState records",
                "unknowns": "runtime behaviour; detector score is not a calibrated probability"})
        qid = f"Q07B_{cls}"
    return {"source": r["source"], "sha256": r["sha256"],
            "program_identity_EVALUATOR_ONLY": {"filename": r["filename"],
                                                "OriginalFilename": r.get("version", {}).get("OriginalFilename"),
                                                "FileDescription": r.get("version", {}).get("FileDescription")},
            "question_id": qid, "question_text": q, "accessibility_class": cls, "capability_family": family,
            "reference_EVALUATOR_ONLY": ref, "true_label_EVALUATOR_ONLY": "benign",
            "label_basis": "OS provenance + valid Microsoft signature"}


def make_cases(audit_path: Path, out: Path) -> Dict[str, Any]:
    if out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out}")
    doc = json.loads(audit_path.read_text(encoding="utf-8"))
    alloc = allocate(doc)
    man = {"track": "RAW_PE_E2E_BENIGN_FRESH_COHORT", "audit_version": AUDIT_VERSION, "seed": SEED,
           "audit_sha256": sha256(audit_path), "created_utc": datetime.now(timezone.utc).isoformat(),
           "questions_version": "task07b-questions (06B-J v2 templates + lexicon)",
           "questions_sha256": hashlib.sha256(json.dumps(qv2.TEMPLATES, sort_keys=True).encode()).hexdigest(),
           "targets": TARGETS, "min_beyond_v3": MIN_BEYOND_V3, "v3_reach": V3_REACH,
           "allocation_notes": alloc["notes"], "evaluation_kind": "DEV_EVALUATION_FRESH_COHORT",
           "confirmatory": "NOT_RUN", "cases": alloc["cases"]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    return man


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit")
    a.add_argument("--out", type=Path, required=True)
    m = sub.add_parser("cases")
    m.add_argument("--audit", type=Path, required=True)
    m.add_argument("--out", type=Path, required=True)
    x = ap.parse_args(argv)
    if x.cmd == "audit":
        d = audit(x.out)
        print(json.dumps({"n_examined": d["n_examined"], "n_pool": d["n_pool"]}))
    else:
        man = make_cases(x.audit, x.out)
        from collections import Counter
        print(json.dumps({"counts": Counter(c["accessibility_class"] for c in man["cases"]),
                          "beyond_v3": sum(c["reference_EVALUATOR_ONLY"].get("beyond_v3_reach", False) for c in man["cases"]),
                          "notes": man["allocation_notes"]}, indent=1))


if __name__ == "__main__":
    main()
