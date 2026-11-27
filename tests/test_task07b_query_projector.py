"""TASK 07B S3: query service and projector v4 (unit; synthetic committed state; no model)."""
import builtins
import copy
import json

import pytest

from d0.validate import digest
from investigation_v4 import imports_table_adapter as A, imports_table_tool as T, query as Q, projector as P

SHA = "a" * 64


def _payload():
    table, lookup = A.load_ordinal_table()
    blocks = [("KERNEL32.dll", False, [(f"Get{i:02d}Thing", None) for i in range(20)] + [("CreateFileW", None)]),
              ("WS2_32.dll", False, [(None, 115), (None, 11), (None, 60000)]),
              ("msvcrt.dll", False, [("fopen", None), ("fclose", None)]),
              ("kernel32.DLL", True, [("GetTickCount", None), ("TerminateProcess", None)])]
    total = sum(len(b[2]) for b in blocks)
    p = A.build_payload(blocks, total, "LIEF test", SHA, table, lookup, 1024)
    T.check_payload(p)
    return p


def _state(payload=None, revision=5):
    payload = payload or _payload()
    ev = [{"evidence_id": "EV-pred", "facet": "static.pe_malware_prediction", "status": "SUCCESS",
           "value": {"predicted_label": "benign", "raw_score": 0.002, "threshold": 0.83, "model_sha256": "f" * 64,
                     "extractor": {"name": "x"}}},
          {"evidence_id": "EV-hdr", "facet": "pe_header", "status": "SUCCESS",
           "value": {"pe_kind": "PE32+", "architecture": "x64", "is_dll": False, "machine_code": 34404}},
          {"evidence_id": "EV-fmt", "facet": "format", "status": "SUCCESS", "value": {"format": "PE", "is_dll": False}},
          {"evidence_id": "EV-meta", "facet": "metadata", "status": "SUCCESS", "value": {"path": "C:/secret/x.exe"}},
          {"evidence_id": "EV-tab", "facet": T.FACET, "status": "SUCCESS", "tool_run_id": "RUN-1", "value": payload}]
    return {"case_id": "CASE-1", "revision": revision, "evidence": ev,
            "target_ref": {"verified_digest": {"value": SHA}, "kind": "FILE"}}


# ----------------------------------------------------------------------------- query
def test_dll_query_merges_blocks_case_insensitive_and_pages():
    s = _state()
    r = Q.query_imports(s, "DLL", "kernel32.dll", 0)
    assert r["total_matches"] == 23  # 21 normal + 2 delay, one merged DLL
    assert len(r["entries"]) == 16 and r["next_page"] == 1
    r1 = Q.query_imports(s, "DLL", "KERNEL32.DLL", 1)
    assert len(r1["entries"]) == 7 and r1["next_page"] is None
    assert {e["delay"] for e in r1["entries"]} == {False, True}
    with pytest.raises(Q.QueryError) as e:
        Q.query_imports(s, "DLL", "KERNEL32.dll", 2)
    assert e.value.code == "QUERY_PAGE_OUT_OF_RANGE"
    idx = Q.list_import_index(s)
    k = [d for d in idx["dlls"] if d["dll"].lower() == "kernel32.dll"]
    assert len(k) == 1 and k[0]["declared_count"] == 23 and k[0]["blocks"] == 2 and k[0]["has_delay_block"]


def test_unknown_dll_rejected():
    with pytest.raises(Q.QueryError) as e:
        Q.query_imports(_state(), "DLL", "advapi32.dll")
    assert e.value.code == "QUERY_UNKNOWN_DLL"


def test_prefix_valid_invalid_and_resolved_symbol():
    s = _state()
    r = Q.query_imports(s, "SYMBOL_PREFIX", "wsastart")
    assert [x["resolved_symbol"] for x in r["entries"]] == ["WSAStartup"] and r["entries"][0]["symbol"] is None
    assert Q.query_imports(s, "SYMBOL_PREFIX", "fop")["total_matches"] == 1
    for bad in ("", "C", "Ge", "x" * 65, "Get*", "Get.", "Get Thing", "(?i)get", "Get\n"):
        with pytest.raises(Q.QueryError) as e:
            Q.query_imports(s, "SYMBOL_PREFIX", bad)
        assert e.value.code == "QUERY_BAD_PREFIX"
    with pytest.raises(Q.QueryError):
        Q.query_imports(s, "REGEX", "Get")
    with pytest.raises(Q.QueryError):
        Q.query_imports(s, "SYMBOL_PREFIX", 123)


