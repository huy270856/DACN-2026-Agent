# TASK 05D — Real-PE validation + Human grading workflow

Hai mục tiêu: (A) kiểm chứng pipeline thật trên PE lành tính đa dạng (RAW_PE_E2E),
(C) công cụ chấm chất lượng giải thích bằng người chấm độc lập (offline, blind).
Không đổi model/threshold, không thêm node, không chạy malware, **không** sửa top-level README.

> **Track:** `RAW_PE_E2E` (PE thật, đọc read-only). Khác hẳn `FEATURE_RECORD_REPLAY` của 05C.
> **Malicious raw-PE E2E = BLOCKED_NO_APPROVED_SAMPLES** (không tải/chạy malware; EICAR không
> phải malicious PE nên không dùng làm bằng chứng).

## Thành phần

| File | Vai trò |
|------|---------|
| `sample_discovery.py` | Tìm PE lành tính (System32/SysWOW64), metadata + chữ ký, manifest (public/evaluator) |
| `validation_runner.py` | Chạy pipeline thật (static-only + static+agent) qua `dacn.investigate_real`, read-only |
| `grading_import.py` | Import + validate chặt annotation nhiều người chấm + inter-rater (Cohen κ) |
| `pilot.py` | Tạo gói pilot 20 mẫu cân đối strata (ẩn strata) từ dữ liệu 05C đã khóa |
| `ui/grading.html` | Giao diện chấm **offline** (không server, không cloud), blind, xuất JSON |
| `tests/test_05d.py` | Unit/integration tests |

## Part A — Chạy real-PE validation

```powershell
# 1) Khám phá mẫu benign (manifest evaluator có path; public bỏ path).
python -m evaluation.task05d.sample_discovery `
  --out evaluation\task05d\results\sample_manifest_full.json `
  --public-out evaluation\task05d\results\sample_manifest.json

# 2) Chạy pipeline thật (resume-safe; home chứa CaseState, gitignored).
python -m evaluation.task05d.validation_runner `
  --manifest evaluation\task05d\results\sample_manifest_full.json `
  --out evaluation\task05d\results `
  --home evaluation\task05d\results\_home
```
Kết quả: `results/validation_results.json` + `.csv` + `results/samples/*.json`.
Không báo Precision/Recall/F1 trên tập benign-only; chỉ đếm false-positive **trong tập này**
(không suy rộng ra thực tế — đây là corpus Microsoft-signed đồng nhất).

## Part C — Workflow chấm điểm (offline, blind)

```powershell
# 1) Tạo gói pilot 20 mẫu (cân đối strata, ẩn strata/nhãn/nhánh).
python -m evaluation.task05d.pilot `
  --audit-manifest evaluation\task05c\results\audit_manifest.json `
  --samples evaluation\task05c\results\samples `
  --records-cache D:\datasets\ember2018-cache\task05c_audit_records.jsonl `
  --out evaluation\task05d\results\pilot_package
```

2) **Mở UI chấm:** mở `evaluation/task05d/ui/grading.html` bằng trình duyệt (double-click,
   chạy offline). Nhập **Reviewer ID**, nạp `pilot_package/annotation_forms_blind_v2.json`,
   chấm 5 tiêu chí (A2/B1/B2/C1/D1) thang **0/1/2**, ghi chú, tiến độ tự lưu (localStorage),
   bấm **Xuất JSON** → file `annotations_<reviewer>_<ts>.json`.

3) **Tổng hợp (cần ≥2 người chấm để có inter-rater):**
```powershell
python -m evaluation.task05d.grading_import `
  --annotations annotations_grader1_*.json annotations_grader2_*.json `
  --forms evaluation\task05d\results\pilot_package\annotation_forms_blind_v2.json `
  --out evaluation\task05d\results\grading_aggregate.json
```
Validate chặt (chỉ 0/1/2; phát hiện duplicate reviewer/sample, mapping thiếu, invalid),
tính per-reviewer + **Cohen's kappa** + **percent agreement**, liệt kê **disagreements** để
con người **adjudicate** (không tự giải quyết), không auto-fill, không LLM-judge. Chỉ COMPLETE
khi mọi slot được điểm hợp lệ.

### Quy tắc blind (bắt buộc)
Người chấm **không** thấy: mapping STATIC_ONLY/STATIC_PLUS_AGENT, ground truth, strata TP/TN/FP/FN,
tên file lộ nhãn. Mapping X/Y→nhánh nằm ở file `branch_mapping_EVALUATOR_ONLY.json`, chỉ mở **sau**
khi chấm xong (bước evaluator).

## Tests

```powershell
python -m unittest evaluation.task05d.tests.test_05d -v
```

Xem `REPORT.md` để biết kết quả thực nghiệm và trạng thái human-grading (PENDING cho đến khi
người chấm thật hoàn thành).
