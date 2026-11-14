# TASK 05A — Phát hiện mã độc PE tĩnh độc lập (EMBER2018 v2 → LightGBM)

Gói này **tự tái lập độc lập** pipeline: EMBER2018 feature version 2 (2381 chiều)
→ huấn luyện LightGBM từ đầu → inference read-only trên PE thật. Mọi kết quả thực
nghiệm trong `REPORT.md` được sinh ra từ chính lượt chạy của TASK 05A.

> **Ranh giới tin cậy (TRUST BOUNDARY).** Gói này **không** dùng lại checkpoint,
> benchmark, hay implementation huấn luyện của thành viên khác. Nguồn tham chiếu
> duy nhất là *đặc tả feature chính thức* của elastic/ember (feature_version=2) và
> *dataset chính thức*, cả hai đều được xác minh bằng checksum khi nạp vào.
> File `ember_model_2018.txt` của upstream chỉ dùng làm **oracle kiểm tra parity**
> (xem `parity_check.py`), **không** phải model deliverable.

## 0. Yêu cầu môi trường

- Python 3.12 (đã kiểm trên 3.12.10, Windows 11).
- Cài dependency *trong môi trường nghiên cứu riêng* (đừng nhét vào runtime D1–D9):

```powershell
python -m pip install -r research/independent_static_ml/requirements.txt
```

Phiên bản đã dùng: numpy 2.5.4, scikit-learn 1.5.2, lightgbm 4.5.0, lief 0.15.1.

- Ổ đĩa: cần ~2 GB cho archive, ~10 GB cho JSONL giải nén, ~6 GB cho cache vector.
  Lưu tất cả **ngoài Git** (ví dụ `D:\datasets\...`). Không commit dataset/model lớn.

## 1. Tải & xác minh dataset (có provenance)

Nguồn chính thức: `https://ember.elastic.co/ember_dataset_2018_2.tar.bz2`
SHA-256 chính thức (từ README elastic/ember):
`b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812`

```powershell
# Tải (1,696,539,273 bytes). KHÔNG dùng -C -/resume (gây hỏng file).
curl -L -o D:\datasets\ember2018-v2\ember_dataset_2018_2.tar.bz2 `
     https://ember.elastic.co/ember_dataset_2018_2.tar.bz2

# Giải nén an toàn (chỉ các member mong đợi) — xem audit_dataset.py để tham khảo.
python -c "import tarfile,os;from pathlib import Path;r=Path(r'D:\datasets\ember2018-v2');[open(r/os.path.basename(m.name),'wb').write(t.extractfile(m).read()) for t in [tarfile.open(r/'ember_dataset_2018_2.tar.bz2','r:bz2')] for m in t.getmembers() if m.isfile()]"
```

## 2. Audit dataset (checksum + nhãn + trùng lặp + leakage)

```powershell
python -m research.independent_static_ml.audit_dataset `
  --data D:\datasets\ember2018-v2 `
  --archive D:\datasets\ember2018-v2\ember_dataset_2018_2.tar.bz2 `
  --out research\independent_static_ml\artifacts\dataset_audit.json
```

Kiểm: archive SHA-256; đếm nhãn 0/1/−1 theo split; số sha256 trùng; overlap
train↔test; histogram năm `appeared` (để làm chronological split).

## 3. Kiểm tra feature parity (độc lập, không phải kết quả deliverable)

```powershell
python -m research.independent_static_ml.parity_check `
  --data D:\datasets\ember2018-v2 `
  --official-model D:\datasets\ember2018-v2\ember_model_2018.txt `
  --n 20000 `
  --out research\independent_static_ml\artifacts\parity_check.json
```

Vector của extractor độc lập + model chính thức → AUC ≈ 0.997 ⇒ chứng minh
feature parity (sai thứ tự/giá trị feature sẽ làm AUC rơi về ~0.5).

## 4. Huấn luyện LightGBM từ đầu

```powershell
python -m research.independent_static_ml.train_lightgbm `
  --data D:\datasets\ember2018-v2 `
  --cache D:\datasets\ember2018-cache `
  --out research\independent_static_ml\artifacts `
  --rounds 600 --early-stopping 60 --seed 42
```

- Chỉ giữ nhãn 0/1 (bỏ −1). Chia **chronological** theo `appeared`: giữ lại các
  tháng mới nhất làm validation. Chọn threshold trên validation (FPR ~1%).
- Lưu `model_lightgbm.txt` + `model_manifest.json` (có model SHA-256, config,
  seed, split counts, threshold, env).

## 5. Đánh giá trên tập test có nhãn (KHÔNG dùng để tuning)

```powershell
python -m research.independent_static_ml.evaluate `
  --data D:\datasets\ember2018-v2 `
  --cache D:\datasets\ember2018-cache `
  --model research\independent_static_ml\artifacts\model_lightgbm.txt `
  --manifest research\independent_static_ml\artifacts\model_manifest.json `
  --out research\independent_static_ml\artifacts\evaluation_results.json
```

Dùng threshold **đóng băng** từ manifest. Xuất confusion matrix, precision,
recall/TPR, F1, FPR, ROC AUC, average precision, latency, FP/FN examples.

## 6. Inference read-only trên 1 file PE

```powershell
python -m research.independent_static_ml.predict_cli `
  --file C:\Windows\System32\notepad.exe `
  --model research\independent_static_ml\artifacts\model_lightgbm.txt `
  --manifest research\independent_static_ml\artifacts\model_manifest.json
```

PE bytes → extractor tin cậy → vector 2381 → LightGBM → raw score → nhãn.
Output JSON có: SHA-256 file, feature version, model id + SHA-256, threshold,
raw score, predicted label, parser status, limitations/error.
**Không thực thi file.** Không tự tải/chạy malware. Mẫu malicious (nếu cần kiểm
raw-PE inference) phải do nhóm cấp qua môi trường được phê duyệt; không chạy trên
máy dev.

## 7. Chạy test

```powershell
python -m unittest discover -s research/independent_static_ml/tests -p "test_*.py" -v
```

25 test: feature contract (chiều/thứ tự/finite/determinism), input hỏng/cụt/rỗng,
PE malformed, thiếu feature group, record không nhãn/không hợp lệ, chống leakage
(split disjoint), sai model digest, mismatch model/feature-version, determinism
dự đoán, lỗi nạp model, dataset not found.

## Cấu trúc

| File | Vai trò |
|------|---------|
| `ember_v2.py` | Vectorizer EMBER v2 độc lập (record → 2381) |
| `pe_extractor.py` | PE bytes → raw features → vector (LIEF, read-only) |
| `dataset.py` | Ingest JSONL, nhãn, audit, vectorize (đa tiến trình, cache) |
| `audit_dataset.py` | CLI audit + verify checksum |
| `parity_check.py` | Kiểm feature parity vs model chính thức |
| `train_lightgbm.py` | CLI huấn luyện từ đầu + threshold + manifest |
| `evaluate.py` | CLI đánh giá trên test có nhãn |
| `predict_cli.py` | CLI inference read-only 1 file |
| `metrics.py` / `manifests.py` | Metrics & manifest môi trường/provenance |
| `tests/` | Unit/integration tests |
| `schema_proposal_static_prediction_v1.md` | Đề xuất schema bổ sung (chưa duyệt) |
| `REPORT.md` | Báo cáo kết quả thực nghiệm (PASS/PARTIAL/BLOCKED) |

Xem `REPORT.md` để biết kết quả thực nghiệm và những gì đã/chưa xác nhận.