def test_broad_prefix_never_returns_whole_table():
    s = _state()
    r = Q.query_imports(s, "SYMBOL_PREFIX", "Get")
    assert r["total_matches"] == 21 and len(r["entries"]) == 16 and r["next_page"] == 1


def test_bad_page_types():
    for page in (-1, True, 1.0, "0", None):
        with pytest.raises(Q.QueryError):
            Q.query_imports(_state(), "SYMBOL_PREFIX", "Get", page)


def test_binding_filled_by_trusted_code_and_mismatch_rejected():
    s = _state()
    r = Q.query_imports(s, "SYMBOL_PREFIX", "Get")
    assert r["case_id"] == "CASE-1" and r["case_revision"] == 5 and r["target_sha256"] == SHA
    assert r["value_sha256"] == digest(s["evidence"][-1]["value"]) and r["tool_run_id"] == "RUN-1"
    assert r["trust_level"] == "UNTRUSTED_CONTENT" and r["new_evidence_created"] is False
    b = Q.binding(s, Q.table_evidence(s))
    for k, v in (("case_id", "CASE-2"), ("case_revision", 4), ("target_sha256", "b" * 64), ("value_sha256", "c" * 64)):
        with pytest.raises(Q.QueryError) as e:
            Q.query_imports(s, "SYMBOL_PREFIX", "Get", 0, expected_binding=dict(b, **{k: v}))
        assert e.value.code == "QUERY_BINDING_MISMATCH"


def test_no_table_wrong_status_or_foreign_target():
    s = _state()
    s["evidence"][-1]["status"] = "FAILED"
    with pytest.raises(Q.QueryError, match="QUERY_NO_COMMITTED_TABLE"):
        Q.list_import_index(s)
    s = _state()
    s["target_ref"]["verified_digest"]["value"] = "b" * 64
    with pytest.raises(Q.QueryError, match="QUERY_TARGET_MISMATCH"):
        Q.query_imports(s, "SYMBOL_PREFIX", "Get")
    s = _state()
    s["evidence"][-1]["facet"] = "static.pe_imports_detail"
    with pytest.raises(Q.QueryError):
        Q.query_imports(s, "SYMBOL_PREFIX", "Get")


def test_query_never_touches_files(monkeypatch):
    s = _state()
    monkeypatch.setattr(builtins, "open", lambda *a, **k: pytest.fail("file access forbidden"))
    Q.list_import_index(s)
    Q.query_imports(s, "SYMBOL_PREFIX", "Get")
    Q.read_table(s, 16)


def test_read_table_offsets():
    s = _state()
    r = Q.read_table(s, 16)
    assert [e["index"] for e in r["entries"]] == list(range(16, 28)) and r["next_offset"] is None
    for bad in (-16, 8, 32, True, "0"):
        with pytest.raises(Q.QueryError):
            Q.read_table(s, bad)


def test_coverage_merged_per_dll():
    v = _payload()
    cov = {c["dll"].lower(): c for c in Q.coverage(v, {0, 1, 26, 27})}
    assert cov["kernel32.dll"] == {"dll": "KERNEL32.dll", "viewed": 4, "count": 23, "returned": 23}
    assert len([c for c in Q.coverage(v, set()) if c["dll"].lower() == "kernel32.dll"]) == 1


# ----------------------------------------------------------------------------- projector
def _build(state=None, **kw):
    state = state or _state()
    args = dict(question="Q?", handles=P.HandleMap(), viewed={}, index_listed=False, queries_run=[],
                queries_left=6, turns_left=8, available_actions=["ANSWER"], retrieval_mode="QUERY",
                max_context_chars=16000)
    args.update(kw)
    return P.build(state, **args)


