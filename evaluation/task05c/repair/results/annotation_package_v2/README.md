# Gói chấm blind v2 (TASK 05C-R)

- 120 mẫu; mỗi mẫu 2 phiếu X/Y (ẩn nhánh) + evidence sheet đầy đủ.
- Mỗi phiếu có: static prediction, evidence observations (ID+facet+value), references trích dẫn, giải thích đầy đủ, limitations, recommendation+priority, cờ human-decision, ghi chú FEATURE_RECORD_REPLAY.
- Chấm 5 tiêu chí semantic (A2/B1/B2/C1/D1) thang 0-2 theo `scoring_guidance`.
- KHÔNG có ground-truth, KHÔNG có strata, KHÔNG lộ nhánh trong phiếu.
- `branch_mapping_EVALUATOR_ONLY.json` chỉ mở sau khi chấm xong.
- Không dùng LLM chấm; không tự chấm nhánh của mình.
- Tổng hợp sau khi điền: `python -m evaluation.task05c.repair.grading_aggregate`.
