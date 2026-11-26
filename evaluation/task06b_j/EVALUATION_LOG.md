# TASK 06B-J — Evaluation log (append-only)

Mỗi sự kiện có ảnh hưởng tới tính hợp lệ của lượt chấm hoặc chạy thử nghiệm đều được ghi vào
đây. Không xóa mục cũ.

## 2026-11-26 — DEV calibration `06BJ-DEV-CAL-v1`, Judge `INTERACTIVE_LLM_JUDGE_BLIND_BATCH`

1. **Track A, session đầu tiên: ABORTED, không tính là grading pass.** Theo lời owner: owner
   vô tình paste toàn bộ `JUDGE_RUNBOOK.md` vào session (runbook nhắc tới mapping
   evaluator-only, calibration key, probe và các bước unblind). Session tự phát hiện
   contamination và xác nhận chưa đọc hay ghi grading item nào, chưa tạo judgment nào. Không
   có file response nào từ session này trong kit (đã kiểm: `responses/` chỉ chứa output của
   session hoàn tất). Không có transcript của session bị hủy trong repo; nguồn duy nhất cho mục
   này là báo cáo của owner.
2. **Track A, session hoàn tất:** session mới, 19/19 item và `_session_note.json`. Các file
   response được ghi lúc 11:28 theo giờ máy (mtime của thư mục `responses/`).
3. **Track B, session hoàn tất:** session mới, 16/16 item và `_session_note.json`.
4. **Metadata model:** chỉ có `self_reported_model = "Claude Opus 5.5 (claude-opus-5-5)"` trong
   session note, ghi là `self_reported_model_UNVERIFIED`. Owner không cung cấp output
   `/model` hay session ID, nên các trường `model`, `model_version_or_digest`, `session_id` =
   `UNKNOWN`.
5. **Import (`judge_kit import`):**
   - Cả hai track `COMPLETE_VALID`, không có problem nào.
   - Raw SHA-256 khớp giữa kit và bản sao trong repo.
   - SHA của package view khớp với `kit_manifest`. Rubric `task06b-j-rubric-v1`
     (`9fa271b8…`).
   - Không có response bọc fence; `human_verified=false`.
   - Kiểm bổ sung ngoài validator: 35 `additional_claims` (Track A) có tag và evidence ID
     hợp lệ, đều có rationale.
6. **Lock** được thực hiện trước khi đọc `EVALUATOR_ONLY/mapping.json` và
   `calibration_key.json` (xem `results/dev/judge_cal_v1/LOCK.json`).
7. Sau lock: `analysis.json` và `calibration_summary.json` được tạo; `CALIBRATION_REPORT.md` được viết. Phần so sánh checker/evaluator cho Track B trong `analysis.json` **không có ý nghĩa** (claim verdict ở Track B là tùy chọn), nên chỉ dùng số liệu Track A trong `calibration_summary.json`.
8. Không có điểm nào bị sửa, tự điền hay chấm lại. Đề xuất rubric v2 và questions v2 đang chờ owner duyệt; v1 cùng toàn bộ judgment v1 được giữ nguyên.
