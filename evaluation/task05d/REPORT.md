# TASK 05D — Báo cáo: Real-PE validation + Human grading workflow

**Kết luận: PARTIAL — ENGINEERING COMPLETE, HUMAN GRADING PENDING.**
Pipeline thật đã chạy trọn vẹn trên 35 PE lành tính (RAW_PE_E2E, 0 lỗi); công cụ chấm
điểm offline/blind + import/aggregate đa người chấm đã xong và test đầy đủ. Chưa có điểm
người chấm thật ⇒ phần semantic vẫn PENDING. Malicious raw-PE E2E = **BLOCKED** (chưa có mẫu).

- Branch `feat/task05d-real-pe-human-eval` (từ `main` đã merge `2b63c527`). Không đổi
  model/threshold, không thêm node, không chạy PE/malware, **không** sửa top-level README,
  không merge/push main. Model digest `5db192ec…c509609` xác minh khớp.
- Mọi số liệu sinh ngày 2026-11-15 (Windows 11, Python 3.12.10, Ollama qwen3.5:4b thinking OFF).

---

## PART A — Real-PE validation (RAW_PE_E2E)

### A.1 Tập benign PE (provenance rõ ràng)
35 PE hệ thống Windows (System32 + SysWOW64), tất cả **Authenticode VALID**:

| Thuộc tính | Phân bố |
|---|---|
| Loại | EXE 22 · DLL 13 |
| Định dạng | PE32+ 27 · PE32 8 |
| Kiến trúc | AMD64 27 · I386 8 |
| Chữ ký | VALID 35/35 |
| Kích thước | 19 KB – 8.1 MB |
| Sections | 5 – 15 |
| Imported functions | 0 – 2666 |

Nhãn benign = **provenance-based** (OS cung cấp, Microsoft-signed). Chữ ký hợp lệ chứng minh
**nguồn gốc**, không tự chứng minh vô hại; độ tin cậy nhãn = MEDIUM-HIGH. Bỏ qua 3 ứng viên
(notepad.exe trùng SHA-256, mspaint.exe/write.exe không tồn tại trên máy). Manifest:
`results/sample_manifest.json` (public, đã bỏ local path); bản evaluator có path để ngoài Git.

### A.2 Kết quả pipeline thật (static-only + static+agent)
Mỗi PE chạy qua `dacn.investigate_real` (Node B → D1–D9 → EMBER v2 + LightGBM → Node C →
Qwen), read-only, **không** bypass D1–D9, **không** mock.

| Chỉ số | Kết quả |
|--------|---------|
| Detector inference success | **35/35 (100%)** |
| Agent completion (LOCAL_QWEN) | **35/35 (100%)** |
| Evidence commit (Node C) | **35/35 (100%)** |
| Report generation | **35/35 (100%)** |
| Parse failures | 0 |
| **False positive (tập này)** | **0/35 (0.0%)** |
| Latency static-only (mean) | **1.74 s** |
| Latency static+agent (mean) | **8.03 s** (overhead agent ~**6.29 s**) |
| Agent alignment | CONSISTENT 34 · INSUFFICIENT_EVIDENCE 1 |
| Agent review_required | 31/35 (88.6%) |

**Không** báo Precision/Recall/F1 trên tập benign-only. False-positive chỉ đếm **trong tập
Microsoft-signed đồng nhất này**, **không** suy ra FPR thực tế (giới hạn A.4).

### A.3 Error analysis
- 0 ca dự đoán MALICIOUS (không có anomaly), 0 parse fail → không có ca cần sửa label.
- 1 ca agent khác CONSISTENT: `kernel32.dll` (PE32+ DLL, score 0.00076 → benign) → agent
  trả **INSUFFICIENT_EVIDENCE** + review=True. Hợp lý: kernel32.dll có **0 import** nên quan
  sát tĩnh quá mỏng để kết luận. Đây là hành vi trung thực, không phải lỗi. Giữ nguyên evidence.
- Phân biệt lớp lỗi (parser / model / orchestration / agent): không lớp nào phát sinh ở lượt này.

### A.4 Giới hạn khi dùng Windows system binaries làm tập benign
- Toàn bộ Microsoft-signed, phân phối chuẩn, giàu import hợp lệ ⇒ **dễ** cho detector; 0 FP ở
  đây **không** đại diện FPR trên phần mềm bên thứ ba/đóng gói. Tập **đồng nhất**, thiếu
  benign "khó" (installer nén, phần mềm hiếm). Không suy rộng.

## PART B — Malicious raw PE

`MALICIOUS_RAW_PE_E2E = BLOCKED_NO_APPROVED_SAMPLES`.
Không tải/không thực thi/không sao chép malware. **Không** dùng EMBER feature records giả làm
raw PE. **Không** dùng EICAR làm bằng chứng phát hiện malware PE (EICAR không phải malicious PE
có feature behavior thực). Chỉ nhận một tập raw PE được cấp hợp lệ trong môi trường cô lập.
Đây là blocker riêng, **không** làm hỏng phần benign validation.

## PART C — Human grading workflow (offline, blind)

- **UI chấm offline** `ui/grading.html`: self-contained, chạy bằng mở file trong trình duyệt,
  **không server/không cloud**. Nạp gói blind JSON → hiển thị static prediction + evidence
  sheet (ID+facet+value) + references + explanation + limitations + recommendation cho mỗi
  phiếu X/Y; chấm A2/B1/B2/C1/D1 thang **0/1/2**; ghi chú; tự lưu (localStorage); **Xuất JSON**.
  Ẩn nhánh/ground-truth/strata.
