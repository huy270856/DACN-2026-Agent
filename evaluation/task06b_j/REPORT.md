# TASK 06B-J — Báo cáo: Independent Semantic & Investigation Evaluation

> Cập nhật sau continuation (Judge calibration và controlled runner). Bản đầu (Stage 1–4) đã
> được gộp vào đây; lịch sử chi tiết xem Git.

**ENGINEERING: PARTIAL, gần hoàn tất.**

- Đã xong: runner 3 arm, neutral staging, leakage audit, holdout audit, Judge kit (export và
  import), validator, lock/analyze, 31 test.
- Còn thiếu: lượt Judge calibration thật (owner phải chạy), UI human grading (owner chưa yêu
  cầu), owner duyệt confirmatory.

> **Cập nhật post-calibration:** Judge calibration DEV v1 đã hoàn tất (2 track, `COMPLETE_VALID`, đã lock). Xem
> `CALIBRATION_REPORT.md`: các probe được phát hiện 4/4 ở mức claim; đề xuất rubric v2 và questions v2 trước confirmatory;
> 6 ca bất đồng về self-corroboration cần người phân xử. Bảng gate mới nhất nằm ở CALIBRATION_REPORT §8.

**RESEARCH: NOT_RUN.**

- `CONFIRMATORY_NOT_RUN`.
- Judge calibration = **PENDING** (kit đã export, chưa có lượt chấm).
- Human grading = **PENDING**.
- Chưa có điểm semantic nào. Câu hỏi "Agent tự gọi tool có thêm giá trị điều tra không"
  **chưa được trả lời**.

## 1. Dùng lại từ TASK 05D-J

- `_cohen_kappa` cho phần agreement.
- Nguyên tắc blind/mapping evaluator-only, không auto-resolve bất đồng.
- `claude_judge.py` là historical (judgment nhúng sẵn, mặc định = 2): **không** dùng, **không**
  diễn giải lại. Rubric 05C bị thay vì đạt trần nhờ boilerplate (AUDIT.md).

## 2. Hạ tầng (`evaluation/task06b_j/`)

| File | Chức năng |
|---|---|
| `rubric.py`, `RUBRIC.md` | `task06b-j-rubric-v1` (R1–R9, applicability, verdict claim). Chưa đổi |
| `blind_package.py` | Package 2 view, reference sheet, leakage scan, mapping evaluator-only |
| `score_validation.py` | Validator chặt. LLM Judge phải có `human_verified=false` |
| `analysis.py` | `lock` rồi `analyze`, có CLI |
| `judge_kit.py`, `JUDGE_RUNBOOK.md` | **Mới**: `INTERACTIVE_LLM_JUDGE_BLIND_BATCH` (export kit ngoài repo, import raw kèm SHA, metadata `UNKNOWN` khi không biết) |
| `judge_adapter.py` | Adapter API trung lập provider. Không dùng (paid API chưa được phép) |
| `runner.py` | **Mới**: runner 3 arm, neutral staging, isolation checks, freeze, leakage mọi turn |
| `questions.py` | **Mới**: 5 loại câu hỏi khai báo trước, phân bổ cân bằng, strata answerability |
| `leakage.py` | **Mới**: token identity (tên, path, version resources, signer); phân biệt ACCIDENTAL và PE_DERIVED |
| `holdout_audit.py` | **Mới**: audit theo SHA và chương trình, near-duplicate, chữ ký; manifest candidate |
| `pipeline_metrics.py` | Metrics tất định và coverage diagnostic |
| `tests/` | 31 test (13 cũ, 18 mới) |

## 3. Xác minh lại các phát hiện trước (từ raw source và trace)

