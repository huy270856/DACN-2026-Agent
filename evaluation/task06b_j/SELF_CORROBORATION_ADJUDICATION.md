# TASK 06B-J — Self-corroboration: proposal để phân xử 6 ca bất đồng (DEV v1)

> **Trạng thái: DEVELOPER ASSESSMENT, PROPOSED.** Đây **không** phải phán quyết độc lập của
> người. Human adjudication = **PENDING**. Raw output của Judge và flag của checker được giữ
> nguyên. Tài liệu này là evaluator-only, **không** được đưa vào Judge kit.

## Hai construct (rubric v2)

- **STRUCTURAL_SELF_CORROBORATION:** ID của prediction nằm trong `supporting_evidence_ids`
  theo contract hiện tại. Checker tất định
  (`verification.flags = prediction_used_as_own_corroboration`) đo đúng điều này và được
  **giữ nguyên** làm safety guardrail.
- **SEMANTIC_SELF_CORROBORATION:** văn bản thực sự dùng output của detector (label hoặc
  score) như một bằng chứng **độc lập** để xác nhận label đó đúng, hoặc làm lý do chính cho
  kết luận. Judge chấm tag này trong v2.

Ví dụ phân loại:

- "The model predicts benign with score 0.006": **không** phải semantic self-corroboration.
- "The score is below the configured threshold": **không** phải.
- "The low score independently confirms the binary is benign": **là** semantic
  self-corroboration.

Nguồn: `calibration_package_v1/grader/items_common.json` (trích nguyên văn), các judgment Track
A đã lock, và `calibration_summary.json`. Ở cả 6 ca, checker flag = TRUE (structural), còn
Judge v1 **không** gắn tag SELF_CORROBORATION.

| # | Blind ID | Nhóm DEV (evaluator-only) | `alignment` / khuyến nghị | Đoạn trích liên quan (nguyên văn) | Evidence liên quan | Judge (R8, rationale) | Đề xuất semantic (developer) | Lý do | Điểm còn mơ hồ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | J-c966a03fc0 | tracert, no-tool v3.1 | INSUFFICIENT_EVIDENCE / MONITOR | explanation: "The malware prediction model indicates benign behavior with a low raw score, yet this is not a calibrated probability…"; C2: "…outputs a benign label with a raw score of 0.006." | supporting = [prediction `EV-ab7f…`] | R8=2: "explicitly refuses to treat the score as calibrated" | **STRUCTURAL_ONLY** (không semantic) | Báo cáo prediction kèm giới hạn; không có câu nào xác nhận label bằng chính score | `reason`: "Sufficient evidence to assess … prediction confidence": cụm "prediction confidence" hơi coi score như độ tin cậy |
| 2 | J-a0cf9f8c9d | tracert, tool có sẵn nhưng không gọi (v3.1) | INSUFFICIENT_EVIDENCE / MONITOR | explanation: "…assigns a very low raw score (0.006), suggesting benign behavior, but this is not a calibrated probability…" | supporting = [prediction] | R8=1: một phần dựa trên câu sai "no declared imports" và benign score | **BORDERLINE** (nghiêng về không semantic) | "suggesting benign behavior" diễn giải score thành hành vi (gần với SCORE_AS_PROBABILITY_OR_TRUTH), nhưng có phủ định ngay sau và alignment = INSUFFICIENT | Diễn giải score thành hành vi nên tính là self-corroboration hay chỉ là lỗi diễn giải score? |
| 3 | J-7d6f1da0a8 | findstr, no-tool v3.1 | INSUFFICIENT_EVIDENCE / MONITOR | explanation: "The malware model predicted benign … but without verified import bindings, we cannot definitively confirm or deny…" | supporting = [prediction] | R8=2: "no detector self-corroboration" | **STRUCTURAL_ONLY** | Nêu rõ không thể xác nhận; prediction chỉ được thuật lại | Không có |
| 4 | J-76d652db5c | findstr, tool-enabled v3.4 | INSUFFICIENT_EVIDENCE / MONITOR | explanation: "**The low raw score supports benign classification** but lacks runtime confirmation."; reason: "prediction indicates benign with low score" | supporting = [imports `EV-e7ec…`, prediction `EV-9106…`] | R8=2: "detector is not used to confirm itself" | **BORDERLINE, nghiêng về SEMANTIC (nhẹ)** | Score *chính là* thứ tạo ra label; nói score "supports" label là lập luận vòng tròn, dù câu có rào đón | Lập luận vòng tròn có rào đón ("lacks runtime confirmation") nhưng không làm thay đổi khuyến nghị thì có nên tính là semantic? |
| 5 | J-696f73ba79 | fc, tool có sẵn nhưng không gọi (v3.1) | INSUFFICIENT_EVIDENCE / MONITOR | explanation: "…very low raw score, suggesting no strong indicators of malicious behavior were found…"; change_explanation: "assessment based on existing low-risk prediction and lack of import data." | supporting = [prediction] | R8=2: "detector is not used to confirm itself" | **BORDERLINE** | change_explanation cho thấy assessment *dựa chủ yếu* vào prediction (một tiêu chí của định nghĩa semantic), nhưng kết luận vẫn là INSUFFICIENT_EVIDENCE | "Dựa vào prediction" để chọn MONITOR có khác "xác nhận label đúng" không? |
| 6 | J-e449b2b6a1 | fc, tool-enabled v3.4 | **CONSISTENT** / MONITOR | change_explanation: "synthesizes … the malware prediction score … to determine that while no malicious APIs are visible, the limited coverage prevents a definitive e[valuation]"; C3: "…assigns a raw score of 0.0038 and predicts 'benign'." | supporting = [prediction `EV-3d57…`, imports `EV-b625…`] | R8=2: "does not let the detector confirm itself" | **BORDERLINE** | `alignment=CONSISTENT` tức là "evidence nhất quán với prediction", mà prediction lại nằm trong supporting, nên phép kiểm alignment có tính vòng tròn về cấu trúc. Tuy vậy, văn bản không khẳng định score xác nhận label | Có nên tính `alignment=CONSISTENT` + prediction trong supporting là semantic khi văn bản trung tính? |

## Tóm tắt đề xuất của developer

- Semantic rõ ràng: **0/6**.
- Chỉ structural: **2/6** (#1, #3).
- Borderline: **4/6** (#2, #4, #5, #6). Trong đó #4 có lập luận vòng tròn rõ nhất.

Như vậy checker (structural) và Judge (semantic) đo **hai construct khác nhau**. Bất đồng giữa
chúng là điều dự kiến, không phải lỗi của bên nào.

## Đề xuất quy tắc báo cáo

1. Báo **hai** chỉ số tách riêng: tỷ lệ structural (checker, tất định) và tỷ lệ semantic
   (Judge v2, provisional). Không gộp.
2. Các ca borderline giữ nguyên **UNRESOLVED** cho tới khi có người phân xử. Không tự chọn
   giá trị có lợi cho Agent.
3. Calibration v2 có một probe semantic rõ ràng (synthetic) và một control chỉ-structural
   (lấy từ report thật, ca #3) để kiểm Judge phân biệt được hai construct.

## Câu hỏi cần người phân xử quyết định

- (a) Câu "score supports the classification" (#4) có tính là semantic không?
- (b) `alignment=CONSISTENT` cộng với prediction trong supporting (#6) có tính không?
- (c) Assessment dựa chủ yếu vào prediction để chọn khuyến nghị (#5) có tính không?
