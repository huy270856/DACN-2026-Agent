# TASK 05B — Báo cáo: Real LightGBM → CaseState → Qwen3.5-4B → Phiếu điều tra

**Kết luận: PASS** (có giới hạn phạm vi nêu ở mục 8).

Tích hợp detector thật của TASK 05A vào stack D1–D9 và Agent Qwen3.5-4B thật,
tạo pipeline điều tra PE chạy được end-to-end. Mọi bằng chứng sinh từ chính lượt
chạy trên máy dev (Windows 11, Python 3.12.10), 2026-11-14.

---

## 0. Verify TASK 05A trước khi dùng (mục 4 đề bài)

- `git`: branch `feat/task05a-independent-static-ml`, HEAD `b52b861`, worktree sạch
  khi bắt đầu. TASK 05B làm trên branch riêng, không reset/clean/discard.
- Model artifact: `research/independent_static_ml/artifacts/model_lightgbm.txt`,
  **SHA-256 khớp manifest** = `5db192ec1bda…c509609`, `feature_count=2381`,
  threshold `0.8321860386013389`. Smoke inference read-only trên PE lành tính
  (`notepad.exe`) → benign, score 0.005086. **Không** dùng model/branch EMBER cũ
  của thành viên khác; **không** thay bằng mock khi artifact hợp lệ.

## 1. Kiến trúc tích hợp (không thêm node, không mở rộng hạ tầng)

Đường chạy thật:

```
PE file → Node B (identity, SHA-256, PE format, target_ref)
        → Node C (case)
        → D1 → D2(registry) → D3(validate args vs pe-predict-input-v1)
        → D4(policy allowlist) → D5(pinned read-only adapter) → D6
        → D7(normalize + validate static-prediction-v1, bind target & model digest)
        → D8(sign) → D9(commit) → Node C evidence (facet static.pe_malware_prediction)
        → Qwen3.5-4B (đọc evidence, đánh giá alignment, KHÔNG ghi đè nhãn)
        → Phiếu điều tra tiếng Việt (JSON + Markdown)
```

Ba kết quả tách bạch (mục 3 đề bài):
- **static_prediction** — nhãn/score/threshold/model id+digest/extractor (LightGBM, có thẩm quyền).
- **agent_assessment** — evidence_alignment ∈ {CONSISTENT, CONFLICT, INSUFFICIENT_EVIDENCE},
  review_required, reasoning, evidence refs, limitations; `does_not_override_static_label=true`.
- **recommendation** — MANUAL_REVIEW / MONITOR / AVOID_EXECUTION / CONSIDER_QUARANTINE
  (chỉ đề xuất), priority, `requires_human_decision=true`, **execution_status luôn NOT_EXECUTED**.

## 2. Những file đã thay đổi

**Thêm mới:**
- `d0/schemas/pe-predict-input-v1.schema.json` — input args (additive).
- `d0/schemas/static-prediction-v1.schema.json` — prediction output (additive; **không**
  sửa `ember-output-v1`).
- `research/independent_static_ml/d5_adapter.py` — adapter D5 pinned, read-only: PE →
  EMBER v2 → LightGBM → static-prediction-v1. Tái dùng extractor/model của 05A, không viết lại.
- `orchestrator/pe_prediction_result.py` — D7 normalizer riêng cho tool mới (mirror EMBER),
  bind target SHA-256 + model id/digest. Không sửa lõi `result_validator.py`.
- `dacn/investigation.py` — backend detector (D2/D4/D5/D7/D8/D9), chạy prediction qua D1–D9,
  đọc evidence, dựng phiếu điều tra JSON + Markdown tiếng Việt.
- `tests/test_task05b.py` — unit + real-model + live-LLM tests.

**Sửa (tối thiểu, additive):**
- `agent/schema.py` — thêm trường tuỳ chọn `finding.assessment` (alignment/review/recommendation).
- `agent/context.py` — khi có prediction thật, hướng dẫn Agent đánh giá alignment và KHÔNG ghi đè nhãn.
- `agent/report.py` — surface `agent_assessment`; sửa dòng limitation cũ (“no LightGBM”).
- `dacn/application.py` — thêm `investigate_real(...)` (intake→predict→agent→report).
- `dacn/cli.py` — `python -m dacn investigate --file <PE>` (giữ `--case-id`, thêm `--no-agent`).

**Không đổi:** D1 core, D2, D3, D4, D5 executor, D6, D8, D9, Node B, Node C, hợp đồng
`ember-output-v1`. Không Ghidra/REA/sandbox. Không thêm node.

## 3. Model artifact / digest (dùng trong lượt này)

- model_id: `dacn-lgbm-ember2018v2-5db192ec1bda`
- model SHA-256: `5db192ec1bda850d0e1873af705b57d05aad414aa35e8520c8315ece1c509609`
- dataset: EMBER2018 feature version 2; feature_version 2; 2381 chiều; threshold 0.8321860.
- Ràng buộc digest 3 lớp: (a) D5 **pin** file model (executor verify digest trước khi chạy);
  (b) adapter tự verify `--expected-model-sha256`; (c) D7 kiểm `payload.model_sha256` khớp
  model đã cài. Sai bất kỳ lớp nào ⇒ từ chối, không chấm điểm.

## 4. Live end-to-end trace (benign PE thật)

Mục tiêu: `C:\Windows\System32\notepad.exe`
SHA-256: `468ffe129c395abf6b21a09efdf261910a95fb98aa982ead73caa7b2b684577e`

