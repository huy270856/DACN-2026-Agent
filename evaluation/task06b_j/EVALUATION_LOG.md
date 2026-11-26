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

## 2026-11-26 — Rubric v2, questions v2, calibration v2 preparation (owner-approved redesign)

9. Tạo `rubric_v2.py` (`task06b-j-rubric-v2`). v1 cùng mọi judgment, lock và mapping v1 được giữ nguyên. Validator mới đã được kiểm lại trên 2 file judgment v1 đã lock: vẫn hợp lệ (0 lỗi).
10. Questions v2 dựa trên accessibility tĩnh (không dùng output của model hay Judge). Phân bổ khả thi 2/6/4/4/4 so với target 4/4/4/4/4, theo quy tắc thiếu hụt khai báo trước (chỉ 2 mẫu có entry liên quan trong trang đầu).
11. Package calibration v2 lần đầu được dựng rồi **dựng lại trước khi giao** (chưa kit nào được dùng): cần thêm `access_limits` vào reference sheet để grader phân loại được `evidence_access`. Bản build bị thay thế chưa từng được chấm hay commit.
12. Đã export 4 kit (P1/P2 × Track A/B) ngoài repo, `kit_audit=PASS`. Developer **không** chạy Judge vì đã biết đáp án probe.

## 2026-11-26 — Calibration v2: import, lock, phân tích (lượt tổng hợp cuối)

13. Trên đĩa có 86 judgment và 4 session note. Cả 4 kit import `COMPLETE_VALID` (import chạy ngay trước khi owner yêu cầu "stop"; lượt này giữ nguyên output đó và kiểm lại hash). Model = UNKNOWN; chỉ có self-reported "Claude Opus 5.5", UNVERIFIED.
14. Session note P1-A ghi rằng response được ghi qua "a local helper script". Trong kit không còn file script nào, nên provenance chưa xác minh được. P1-A không bị loại, chỉ ghi nhận như một giới hạn.
15. Lock (`judge_cal_v2/LOCK.json`) trước khi mở mapping. Quy tắc dừng đã khóa được áp đúng nguyên văn; R1 (0.75), R5 (0.667, n=3), R8 (0.733) = UNRELIABLE. Không sửa rubric, không mở v3, không thêm probe hay phiên Judge.
16. Khuyến nghị CONDITIONAL GO (CALIBRATION_V2_REPORT §10). Confirmatory chưa chạy.

## 2026-11-26 — CONFIRMATORY AUTHORIZATION và thực thi

17. **Owner authorization:** `DACN_PROJECT_OWNER_06BJ_CONDITIONAL_GO` (CONDITIONAL GO).
    - Phạm vi: **một** lượt confirmatory đóng băng của protocol 20 case × 3 arm (A static, B v3.4 no-tool, C v3.4 tool-enabled), questions v2 (2/6/4/4/4).
    - Primary: verdict mức claim, R2, R3, R4, R6, R7, cùng metrics tất định.
    - Exploratory: R1, R5, R8, R9 và `evidence_access` do Judge gán.
    - Owner đã chấp nhận các giới hạn ở CALIBRATION_V2_REPORT §10.
    - Phân loại self-corroboration do **AI reviewer** đề xuất (không phải human adjudication): #4 AMBIGUOUS, #6 STRUCTURAL_ONLY, #5 NOT_SEMANTIC (giả định prediction dùng để triage). Judgment gốc và flag của checker giữ nguyên.
18. **Sai khác về lệnh:** REPORT §7 viết `--cases ...candidate_cases_v1_EVALUATOR_ONLY.json` (viết trước khi questions v2 được duyệt). Protocol được duyệt dùng questions v2, nên lượt chạy dùng `candidate_cases_v2_EVALUATOR_ONLY.json`. Mọi tham số khác giữ đúng như §7.
19. **Pre-inference:**
    - Manifest v2: 20 case, phân bổ 2/6/4/4/4, 0 SHA drift, questions sha khớp code, không có tên hay path trong câu hỏi.
    - Rubric v2 `dbb791cd…`. LightGBM `5db192ec…`, threshold 0.83219 (không đổi).
    - CFG giống 06B-R2.
    - Test 06B-J 45/45 (gồm MOCK isolation).
    - Ollama ban đầu **UNAVAILABLE** (không có process). Developer đã khởi động `ollama serve` với `OLLAMA_HOST=127.0.0.1:11434` (loopback). Sau đó `qwen3.5:4b` digest `d8b0f5e9…`, Ollama 0.40.16, giống DEV smoke và R2 DEBUG.
20. **Freeze** `results/confirmatory/run_v1/freeze.json`:
    - mode CONFIRMATORY, base 60f58b97, Ollama AVAILABLE, digest d8b0f5e9…, questions v2 c70aa8a6…, LightGBM 5db192ec…, 19 source hash.
    - Prepare 20/20; leakage context ban đầu: 0 hit tình cờ ở mọi case.
    - **Đính chính metadata (không sửa freeze):** trường `rubric_id` trong freeze ghi `task06b-j-rubric-v1`, vì runner import module rubric mặc định. Rubric không tham gia vào inference của Agent. Việc chấm confirmatory dùng rubric **v2** (`dbb791cd…`) như đã duyệt.
21. **Thực thi confirmatory run_v1:** đúng **một** lượt, runner exit 0. 40 lượt Agent (20 B + 20 C) và 20 report static A; isolation 40/40 PASS, target SHA 40/40, 0 leak tình cờ (mọi turn). Không chạy lại case nào. Stdout lưu ở `run_v1_stdout.log`.
22. Package chấm semantic `package_conf_p1/p2` (rubric v2 `dbb791cd…`, 2 seed). Đã export 4 kit ngoài repo, `kit_audit=PASS`. Developer **không** chấm. Trạng thái: SEMANTIC_GRADING_PENDING. Hướng dẫn: OWNER_FINAL_JUDGE_COMMANDS.md.
23. Bản `package_v1` (id `06BJ-CONF-v1`) dựng trước đó đã bị thay bằng `package_conf_p1/p2` để đặt tên pass rõ ràng; bản cũ chưa được giao, chấm hay commit.
24. **Quyết định của owner về push (2026-11-26):** repo là PUBLIC. Push lúc này sẽ công khai mapping evaluator-only, output thô từng arm của run_v1 và reference answer của holdout trong khi chấm semantic confirmatory còn PENDING. Owner chọn **hoãn push** tới khi 4 kit đã được import và lock. Các commit vẫn ở local; remote `origin/feat/task06b-real-multistep-investigation` vẫn ở `7da1302`.

## 2026-11-26 — Chấm semantic confirmatory và đóng TASK 06

25. Đã import 4 kit confirmatory (200 judgment + 4 session note), tất cả `COMPLETE_VALID`; hash và validate lại đều PASS. Model UNKNOWN (self-reported "Claude Opus 5.5", UNVERIFIED). `judge/LOCK.json` được tạo trước khi mở mapping.
26. Self-consistency trên confirmatory: R2 0.319 và R5 0.300 không ổn định; các tiêu chí khác ≥ 0.80. Phân loại primary/exploratory giữ nguyên như đã khóa; kết luận về R2 ghi là INCONCLUSIVE.
27. Kết luận TASK 06: INCONCLUSIVE, nghiêng về âm tính (CONFIRMATORY_REPORT §6). README gốc và TASK06_FINAL_REPORT §9 được cập nhật theo ủy quyền của owner.
