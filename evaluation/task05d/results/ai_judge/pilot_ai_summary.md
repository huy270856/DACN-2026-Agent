# TASK 05D-J — AI grading (PROVISIONAL) — tóm tắt

- **evaluation_type:** AI_JUDGE_PROVISIONAL · **human_verified:** False
- judge_model: `claude-opus-4-8` · method: rubric-encoded deterministic scoring (transparent/auditable; not an opaque LLM call)
- judge_version: ai-judge-v1.1 · rubric: task05c-rubric-v1
- source_manifest_hash: `8bf30d09dc5f91fa…` · 2026-11-15T07:47:18.141971+00:00
- **Phiếu đã chấm:** 40 · **Flag cần người review:** 7

> ĐÂY KHÔNG PHẢI human grading. Human grading của TASK 05D vẫn **PENDING**. Điểm AI là tạm thời, để chuyển sang TASK 06; người đánh giá kiểm tra lại sau.

## Phân bố điểm theo tiêu chí (blind, 40 phiếu)
| Tiêu chí | 0 | 1 | 2 | null |
|---|--:|--:|--:|--:|
| A2_claims_supported | 0 | 20 | 20 | 0 |
| B1_score_vs_truth_distinction | 2 | 13 | 25 | 0 |
| B2_no_feature_importance_from_score | 0 | 0 | 40 | 0 |
| C1_uncertainty | 0 | 0 | 40 | 0 |
| D1_recommendation_appropriate | 0 | 5 | 35 | 0 |

## Tổng hợp Static-only vs Static+Agent (AI provisional)
| Tiêu chí | Static-only (mean) | Static+Agent (mean) |
|---|--:|--:|
| A2_claims_supported | 2.0 | 1.0 |
| B1_score_vs_truth_distinction | 2.0 | 1.15 |
| B2_no_feature_importance_from_score | 2.0 | 2.0 |
| C1_uncertainty | 2.0 | 2.0 |
| D1_recommendation_appropriate | 2.0 | 1.75 |
| **overall** | **2.0** | **1.58** |

Lưu ý: chênh lệch là **AI provisional**, chưa được người xác minh; không dùng để tuyên bố nhánh nào thắng.

## Vấn đề bằng chứng & khuyến nghị (AI provisional)
- Claim không được evidence hỗ trợ (A2=0, có forbidden claim): **0**
- Trích dẫn id không có trong evidence sheet / grounding chưa đủ (A2=1): **20** (lưu ý: gói annotation bỏ sót evidence prediction khỏi sheet ⇒ một số citation không kiểm được, cần người xác nhận)
- Khuyến nghị chưa hợp lý (D1 mismatch): **5** (chủ yếu: dự đoán malicious nhưng khuyến nghị MONITOR — under-cautious)

## Ưu / nhược điểm (AI provisional, chưa được người xác minh)
- **Static-only (baseline template):** mạnh & nhất quán ở A2/B1/D1 (grounding + nêu rõ score chưa hiệu chỉnh + khuyến nghị đúng mức); overall 2.0.
- **Static+Agent (Qwen):** ngang ở B2/C1 (không bịa feature-importance; nêu limitations), nhưng yếu hơn ở A2 (trích dẫn evidence prediction không có trong sheet ⇒ chưa kiểm được), B1 (không nhất quán nêu score chưa hiệu chỉnh), D1 (đôi khi MONITOR trên ca dự đoán malicious); overall 1.58.
- Kết quả **AI provisional** khớp hướng 05C (Agent chưa tạo thêm giá trị giải thích vượt baseline); **chờ người chấm xác minh**, không kết luận cuối.

## Cần người review
- AI_SCORE_0_needs_human_confirm: 2
- AI_recommendation_mismatch: 5

Audit trail: `pilot_ai_scores.json`, `pilot_ai_reasoning.json`, `human_review_queue.json`.