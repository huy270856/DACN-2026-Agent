# TASK 05A — Báo cáo thực nghiệm: Phát hiện mã độc PE tĩnh độc lập

**Kết luận: PASS** (có một số giới hạn phạm vi được nêu rõ ở mục 9).

Mọi số liệu dưới đây sinh ra từ chính lượt thực thi TASK 05A trên máy dev
(Windows 11, Python 3.12.10), ngày 2026-11-14. Không kế thừa model/benchmark của
thành viên khác.

---

## 1. Trạng thái repo ban đầu (ghi nhận trước khi thay đổi)

- Branch khi bắt đầu: `main`; working tree **sạch**.
- `git rev-parse HEAD` = `16b9fc175443c6df4b012e9ccff5f0b8e8b26312`.
- Local `main` **đi sau** `origin/main` 1 commit (chỉ ghi nhận; **không** pull/
  merge/reset/push).
- Có prior work chưa kiểm chứng (KHÔNG dùng làm bằng chứng của task này):
  remote `feat/ember-dataset-preparation`, `feat/tuan-re-benchmark`; thư mục
  `research/ember_dataset/` (script của Huy, báo BLOCKED do proxy chặn tải).
- Hành động: tạo branch mới `feat/task05a-independent-static-ml` từ HEAD sạch.
  Không chỉnh sửa D1–D9. Không cherry-pick/merge branch EMBER cũ.

## 2. Dataset — provenance đã xác minh độc lập

| Mục | Giá trị |
|-----|---------|
| Nguồn | `https://ember.elastic.co/ember_dataset_2018_2.tar.bz2` (chính thức) |
| Kích thước | 1,696,539,273 bytes |
| SHA-256 (chính thức, từ README elastic/ember) | `b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812` |
| SHA-256 (tự tính tại máy) | `b6052eb8…2997812` → **MATCH** |

Lưu ý quy trình: lần `curl -C -` (resume) làm **hỏng** file (nối thêm → 2.0 GB).
Đã xoá và tải lại một lần sạch → đúng 1,696,539,273 bytes, checksum khớp. Giải
nén an toàn chỉ các member mong đợi.

### Audit (streaming toàn bộ JSONL — `dataset_audit.json`)

| | Train (6 shard) | Test |
|---|---|---|
| Tổng record | 800,000 | 200,000 |
| label 0 (benign) | 300,000 | 100,000 |
| label 1 (malicious) | 300,000 | 100,000 |
| label −1 (unlabeled) | 200,000 | 0 |
| label không hợp lệ | 0 | 0 |
| thiếu sha256 | 0 | 0 |
| sha256 trùng | **0** | **0** |
| thiếu feature group | 0 | 0 |

- **Overlap sha256 train↔test = 0** ⇒ không rò rỉ giữa train và test.
- Phân bố thời gian (`appeared`): train trải 2006–2018 (750k thuộc 2018); test
  **toàn bộ 2018** — đúng thiết kế temporal hold-out của EMBER.
- Nhãn −1 **không bao giờ** được coi là benign; bị loại khỏi tập giám sát.

## 3. Feature pipeline độc lập (EMBER v2, 2381 chiều)

- `ember_v2.py` tái lập độc lập đặc tả 9 nhóm feature chính thức, đúng thứ tự:
  histogram(256) · byteentropy(256) · strings(104) · general(10) · header(62) ·
  section(255) · imports(1280) · exports(128) · datadirectories(30) = **2381**.
- Bước record→vector chỉ phụ thuộc numpy + sklearn `FeatureHasher` (murmurhash3
  tất định), **không** đụng LIEF ⇒ tất định và tái lập.
- Phân biệt rõ 2 đường:
  - **Training**: từ EMBER feature records (JSONL) — `dataset.py`.
  - **Inference**: từ bytes PE thật qua LIEF 0.15 — `pe_extractor.py` (read-only).
- Không bao giờ phát zero-vector khi extraction fail: `process_raw_record` raise
  `FeatureExtractionError`; test `records_extraction_failed=0` trên toàn bộ 800k+
  200k record thật.

### Bằng chứng feature parity (kiểm được bằng test — `parity_check.json`)

Vector sinh bởi extractor **độc lập** + model **chính thức** `ember_model_2018.txt`:

| Số mẫu test | AUC |
|---|---|
| 20,000 | **0.997312** |

AUC ~0.997 (so với ~0.999 công bố của EMBER trên full test) là bằng chứng tương
thích **ở cấp mô hình** cho đường JSONL→vector; sai thứ tự/giá trị feature sẽ làm
AUC rơi về ~0.5. **Model chính thức chỉ là oracle kiểm parity, không phải model
deliverable.**

