# TASK 05C — Đánh giá có kiểm soát: Static-only vs Static + Qwen Agent

So sánh hai nhánh trên **cùng** model/score/threshold và **cùng** evidence projection,
nhằm đo giá trị thực nghiệm mà Agent SLM thêm vào (và chi phí của nó). Không retrain,
không đổi model/threshold, không thêm node, không thực thi malware.

> **Hai track tách biệt (không trộn):**
> - `FEATURE_RECORD_REPLAY` — chạy LightGBM trên **feature records** EMBER2018 v2; Agent
>   suy luận trên bản *projection* có provenance. **KHÔNG** phải raw-PE E2E.
> - `RAW_PE_E2E` — pipeline 05B trên PE thật (chỉ benign ở môi trường này; malicious
>   raw-PE = BLOCKED, không tải/chạy malware).

Ground truth **chỉ** dùng cho evaluator (chọn mẫu + metric), **không bao giờ** vào input của Agent.

## Thành phần

| File | Vai trò |
|------|---------|
| `sampling.py` | Chấm toàn bộ test, phân tầng TP/TN/FP/FN + near-threshold, xuất manifest có seed |
| `evidence_projection.py` | Record → observations tĩnh an toàn (không raw floats, không bịa hành vi) |
| `static_only.py` | Baseline A: giải thích + khuyến nghị theo template/quy tắc cố định (đóng băng) |
| `agent_replay.py` | Nhánh B: chạy Qwen thật (tái dùng agent context/planner/schema) trên cùng evidence |
| `rubric.py` | Rubric 0–2 + auto-check (citation, forbidden-claim, safety) + phiếu chấm blind |
| `metrics.py` | Detection (full test) + investigation aggregation + Wilson CI + McNemar |
| `runner.py` | Điều phối, resume theo từng mẫu, xuất results/CSV/annotation package |
| `examples.py` | Sinh phiếu ví dụ đã ẩn thông tin |
| `tests/test_05c.py` | Negative tests (leakage, fake/cross-case IDs, unsupported claims, injection, …) |

## Chạy

```powershell
# 1) Tạo manifest audit (seed, phân tầng). Dùng model + manifest của TASK 05A.
python -m evaluation.task05c.sampling `
  --cache D:\datasets\ember2018-cache `
  --model research\independent_static_ml\artifacts\model_lightgbm.txt `
  --model-manifest research\independent_static_ml\artifacts\model_manifest.json `
  --out evaluation\task05c\results\audit_manifest.json

# 2) Chạy đánh giá (resume được; FEATURE_RECORD_REPLAY).
python -m evaluation.task05c.runner `
  --manifest evaluation\task05c\results\audit_manifest.json `
  --model research\independent_static_ml\artifacts\model_lightgbm.txt `
  --model-manifest research\independent_static_ml\artifacts\model_manifest.json `
  --jsonl D:\datasets\ember2018-v2\test_features.jsonl `
  --records-cache D:\datasets\ember2018-cache\task05c_audit_records.jsonl `
  --out evaluation\task05c\results

# 3) Phiếu ví dụ đã ẩn thông tin.
python -m evaluation.task05c.examples --out evaluation\task05c\results

# Tests
python -m unittest evaluation.task05c.tests.test_05c -v
```

Cấu hình Qwen (thinking OFF) và mọi version (baseline/prompt/rubric/model digest) được
ghi trong `results/eval_results.json`. Chạy lại bỏ qua các mẫu đã hoàn thành (resume).

## Kết quả & giới hạn

Xem `REPORT.md`. Các tiêu chí semantic của rubric (A2/B1/B2/C1/D1) để **CHƯA CHẤM** và
kèm gói chấm blind (`results/annotation_package/`) cho chủ dự án chấm độc lập — không
dùng LLM làm giám khảo, không tự chấm.
