# TASK 07C — EVALUATION_LOG (append-only)

## 2026-11-28 — Quyết định Owner (qua Planner)

- Plan: `research/agent_architecture_review/PLAN_TASK07C.md`; branch `feat/task07c-absence-grounding` từ `ee5583b`.
- Authorization:
  - `DACN_OWNER_07C_DEV_GO`: S2 smoke và debug DEV.
  - `DACN_OWNER_07C_EVAL_GO`: S4 eval 40 run; chỉ dùng sau khi review PASS bản freeze, do Owner chạy ngoài session.
- Chỉ sửa lỗi core; không push.

## 2026-11-28 — S0/S1

- S0 `ef4f62a` (plan, challenge logs, CLAUDE.md). S1 `c3193f3`: ledger, contract investigation-v4.1,
  verifier `check_absence_claims`, coverage summary ở lượt final, arm `V4_1`, metrics `task07b-metrics-v2`.
  Full regression 872 passed / 0 failed / 4 skipped.

## 2026-11-28 — S2: DEV smoke 2 case (V4_1 s42, `results/dev_smoke/V4_1_s42_r1`, DACN_OWNER_07C_DEV_GO)

- Ollama 0.40.16 headless (PID 18000, Planner kiểm). 2/2 FINISHED_FLAGGED, isolation PASS, cả hai trích đúng entry liên quan.
- sample_0010: final lần 1 có free-text absence → repair → lần 2 dùng ledger: `Winhttp.dll`@Q1(INDEX) **accepted**;
  `ICMP`@Q1 rejected (OUT_OF_SCOPE); câu free-text vẫn giữ nguyên → `free_text_absence_rejected`.
- sample_0012: dùng hết lượt (5 query) → FORCED_FINAL không còn lượt repair; 2 câu free-text absence
  ("does not import CreateFile, ReadFile, WriteFile ... zero matches") bị reject; `absence_claims=[]`.
- Dấu hiệu: model **có** dùng ledger khi được repair, nhưng vẫn viết absence bằng văn bản tự do (kể cả câu
  có phạm vi "in the currently viewed entries"), và lượt FORCED_FINAL không có repair. Đã báo Planner, không
  tự lặp debug.

## 2026-11-28 — Quyết định Planner sau S2 (trong phạm vi plan) và smoke lần 2

- (1) Một lượt repair **riêng** cho rejection absence, kể cả ở FORCED_FINAL; chỉ sửa final (không tool/query);
  trace `absence_repair_used`; tính vào budget token (thêm đúng 1 slot lượt chỉ khi đang chờ repair này).
- (2) Câu free-text absence được giữ khi đủ 3 điều kiện: khớp `SCOPE_RE` (07A), không có từ deny-list
  (`BROAD_RE`), nêu tên API/DLL cụ thể (`API_TOKEN_RE`). Mọi câu khác vẫn reject. SYSTEM_41 thêm câu ưu tiên
  absence_claims. Test thêm; full regression 879 passed / 0 failed / 4 skipped.
- Smoke lần 2 `results/dev_smoke_2/V4_1_s42_r2` (thư mục `..._r1` trong dev_smoke_2 là prepare hỏng do trùng tên
  staging runtime với dev_smoke, không có run; giữ nguyên):
  - sample_0010: repair absence dùng; lần 2 vẫn câu free-text rộng ("No HTTP or ICMP-specific APIs were observed in
    the viewed entries") → reject (từ "APIs" + họ HTTP/ICMP không cụ thể). Trích đúng WS2_32 entries.
  - sample_0012: FORCED_FINAL → repair absence chạy được (thêm 1 lượt FINAL). Lần 2: **5/5 absence_claims accepted**
    (prefix Create/Read/Write/Open/Move @Q2–Q6, đều exhausted), nhưng model vẫn lặp câu free-text rộng → reject.
- Nhận định: cơ chế ledger + repair hoạt động (model chuyển được absence sang absence_claims), nhưng model
  không bỏ câu free-text rộng dù đã được nhắc. Không phải vấn đề kiến trúc mới (cùng hiện tượng S2 lần 1).
