# TASK 06B-J — Rubric `task06b-j-rubric-v2`

Nguồn chuẩn máy đọc: `rubric_v2.py` (sha256 `dbb791cd…`, đúng bằng giá trị ghi trong
package/kit v2). Bản v1 (`rubric.py`, `RUBRIC.md`, sha256 `9fa271b8…`) cùng **toàn bộ**
judgment v1 (19 Track A, 16 Track B), raw output, session note, lock và mapping được **giữ
nguyên**. v2 không chấm lại v1.

v2 được tạo sau DEV calibration v1 (CALIBRATION_REPORT §4–§6) và **trước** mọi inference
confirmatory. Phạm vi thay đổi: chỉ evaluation layer; không sửa Agent, Qwen, LightGBM,
analyzer hay D1–D9.

## 1. Change log v1 → v2 (các quy tắc chấm thay đổi)

| # | Hạng mục | v1 | v2 | Vì sao cải thiện validity |
|---|---|---|---|---|
| 1 | R2 | `R2_evidence_attribution`: anchor chỉ mô tả trích sai; report không trích gì bị chấm 0 (3/3 template) | `R2_evidence_traceability`. 0 = trích sai hoặc sai scope; 1 = có câu không truy được nguồn (không ID, không có bản ghi nhúng); 2 = mọi câu truy được qua ID **hoặc** bản ghi nhúng nguyên văn. ID hợp lệ tự thân không được điểm | Đo khả năng truy nguồn thay vì định dạng citation. Áp dụng như nhau cho static, no-tool, tool-enabled và cho văn bản tự do. Không tự điền citation thay model |
| 2 | Claim verdict | Chỉ có verdict + tag | Thêm **`evidence_access`** bắt buộc với UNSUPPORTED/CONTRADICTED: `AGENT_VISIBLE`, `ACCESSIBLE_NOT_RETRIEVED`, `INACCESSIBLE_BEYOND_LIMITS`, `NO_STATIC_SOURCE`. Thêm tag **`SCOPE_OVERCLAIM`** | Tách được "Agent không thể biết" với "Agent khẳng định vượt phạm vi đã thấy" (Issue B) |
| 3 | R1 | Anchor chung | Không phạt việc không biết dữ liệu ngoài tầm. SCOPE_OVERCLAIM **luôn** là lỗi. Anchor 2 yêu cầu claim "scoped to what was seen" | Giữ đúng phán định tracert (scope overclaim), không phạt các claim đã giới hạn phạm vi đúng |
| 4 | Chồng lấn tiêu chí | Không có quy tắc; một lỗi đã kéo giảm R2/R5/R6/R7 cùng lúc | **Primary-criterion rule**: chỉ giảm một tiêu chí khi lỗi vi phạm *chính construct đó*, và mỗi rationale phải nêu lý do riêng | Giảm việc một lỗi bị tính nhiều lần (Issue C) |
| 5 | R5 | `R5_evidence_consumption` | `R5_new_evidence_consumption`: **chỉ** đánh giá evidence mới từ tool/retrieval; lỗi không liên quan (ví dụ score-as-probability) không làm giảm R5 | Construct hẹp và rõ ràng |
| 6 | R6 | Như v2 nhưng không có danh sách loại trừ | Ghi rõ không thưởng cho: gọi tool, liệt kê import, lặp lại prediction, viết dài; report chính xác vẫn có thể đạt 0; −1 vẫn được giữ | Đo đúng giá trị gia tăng ròng |
| 7 | R7 | Anchor chung | Một lỗi factual chỉ làm giảm R7 khi nó mâu thuẫn hoặc bỏ sót một giới hạn đã nêu | Theo primary-criterion rule |
| 8 | R9 | `R9_investigation_planning`, primary | `R9_next_step_planning`: **EXPLORATORY**, không thuộc primary aggregate. Grader tìm next-step trong **toàn bộ** văn bản; không tự viết plan | Contract v3.4 không có trường next-step, nên R9 đo năng lực output của hệ thống chứ không thuần là suy luận của Qwen. Floor effect ở v1 (11/12 = 0) |
| 9 | Self-corroboration | Tag `SELF_CORROBORATION` không có định nghĩa; checker và Judge đo hai thứ khác nhau | Judge chỉ chấm **`SEMANTIC_SELF_CORROBORATION`** (có định nghĩa và ví dụ). **STRUCTURAL** được giữ ở checker tất định (không đổi) | Tách hai construct (SELF_CORROBORATION_ADJUDICATION.md) |
| 10 | Reference sheet | Chỉ đánh dấu entry nhìn thấy | Thêm `access_limits` cho evidence imports (tổng số entry, số đã commit, số chưa bao giờ commit, ghi chú budget) | Để grader có căn cứ phân loại `evidence_access` mà không lộ arm |
| 11 | Tổng hợp | Không có điểm tổng | Không thay đổi. **Primary** = phân bố verdict mức claim, cùng R1, R2, R7, R8 (common) và R3, R4, R5, R6 (investigation). **Exploratory** = R9 | Kết quả chính đặt ở mức claim |

