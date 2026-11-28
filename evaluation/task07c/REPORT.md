# TASK 07C — Grounding cho khẳng định vắng mặt (investigation-v4.2): kết quả

| Hạng mục | Giá trị |
|---|---|
| Loại | `DEV_DIAGNOSTIC` trên cohort **đã tiêu thụ** `cases_v2` của 07B. **Không** confirmatory. Metric tất định (`task07b-metrics-v3`), không phải semantic grading |
| Track | `RAW_PE_E2E`, `LOCAL_QWEN` (`qwen3.5:4b`, digest `d8b0f5e9…`, Ollama 0.40.16 headless) |
| Freeze | `f7a4ec6f89a0834bb7446976b91600b55e7c1f09`; review PASS (sau 1 vòng FAIL vì High về kind) |
| Run | S4 do Owner chạy ngoài session, 08:48:33–09:08:30 (~20 phút). V4_2 × seed 42/7 = **40/40 run có final** (25 FINISHED, 15 FINISHED_FLAGGED) |
| Baseline | Trace frozen 07B: V4 và BASE (`evaluation/task07b/results/frozen/metrics_v1.json`), không chạy lại |
| Artifact | `results/frozen/V4_2_s{42,7}/`, `results/frozen/metrics_v3.json`, `EVALUATION_LOG.md` |
| Engineering completion | **PASS** |
| Research completion | **PARTIAL**: tiêu chí sản phẩm **không đạt** (M1b render 5/8 và 4/8 < 6/8); absence claim không phạm vi giảm mạnh, nhưng với cái giá là bỏ trống phát hiện có mặt |

## 1. Tóm tắt

- **Vấn đề của 07B (A4)** được xử lý ở mức báo cáo:
  - M4-UNSCOPED trên báo cáo render = **0/20** ở cả hai seed, nhưng giá trị này **thỏa do cấu trúc** (trusted
    filter), không phải bằng chứng.
  - Hành vi model (M4_raw trên statement model viết) = 0.05 và 0.10, so với 0.60 và 0.55 của V4 ở 07B. Định
    dạng final khác nhau nên phép so này **có giới hạn**.
  - Model chuyển phần lớn absence sang `absence_claims` có cấu trúc: 30 và 32 claim được chấp nhận, 8 và 4
    claim bị reject.
- **Nhưng M1b giảm:** V4_2 đạt 5/8 và 4/8, so với 7/8 và 7/8 của V4 ở 07B. Vượt nhiễu: nhiễu V4_2 = 1, V4
  07B = 0.
  - Trong cả 7 run RELEVANT_PRESENT bị trượt, `findings` đều **rỗng**; model chỉ ghi `absence_claims`.
  - Có 4/7 run trong số đó query đã trúng entry liên quan (M8), tức model **đã thấy** nhưng không viết phát
    hiện có mặt.
  - Đây là tác dụng phụ của việc cho phép `findings` rỗng cộng với nhấn mạnh absence trong prompt.
- **Đạt tiêu chí sản phẩm nhờ trusted filter ≠ model đã học được.** Ở 07C, ngay cả tiêu chí sản phẩm cũng
  không đạt đủ, vì M1b trượt.
- Bảng quyết định: dòng **"M4 giảm nhưng M1b giảm → xem lại prompt hoặc độ dài summary"**.

## 2a. Tiêu chí sản phẩm (trên báo cáo render; đăng ký trước, phải đạt cả hai seed)

| Tiêu chí | Ngưỡng | s42 | s7 | Kết luận |
|---|---|---|---|---|
| M4-UNSCOPED render | ≤ 0.20 | 0/20 (0.00) | 0/20 (0.00) | đạt — **do cấu trúc**, không phải bằng chứng |
| M1b render | ≥ 6/8 | **5/8** | **4/8** | **không đạt** |
| M10 | ≥ 19/20 | 20/20 | 20/20 | đạt |
| Median latency V4_2 / V4 (07B) | ≤ 1.5 | 26.71 / 24.62 = 1.08 | 30.35 / 27.56 = 1.10 | đạt |

M1b render bằng đúng M1b trên mọi ref ở cả hai seed: không có trích dẫn liên quan nào bị loại cùng một
statement phủ định.

## 2b. Hành vi model (DIAGNOSTIC, không ngưỡng)

