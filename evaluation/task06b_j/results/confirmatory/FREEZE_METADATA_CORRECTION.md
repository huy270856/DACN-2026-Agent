# Đính chính metadata freeze — `run_v1` (không sửa artifact gốc)

- Freeze gốc: `results/confirmatory/run_v1/freeze.json`, SHA-256
  `4b37c37f1a0648c333af794e407c161abd9d6784c8d2cdb5ac82ac6c7f8dcfe9` (giữ nguyên, **không**
  chỉnh sửa).
- Trường sai: `rubric_id = task06b-j-rubric-v1`, `rubric_sha256 = 9fa271b8…`.
- Rubric thực tế dùng cho việc chấm confirmatory: **`task06b-j-rubric-v2`**, SHA-256
  `dbb791cda454d56bdc11d1c5cf72a622d96ced72359214794f0932feeae91557`. Đây là rubric đã duyệt ở
  RUBRIC_V2.md và CALIBRATION_V2_REPORT.md.

## Xác minh từ source (đọc, không sửa)

1. `evaluation/task06b_j/runner.py` import `rubric` (v1) và chỉ dùng nó ở dòng ghi
   `"rubric_id": rubric.RUBRIC_ID, "rubric_sha256": rubric.rubric_sha256()` vào freeze, cùng
   với việc băm file `rubric.py` trong `HARNESS_SOURCES`. Không có lời gọi nào khác.
2. `grep -rn rubric investigation_v3/ agent/` không có kết quả nào: Agent (prompt, schema,
   workflow v3.4, Controller, planner) không đọc rubric.
3. Câu hỏi: cả 20 dòng trong `run_v1/cases.json` có `question` trùng **đúng nguyên văn** với
   `question_text` trong `candidate_cases_v2_EVALUATOR_ONLY.json`. Freeze ghi
   `questions_version = task06b-j-questions-v2`.
4. Model, config và tool: `qwen3.5:4b` digest `d8b0f5e9…`, `max_iterations=5`,
   `max_tool_calls=1`, `num_predict=2048`, `temperature=0.1`, giống 06B-R2/CFG. LightGBM
   `5db192ec…`, threshold 0.83219. Có 19 source hash (Agent và harness) được freeze; runner
   tự kiểm `SOURCE_DRIFT` trước khi chạy.
5. Package chấm semantic được dựng bằng `blind_package --rubric-id task06b-j-rubric-v2`
   (xem `package_manifest.json` của package confirmatory: `rubric_sha256 = dbb791cd…`).

## Kết luận

**Chỉ là sai sót metadata, không phải protocol deviation.** Không ảnh hưởng tới treatment,
input hay hành vi của Agent. Freeze gốc được giữ nguyên làm bằng chứng; file này là bản đính
chính có liên kết.