Không thay đổi: thang 0/1/2 (R6: −1..2); quy tắc applicability (`rubric_v2.applicability`
chỉ đổi tên tiêu chí); NOT_APPLICABLE/NOT_ASSESSABLE không bao giờ bị quy thành 0 hay 2;
lock trước unblind.

## 2. Calibration v2 (lượt cuối dự kiến)

- Package `calibration_package_v2_pass{1,2}`: 23 item common, 20 item investigation. Gồm 15
  report thật (DEV) và **8 probe developer-authored** được gắn vào report fc v3.4 (base đã
  được v1 chấm R1=2, R2=2).
- Probe âm: API bịa, khẳng định runtime, score-as-probability, absence overclaim,
  semantic self-corroboration, wrong attribution.
- Probe dương: quan sát giới hạn phạm vi đúng, từ chối kết luận đúng.
- Control lấy từ report thật:
  - Template static: control truy nguồn không cần ID.
  - findstr no-tool v3.1: control chỉ-structural self-corroboration (đánh giá của developer).
- Hai pass dùng seed khác nhau, nên ID ẩn danh và thứ tự đều khác. Kỳ vọng nằm ở
  `EVALUATOR_ONLY/calibration_key.json`, là giả thuyết của developer, **không** phải ground
  truth.
- Developer **không** tự chạy Judge (vì đã biết đáp án). Owner chạy theo
  `OWNER_JUDGE_COMMANDS.md`.

## 3. Quy tắc dừng và xử lý bất đồng (áp dụng sau calibration v2)

Đây là vòng redesign cuối. **Không** có rubric v3 trừ khi một tiêu chí hoàn toàn mất tác
dụng. Sau calibration v2:

1. Phân loại mỗi bất đồng (pass1 vs pass2, Judge vs kỳ vọng, Judge vs checker) thành:
   `JUDGE_INCONSISTENT` | `RUBRIC_AMBIGUOUS` | `EXPECTATION_DEBATABLE` | `CONSTRUCT_DIFFERENCE`
   (ví dụ structural so với semantic).
2. Một tiêu chí được coi là **đủ tin cậy** cho primary aggregate nếu thỏa cả hai điều kiện:
   - Self-consistency pass1/pass2 có percent agreement ≥ 0.8 trên các report thật assessable.
   - Probe tương ứng đi đúng chiều: probe âm không được điểm cao hơn base, probe dương không
     bị phạt.

   Tiêu chí không đạt được báo **UNRELIABLE**: vẫn báo cáo nhưng chỉ ở mức exploratory, và
   loại khỏi primary aggregate **trước** confirmatory.
3. Không yêu cầu Judge khớp mọi kỳ vọng của developer. Các ca `EXPECTATION_DEBATABLE` được
   chuyển cho người phân xử (PENDING).
4. Không sửa Agent để đạt rubric. Không đổi rubric sau khi đã thấy kết quả confirmatory.
