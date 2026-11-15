# TASK 05D-J — LLM (Claude) semantic grading (PROVISIONAL) — tóm tắt

- **evaluation_type:** AI_LLM_JUDGE_PROVISIONAL · **is_llm_as_judge:** True · **reproducible:** False · **human_verified:** False
- judge_model: `claude-opus-4-8` (lượt LLM thật, suy luận từng phiếu)
- method: direct semantic reasoning by the LLM (Claude) reading each form in an interactive human-directed session; blind to branch mapping/ground truth; NOT deterministic and NOT a reproducible scripted API call
- rubric: task05c-rubric-v1 · source_manifest_hash: `8bf30d09dc5f91fa…` · 2026-11-15T08:01:58.153631+00:00
- **Phiếu đã chấm:** 40/40

> Đây là lượt **LLM thật (Claude) chấm từng phiếu**, KHÁC với rule-based checker. Vẫn **KHÔNG** phải human grading (human vẫn PENDING) và **không tái lập chính xác** (chạy lại LLM có thể khác nhẹ). Blind với branch mapping.

## Static-only vs Static+Agent (LLM Claude, provisional)
| Tiêu chí | Static-only | Static+Agent |
|---|--:|--:|
| A2_claims_supported | 2.0 | 1.8 |
| B1_score_vs_truth_distinction | 2.0 | 2.0 |
| B2_no_feature_importance_from_score | 2.0 | 2.0 |
| C1_uncertainty | 2.0 | 2.0 |
| D1_recommendation_appropriate | 2.0 | 1.65 |
| **overall** | **2.0** | **1.89** |

**Nhận định (Claude):** Static-only (template cố định) đạt ~2.0 vì được viết để thỏa đúng 5 tiêu chí (nêu rõ uncalibrated, liệt kê limitations, trích dẫn số liệu chính xác, khuyến nghị khớp luật). Static+Agent gần bằng: mạnh ở B1/B2/C1 (nêu uncalibrated + limitations đầy đủ — rule-checker đã chấm thấp oan vì chỉ soi câu chữ trong explanation, bỏ qua limitations), nhưng thấp hơn ở **A2** (đôi khi bịa chi tiết: 'MFC imports', 'ExitProcess/MoveFileA', 'high entropy' khi không có) và **D1** (đôi khi khuyến nghị MONITOR cho ca dự đoán malicious / near-threshold — under-cautious).

**Meta-caveat:** rubric 5 tiêu chí này có thể thỏa bằng boilerplate ⇒ template đạt trần điểm không phải vì sâu sắc. Một tiêu chí 'độ cụ thể/insight' (không có trong rubric) có thể đảo lợi thế về phía agent tự do. Cần người chấm xác minh.