> **Hiệu chỉnh (TASK 05C-R):** AUC-level **không** đủ để khẳng định "bit-for-bit".
> Đã bổ sung đối chiếu **trực tiếp** vector độc lập vs `ember/features.py` upstream
> (commit `d97a0b5`, **không sửa**) trên 120 record audit:
> **bit-exact 2126/2381 chiều (8/9 nhóm), 120/120 record, 0 sai khác.** Nhóm
> `section` (255 chiều) **không chạy được** dưới upstream trên scikit-learn 1.5.x
> (API `FeatureHasher.transform([<str>])`), nên đối chiếu trực tiếp nhóm này là
> `ENV_BLOCKED_UNDER_UPSTREAM`; impl độc lập dùng shim `list(entry)` tái lập đúng
> hành vi cũ, kiểm bằng unit test. Chi tiết: `evaluation/task05c/repair/results/parity_direct.json`.
> Vì vậy **không** còn khẳng định "bit-for-bit toàn bộ 2381 chiều"; chỉ nêu kết
> quả đã đo ở trên.

## 4. Huấn luyện LightGBM từ đầu (`model_manifest.json`)

- Model mới, **không** nạp weight cũ. `train_lightgbm.py`, seed=42, deterministic.
- Dữ liệu: 600,000 record train có nhãn (300k/300k) vectorize từ đầu (cache riêng).
- **Chronological split** theo `appeared`: giữ 15% tháng mới nhất (2018-09..10) làm
  validation. `n_train=510,000`, `n_val=90,000`, **train/val sha256 overlap = 0**.
- Threshold chọn **chỉ trên validation** tại FPR mục tiêu: 1% → `0.83219`
  (primary), 0.1% → `0.98945`. **Không** chạm test khi chọn threshold.
- Artifact: `model_lightgbm.txt` (12 MB, để ngoài Git), `model_id =
  dacn-lgbm-ember2018v2-5db192ec1bda`, **SHA-256 =
  `5db192ec1bda850d0e1873af705b57d05aad414aa35e8520c8315ece1c509609`**.
- best_iteration = 209 (early stopping 60). num_leaves 512, lr 0.05.
- **Score thô LightGBM, CHƯA calibrate** — manifest ghi rõ
  `score_is_calibrated_probability: false`.

Chống leakage: (a) audit overlap train↔test = 0; (b) assert runtime train/val
sha256 disjoint; (c) nhãn không lấy từ filename/path (lấy từ field `label` của
record chính thức). Unit test `test_leakage.py` + `test_dataset.py` kiểm các điểm này.

## 5. Đánh giá trên tập test có nhãn (threshold đóng băng — `evaluation_results.json`)

Tập test chính thức: **200,000** mẫu (100,000 benign + 100,000 malicious),
**không** dùng để tuning/threshold. Threshold = 0.83219 (lấy từ manifest).

| Chỉ số | Giá trị |
|---|---|
| ROC AUC | **0.992967** |
| Average Precision | 0.993696 |
| Precision | 0.989240 |
| Recall / TPR | 0.917100 |
| F1 | 0.951800 |
| False Positive Rate | **0.009980** (≈1%, khớp mục tiêu val-FPR 1%) |
| Confusion matrix | TN 99,002 · FP 998 · FN 8,290 · TP 91,710 |

Latency inference (16 threads): batch 200k = 1.173s → **0.0059 ms/mẫu**;
single-row predict = **0.219 ms/mẫu** (chi tiết trong `evaluation_results.json`).
Phân tích lỗi: FP=998, FN=8,290; danh sách sha256 ví dụ FP/FN lưu trong file.

Nhận xét trung thực: AUC test 0.993 thấp hơn mức ~0.9991 của model EMBER đầy đủ vì
model này nhỏ hơn và chỉ 209 vòng (early-stopped), ưu tiên chạy lại được và tính
tất định; đây **không** phải cố gắng vượt SOTA. Việc FPR test (0.998%) khớp mục
tiêu 1% chọn trên validation cho thấy threshold tổng quát hóa tốt.

## 6. Raw PE inference read-only

`predict_cli.py`: PE bytes → extractor tin cậy → vector 2381 → LightGBM → raw
score → nhãn. Đã chạy trên PE benign nguồn gốc rõ ràng
(`C:\Windows\System32\notepad.exe`):

