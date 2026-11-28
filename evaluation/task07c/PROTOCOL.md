# TASK 07C — PROTOCOL (frozen trước S4)

| Hạng mục | Giá trị |
|---|---|
| Loại | `DEV_DIAGNOSTIC` trên cohort **đã tiêu thụ** `cases_v2` của 07B (digest `f984cc7f…`). **Không** confirmatory |
| Track | `RAW_PE_E2E`; `LOCAL_QWEN` `qwen3.5:4b` digest `d8b0f5e9…`, Ollama 0.40.16 headless (pin như 07B) |
| Arm | **V4_2** = V4 của 07B + contract `investigation-v4.2` (final có cấu trúc, ledger, `absence_claims`, trusted renderer có loại bỏ theo P1). 2 seed (42, 7) × 20 case = **40 run** |
| Baseline | Trace frozen của 07B (`evaluation/task07b/results/frozen/{V4,BASE}_s{42,7}`), cùng Ollama, digest và cohort. **Không** chạy lại 07B |
| Metric | `task07b-metrics-v3` (`evaluation/task07b/metrics.py`). Tất định, không phải semantic grading |
| Authorization | `DACN_OWNER_07C_EVAL_GO`, chỉ dùng sau khi review PASS bản freeze. Owner tự chạy `evaluation\task07c\run_s4.ps1 -FreezeCommit <SHA>` ngoài session |

## 1. Thay đổi so với V4 (07B)

Tóm tắt PLAN_TASK07C §2 và §2b:

- Coverage ledger tất định `Q1..Qn` (index và từng query đã gộp trang, có cờ `exhausted`).
- Final `investigation-v4.2` chỉ có trường có cấu trúc:
  - `findings[{kind OBSERVED|INFERENCE, statement, refs≥1}]`, chỉ cho khẳng định có mặt, được phép rỗng;
  - `absence_claims[{api_or_prefix, scope_ref}]`;
  - không có `answer` văn bản tự do.
- Verifier:
  - một claim chỉ hợp lệ khi `scope_ref` là một Qk đã exhausted, đúng scope và không bị bảng đầy đủ mâu
    thuẫn;
  - statement phủ định bị reject.
- Một lượt repair absence riêng, kể cả ở FORCED_FINAL; lượt này chỉ được sửa final.
- **P1:** sau repair mà vẫn sai thì statement phủ định bị **loại khỏi báo cáo render** và liệt kê ở
  "Nội dung bị loại". Chữ của model không bị sửa; run vẫn FLAGGED.
- Trusted renderer dựng báo cáo tiếng Việt: trích nguyên văn statement, absence render theo Qk, phạm vi
  render từ ledger.

## 2. Tiêu chí (đăng ký trước; phải đạt ở **cả hai seed**)

### 2a. Tiêu chí sản phẩm, trên báo cáo đã render (`v42_product`)

| Tiêu chí | Ngưỡng |
|---|---|
| M4-UNSCOPED rate trên báo cáo render (statement được giữ) | ≤ 0.20 |
| M1b trên báo cáo render (entry liên quan được trích bởi statement được giữ) | ≥ 6/8 |
| M10 final hợp lệ | ≥ 19/20 |
| Median latency V4_2 / V4 (07B cùng seed) | ≤ 1.5 |

### 2b. Chỉ số hành vi model (DIAGNOSTIC, **không có ngưỡng**)

- `M4_raw_unscoped`: M4 trên **mọi** statement model viết, kể cả statement bị loại.
- Số run có statement bị loại; tổng số statement bị loại.
- `absence_claims`: số được chấp nhận, số bị reject, số run có rejection; `absence_repair_used`.
- M1b của trace (`M1b_relevant_cited`, tính trên mọi ref), M8, M2_correct_no_tool, M9.

REPORT **phải** trình bày 2a và 2b cạnh nhau và ghi rõ: **"đạt tiêu chí sản phẩm nhờ trusted filter ≠
model đã học được"**.

## 3. So sánh với 07B (giới hạn)

- Định dạng final khác 07B: v4.2 không có `answer` văn bản tự do. M4 của V4_2 chấm trên `statement`
  (M4_raw) hoặc trên statement được giữ (M4 render), còn M4 của 07B chấm trên answer + findings text. So
  sánh M4 với 07B vì thế **có giới hạn** và chỉ mang tính mô tả.
- M1b, M8, M10 và latency so trực tiếp được (cùng cohort, cùng engine retrieval).

## 4. Nhiễu, bảng quyết định, quy tắc dừng

- Nhiễu = |Δ| giữa seed 42 và 7 của V4_2; M4 so theo rate.
- Bảng quyết định (PLAN §3):
  - đạt cả bốn tiêu chí 2a → v4.2 thành nhánh chính của Agent; 07D chạy confirmatory trên cohort mới nhỏ.
    Phải ghi kèm chỉ số 2b;
  - M4 giảm nhưng M1b giảm → xem lại prompt hoặc độ dài summary;
  - M4 không giảm → ghi `docs/CHALLENGES_ARCHITECTURE.md` (A4), cân nhắc bỏ hẳn absence khỏi contract.
- Quy tắc dừng: như PROTOCOL 07B §6.
  - Mỗi run chạy một lần, write-once; lỗi tính vào mẫu số.
  - Lỗi theo case được ghi trace rồi đi tiếp.
  - Drift, Qwen sai hoặc Ollama down thì dừng toàn bộ, resume được.
  - Kiểm health Ollama trước mỗi case.
  - Không sửa file tracked trong lúc chạy.
