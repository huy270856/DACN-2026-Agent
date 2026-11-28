"""TASK 07C rev 2: trusted renderer for investigation-v4.2 structured finals (Vietnamese report).

Quotes model statements VERBATIM and labels them as model-authored; renders accepted absence claims only
from their ledger scope; renders coverage from the trusted ledger. It never creates, completes or
rewrites a claim (CLAUDE.md §3). Rejected absence claims are listed as rejected, not as facts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

STATUS_VI = {"ANSWERED": "Đã trả lời", "PARTIALLY_ANSWERED": "Trả lời một phần",
             "NOT_STATICALLY_ANSWERABLE": "Không trả lời được bằng phân tích tĩnh"}
REL_VI = {"AGREES": "phù hợp với", "CONFLICTS": "mâu thuẫn với", "NOT_INFORMATIVE": "không cho thêm thông tin về"}


def _scope(e: Dict[str, Any]) -> str:
    if e["kind"] == "INDEX":
        return f"{e['id']}: chỉ mục DLL của bảng import"
    if e["kind"] == "DLL":
        return f"{e['id']}: toàn bộ entry của {e['value']} ({e['returned']}/{e['total_matches']})"
    return f"{e['id']}: tên bắt đầu bằng '{e['value']}' ({e['returned']}/{e['total_matches']})"


def render(final: Dict[str, Any], ledger: List[Dict[str, Any]], absence: Optional[Dict[str, Any]],
           resolved_sources: List[Dict[str, Any]], detector: Optional[Dict[str, Any]], question: str) -> str:
    lit = {s["handle"]: s.get("literal") or s.get("evidence_id") for s in resolved_sources}
    led = {e["id"]: e for e in ledger}
    out = ["# Báo cáo điều tra tĩnh (investigation-v4.2, do trusted code dựng từ các trường có cấu trúc)", "",
           f"**Câu hỏi:** {question}", "",
           f"**Trạng thái trả lời (model chọn):** {STATUS_VI.get(final.get('answer_status'), final.get('answer_status'))}", ""]
    if detector:
        rel = (final.get("detector_relation") or {}).get("value")
        out += [f"**Detector (ngữ cảnh, không phải bằng chứng):** nhãn {detector.get('predicted_label')}, raw score "
                f"{detector.get('raw_score')} (KHÔNG phải xác suất). Model đánh giá bằng chứng tĩnh "
                f"{REL_VI.get(rel, rel)} nhãn này.", ""]
    dropped = set((absence or {}).get("free_text_absence_rejected", []))
    out.append("## Phát hiện (nguyên văn do model viết)")
    kept = [f for f in final.get("findings", []) if f["statement"] not in dropped]
    if not kept:
        out.append("- (không có phát hiện có mặt nào được giữ)")
    for f in kept:
        refs = ", ".join(f"{h} = {lit.get(h, h)}" for h in f.get("refs", []))
        out.append(f"- [{f['kind']}] \"{f['statement']}\" — nguồn: {refs} *(model-authored)*")
    out += ["", "## Khẳng định vắng mặt (đã kiểm theo ledger)"]
    acc = (absence or {}).get("accepted", [])
    for a in acc:
        out.append(f"- Không thấy `{a['api_or_prefix']}` trong phạm vi {_scope(led[a['scope_ref']])}, đã đọc hết. "
                   "Điều này không loại trừ API được resolve động.")
    if not acc:
        out.append("- (không có khẳng định vắng mặt nào được chấp nhận)")
    for r in (absence or {}).get("rejected", []):
        out.append(f"- BỊ LOẠI (không phải dữ kiện): `{r['api_or_prefix']}` @ {r['scope_ref']} — {r['reason']}")
    if dropped:
        out += ["", "## Nội dung bị loại (không phải dữ kiện; PLAN §2 mục 4)"]
        for f in final.get("findings", []):
            if f["statement"] in dropped:
                out.append(f"- \"{f['statement']}\" — lý do: statement dạng phủ định/vắng mặt không được phép trong "
                           "investigation-v4.2; absence chỉ hợp lệ qua absence_claims đã kiểm theo ledger")
    out += ["", "## Phạm vi đã xem / chưa xem (trusted ledger)"]
    for e in ledger:
        out.append(f"- {_scope(e)} — {'đã đọc hết' if e['exhausted'] else 'CHƯA đọc hết'}")
    out.append("- Mọi phần khác của bảng import: CHƯA xem.")
    for k, title in (("evidence_needed", "Bằng chứng còn thiếu (model viết)"),
                     ("next_verification", "Bước kiểm chứng tiếp theo (model viết)")):
        if final.get(k):
            out += ["", f"## {title}"] + [f"- \"{x}\"" for x in final[k]]
    out += ["", "_Khai báo import là capability tĩnh, không phải hành vi runtime. Báo cáo này không thực thi hay "
            "cách ly (containment) gì._"]
    return "\n".join(out)


UNRESOLVED_VI = {"NOT_STATIC_DETERMINABLE": "không xác định được bằng phân tích tĩnh",
                 "NOT_COVERED": "chưa được xem (ngoài phạm vi đã phủ)",
                 "INSUFFICIENT_EVIDENCE": "chưa đủ bằng chứng"}


def render_v43(final, ledger, absence, resolved_sources, detector, question) -> str:
    """investigation-v4.3: same template as v4.2 plus model-authored `unresolved` items (topic verbatim, enum reason)."""
    out = render(final, ledger, absence, resolved_sources, detector, question).split("\n")
    i = next((k for k, line in enumerate(out) if line.startswith("## Phạm vi đã xem")), len(out))
    block = ["## Câu hỏi còn mở (model viết; lý do theo enum)"]
    block += [f"- \"{u['topic']}\" — {UNRESOLVED_VI[u['reason']]} ({u['reason']})" for u in final.get("unresolved", [])] \
        or ["- (không có)"]
    return "\n".join(out[:i] + block + [""] + out[i:])
