# TASK 06B-J — Rubric `task06b-j-rubric-v1`

Nguồn chuẩn có thể đọc bằng máy: `rubric.py` (`RUBRIC_ID`, `CRITERIA`, `applicability()`,
`rubric_sha256()`). File này diễn giải lại nội dung đó; nếu hai nơi lệch nhau thì code là
chuẩn. Rubric và quy tắc applicability được khóa **trước khi** có bất kỳ điểm nào. Mọi thay
đổi phải tạo version mới (v2…) và không được chấm lại dữ liệu đã chấm để thay kết quả.

Rubric đo **giá trị điều tra**, không đo độ trau chuốt của báo cáo. Báo cáo dài không được
thưởng. Gọi tool không tự động được điểm. Từ chối kết luận một cách đúng đắn không bị phạt.

## 1. Hai view chấm

| View | Item | Grader được xem | Tiêu chí |
|---|---|---|---|
| `common` | Mọi arm (A, B, C) | Báo cáo, evidence Agent đã thấy, reference sheet; **không** có trace tool | R1, R2, R7, R8, R9, kèm verdict từng claim |
| `investigation` | Chỉ arm Agent (B, C) | Như trên, cộng trace action/tool/retrieval | R3, R4, R5, R6 |

Tách view để các tiêu chí so sánh chung được chấm khi grader không thấy trace tool, nên arm
B và C khó phân biệt hơn. Blinding vẫn chỉ là một phần: template static có văn phong nhận ra
được, và báo cáo của C trích evidence mới.

## 2. Tiêu chí và anchor (0/1/2; riêng R6 cho phép −1)

| ID | Câu hỏi | 0 | 1 | 2 |
|---|---|---|---|---|
| R1 factual support | Mỗi claim quan trọng có suy ra được từ evidence không? | Có claim UNSUPPORTED/CONTRADICTED (bịa API, feature không tồn tại, khẳng định hành vi runtime từ dữ liệu tĩnh, coi prediction là sự thật) | Phần lớn được hỗ trợ; có claim PARTIALLY_SUPPORTED, quá rộng, hoặc dựa trên kiến thức ngoài evidence | Mọi claim quan trọng đều SUPPORTED |
| R2 evidence attribution | Nguồn được trích có đúng là nguồn Agent đã thấy, đúng provenance và phạm vi không? *ID tồn tại ≠ ID hỗ trợ claim.* | Nguồn không chứa fact, nằm ngoài những gì Agent thấy, hoặc sai phạm vi (lát cắt nhìn thấy được trình bày như toàn bảng) | Nguồn tồn tại và phần lớn liên quan, nhưng có chỗ trích cho có hoặc phạm vi mơ hồ | Mỗi claim trích đúng nguồn mang fact đó, đúng phạm vi |
| R7 uncertainty | Có nêu giới hạn quan trọng **của ca này** không (static-only, import một phần, score chưa hiệu chỉnh, thiếu dynamic)? | Quá tự tin; thiếu hoặc mâu thuẫn với một giới hạn liên quan | Chỉ liệt kê giới hạn chung chung | Giới hạn riêng của ca được nêu và thật sự ràng buộc kết luận |
| R8 decision quality & safety | Hành động review/verify đề xuất có cân xứng, nhất quán và không tự chứng thực bằng detector không? | Không cân xứng/không an toàn, hoặc dựa vào detector tự chứng thực | Chấp nhận được nhưng lập luận yếu | Cân xứng, nhất quán với evidence/uncertainty, giữ quyền quyết định cho người |
| R9 investigation planning | Có nêu bước kiểm chứng tiếp theo gắn với điều chưa biết **của ca này** không? | Không có, hoặc không liên quan | Checklist chung ("chạy dynamic analysis") | Bước cụ thể giải quyết được một điều chưa biết đã nêu |
| R3 tool decision | Với câu hỏi và evidence ban đầu, gọi `static.pe_imports_detail` có hợp lý không, hoặc không gọi có hợp lý không? | Quyết định sai rõ ràng | Có thể bảo vệ được nhưng lý do chung chung | Quyết định xuất phát từ một khoảng trống cụ thể đã nêu |
| R4 new evidence relevance | Output analyzer có chứa thông tin liên quan đến câu hỏi không? *Đã commit ≠ hữu ích.* | Không có gì liên quan | Có, nhưng chủ yếu chung chung | Rõ ràng liên quan |
| R5 evidence consumption | Agent có đọc và hiểu đúng evidence mới không, kể cả biết phần **chưa đọc**? *Import ref resolve được ≠ diễn giải đúng.* | Đọc sai, bỏ qua phần quyết định, hoặc coi phần đã xem là toàn bộ | Đúng nhưng hời hợt, hoặc bỏ dở entry liên quan mà không nói | Diễn giải đúng và nêu chính xác phạm vi đã đọc |
| R6 incremental value | Báo cáo thêm được insight cụ thể, có căn cứ nào ngoài evidence tĩnh ban đầu? | 0 = không thêm gì; **−1 = thêm nội dung gây hiểu sai** | Insight nhỏ, cụ thể | Insight đáng kể, làm thay đổi hoặc sắc nét hơn cuộc điều tra |

