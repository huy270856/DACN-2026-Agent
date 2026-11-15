# TASK 06A — giao thức DEV v2.1 (định nghĩa trước inference)

Đây là ablation phát triển, không phải confirmatory benchmark. Hai nhánh:
A = production v1 tại `edd0a25`, nguyên source/prompt/parser;
B = neutral assessment v2.1, schema có claim types và kiểm tra sau inference.
Gói B thay đồng thời prompt và schema: không thể quy tác động riêng cho prompt.
Guardrails deterministic được đo riêng với raw reasoning, không tính là năng lực LLM.

## Dữ liệu, bất biến và ngân sách

- Chọn 12 record label 0 và 12 record label 1 đầu tiên sau dòng 1000 của
  `train_features_1.jsonl`; bỏ SHA đã có trong mọi JSON artifacts 05C/05D và toàn bộ
  200.000 SHA của `test_features.jsonl`. Không chọn theo score/kết quả LLM.
- Đây là convenience DEV có cân bằng nhãn, không đại diện thực tế. Nguồn train đã
  dùng fit/validation detector; **không độc lập với detector**. Không tuyên bố chưa
  từng được đọc trong những session không lưu artifacts.
- Ground truth chỉ nằm trong `manifest_EVALUATOR_ONLY.json`. `inputs.json` chứa
  CaseState/projection/prediction, không label/avclass. Runner inference không đọc
  nội dung manifest evaluator. Có assertion trên prompt hai nhánh và test leakage.
- Chính model/threshold 05A, kiểm SHA binary. Cùng facts sau cắt context của v1,
  Qwen digest, seed 42, temperature 0.1, thinking OFF, num_ctx 8192,
  output tối đa 1536 tokens, timeout 180s, **1 attempt mỗi nhánh mỗi ca**.
  Thứ tự nhánh đổi luân phiên theo index. Không chạy model đồng thời với regression
  live tests. Không warm-up có chọn lọc hoặc bỏ ca thất bại.
- Cả hai nhánh không có tool. Đây là one-shot FEATURE_RECORD_REPLAY, không
  RAW_PE_E2E/multi-step và không có D9 commit mới. Không tạo đường production mới.
- Freeze source/config/model/input/manifest trước inference. Giữ đầy đủ raw response,
  exact context, token counts, elapsed time và kết quả verifier. Không ghi đè kết quả
  khi resume, kể cả failures. Code/data drift bắt buộc tạo experiment version mới.

## Định nghĩa metrics

Mẫu số chung = 24 attempts mỗi nhánh, kể cả timeout/malformed.

| Metric | Định nghĩa / giới hạn |
|---|---|
| Schema-valid | Báo cả parser chấp nhận theo code riêng của nhánh và JSON Schema decode contract đúng; không nhầm acceptance của parser v1 với strict validation v2 |
| Citation coverage | Số refs tồn tại trong **facts thực sự nhìn thấy** / số refs, kèm số ca có refs và invalid IDs; list v2 có nhiều refs hơn nên luôn báo mẫu số |
| Grounding errors / unsupported specifics | Rule screen chung trên prose, lexicon API/library, entropy và runtime phrases; **suspected**, chưa phải semantic adjudication |
| Claim binding v2 | OBSERVED phải có ID; specifics kiểm trên nguồn được claim trích; missing/truncated source → cần xác minh. Không dùng metric chỉ có ở v2 để tuyên bố v1 kém |
| Alignment | Phân phối CONSISTENT/CONFLICT/INSUFFICIENT; không có hướng nào mặc nhiên tốt |
| Appropriate uncertainty | PENDING review độc lập. Phân phối alignment và limitation không chứng minh đúng mức bất định |
| Recommendation consistency | Chung cho hai nhánh: nhãn/score/threshold, enum, MONITOR trên malicious hoặc near threshold ±0.05 raw score, CONFLICT/INSUFFICIENT thiếu review, MANUAL_REVIEW nhưng review=false |
| Review load | Raw bool và effective guardrail riêng. Requires_human_decision=true không đồng nghĩa mọi ca đều bắt buộc phân tích lại |
| Invalid action | Recommendation ngoài enum/thiếu; action khác FINISH của v1 báo riêng; v2 không có tool action schema |
| Latency / tokens | Wall time mọi attempt; tổng prompt/output tokens do Ollama trả, cả malformed; chi phí tiền N/A local, không gán USD giả |
| Tool validity / provenance | Calls=0, validity=N/A; replay provenance có source hash/dòng/record hash/prediction digest; không phải signed D9 evidence mới |

Ghép theo SHA; báo cả flags biến mất và xuất hiện. Không dùng những khác biệt nhỏ
trong 24 mẫu để suy thống kê tổng quát hóa. Không đo detection gain vì label giữ nguyên.
Nếu phân tích error-review với ground truth về sau: sensitivity = flagged error / tất
cả classifier errors; specificity = unflagged correct / tất cả correct. Không có error
trong DEV thì sensitivity **undefined**, không ghi 100%.

## Judge và rubric

Không LLM judge trong lượt này, không human score; human grading 05D vẫn PENDING.
Rubric v1 A2/B1/B2/C1/D1 giữ nguyên; template đạt trần không chứng minh investigation
value. Rule screen chỉ giúp tìm ca cần đọc lại; phủ định, giả thuyết, packing không
đồng nghĩa entropy cao, và imports bị cắt có thể tạo false positives. Không gọi
`grounded=true` của module cũ là ngữ nghĩa đã được chứng minh.

Rubric v2 **mới, exploratory, chưa chấm**: mỗi tiêu chí 0/1/2, cần ghi nguồn và lý do:

1. Claim accuracy/binding: từng observed fact đúng nguồn; hypothesis tách rõ.
2. Evidence discrimination: chỉ rõ bằng chứng nào giúp phân biệt và bằng chứng nào
   không đủ; không coi prediction là corroboration độc lập.
3. Unknown prioritization: nêu gap cụ thể và tác động lên kết luận.
4. Actionable verification: câu hỏi cần trả lời, analyzer/phép xác minh read-only,
   kết quả nào sẽ làm đổi assessment; không hứa tool chưa có.
5. Decision coherence: confidence/review/recommendation tương thích; human có quyền
   quyết định; không nhầm raw score với xác suất.

Không cộng rubric mới vào score rubric cũ. Confirmatory **NOT_RUN**: chỉ lập tập
xác nhận khi có tín hiệu DEV đáng tin và đóng băng phiên bản trước khi xem kết quả.