| Chỉ số | V4_2 s42 | V4_2 s7 | V4 07B s42 / s7 (định dạng khác) | BASE 07B s42 / s7 |
|---|---|---|---|---|
| M4_raw_unscoped (final cuối) | 1/20 (0.05) | 2/20 (0.10) | 0.60 / 0.55 | 0.05 / 0.20 |
| M4_raw_pre_repair (final đầu) | 0/20 (0.00) | 2/20 (0.10) | — | — |
| Run có statement bị loại (P1) | 6/20 | 6/20 | — | — |
| Statement bị loại | 7 | 6 | — | — |
| absence_claims accepted / rejected | 30 / 8 | 32 / 4 | — | — |
| Run có rejection absence | 7 | 8 | — | — |
| M1b (mọi ref) tầng ≥ 48 / < 48 | 3/5, 2/3 | 2/5, 2/3 | 4/5, 3/3 ở cả hai seed | 0/5, 0/3 |
| M8 query_hit | 6/8 | 7/8 | 7/8 / 7/8 | — |
| M2_correct_no_tool | 4/8 | 4/8 | 4/8 / 4/8 | 0/8 / 0/8 |
| M9 | 7/8 | 6/8 | 7/8 / 7/8 | — |
| Truncation / overflow / lỗi hạ tầng / isolation fail | 0/0/0/0 | 0/0/0/0 | 0 | 0 |

**Các run RELEVANT_PRESENT trượt** (`findings = []`):

| Seed | Case | M8 trúng | Số absence_claims |
|---|---|---|---|
| s42 | 0004 | không | 4 |
| s42 | 0008 | **có** | 1 |
| s42 | 0009 | không | 4 |
| s7 | 0004 | không | 2 |
| s7 | 0006 | **có** | 2 |
| s7 | 0009 | **có** | 2 |
| s7 | 0019 | **có** | 5 |

## 3. Bảng quyết định (PLAN §3; PROTOCOL §4)

| Dòng | Quan sát | Áp dụng? |
|---|---|---|
| Đạt cả bốn tiêu chí → v4.2 thành nhánh chính; 07D chạy confirmatory | M1b render 5/8 và 4/8 không đạt | **Không** |
| M4 giảm nhưng M1b giảm → xem lại prompt hoặc độ dài summary | M4_raw 0.05/0.10 (so với 0.60/0.55 ở 07B, có giới hạn); M1b 5 và 4 so với 7 và 7, vượt nhiễu | **Có** |
| M4 không giảm → A4, cân nhắc bỏ absence | M4 giảm | Không |

**Hướng tiếp theo** (Owner/Planner quyết, không tự mở rộng): chỉnh đúng nguyên nhân đo được.

- `findings` rỗng trong khi đã có entry liên quan được xem.
- Phương án tối thiểu: khôi phục `findings` minItems ≥ 1 cho các run đã xem ít nhất một entry, hoặc bỏ câu
  "để findings rỗng" khỏi SYSTEM_42. Cả hai đều có rủi ro model quay lại điền câu phủ định vào ô bắt buộc,
  như đã thấy ở smoke 3.
- Cách khác là thêm vào prompt câu nhắc tất định "bạn đã xem các entry I…; findings phải nêu những gì có mặt".
- Phải đo lại trên DEV trước.

## 4. Sự cố, deviation, limitation

- **Sự cố S4:** không có. Không lỗi hạ tầng, truncation hay overflow.
- **Deviation:** không có sau freeze. `metrics.py` không đổi so với `f7a4ec6`.
- **Limitation:**
  - Cohort đã tiêu thụ (07B), n = 8 RP mỗi seed, chỉ PE benign. Kết quả là chẩn đoán, không khái quát hóa
    được.
  - M4 render thỏa do cấu trúc.
  - So M4 với 07B có giới hạn vì định dạng final khác.
  - M1b chỉ đo việc trích entry liên quan, không đo câu trả lời có đúng về ngữ nghĩa hay không. Semantic
    grading: NOT_RUN.
  - Trong quá trình phát triển, contract đổi 3 lần (v4.1 → v4.2 → P1) dựa trên smoke DEV của 2 case 06B-J.
    Mỗi lần đổi đã ghi log và được duyệt trước freeze.

## 5. Completion

- **Engineering: PASS.**
  - Coverage ledger, contract `investigation-v4.1` và `investigation-v4.2`, verifier absence, lượt repair
    absence riêng, trusted renderer có loại bỏ theo P1, arm V4_2, metrics v3.
  - Đều có test (unit và MOCK_LLM qua D1–D9 thật).
  - Freeze trước run, review PASS, 40/40 run write-once.
  - Full regression: 895 passed, 0 failed, 4 skipped (+83 subtests) tại commit freeze. Lần chạy trước commit
    kết quả: xem `EVALUATION_LOG.md`.
- **Research: PARTIAL.**
  - Absence không phạm vi giảm mạnh ở cả báo cáo render lẫn hành vi model (so sánh có giới hạn).
  - Nhưng tiêu chí sản phẩm M1b không đạt, vì model bỏ trống phát hiện có mặt.
  - Không đủ điều kiện đưa v4.2 thành nhánh chính.