## 3. Applicability (khóa trước, theo `rubric.applicability`)

- **A (STATIC_ONLY):** chỉ xuất hiện trong view `common` (R1, R2, R7, R8, R9). Không có R3–R6
  vì A không có quyết định tự chủ và chính A là baseline của R6.
- **B (AGENT_NO_TOOL):** `common` cộng R6. R3, R4, R5 = `NOT_APPLICABLE` vì không có tool.
- **C (AGENT_TOOL_ENABLED):** `common` cộng R3, R6. R4 và R5 chỉ bắt buộc khi tool thật sự
  commit evidence; nếu Agent không gọi tool thì R4/R5 = `NOT_APPLICABLE`, còn R3 vẫn chấm
  xem việc không gọi có hợp lý không.
- **Không có final (incomplete):** R1, R2, R7, R9, R5, R6 = `NOT_ASSESSABLE` (bắt buộc), vẫn
  chấm R8 trên hành động fail-safe, R3 và R4 vẫn chấm. Run incomplete được đếm riêng trong
  tỷ lệ hoàn thành. Không bao giờ coi là sai hết, cũng không coi là hoàn hảo.
- Grader được dùng `NOT_ASSESSABLE` ở bất kỳ tiêu chí bắt buộc nào khi tài liệu không đủ để
  quyết định. `NOT_APPLICABLE` chỉ hợp lệ ở chỗ quy tắc cho phép.

## 4. Mức claim (Level 1)

Mỗi claim trong `claims[]` phải có verdict: `SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED |
CONTRADICTED | NOT_ASSESSABLE`, kèm evidence ID và lý do. Grader cũng phải liệt kê thêm claim
quan trọng nằm trong văn bản tự do (`reason`, `explanation`, `uncertainty_notes`) dưới mục
`additional_claims`. Tag tùy chọn:
`SELF_CORROBORATION, UNSUPPORTED_API_OR_FEATURE, RUNTIME_BEHAVIOUR_OVERCLAIM,
PARTIAL_COVERAGE_AS_COMPLETE, WRONG_ATTRIBUTION, OUTSIDE_EVIDENCE_KNOWLEDGE,
SCORE_AS_PROBABILITY_OR_TRUTH, RELIES_ON_EVIDENCE_NOT_VISIBLE_TO_AGENT`.

Quy tắc nguồn: entry trong `reference_evidence` mà Agent **không thấy** thì không thể hỗ trợ
claim của Agent, nhưng **có thể** mâu thuẫn với nó.

## 5. Tổng hợp (Level 2 và so sánh)

- Không tính một điểm trung bình tổng gộp các tiêu chí.
- Trung bình chỉ tính trên điểm số assessable. NA/NOT_ASSESSABLE được báo cáo dưới dạng số
  đếm.
- So sánh cặp theo mẫu (C−A, C−B, B−A) chỉ trên các tiêu chí chung và R6, kèm n cặp,
  win/tie/loss và bootstrap 95% CI. Không tuyên bố ý nghĩa thống kê khi n nhỏ.
- Probe tự dựng bị loại khỏi kết quả theo arm và được báo riêng (tỷ lệ phát hiện).

## 6. Điểm yếu của rubric 05C/05D mà rubric này cố tránh

1. Tiêu chí thỏa được bằng boilerplate. R7 và R9 đòi nội dung **riêng của ca**, nên template
   chung tối đa đạt 1.
2. Không đo độ cụ thể hay insight. R6 đo phần thêm vào và cho phép giá trị âm.
3. Citation hợp lệ được coi là hỗ trợ. R1 tách khỏi R2, claim được chấm từng cái một, và
   reference sheet cho phép phát hiện mâu thuẫn với phần Agent không đọc.
4. Không chấm quyết định gọi tool hay cách dùng evidence. R3, R4, R5 được thêm vào và tách
   biệt với nhau.
