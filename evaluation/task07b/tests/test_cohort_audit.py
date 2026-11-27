"""TASK 07B cohort_audit unit tests (synthetic audit docs; no Authenticode/LIEF sweep, no model)."""
import json

import pytest

from evaluation.task07b import cohort_audit as CA


def test_explicit_exclusions_cover_prior_tasks():
    ex = CA.excluded_programs()
    for n in ("robocopy.exe", "compact.exe", "tracert.exe", "findstr.exe", "whoami.exe", "where.exe"):
        assert n in ex, n
    # 06B-J holdout sources (tracked manifests mention System32 paths) are excluded by name too.
    man = json.loads((CA.ROOT / "evaluation/task06b_j/results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json")
                     .read_text(encoding="utf-8"))
    for c in man["cases"]:
        assert c["source"].split("\\")[-1].lower() in ex


def test_tracked_shas_include_06bj_cohort():
    shas = CA.tracked_shas()
    man = json.loads((CA.ROOT / "evaluation/task06b_j/results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json")
                     .read_text(encoding="utf-8"))
    assert all(c["sha256"] in shas for c in man["cases"])


def test_relevant_exact_lexicon():
    entries = [{"library": "KERNEL32.dll", "symbol": "CreateFileW", "ordinal": None},
               {"library": "KERNEL32.dll", "symbol": "CreateFileMappingW", "ordinal": None},  # not a file API by lexicon
               {"library": "WS2_32.dll", "symbol": None, "ordinal": 115},
               {"library": "ADVAPI32.dll", "symbol": "OpenProcessToken", "ordinal": None}]
    assert CA.relevant(entries, "FILE") == [(0, "KERNEL32.dll!CreateFileW")]
    assert CA.relevant(entries, "NETWORK") == [(2, "WS2_32.dll!#115")]
    assert CA.relevant(entries, "PROCESS") == []


def _row(name, fams):
    return {"filename": name, "source": f"C:\\Windows\\System32\\{name}", "sha256": CA._rank(name)[:64],
            "eligible": True, "declared_imports": 100, "version": {"OriginalFilename": name},
            "family_relevant": {f: {"indices": fams.get(f, []), "literals": [f"X.dll!{f}{i}" for i in fams.get(f, [])]}
                                for f in CA.FAMILIES}}


def _doc(n_beyond=6, n_low=6, n_plain=20):
    rows = [_row(f"b{i}.exe", {"FILE": [60 + i]}) for i in range(n_beyond)]
    rows += [_row(f"l{i}.exe", {"PROCESS": [3 + i]}) for i in range(n_low)]
    rows += [_row(f"p{i}.exe", {}) for i in range(n_plain)]
    return {"candidates": rows}


def test_allocation_targets_and_beyond_v3():
    a = CA.allocate(_doc())
    from collections import Counter
    cnt = Counter(c["accessibility_class"] for c in a["cases"])
    assert cnt == CA.TARGETS and not a["notes"]
    rp = [c for c in a["cases"] if c["accessibility_class"] == "RELEVANT_PRESENT"]
    assert sum(c["reference_EVALUATOR_ONLY"]["beyond_v3_reach"] for c in rp) == CA.MIN_BEYOND_V3
    assert sum(not c["reference_EVALUATOR_ONLY"]["beyond_v3_reach"] for c in rp) == CA.WITHIN_V3
    assert len({c["source"] for c in a["cases"]}) == 20  # each program once
    assert [c["alias"] for c in a["cases"]] == [f"sample_{i:04d}" for i in range(1, 21)]
    ra = [c for c in a["cases"] if c["accessibility_class"] == "RELEVANT_ABSENT"]
    assert all(not c["reference_EVALUATOR_ONLY"]["relevant_entries"] for c in ra)
    assert CA.allocate(_doc()) == a  # deterministic


def test_allocation_shortfall_recorded_not_hidden():
    a = CA.allocate(_doc(n_beyond=2))
    assert any("Only 2 RELEVANT_PRESENT" in n for n in a["notes"])


def test_question_text_and_no_label_in_question():
    a = CA.allocate(_doc())
    for c in a["cases"]:
        assert "benign" not in c["question_text"].lower() and c["true_label_EVALUATOR_ONLY"] == "benign"
        assert c["question_text"]


def test_make_cases_write_once(tmp_path):
    p = tmp_path / "audit.json"
    p.write_text(json.dumps(_doc()), encoding="utf-8")
    out = tmp_path / "cases.json"
    CA.make_cases(p, out)
    with pytest.raises(FileExistsError):
        CA.make_cases(p, out)
    with pytest.raises(FileExistsError):
        CA.audit(out)


def test_within_v3_shortfall_recorded():
    a = CA.allocate(_doc(n_low=1))
    assert any("Only 1 RELEVANT_PRESENT cases with first relevant index < 48" in n for n in a["notes"])
