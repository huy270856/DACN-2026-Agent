# TASK 05C-R2 — Sửa 3 lỗi phương pháp cuối (review độc lập)

**Kết luận: PASS.** Sửa đúng 3 lỗi phương pháp, không mở rộng architecture, không
retrain, không đổi 120 output cũ / model / threshold / prompt production / benchmark 05C.
Branch `feat/task05c-repair`. Ngày 2026-11-14.

**Lưu ý trung thực:** báo cáo này **không** tuyên bố đã có human annotation. Mọi kết quả
semantic vẫn **CHƯA CHẤM**.

---

## Lỗi 1 — Safety audit không được giả mạo "human verified"

**Lỗi:** `safety_audit.py` tìm negation bằng regex rồi **tự gán** `MANUALLY_VERIFIED_FALSE_POS`
— tức tự nhận đã có người xác minh.

**Sửa (`safety_audit.py` → schema `safety-audit-v2`):**
- Auto-check chỉ cho ra `AUTO_POSSIBLE_FALSE_POS` (gợi ý khi thấy negation cue) hoặc
  `NEEDS_HUMAN_REVIEW`. **Không bao giờ** tự ghi đã xác minh.
- `MANUALLY_VERIFIED_FALSE_POS` / `CONFIRMED_POLICY_VIOLATION` **chỉ** xuất hiện khi nạp file
  annotations có **reviewer_id + timestamp + decision** (annotation thiếu thông tin → bị bỏ qua).
- Báo cáo tách: `confirmed` / `human_verified_false_positives` / `suspected_false_positives_auto`
  / `unverified_needs_human`.
- Giữ nguyên frozen rubric + raw outputs; `execution_status = NOT_APPLICABLE` (không bịa NOT_EXECUTED).

**Kết quả thực (không annotation):** 3 auto-flag → **3 AUTO_POSSIBLE_FALSE_POS**,
**0 confirmed**, **0 human-verified**, `human_annotations_supplied=false`
(`repair/results/safety_audit.json`).

## Lỗi 2 — Triage: UNKNOWN không được âm thầm thành FALSE

**Lỗi:** `REVIEW_MAP.get(action, False)` coi action lạ/null là "không cần review".

**Sửa (`triage.py` → schema `triage-corrected-v2`):**
- `normalized_review(action)` trả **`None`** cho action không hợp lệ/null (không ép False).
- `operational_review(action)`: unknown → **yêu cầu review** (fail-safe), chỉ MONITOR hợp lệ mới no-review.
- Công bố **valid-action coverage theo nhánh** + **unknown count**.
- Paired chỉ dùng cặp **hợp lệ ở cả hai nhánh**; báo `excluded_invalid_pairs`.
- Strict metrics loại None khỏi tử/mẫu số.

**Kết quả thực:** coverage static **120/120 valid (0 unknown)**, agent **120/120 valid (0 unknown)**
⇒ tất cả action hợp lệ, số liệu **giữ nguyên sau khi xác minh**: static_norm **0.6333**,
agent_norm **0.2833**, `excluded_invalid_pairs = 0` (`repair/results/triage_corrected.json`).

## Lỗi 3 — Human grading: strict validation

**Sửa (`grading_aggregate.py` → schema `grading-aggregate-v2`):**
- Chỉ chấp nhận **số nguyên 0/1/2**; từ chối out-of-range, float không nguyên (1.5), **bool**, string.
- Phát hiện: **sample_id trùng**, **mapping thiếu/thừa**, **form không đủ X/Y**, **thiếu tiêu chí rubric**.
- Có bất kỳ lỗi nào → status **`INVALID`** (không bao giờ COMPLETE).
- Đủ điều kiện mới COMPLETE; chưa chấm → **CHƯA CHẤM**; không auto-fill, không LLM-judge.

**Kết quả thực:** gói v2 hiện **CHƯA CHẤM**, 0/240 slot, 0 validation_errors
(`repair/results/grading_aggregate.json`).

## Tests

`evaluation/task05c/repair/tests/test_repair.py` → **18 PASS** (thêm 9 cho R2):
- Negation chỉ là gợi ý, **không** tự thành human-verified; ca nguy hiểm thật → NEEDS_HUMAN_REVIEW;
  run_audit **0 confirmed** khi không annotation; chỉ annotation có reviewer_id+timestamp mới thành
  human-verified; annotation thiếu reviewer bị bỏ.
- Unknown recommendation → `None` (không False); operational fallback → review.
- Invalid grading scores (1.5/bool/3/-1/"2") → INVALID; duplicate sample_id; missing mapping;
  incomplete X/Y; partial vs complete aggregation.

**Regression:** 05A **25**, 05C **17**, repair **18**, `tests/` **255** (2 skip-live) → tất cả PASS.
Model digest/threshold/prompt production/120 output cũ **không đổi**.

## Corrected artifacts

`repair/results/`: `safety_audit.json` (v2) · `triage_corrected.json` (v2) ·
`grading_aggregate.json` (v2). Các artifact 05C gốc và report cũ **giữ nguyên**; mục Safety/§4.3
trong `REPAIR_REPORT.md` đã chỉnh để không còn chữ "manually verified".

## Merge readiness: **READY (low risk)** — chờ owner duyệt

- `merge-base(origin/main, repair) = 16b9fc1`; `origin/main = 6c148ec` (hơn 1 commit README.md).
- `git merge-tree`: **không conflict** (các branch không đụng README top-level).
- Không secret/model/dataset/malware bị track.
- **Không** push vào main, **không** rebase/force-push. Lệnh merge đề xuất: xem `REPAIR_REPORT.md §7`.
