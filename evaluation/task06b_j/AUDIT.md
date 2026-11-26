# TASK 06B-J — Stage 1: Audit repository và hạ tầng chấm

Audit dựa trên source, test và artifact thật (không chỉ dựa trên Markdown). Base: tree của
`HEAD` trùng `origin/main` (diff rỗng; `origin/main` = merge PR #14 chứa 06B-R2 + docs TASK06).
Branch `main` local đang cũ hơn `origin/main`, nên không dùng làm base.

## 1. TASK 05D-J: dùng lại được gì, không dùng được gì

| Thành phần 05D-J | Thực trạng (đã đọc source) | Quyết định cho 06B-J |
|---|---|---|
| `claude_judge.py` | Judgment được **nhúng sẵn** trong `CLAUDE_JUDGMENTS` (10 phiếu); mọi tiêu chí còn lại **mặc định = 2** với lý do template `DEFAULT_REASON`. Không có lời gọi inference, không có raw request/response. | **Không dùng làm Judge.** Giữ nguyên là historical artifact. Không được gọi đây là lượt chấm mới, độc lập cho v3.4. |
| `rule_checker.py` | Heuristic keyword/regex, đã được relabel trung thực (`RULE_BASED_HEURISTIC_PROVISIONAL`). | Không dùng làm semantic judge. Rule screen của 06B (`verification.flags`) chỉ được giữ ở phía evaluator để **so sánh** với Judge/người chấm. |
| Rubric `task05c-rubric-v1` (A2/B1/B2/C1/D1) | Template static cố định đạt trần 2.0 vì cả 5 tiêu chí đều thỏa được bằng boilerplate (05D-J tự ghi nhận). Không có tiêu chí nào về độ cụ thể, quyết định gọi tool, cách dùng evidence mới, hay kế hoạch điều tra. | Thay bằng rubric mới `task06b-j-rubric-v1` (R1–R9) có anchor riêng và quy tắc applicability. Rubric 05C/05D giữ nguyên, không diễn giải lại. |
| Blind forms `annotation_forms_blind_v2.json` + `branch_mapping_EVALUATOR_ONLY.json` | Thiết kế 2 nhánh X/Y, mapping tách riêng. | Dùng lại **ý tưởng**: id ẩn danh, mapping evaluator-only, thứ tự xáo trộn tất định. Code mới vì có 3 arm, 2 view và reference sheet. |
| `grading_import.py` (`_cohen_kappa`, tổng hợp nhiều reviewer, không auto-resolve) | Chạy được, có test. | **Import lại** `_cohen_kappa` trong `analysis.py`. Giữ nguyên nguyên tắc: bất đồng được chuyển cho người phân xử. |
| `ui/grading.html` | Gắn với schema 05D (5 tiêu chí, X/Y). | **Không dùng lại** cho 06B-J. Cần UI mới cho R1–R9 cùng phần claim-level. Hiện chưa làm (NOT_IMPLEMENTED). |
| `pilot.py` | Chọn mẫu cân bằng strata trên dữ liệu replay 05C. | Không áp dụng: 06B-J dùng RAW_PE, không có strata FP/FN. |

## 2. TASK 06B / 06B-R2 (v3.4): những gì thật sự tồn tại

- `investigation_v3/workflow_v34.run(..., tool_enabled=True|False)` hỗ trợ cả arm có tool và
  arm không tool với **cùng** contract v3.4. Nhưng **chưa từng có** lượt chạy v3.4 với
  `tool_enabled=False`. Arm B trên DEV hiện chỉ có ở contract v3.1 (`repair_dev_v2`) và v3.3
  (`repair_dev_v4`).
- `r2_debug_v34` chỉ có arm E (v3.4 tool-enabled) trên tracert/findstr/fc. Theo R2_PROTOCOL
  đây là DEBUG, không phải confirmatory.
- Arm A (static template) của `repair_dev_v4` và arm E của `r2_debug_v34` đến từ **hai lượt
  intake khác nhau** trên cùng SHA, nên evidence ID khác nhau. Trên DEV không có bộ ba nào
  thật sự matched.
- **Rò rỉ provenance trong prompt Agent:** `facts.unknowns` chứa đường dẫn thật
  `C:\Windows\System32\<tên>.exe`. Agent của tracert đã dựa vào tên file/đường dẫn để viết
  một claim ngoài evidence ("kích thước 40 KB là bất thường với tracert.exe"). Với một cohort
  toàn file System32, đường dẫn gần như tiết lộ nhãn benign. Protocol confirmatory vì vậy phải
  stage target dưới tên trung tính (xem PROTOCOL §6).
- Projection mặc định chỉ hiển thị 16/64 entry import; đọc thêm bằng `READ_EVIDENCE` (tối đa
  2 trang × 16). Analyzer chỉ commit tối đa 64 entry, trong khi file có thể có nhiều hơn
  (findstr 102, fc 112).

## 3. Khả năng chạy (môi trường hiện tại)

| Hạng mục | Trạng thái |
|---|---|
| Full regression trước khi sửa | 649 passed, 4 skipped, 81 subtests |
| Ollama `127.0.0.1:11434` | **Không phản hồi** trong phiên này, nên không chạy được inference Qwen mới |
| Judge provider | Không có API key (`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` unset), không có SDK `anthropic`, không có ủy quyền dùng API trả phí, nên fresh Judge = **BLOCKED** |
| Người chấm | Không có, nên human grading = **PENDING** |
| LightGBM model | Nằm ngoài Git; chưa kiểm tra lại trong phiên này vì không cần cho Stage 1–4 |

## 4. Tóm tắt quyết định

- Dùng lại: `_cohen_kappa`, nguyên tắc blind/mapping evaluator-only, rule screen 06B (chỉ
  để so sánh), các frozen trace DEV (chỉ đọc, làm dữ liệu calibration).
- Mới: rubric R1–R9 kèm applicability, package builder 2 view có reference sheet và leakage
  scan, validator chặt, lock-then-unblind analysis, Judge adapter không có fallback,
  metrics pipeline/coverage tất định.
- Không đụng tới: Agent, Controller, D1–D9, Node B/C, LightGBM/threshold, README gốc, và
  mọi artifact 05C/05D/06A/06B.