- **Import/aggregate** `grading_import.py`: validate chặt (chỉ 0/1/2; phát hiện duplicate
  reviewer, duplicate (sample,label), blind_label sai, invalid score, mapping thiếu/thừa);
  per-reviewer status; **inter-rater** percent-agreement + **Cohen's kappa** khi ≥2 người;
  liệt kê **disagreements** để con người adjudicate (không tự giải quyết). Giữ raw, không
  auto-fill, không LLM-judge. COMPLETE chỉ khi mọi slot hợp lệ.
- **Pilot** `pilot.py`: gói 20 mẫu cân đối strata (4/strata, **ẩn strata**) từ dữ liệu 05C đã
  khóa → `results/pilot_package/` (+ rubric_version). Không tự điền điểm.

**Trạng thái: CHƯA CHẤM** (chưa có reviewer thật). **Không** tuyên bố đã có human annotation.

## PART D — So sánh Static-only vs Static+Agent (trên 35 PE thật)

| Khía cạnh | Static-only | Static+Agent | Ghi chú |
|---|---|---|---|
| Nhãn phát hiện | benign ×35 | benign ×35 (không ghi đè) | detection **đồng nhất** (cùng model/score/threshold) |
| Report completeness | 35/35 | 35/35 | cả hai đầy đủ |
| Evidence ref validity | n/a (template) | hợp lệ (committed evidence) | agent trích dẫn evidence thật |
| Latency | 1.74 s | 8.03 s | **agent đắt hơn ~6.3 s/mẫu** |
| Unsupported claims | 0 | 0 (ở tập benign này) | — |
| Ca static-only "tốt hơn" | — | — | agent không thêm năng lực phát hiện ở benign-only |
| Semantic rubric | CHƯA CHẤM | CHƯA CHẤM | cần người chấm |

Trên tập benign này Agent **không** cải thiện detection (không có FP để bắt), thêm chi phí
~6.3 s/mẫu và một phần giải thích/triage; 1 ca trả INSUFFICIENT_EVIDENCE (thận trọng hơn).
**Không** giả định Agent phải thắng. **Không** trộn với feature-record replay của 05C.

## TESTS

`evaluation/task05d/tests/test_05d.py` → **15 PASS**: non-PE rejection, SHA-256 consistency,
real PE metadata+signature, provenance manifest, public manifest strip path; grading import
(invalid/bool/out-of-range scores, duplicate reviewer, duplicate (sample,label), bad
blind_label, partial-vs-complete, inter-rater κ, no-autofill); pilot balanced + no leak;
runner aggregate (FP count, latency, **không** precision/recall/f1).

**Phân mức (không gộp):**
- Unit: **PASS** (15).
- Real-PE detector: **PASS** (35/35 qua pipeline thật).
- Live Qwen: **PASS** (35/35 LOCAL_QWEN).
- Human grading: **PENDING** (công cụ sẵn sàng; chưa có reviewer thật).
- Malicious raw-PE: **BLOCKED_NO_APPROVED_SAMPLES**.

**Regression:** 05A 25 · 05C repair 18 · `tests/` 255 (2 skip-live) → tất cả PASS. Model
digest/threshold/kết quả 05A–05C **không đổi** (05D additive).

## Đối chiếu CRITERIA (mục 9)

| # | Tiêu chí | Trạng thái |
|---|----------|-----------|
| 1 | Real PE benign validation có kết quả thật | ✅ 35/35 |
| 2 | Detector/Agent qua pipeline chính | ✅ không bypass D1–D9 |
| 3 | Sample manifest/provenance | ✅ public + evaluator |
| 4 | Errors + latency | ✅ A.2/A.3 |
| 5 | Offline human grading workflow hoạt động | ✅ UI + import + pilot (test) |
| 6 | Validation/aggregation đúng | ✅ strict + inter-rater |
| 7 | Không safety regression | ✅ 0 vi phạm; D4/D8 nguyên |
| 8 | Không đổi kết quả 05A–05C | ✅ additive |
| 9 | Human grading thật hoàn thành | ⏳ **PENDING** |

⇒ Engineering đạt; còn tiêu chí 9 (người chấm) ⇒ **PARTIAL**.

## Hướng dẫn owner mở UI & chấm pilot

1. Mở `evaluation/task05d/ui/grading.html` bằng trình duyệt (double-click, offline).
2. Nhập **Reviewer ID**, nạp `evaluation/task05d/results/pilot_package/annotation_forms_blind_v2.json`.
3. Chấm A2/B1/B2/C1/D1 (0/1/2) cho từng phiếu X/Y, ghi chú; tiến độ tự lưu; bấm **Xuất JSON**.
4. Lặp với ≥2 người chấm (Reviewer ID khác nhau) để tính inter-rater.
5. Tổng hợp: `python -m evaluation.task05d.grading_import --annotations <các file xuất> --forms
   evaluation/task05d/results/pilot_package/annotation_forms_blind_v2.json --out
   evaluation/task05d/results/grading_aggregate.json`.
6. Chỉ mở `branch_mapping_EVALUATOR_ONLY.json` **sau** khi chấm xong (bước evaluator).

## Artifacts (`evaluation/task05d/`)

`results/sample_manifest.json` (public) · `results/validation_results.json` + `.csv` ·
`results/samples/*.json` (35) · `results/pilot_package/` · `ui/grading.html` · code +
`tests/test_05d.py`. Không commit: raw PE, model binary, dataset, evaluator-only manifest, `_home`.
