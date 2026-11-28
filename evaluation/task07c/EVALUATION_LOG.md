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

## 2026-11-28 — Owner chọn (B): investigation-v4.2 (structured final) + smoke lần 3

- Thực hiện PLAN §2b: `final_schema("4.2")` (bỏ `answer`; findings `{kind OBSERVED|INFERENCE, statement, refs≥1}`;
  `absence_claims`), `verifier.v42_view` / `statement_absence` (statement có phủ định → reject), repair absence
  1 lần (kể cả FORCED_FINAL), `renderer.py` (báo cáo tiếng Việt, statement nguyên văn, absence theo Qk, phạm vi từ
  ledger), arm `V4_2`, metrics `task07b-metrics-v3` (M4 v4.2 chấm trên statement). v4.0/v4.1 giữ nguyên.
  Test mới 11; full regression 890 passed / 0 failed / 4 skipped.
- Smoke `results/dev_smoke_3/V4_2_s42_r1` (DACN_OWNER_07C_DEV_GO, Ollama 0.40.16): 2/2 FINISHED_FLAGGED, isolation PASS.
  - sample_0010: repair absence dùng; lần 2 `WinHttp`@Q3 accepted, nhưng vẫn 1 statement phủ định ("The absence of
    WinHttp symbols ... indicates no HTTP communication capability") → reject. Các statement có mặt đúng (WS2_32).
  - sample_0012: FORCED_FINAL → repair; lần 2 `CreateFile/ReadFile/WriteFile` @Q2–Q4 **accepted**, nhưng 2/2
    statement vẫn là phủ định ("No import entries matching ... were found") → reject; không có statement có mặt nào.
- Nhận định: cùng hiện tượng — model dùng absence_claims đúng khi repair, nhưng **vẫn** viết absence vào chỗ dành
  cho văn bản (statement), kể cả khi contract chỉ cho phép statement có mặt. Đã báo Planner, không tự lặp.

## 2026-11-28 — Planner chọn P1 (PLAN §2 mục 4) + smoke lần 4

- P1: statement phủ định bị **loại** khỏi báo cáo render, liệt kê ở "Nội dung bị loại" kèm lý do, ghi trace
  `rendered_dropped_statements`; không sửa chữ; final vẫn FLAGGED. `findings` minItems 0; SYSTEM_42 thêm câu
  "để findings rỗng nếu không có phát hiện có mặt". Metrics v3: `v42_product` (M1b/M4 trên báo cáo render) và
  `v42_model_behaviour` (M4_raw, run/statement bị loại; DIAGNOSTIC, không ngưỡng). Test; full regression
  893 passed / 0 failed / 4 skipped.
- Smoke `results/dev_smoke_4/V4_2_s42_r4`: sample_0010 FINISHED_FLAGGED (1 statement phủ định bị loại; statement
  WS2_32 giữ); sample_0012 FINISHED (findings rỗng; 5/5 absence_claims accepted ở lần đầu). Không có lỗi khác.

## 2026-11-28 — S3: review FAIL (1 High) → sửa → re-review PASS → pre-run freeze

- Review a013d18: High = kind sai trong run_s4 (đã thêm `DEV_DIAGNOSTIC_CONSUMED_COHORT` + guard tree sạch);
  Medium: ghi "M4 render thỏa do cấu trúc", thêm `M4_raw_pre_repair`. Sửa ở `a9c6408`; re-review PASS.
- Commit tiếp theo là **pre-run freeze**. S4 do Owner chạy ngoài session:
  `run_s4.ps1 -FreezeCommit <SHA>` (authorization `DACN_OWNER_07C_EVAL_GO`). Không sửa file tracked trong lúc chạy.

## 2026-11-28 — S4 (Owner) và S5

- S4: Owner chạy `run_s4.ps1 -FreezeCommit f7a4ec6…`, 08:48:33–09:08:30; Ollama 0.40.16, digest `d8b0f5e9…`.
  40/40 run có final (25 FINISHED, 15 FINISHED_FLAGGED); 0 lỗi hạ tầng/truncation/overflow/isolation.
- S5: `metrics.py` không đổi sau freeze (`task07b-metrics-v3`) → `results/frozen/metrics_v3.json` (write-once).
  Tiêu chí sản phẩm: M4 render 0/20 & 0/20 (do cấu trúc), **M1b render 5/8 & 4/8 (< 6/8, không đạt)**, M10 20/20 &
  20/20, latency 1.08 & 1.10 × V4. Hành vi: M4_raw 0.05/0.10; 7/7 run RP trượt có `findings = []`.
  Bảng quyết định: "M4 giảm nhưng M1b giảm". `REPORT.md` viết xong; CHALLENGES_ARCHITECTURE A4 → PARTIAL, thêm A5.
- Full regression trước commit kết quả: 895 passed / 0 failed / 4 skipped (+83 subtests).
