"""Unit tests for the post-freeze SUPPLEMENTARY classifier (no model, no I/O beyond tmp)."""
import json

from evaluation.task07a import supplementary_v1 as sup


def test_classify_statuses():
    assert sup.classify({"final": {"x": 1}, "turns": []}) == "COMPLETED_FINAL"
    assert sup.classify({"final": None, "failure": "Ollama inference failed: URLError: x", "turns": []}) == "INFRA_OLLAMA_ERROR"
    assert sup.classify({"final": None, "failure": "Ollama returned empty content (thinking_chars=5, done_reason=length, eval_count=9)",
                         "turns": []}) == "MODEL_OUTPUT_TRUNCATION"
    assert sup.classify({"final": None, "failure": "VALIDATION_REPAIR_EXHAUSTED",
                         "turns": [{"meta": {"done_reason": "length"}}]}) == "MODEL_OUTPUT_TRUNCATION"
    assert sup.classify({"final": None, "failure": "MODEL_REQUESTED_MORE_EVIDENCE", "turns": []}) == "MODEL_INCOMPLETE"


def test_slot_status_not_run_blocked_and_declared(tmp_path):
    d = tmp_path / "V1_s42"
    d.mkdir()
    assert sup.slot_status(d, "sample_0001", {"ollama": {"status": "UNAVAILABLE"}})["run_status"] == "NOT_RUN_BLOCKED"
    (d / "cases.json").write_text(json.dumps([]), encoding="utf-8")
    assert sup.slot_status(d, "sample_0008", {"ollama": {"status": "AVAILABLE"}})["run_status"] == "INFRA_INTERRUPTED"


def test_think_regex():
    m = sup.THINK_RE.search("Ollama returned empty content (thinking_chars=42912, done_reason=length, eval_count=12288)")
    assert m and m.groups() == ("42912", "length", "12288")