```
Node B/C      → case CASE-4278…, target_ref verified (PE)
D1–D9 predict → RUN-ccec4b94…, outcome SUCCESS
Node C commit → evidence EV-6445…  facet=static.pe_malware_prediction
static label  → BENIGN (class 0), raw_score 0.005086, threshold 0.832186 (uncalibrated)
Qwen3.5-4B    → planner=LOCAL_QWEN; evidence_alignment=CONSISTENT; review_required=true;
                verdict riêng=INSUFFICIENT_EVIDENCE (không ghi đè nhãn tĩnh);
                cited EV-6445…(prediction), EV-333…(pe_header), EV-046…(format)
recommendation→ MONITOR, priority LOW, requires_human_decision=true, NOT_EXECUTED
report        → investigation_report.{json,md} (phiếu tiếng Việt)
```

Phiếu điều tra mẫu: `…/artifacts/investigation_reports/<case>/investigation_report.md`
(sinh ra khi chạy `python -m dacn investigate --file <PE>`).

## 5. Lệnh chạy

```powershell
# Pipeline thật đầy đủ (detector + Qwen + phiếu):
python -m dacn investigate --file C:\Windows\System32\notepad.exe

# Chỉ detector + phiếu (bỏ qua SLM) để kiểm tra nhanh / CI:
python -m dacn investigate --file C:\Windows\System32\notepad.exe --no-agent
```

## 6. Kết quả test (phân biệt rõ các mức — mục 11 đề bài)

| Mức | Bộ test | Kết quả |
|-----|---------|---------|
| Unit (05B) | schema additive, D7 binding (sai target hash/model digest/failed+payload), report builder, recommendation | 13 PASS |
| Real-model integration (Windows + artifact) | benign PE → predict + commit (không agent); malformed PE → **không** commit nhãn benign giả | 2 PASS |
| Blocker | model thiếu → `DetectorUnavailableError` (không mock) | 1 PASS |
| Live LLM (Qwen) | full pipeline benign → alignment hợp lệ, không ghi đè | PASS khi `DACN_AGENT_LIVE=1` (mặc định SKIP) |
| Regression | `tests/` (255, 2 skip-live), `research/independent_static_ml/tests` (25), `test_dacn` (20) | ALL PASS |

Tổng: 300 test PASS, 2 SKIP (live-Qwen theo thiết kế). **Không có safety regression.**
Lưu ý phân mức: *Unit PASS ≠ Mock-integration PASS ≠ Real-model PASS ≠ Live-LLM PASS ≠
Full real E2E PASS* — tất cả các mức trên đều đã đạt trong lượt này.

Các tình huống lỗi đã kiểm (mục 9/10): malformed PE, model missing, wrong model digest
(D7 + adapter + pin), feature/version mismatch (adapter + D7 tool-contract check),
inconsistent target SHA-256 (D7 TARGET_CHANGED), tool DENY (policy allowlist + agent
test), prompt injection (agent test), Qwen unavailable (xử lý thành error, không kết luận
benign). Mẫu malicious raw-PE: **không** tự tải/chạy (xem mục 8).

## 7. Đối chiếu tiêu chí PASS (mục 14 đề bài)

| # | Tiêu chí | Trạng thái |
|---|----------|-----------|
| 1 | Gọi model LightGBM 05A thật thành công | ✅ RUN-ccec…, SUCCESS |
| 2 | Raw benign PE phân tích read-only | ✅ notepad.exe, không thực thi |
| 3 | Prediction validate + commit Node C qua D1–D9 | ✅ EV-6445…, facet static.pe_malware_prediction |
| 4 | Qwen3.5-4B thật đọc prediction/evidence | ✅ planner=LOCAL_QWEN |
| 5 | Agent xuất assessment, không ghi đè nhãn | ✅ alignment=CONSISTENT, does_not_override=true |
| 6 | Phiếu điều tra tiếng Việt có evidence refs | ✅ JSON + Markdown |
| 7 | Không safety regression / test quan trọng FAIL | ✅ 300 PASS |
| 8 | Live E2E trace + model digest | ✅ mục 4 + mục 3 |
| 9 | Không mock analyzer trong live E2E chính | ✅ build_detector_backend chỉ đăng ký tool thật |

## 8. Giới hạn còn lại

- **Raw malicious PE chưa kiểm chứng E2E**: không tự tải/chạy malware. Mới chứng minh
  phát hiện malicious trên *feature records* (tập test 05A, AUC 0.993); đường bytes→vector
  trên mẫu độc hại thật cần mẫu do nhóm cấp qua môi trường được phê duyệt.
- Inference dùng LIEF 0.15.1 vs training records LIEF 0.9.0 → không khẳng định parity cho
  đường raw-PE→vector (đã ghi trong `limitations` của mọi prediction).
- Raw score **chưa calibrate** (không phải xác suất).
- Agent giải thích “feature nào ảnh hưởng” chỉ là **dấu hiệu quan sát** (PE structure), không
  phải attribution nhân quả của LightGBM; chưa tích hợp feature-importance có nguồn.
- Chất lượng suy luận SLM 4B hạn chế; phiếu luôn ghi review_required và cần người quyết định.
- D4/D8 giữ nguyên; approval gate tool-call vẫn fail-closed (không có wire schema).

## 9. Điều kiện để làm TASK 05C

- Bộ mẫu benign + malicious có nhãn, raw-PE, được cấp qua môi trường phê duyệt (cho E2E malicious).
- Khung đánh giá so sánh Static-only vs Static+Agent (accuracy, FP/FN, chất lượng giải thích).
- (Tuỳ chọn) calibration tách tập, và feature-importance attribution có nguồn cho phần giải thích.
- Owner duyệt schema `static-prediction-v1` / `investigation-report-v1` (hiện PROPOSED, additive).