def test_handles_stable_and_reverse_map():
    h = P.HandleMap()
    a = _build(handles=h)["facts"]
    b = _build(handles=h)["facts"]
    assert [e["handle"] for e in a["evidence"]] == [e["handle"] for e in b["evidence"]] == ["E1", "E2", "E3"]
    assert h.resolve("E1") == {"kind": "EVIDENCE", "evidence_id": "EV-hdr"}
    assert h.resolve("E3") == {"kind": "EVIDENCE", "evidence_id": "EV-tab"}
    assert h.resolve("I47") == {"kind": "IMPORT_ENTRY", "index": 47}
    for bad in ("E9", "I", "I01", "Ix", "X1", "EV-pred"):
        assert h.resolve(bad) is None
    assert h.to_trace() == {"E1": "EV-hdr", "E2": "EV-fmt", "E3": "EV-tab"}


def test_detector_context_has_no_handle_and_is_not_evidence():
    f = _build()["facts"]
    dc = f["detector_context"]
    assert set(dc) == {"predicted_label", "raw_score", "threshold", "note"} and "NOT a probability" in dc["note"]
    assert "handle" not in json.dumps(dc)
    assert all(e["kind"] != "static.pe_malware_prediction" for e in f["evidence"])


def test_noise_dropped_and_omitted_counted():
    text = _build()["user"]
    for leak in ("model_sha256", "extractor", "full_detail_ref", "C:/secret", "machine_code", "EV-", "inode"):
        assert leak not in text, leak
    assert _build()["facts"]["omitted"] == "1 collector facets omitted as not relevant"


def test_no_evaluator_only_fields_and_untrusted_wrapper():
    s = _state()
    s["evidence"].append({"evidence_id": "EV-x", "facet": "x", "status": "SUCCESS",
                          "value": {"relevant_entries_EVALUATOR_ONLY": ["a"], "true_label_EVALUATOR_ONLY": "benign"}})
    out = _build(s)
    assert "EVALUATOR_ONLY" not in out["user"] and "relevant_entries" not in out["user"]
    assert out["user"].startswith("UNTRUSTED_CASE_DATA\n") and out["user"].endswith("\nEND_UNTRUSTED_CASE_DATA")


def test_index_only_after_listing_and_viewed_imports_handles():
    s = _state()
    assert "import_index" not in _build(s)["facts"]
    viewed = {i: Q.entry_view(_payload(), i) for i in (21, 22)}
    f = _build(s, index_listed=True, viewed=viewed,
               queries_run=[{"by": "SYMBOL_PREFIX", "value": "ws", "page": 0, "total_matches": 1}])["facts"]
    assert {d["dll"] for d in f["import_index"]} == {"KERNEL32.dll", "WS2_32.dll", "msvcrt.dll"}
    assert [x["handle"] for x in f["viewed_imports"]] == ["I21", "I22"]
    assert f["viewed_imports"][0]["resolved_symbol"] == "WSAStartup"
    assert f["coverage"]["dlls_viewed"] == [{"dll": "WS2_32.dll", "viewed": 2, "count": 3, "returned": 3}]


def test_noq_mode_shows_no_index_or_dll_scent():
    f = _build(retrieval_mode="READ_TABLE", index_listed=True,
               queries_run=[{"offset": 0}], viewed={0: Q.entry_view(_payload(), 0)})["facts"]
    assert "import_index" not in f and "dlls_viewed" not in f["coverage"]
    assert f["coverage"]["reads_run"] == [0] and f["coverage"]["table_entries"] == 28


def test_context_budget_raises_not_truncates():
    with pytest.raises(ValueError, match="V4_CONTEXT_BUDGET"):
        _build(max_context_chars=200)


def test_full_viewed_budget_fits_default_limit():
    # 6 queries x 16 entries with long names stays under the default 16000-char budget.
    v = _payload()
    viewed = {i: dict(Q.entry_view(v, i % 28), library="api-ms-win-core-processthreads-l1-1-0.dll",
                      symbol="S" * 40) for i in range(96)}
    out = _build(viewed=viewed, index_listed=True)
    assert len(json.dumps(out["facts"])) < 16000