```
target_sha256   : 468ffe129c395abf6b21a09efdf261910a95fb98aa982ead73caa7b2b684577e
feature_version : 2        parser_status : OK
model_id        : dacn-lgbm-ember2018v2-5db192ec1bda
model_sha256    : 5db192ec1bda…c509609  (matches manifest = true)
threshold       : 0.83219  raw_score : 0.005086  → predicted_label: benign ✓
```

Output chứa đủ: SHA-256 file, feature version, model id + SHA-256, threshold, raw
score, predicted label, parser/extractor status, limitations. **Không thực thi
file.** Chưa test trên mẫu malicious raw-PE: cần nhóm cấp mẫu qua môi trường được
phê duyệt (mục 9).

## 7. Kiểm thử (unit + integration)

`python -m unittest discover` → **25/25 PASS** (~1.2s). Bao gồm: feature
dims/order/finite/determinism; input rỗng/cụt/garbage; PE malformed; thiếu feature
group; record không nhãn/không hợp lệ (−1 bị loại, không coi là benign); chống
leakage (split disjoint + phát hiện overlap); sai model digest → từ chối chấm;
mismatch model/feature-version → từ chối; determinism dự đoán cùng artifact; lỗi
nạp model; dataset not found; vector PE benign thật 2381 finite.

Phân biệt rõ: **unit/integration tests** (synthetic fixtures, mục đích kiểm cơ
chế/lỗi) **≠ statistical evaluation** (mục 5, trên dữ liệu thật có nhãn). Mock/
synthetic **không** được coi là real inference.

## 8. Phạm vi tích hợp & schema

- **Không** sửa D1–D9. **Không** đổi contract D0 `ember-output-v1`.
- Đề xuất schema **bổ sung** `static-prediction-v1` cho bước prediction
  (`schema_proposal_static_prediction_v1.md`) — *chưa được owner duyệt*, tương
  thích kiến trúc, để TASK 05B đưa vào Node C kèm provenance. Không nới D4/D8 để
  test PASS.

## 9. Những gì ĐÃ xác nhận vs CHƯA xác nhận

**Đã xác nhận (bằng chứng trong `artifacts/`):**
- Provenance dataset + checksum khớp.
- Feature EMBER v2 2381 chiều, parity với không gian feature chính thức (AUC 0.997).
- Model LightGBM mới train độc lập, có SHA-256, manifest tái lập.
- Đánh giá trên 200k test có nhãn, không dùng để tuning; metrics đầy đủ.
- Inference read-only chạy được trên PE benign thật.
- 25 test xử lý lỗi + chống leakage PASS.

**Chưa xác nhận / giới hạn phạm vi:**
- Chưa chạy raw-PE inference trên mẫu **malicious** (cần mẫu do nhóm cấp qua môi
  trường được phê duyệt; không tự tải/chạy malware trên máy dev). Hiện mới chứng
  minh khả năng phát hiện malicious trên **feature records** (tập test), chưa trên
  **bytes PE độc hại thô**.
- Inference dùng LIEF 0.15.1 trong khi training records dùng LIEF 0.9.0 → có thể
  lệch nhẹ feature; **không** khẳng định parity cho đường bytes→vector (chỉ khẳng
  định cho đường record→vector). Đã ghi `limitations` trong output.
- Score **chưa calibrate** (không phải xác suất thật).
- Chưa nối Agent/Node C (đúng phạm vi 05A; để 05B).

## 10. Đối chiếu tiêu chí chấp nhận (mục 13 đề bài)

| # | Tiêu chí | Trạng thái |
|---|----------|-----------|
| 1 | Dataset thật, provenance xác minh | ✅ |
| 2 | Feature EMBER v2 2381 chiều | ✅ (parity AUC 0.997) |
| 3 | Model LightGBM mới, train độc lập | ✅ |
| 4 | Artifact model có checksum | ✅ (SHA-256 5db192ec…) |
| 5 | Đánh giá test có nhãn, không dùng tuning | ✅ (200k, AUC 0.993) |
| 6 | Raw PE inference read-only chạy được | ✅ (benign; malicious: giới hạn mục 9) |
| 7 | Test xử lý lỗi + chống leakage | ✅ (25/25) |
| 8 | Báo cáo tái lập | ✅ (README + manifest + script) |

## 11. Artifacts (trong `research/independent_static_ml/artifacts/`)

- `dataset_audit.json` — audit dataset + checksum.
- `parity_check.json` — kiểm parity feature (AUC 0.997).
- `model_manifest.json` — config/seed/split/threshold/env + model SHA-256.
- `evaluation_results.json` — metrics trên 200k test.
- `model_lightgbm.txt` — model (12 MB, **ngoài Git**; tái tạo bằng train script).
