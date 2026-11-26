"""Candidate holdout audit (evaluator-only; read-only static parsing, never executes targets).

Checks SHA overlap AND program identity: filename stem, OriginalFilename/InternalName,
previously evaluated/reserved program names, different builds of the same program, and
near-duplicate import profiles (Jaccard) against previously evaluated programs present on
disk and among candidates. Eligibility rules are fixed in ELIGIBILITY before results exist.
No detector or Agent inference is run here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from evaluation.task06b_j import leakage, questions

ROOT = Path(__file__).resolve().parents[2]
SYSTEM32 = Path("C:/Windows/System32")
AUDIT_VERSION = "task06b-j-holdout-audit-v1"
ELIGIBILITY = {
    "pe": "PE32+ x64 EXE (not DLL)",
    "signature": "Authenticode status Valid, subject contains 'Microsoft'",
    "max_size_bytes": 8 * 1024 * 1024,
    "sha_disjoint": "SHA-256 absent from every tracked evaluation/research/docs artifact",
    "program_disjoint": "stem and OriginalFilename stem not previously evaluated or reserved",
    "near_duplicate": "import-set Jaccard < 0.85 vs previously evaluated programs on disk and earlier candidates",
    "min_declared_imports": 1,
}
JACCARD_MAX = 0.85

CANDIDATES_V1 = ["compact.exe", "more.com", "sort.exe", "auditpol.exe", "bcdedit.exe", "bitsadmin.exe",
                 "makecab.exe", "chcp.com", "dsregcmd.exe", "esentutl.exe", "expand.exe", "ipconfig.exe",
                 "nslookup.exe", "arp.exe", "pathping.exe", "sc.exe", "robocopy.exe", "icacls.exe",
                 "takeown.exe", "systeminfo.exe", "driverquery.exe", "cmdkey.exe"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_sha_set() -> set:
    files = subprocess.check_output(["git", "ls-files", "evaluation", "research", "docs", "benchmarks", "examples"],
                                    cwd=ROOT, text=True).split()
    out = set()
    for f in files:
        if f.endswith((".json", ".jsonl", ".md", ".csv", ".txt", ".log", ".xml")) and "task06b_j" not in f:
            out |= set(re.findall(r"\b[0-9a-f]{64}\b", (ROOT / f).read_text(encoding="utf-8", errors="ignore")))
    return out


def prior_programs() -> Dict[str, str]:
    """name(lower) -> where it was evaluated or reserved."""
    out: Dict[str, str] = {}
    d5 = ROOT / "evaluation/task05d/results"
    for p in [d5 / "sample_manifest_full.json", d5 / "sample_manifest.json", *sorted((d5 / "samples").glob("*.json"))]:
        if p.exists():
            obj = json.loads(p.read_text(encoding="utf-8"))
            for s in obj.get("samples", [obj]):
                if s.get("filename"):
                    out.setdefault(s["filename"].lower(), "05D RAW_PE_E2E")
    for m in sorted((ROOT / "evaluation/task06b/results").glob("*/manifest_EVALUATOR_ONLY.json")):
        obj = json.loads(m.read_text(encoding="utf-8"))
        for key in ("dev", "reserve_NOT_EVALUATED"):
            for s in obj.get(key) or []:
                out.setdefault(s["filename"].lower(), f"06B {m.parent.name} {key}")
    return out


def pe_profile(path: Path) -> Dict[str, Any]:
    import lief
    b = lief.parse(str(path))
    if b is None:
        return {"parse": "FAILED"}
    entries = []
    for delay, table in ((False, b.imports), (True, b.delay_imports)):
        for lib in table:
            for it in lib.entries:
                entries.append({"library": lib.name, "symbol": None if it.is_ordinal else it.name,
                                "ordinal": int(it.ordinal) if it.is_ordinal else None, "delay": delay})
    hdr = b.header
    return {"parse": "OK", "machine": str(hdr.machine).split(".")[-1],
            "pe_kind": "PE32+" if b.optional_header.magic == lief.PE.PE_TYPE.PE32_PLUS else "PE32",
            "is_dll": bool(b.header.has_characteristic(lief.PE.Header.CHARACTERISTICS.DLL)),
            "declared_imports": len(entries), "libraries": sorted({e["library"].lower() for e in entries}),
            "import_set": sorted({f"{e['library'].lower()}!{e['symbol'] or '#' + str(e['ordinal'])}" for e in entries}),
            "entries": entries}


def jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def audit(names: List[str], out: Path, *, system32: Path = SYSTEM32) -> Dict[str, Any]:
    if out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out}")
    shas = tracked_sha_set()
    prior = prior_programs()
    prior_profiles = {}
    for name in sorted(prior):
        p = system32 / name
        if p.exists() and p.suffix.lower() in (".exe", ".com"):
            prof = pe_profile(p)
            if prof.get("parse") == "OK":
                prior_profiles[name] = prof["import_set"]
    paths = [system32 / n for n in names if (system32 / n).exists()]
    sigs = leakage.authenticode(paths)
    rows, accepted_sets = [], {}
    for n in names:
        p = system32 / n
        row: Dict[str, Any] = {"filename": n, "source": str(p)}
        if not p.exists():
            rows.append(dict(row, eligible=False, reasons=["MISSING"])); continue
        prof = pe_profile(p)
        ver = leakage.version_strings(p)
        sig = sigs.get(str(p), {"status": "UNKNOWN", "subject": ""})
        h = sha256(p)
        orig_stem = Path(ver.get("OriginalFilename", n)).stem.lower()
        reasons = []
        if prof.get("parse") != "OK" or prof["pe_kind"] != "PE32+" or prof["machine"] != "AMD64" or prof["is_dll"]:
            reasons.append("NOT_PE32PLUS_X64_EXE")
        if sig.get("status") != "Valid" or "microsoft" not in str(sig.get("subject", "")).lower():
            reasons.append("SIGNATURE_NOT_VALID_MICROSOFT")
        if p.stat().st_size > ELIGIBILITY["max_size_bytes"]:
            reasons.append("TOO_LARGE")
        if h in shas:
            reasons.append("SHA_OVERLAP")
        stems = {Path(k).stem for k in prior}
        if Path(n).stem.lower() in stems or orig_stem in stems:
            reasons.append("PROGRAM_PREVIOUSLY_EVALUATED_OR_RESERVED (" +
                           prior.get(n.lower(), prior.get(orig_stem + ".exe", "name match")) + ")")
        near = {k: round(jaccard(prof.get("import_set", []), v), 3) for k, v in prior_profiles.items()}
        near_hit = {k: v for k, v in near.items() if v >= JACCARD_MAX}
        if near_hit:
            reasons.append(f"NEAR_DUPLICATE_OF_PRIOR {near_hit}")
        cand_hit = {k: round(jaccard(prof.get("import_set", []), v), 3) for k, v in accepted_sets.items()
                    if jaccard(prof.get("import_set", []), v) >= JACCARD_MAX}
        if cand_hit:
            reasons.append(f"NEAR_DUPLICATE_OF_EARLIER_CANDIDATE {cand_hit}")
        if prof.get("declared_imports", 0) < ELIGIBILITY["min_declared_imports"]:
            reasons.append("NO_DECLARED_IMPORTS")
        eligible = not reasons
        if eligible:
            accepted_sets[n] = prof["import_set"]
        rows.append(dict(row, sha256=h, size_bytes=p.stat().st_size, machine=prof.get("machine"),
                         pe_kind=prof.get("pe_kind"), is_dll=prof.get("is_dll"),
                         declared_imports=prof.get("declared_imports"), libraries=prof.get("libraries"),
                         version=ver, signature=sig,
                         max_jaccard_vs_prior=max(near.values()) if near else None,
                         max_jaccard_prior_program=max(near, key=near.get) if near else None,
                         answerability={q: questions.answerability(q, prof.get("entries", [])) for q in questions.QUESTIONS},
                         eligible=eligible, reasons=reasons,
                         true_label_EVALUATOR_ONLY="benign", label_basis="OS provenance + valid Microsoft signature"))
    doc = {"audit_version": AUDIT_VERSION, "created_utc": datetime.now(timezone.utc).isoformat(),
           "track": "RAW_PE_E2E_BENIGN_CANDIDATE_HOLDOUT", "eligibility_rules": ELIGIBILITY,
           "prior_programs": prior, "prior_profiles_on_disk": sorted(prior_profiles),
           "n_candidates": len(names), "n_eligible": sum(r["eligible"] for r in rows),
           "limitations": ["Benign-only cohort (signed Windows utilities); no malicious, packed, third-party, DLL or "
                           "detector-error strata.",
                           "Program-level independence is judged by name/version/import similarity; functional "
                           "relatedness (e.g. network diagnostics family) remains possible."],
           "candidates": rows}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc


def make_cases(audit_path: Path, out: Path, seed: str, track: str) -> Dict[str, Any]:
    """Freeze the candidate case manifest BEFORE any inference: neutral aliases (seeded order, so
    aliases do not reveal names) and a balanced, predeclared question per case."""
    if out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out}")
    import random
    doc = json.loads(audit_path.read_text(encoding="utf-8"))
    eligible = [r for r in doc["candidates"] if r["eligible"]]
    order = sorted(eligible, key=lambda r: r["sha256"])
    random.Random(seed + "|alias").shuffle(order)
    aliases = {r["sha256"]: f"sample_{i + 1:04d}" for i, r in enumerate(order)}
    qmap = questions.assign(list(aliases.values()), seed + "|questions")
    cases = []
    for r in order:
        alias = aliases[r["sha256"]]
        qid = qmap[alias]
        cases.append({"alias": alias, "source": r["source"], "filename_EVALUATOR_ONLY": r["filename"],
                      "sha256": r["sha256"], "size_bytes": r["size_bytes"], "question_id": qid,
                      "answerability_EVALUATOR_ONLY": r["answerability"][qid],
                      "true_label_EVALUATOR_ONLY": r["true_label_EVALUATOR_ONLY"], "label_basis": r["label_basis"]})
    man = {"track": track, "seed": seed, "created_utc": datetime.now(timezone.utc).isoformat(),
           "audit_file": audit_path.name, "audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
           "questions_version": questions.QUESTIONS_VERSION, "questions_sha256": questions.questions_sha256(),
           "status": "CANDIDATE_PENDING_OWNER_APPROVAL", "confirmatory": "NOT_RUN",
           "selection_rule": "all eligible candidates; no model output used", "cases": cases}
    out.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    return man


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit candidate holdout PEs (evaluator-only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("audit"); a1.add_argument("--out", type=Path, required=True)
    a2 = sub.add_parser("cases"); a2.add_argument("--audit", type=Path, required=True)
    a2.add_argument("--out", type=Path, required=True); a2.add_argument("--seed", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "audit":
        doc = audit(CANDIDATES_V1, a.out)
        for r in doc["candidates"]:
            print(f"{r['filename']:16s} {'ELIGIBLE' if r['eligible'] else 'EXCLUDED'} {r['reasons']}")
        print("eligible:", doc["n_eligible"], "/", doc["n_candidates"])
    else:
        man = make_cases(a.audit, a.out, a.seed, "RAW_PE_E2E_BENIGN_CANDIDATE_HOLDOUT")
        for c in man["cases"]:
            print(c["alias"], c["question_id"], c["answerability_EVALUATOR_ONLY"]["stratum"])


if __name__ == "__main__":
    main()


def accessibility(cases_path: Path, out: Path) -> Dict[str, Any]:
    """Per-case, per-assigned-question evidence accessibility (evaluator-only, static parse).

    Access model of the frozen v3.4 tool path: Agent sees NO import entry before the tool;
    after the tool the first page (entries 0-15) is visible; up to 2 READ_EVIDENCE calls of
    <=16 entries each may reveal any other committed entries (0-63); entries >= 64 are never
    committed (analyzer cap) and therefore inaccessible.
    """
    if out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out}")
    man = json.loads(cases_path.read_text(encoding="utf-8"))
    rows = []
    for c in man["cases"]:
        p = Path(c["source"])
        if sha256(p) != c["sha256"]:
            raise ValueError(f"TARGET_DRIFT {c['alias']}")
        prof = pe_profile(p)
        q = c["question_id"]
        pos = questions.relevant_positions(q, prof["entries"])
        first = [i for i in pos if i < questions.PAGE]
        retr = [i for i in pos if questions.PAGE <= i < questions.COMMIT_CAP]
        inacc = [i for i in pos if i >= questions.COMMIT_CAP]
        pages = sorted({i // questions.PAGE for i in retr})
        rel = lambda idx: [f"{prof['entries'][i]['library']}!{prof['entries'][i]['symbol'] or '#' + str(prof['entries'][i]['ordinal'])}" for i in idx]
        if q == "Q_RUNTIME_LIMIT":
            answerable, abstain = "NO (runtime behaviour is not observable statically)", "YES - stating the static limit is the correct answer"
        elif q == "Q_NO_TOOL":
            answerable, abstain = "YES from initial evidence (pe_header/format/prediction)", "A tool call is unnecessary; answering without it is correct"
        elif first or retr:
            answerable = "PARTIALLY (declared capability only)" + ("" if first else "; requires tool + retrieval")
            abstain = "NO for the visible part; must still scope absence beyond what was read"
        elif inacc:
            answerable = "NO via current tool (relevant entries only beyond the 64-entry commit cap)"
            abstain = "YES - correct answer is 'not found in the committed 64 entries; remaining entries unknown'"
        else:
            answerable = "YES as absence, but only completely if declared_entries <= 64"
            abstain = ("Absence claim must be scoped to entries read" if prof["declared_imports"] > questions.COMMIT_CAP
                       else "Absence over the whole table is reachable only if all 64 committed entries are read (16 + 2x16 = 48 max)")
        rows.append({"alias": c["alias"], "question_id": q, "declared_imports": prof["declared_imports"],
                     "relevant_reference_n": len(pos), "relevant_reference_examples": rel(pos[:6]),
                     "in_first_64": len(first) + len(retr), "in_initial_projection_before_tool": 0,
                     "in_first_visible_page_after_tool": len(first),
                     "accessible_only_via_retrieval": len(retr), "retrieval_pages_needed": len(pages),
                     "fully_reachable_within_2_reads": len(pages) <= 2,
                     "inaccessible_beyond_cap": len(inacc),
                     "inaccessible_examples": rel(inacc[:4]),
                     "static_answerable": answerable, "abstention_reasonable": abstain,
                     "filename_EVALUATOR_ONLY": c["filename_EVALUATOR_ONLY"]})
    doc = {"audit": "task06b-j-accessibility-v1", "cases_file": cases_path.name,
           "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
           "access_model": accessibility.__doc__.strip(), "lexicon": questions.QUESTIONS_VERSION, "rows": rows}
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc


def make_cases_v2(cases_v1: Path, audit_path: Path, out: Path, seed: str) -> Dict[str, Any]:
    """Questions v2 manifest (EVALUATOR_ONLY; never shown to the Agent). Same 20 samples and aliases
    as v1; only questions change, using static accessibility (no model or Judge output)."""
    from evaluation.task06b_j import questions_v2 as q2
    if out.exists():
        raise FileExistsError(f"NEW_VERSION_REQUIRED: {out}")
    v1 = json.loads(cases_v1.read_text(encoding="utf-8"))
    aud = {r["filename"]: r for r in json.loads(audit_path.read_text(encoding="utf-8"))["candidates"]}
    prof = {}
    for c in v1["cases"]:
        if sha256(Path(c["source"])) != c["sha256"]:
            raise ValueError(f"TARGET_DRIFT {c['alias']}")
        prof[c["alias"]] = pe_profile(Path(c["source"]))
    res = q2.assign({a: p["entries"] for a, p in prof.items()}, seed)
    cases = []
    for c in v1["cases"]:
        a = c["alias"]
        cat, fam, acc = res["assignment"][a]
        p, r = prof[a], aud[c["filename_EVALUATOR_ONLY"]]
        declared = p["declared_imports"]
        if cat == "INITIAL_EVIDENCE_SUFFICIENT":
            ref = {"answer": f"{p['pe_kind']} {p['machine']} {'DLL' if p['is_dll'] else 'EXE'} (static parse); detector "
                             "label/score = whatever the frozen initial CaseState records (not computed pre-inference)",
                   "unknowns": "runtime behaviour; detector score is not a calibrated probability"}
            flags = dict(initial_sufficient=True, tool_useful=False, retrieval_necessary=False,
                         definitive_possible=True,
                         abstention="Not needed; a tool call is unnecessary (judged under R3), not an error per se")
        elif cat == "NOT_STATIC_ANSWERABLE":
            netfam = q2.access_class("NETWORK", p["entries"])
            ref = {"answer": "UNANSWERABLE statically: declared imports can at most show a declared network "
                             "capability, never actual runtime communication",
                   "declared_network_references": netfam["relevant_entries"],
                   "network_access_class": netfam["class"]}
            flags = dict(initial_sufficient=False, tool_useful="LIMITED (declared capability only)",
                         retrieval_necessary=False, definitive_possible=False,
                         abstention="REQUIRED: state that static evidence cannot establish runtime behaviour")
        else:
            ref = {"answer": f"Declared {fam} references in the full import table: {len(acc['relevant_indices'])}",
                   "relevant_entries": acc["relevant_entries"], "relevant_indices": acc["relevant_indices"],
                   "in_initial_tool_projection": acc["in_projection"],
                   "reachable_by_2_sequential_reads": acc["reachable_sequential"],
                   "committed_only_nonsequential": acc["committed_nonsequential"],
                   "never_committed": acc["inaccessible"], "declared_entries": declared,
                   "note": "Declared imports are capabilities, not runtime behaviour."}
            complete = "YES" if declared <= 64 else f"NO for a complete list ({declared} declared > 64 committed)"
            if cat == "IN_INITIAL_TOOL_PROJECTION":
                flags = dict(initial_sufficient=False, tool_useful=True, retrieval_necessary=False,
                             definitive_possible="YES for presence of the declared capability; complete list: " + complete,
                             abstention="Not appropriate for presence; any absence beyond what was read must be scoped")
            elif cat == "REACHABLE_BY_BOUNDED_RETRIEVAL":
                flags = dict(initial_sufficient=False, tool_useful=True, retrieval_necessary=True,
                             definitive_possible="YES for presence only if the right page(s) are read within budget; "
                                                 "complete list: " + complete,
                             abstention="A scoped 'not seen in the entries read' with stated coverage is acceptable; "
                                        "claiming absence is a SCOPE_OVERCLAIM")
            else:
                flags = dict(initial_sufficient=False, tool_useful="LIMITED (absence within 64 committed only)",
                             retrieval_necessary=False, definitive_possible=False,
                             abstention="REQUIRED: 'not found in committed entries; remaining entries unknown'")
        cases.append({"alias": a, "source": c["source"], "sha256": c["sha256"],
                      "program_identity_EVALUATOR_ONLY": {"filename": c["filename_EVALUATOR_ONLY"],
                                                          "OriginalFilename": r["version"].get("OriginalFilename"),
                                                          "FileDescription": r["version"].get("FileDescription")},
                      "question_category": cat, "capability_family": fam,
                      "question_id": f"QV2_{cat}" + (f"_{fam}" if fam else ""),
                      "question_text": q2.question_text(cat, fam), "accessibility_class": cat,
                      "reference_EVALUATOR_ONLY": ref, **flags,
                      "true_label_EVALUATOR_ONLY": c["true_label_EVALUATOR_ONLY"], "label_basis": c["label_basis"]})
    man = {"track": "RAW_PE_E2E_BENIGN_CANDIDATE_HOLDOUT", "questions_version": q2.QUESTIONS_VERSION,
           "questions_sha256": q2.questions_sha256(), "seed": seed,
           "created_utc": datetime.now(timezone.utc).isoformat(),
           "supersedes_questions_of": cases_v1.name, "same_samples_and_aliases": True,
           "allocation": {k: res[k] for k in ("counts", "requested_target", "feasible_target", "shortfall_rule",
                                              "samples_with_option", "requested_target_met", "feasible_target_met")},
           "budget_model": q2.__doc__.strip(), "status": "CANDIDATE_PENDING_OWNER_APPROVAL", "confirmatory": "NOT_RUN",
           "inputs_used": "static parse of approved PEs + analyzer/projection/retrieval/turn limits; no model or Judge output",
           "cases": cases}
    out.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    return man
