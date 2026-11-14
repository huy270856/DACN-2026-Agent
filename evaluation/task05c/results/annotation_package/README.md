# Gói chấm điểm (blind)

- `annotation_forms_blind.json`: mỗi mẫu có 2 phiếu (X và Y), ẩn nhánh.
- Chấm các tiêu chí semantic (A2,B1,B2,C1,D1) thang 0-2 theo rubric.
- `branch_mapping_EVALUATOR_ONLY.json`: ánh xạ X/Y -> nhánh (chỉ mở sau khi chấm).
- Không dùng LLM để chấm; không tự chấm nhánh của mình.