| Phát hiện | Cách xác minh | Kết quả |
|---|---|---|
| tracert: WS2_32/IPHLPAPI đã commit (idx 26–41) nhưng không đọc | `pipeline_metrics.coverage_diagnostic` trên `r2_debug_v34/00_E.json`; test `test_coverage_diagnostic_on_frozen_tracert_trace` | Xác nhận: 15/15 entry liên quan không bao giờ hiển thị, 0 read |
| Rò rỉ path System32 trong prompt | `leakage.scan_facts` trên turn 1 của trace đó; test `test_leakage_detects_original_path_in_unstaged_historical_prompt` | Xác nhận: `FAIL_ACCIDENTAL_IDENTITY_LEAK` (vị trí `unknowns`) |
| SHA trôi do Windows Update | Audit holdout | Xác nhận, và **mở rộng**: `ipconfig.exe` (đã dùng ở 05D) có SHA mới nhưng import trùng 100%. Audit lần trước chỉ theo SHA nên đã xếp sai vào "disjoint" |
| Self-corroboration 3/3 | ID của prediction ∈ `supporting_evidence_ids` ở cả 3 final v3.4 | Xác nhận về cấu trúc. Mức độ nghiêm trọng về semantic: PENDING |

## 4. Judge

- **Lượt gọi Judge đã diễn ra: không có.** Kit đã export cho owner chạy:
  - `C:\src\06bj_judge_kits\06BJ-DEV-CAL-v1-trackA`: 19 item, blind với nhãn arm, không blind
    hoàn toàn với treatment.
  - `C:\src\06bj_judge_kits\06BJ-DEV-CAL-v1-trackB`: 16 item, nhìn thấy trace, không blind
    với hành vi tool.
- Kit chỉ chứa item phía grader, `JUDGE_PROMPT.md`, `RUBRIC.md` và `kit_manifest.json`.
  Không có mapping, kỳ vọng, flag của checker hay điểm cũ; leakage scan trên toàn bộ kit đều
  sạch (đã có test).
- Prompt SHA-256 Track A `e6926fed…`, Track B `cc0f807d…`. Bản sao lưu ở
  `results/dev/judge_kit_exports_v1/`.
- Giới hạn độc lập:
  - Judge (Claude) cùng họ model với developer đã viết probe và kỳ vọng.
  - Phiên Judge có thể đọc ra ngoài kit nếu owner cấp quyền.
  - Item DEV vẫn chứa path System32 vì là trace lịch sử chưa stage.

## 5. Runner 3 arm và neutral staging

- **MOCK integration** (Node B, LightGBM, D1–D9 thật; planner MOCK) trên whoami/where (file
  test của 05D/06B):
  - A/B/C có cùng initial state, cùng score, cùng câu hỏi; home tách riêng.
  - B: 0 tool, 0 retrieval, không có event D*, CaseState không đổi, không thấy evidence mới
    của C (kể cả khi C chạy trước).
  - Path đã stage không chứa tên gốc hay `System32`.
  - Runner từ chối ghi đè, phát hiện source drift, và từ chối run live khi thiếu authorization.
- **DEV smoke với Qwen thật** (`results/dev/staging_smoke_v2`, `DEV_SMOKE`, một lượt):
  - File: tracert (Q_NET) và findstr (Q_FILE). Cả hai là file DEV, **không** thuộc holdout.
  - Ollama v0.40.16, `qwen3.5:4b`, digest `d8b0f5e9…`, khớp với freeze.
  - Kết quả: isolation **4/4 PASS**; leakage trên mọi turn **0 hit** (cả token chương trình
    lẫn provenance).
  - Quan sát DEV, n=2, không suy rộng:
    - B: cả hai `REQUEST_MORE_EVIDENCE` → incomplete.
    - C tracert: đọc thêm 1 trang và trích WS2_32 → `FINISHED_FLAGGED` (self-corroboration).
    - C findstr: `FINISHED` không flag.
  - Không thể quy kết sự khác biệt so với DEBUG cũ cho staging hay câu hỏi: prompt, câu hỏi
    và lượt chạy đều khác nhau.

### Leakage còn lại (residual)

- Context ban đầu và tool output đã stage không còn token tên chương trình hay provenance.
- Tuy vậy, bộ import (ví dụ `ulib.dll`, API ICMP) vẫn có thể giúp Qwen nhận ra tiện ích
  Windows quen thuộc. Đây là static evidence hợp lệ và **không** bị xóa.
- Vì vậy chỉ được nói "giảm leakage tình cờ", **không** được nói "ẩn danh hoàn toàn".

## 6. Holdout

Chi tiết: DATASET_AUDIT.md §6.

- Đủ điều kiện: 20/22. Loại `ipconfig` (đã đánh giá ở 05D, Jaccard 1.0) và `pathping`
  (near-duplicate của tracert, Jaccard 0.941).
- Manifest candidate: 20 alias, mỗi loại câu hỏi 4 case. Trạng thái
  **CANDIDATE_PENDING_OWNER_APPROVAL**.
- Toàn bộ là benign, ký Microsoft. **Không** suy rộng sang malware, **không** tuyên bố cải
  thiện detection.
- Phát hiện: với 14/20 file, API process liên quan nằm sau cap 64 entry của analyzer.

## 7. Gate confirmatory

| # | Điều kiện | Trạng thái |
|---|---|---|
| 1 | Runner 3 arm đã kiểm chứng | **PASS** (MOCK integration + live DEV smoke 4/4 isolation) |
| 2 | Manifest holdout đủ điều kiện | **READY, chờ owner duyệt** (20 case) |
| 3 | Audit overlap mức chương trình | **PASS** (tên, OriginalFilename, Jaccard). Còn rủi ro liên quan chức năng |
| 4 | Giảm leakage, ghi residual | **PASS (mitigated)**. Residual: nhận diện qua import |
| 5 | Rubric đóng băng | **PASS** v1 (chưa có calibration nên chưa có lý do đổi) |
| 6 | Judge calibration | **PENDING**: owner chạy kit A/B, import, lock, analyze |
| 7 | Validation khi import Judge | **PASS** (đã test với dữ liệu MOCK) |
| 8 | Freeze Agent/model/config | **READY_NOT_FROZEN**: freeze tạo lúc `prepare` holdout. CFG giống 06B-R2; Agent source không đổi |
| 9 | Ollama | **AVAILABLE** lúc kiểm (v0.40.16, digest `d8b0f5e9…`). Phải kiểm lại lúc chạy |
| 10 | Owner authorization | **NOT_GRANTED** |

Kết luận: **chưa chạy confirmatory.** Thứ tự đề xuất: (6) calibration → nếu cần thì rubric v2
→ owner duyệt (2) và (10) → `prepare` holdout (tạo freeze, gate 8) → `run` một lần duy nhất.

Lệnh dự kiến (chỉ chạy sau khi được duyệt):

```powershell
python -m evaluation.task06b_j.runner prepare --cases evaluation\task06b_j\results\holdout\candidate_cases_v1_EVALUATOR_ONLY.json --out evaluation\task06b_j\results\confirmatory\run_v1 --mode CONFIRMATORY
python -m evaluation.task06b_j.runner run --out evaluation\task06b_j\results\confirmatory\run_v1 --authorized-by "<owner, ngày, phạm vi>"
python -m evaluation.task06b_j.runner spec --out evaluation\task06b_j\results\confirmatory\run_v1 --spec evaluation\task06b_j\results\confirmatory\package_spec_v1.json
python -m evaluation.task06b_j.blind_package --spec evaluation\task06b_j\results\confirmatory\package_spec_v1.json --out evaluation\task06b_j\results\confirmatory\package_v1 --seed <seed mới> --package-id 06BJ-CONF-v1
# sau đó: judge_kit export/import, rồi analysis lock/analyze (xem JUDGE_RUNBOOK.md)
```

## 8. Error analysis DEV (developer diagnostic, không phải điểm)

Các mục trong bản trước vẫn giữ nguyên giá trị:

- Self-corroboration 3/3.
- FINISHED_FLAGGED khác với MANUAL_REVIEW hiệu lực.
- tracert không đọc entry network đã commit.
- `reason` khẳng định vắng mặt mà không giới hạn phạm vi.
- Import ref resolve được ≠ hỗ trợ claim.
- Kiến thức ngoài evidence nhờ rò rỉ path.
- Arm B v3.3 incomplete 3/3.

Tất cả là *candidate* trong `calibration_key.json`, cần Judge hoặc người phân xử.

## 9. Kiểm chứng của lượt này

- `python -m pytest evaluation/task06b_j/tests -q`: **31 passed** (gồm MOCK integration với
  D1–D9 thật).
- Full regression: xem tin nhắn bàn giao và commit.
- Live Qwen: **chỉ** DEV smoke 2 file × 2 arm (A không gọi LLM). Không chạy confirmatory.
- Không sửa source Agent, D1–D9, LightGBM/threshold, README gốc hay artifact đóng băng nào.
