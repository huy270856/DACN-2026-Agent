# Huy — EMBER v2 / LightGBM research baseline

Ngày chạy: 10/11/2026 (Asia/Saigon). Code và báo cáo nhỏ ở nhánh local `feat/ember-dataset-local-validation`; model và dữ liệu lớn chỉ ở ổ D. Chưa push, chưa sửa D1–D9.

## Cách train và ranh giới test

- Nguồn: EMBER2018 feature v2 đã verify; matrix `D:\datasets\ember2018-matrix` (float32, 2.381 cột). Archive SHA-256 `b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812`.
- Chỉ dùng nhãn 0/1. Từ 600.000 dòng train có nhãn, **513.586 dòng trước 2018-10** để fit và **86.414 dòng tháng 2018-10** để chọn số vòng/ngưỡng. Mọi dòng có `appeared` hợp lệ. Không dùng 200.000 dòng -1 để fit.
- LightGBM GBDT, `learning_rate=0.05`, `num_leaves=64`, `feature_fraction=0.8`, `max_bin=255`, seed 2026; tối đa 300 vòng. Best iteration theo AUC validation: **296** (chưa đạt điều kiện early stopping trong giới hạn 300 vòng). Không grid search trên tập test.
- Ngưỡng **0,8521730479** chọn bằng benign validation để FPR validation không quá 1%. Model lưu là chính model được validation; không train lại trên tháng 10 rồi dùng ngưỡng cũ.
- Sau khi model/ngưỡng đã cố định, đánh giá đúng một lần trên official test 200.000 dòng (2018-11 và 2018-12). Nhãn cân bằng 100.000/100.000. Không dùng test để chọn tham số.

| Chỉ số | Validation 2018-10 | Official test 2018-11/12 |
|---|---:|---:|
| ROC AUC | 0,976687 | 0,988729 |
| Partial ROC AUC, FPR ≤ 1% (sklearn standardized) | 0,857672 | 0,879526 |
| Average precision | 0,988483 | 0,989926 |
| FPR tại ngưỡng đã chốt | 299/29.955 = 0,9982% | 864/100.000 = 0,864% |
| TPR tại ngưỡng đã chốt | 46.809/56.459 = 82,908% | 85.996/100.000 = 85,996% |

Nguồn số đo máy: [REPORT.json](results/training_2026_11_10/REPORT.json), [log train](results/training_2026_11_10/train_stdout.txt). Sau training, SHA-256 và số byte của cả bảy file matrix/metadata/COMPLETE vẫn khớp [independent matrix check](results/local_windows/matrix_check.json). `model.txt` dài **2.253.584 byte**, SHA-256 `b5f5fd69e06c59d44407c1a87c3af4403f2b274ee308127852c99f18e29abf4f`, khớp `Get-FileHash` và manifest của lượt train. Model ở `D:\datasets\ember2018-model-runs\2026-11-10-v2\model.txt`, không nằm trong Git. Lượt `2026-11-10-v1` đã ngắt trước khi train xong do phát hiện ngưỡng validation không nên áp cho model refit; chỉ `v2` là lượt hoàn chỉnh.

## Inference trên PE thật, chỉ đọc

`infer_pe.py` mở file như dữ liệu, yêu cầu LIEF parse được PE, trích xuất vector v2, kiểm 2.381 giá trị hữu hạn, kiểm model hash và số cột rồi trả score/nhãn theo ngưỡng trên. Không thực thi file đích, không ghi CaseState và không tự nhận là verdict malware.

| File Windows đã xác minh | SHA-256 | Score | Nhãn model |
|---|---|---:|---:|
| `C:\Windows\System32\notepad.exe` | `da5807bb0997cc6b5132950ec87eda2b33b1ac4533cf1f7a22a6f3b576ed7c5b` | 0,0071204 | 0 |
| `C:\Windows\System32\kernel32.dll` | `4636f65d449b1353100578c6cb139933cf2b134f5e246119d18968873a058bed` | 0,0003003 | 0 |

Hai hash khớp `Get-FileHash`; Authenticode status `Valid`, signer `Microsoft Windows`. [Notepad inference](results/training_2026_11_10/notepad-inference.json), [kernel32 inference](results/training_2026_11_10/kernel32-inference.json). Đây là smoke test parser→vector→model trên hai file lành tính, chưa phải đánh giá accuracy ngoài phân phối EMBER.

## Lệnh chạy lại

Từ root worktree, trong PowerShell; chọn một **output directory mới** vì script từ chối ghi đè:

```powershell
$py = 'D:\datasets\envs\ember-v2\Scripts\python.exe'
& $py -m unittest discover -s research/ember_dataset -p 'test_*.py' -v
& $py research/ember_dataset/train_lightgbm.py --matrix D:\datasets\ember2018-matrix --output D:\datasets\ember2018-model-runs\NEW-RUN --max-rounds 300 --max-fpr 0.01 --threads 8
& $py research/ember_dataset/infer_pe.py --model-dir D:\datasets\ember2018-model-runs\2026-11-10-v2 --file C:\Windows\System32\notepad.exe
```

20 unit test của `research/ember_dataset` pass. Môi trường nghiên cứu: Python 3.7.9, LightGBM 3.3.5, NumPy 1.21.6, official `ember` tại commit `d97a0b523de02f3fe5ea6089d080abacab6ee931`, LIEF 0.10.1. LIEF phát cảnh báo vì dữ liệu gốc dùng 0.9.0; upstream ghi 0.10.1 nhất quán cho v2 trên Windows/Linux, nhưng không khẳng định tương đương tuyệt đối trên mọi PE.

## Giới hạn và việc còn lại

- EMBER2018 là benchmark lịch sử; ROC AUC/FPR trên tập test cân bằng không đo trực tiếp tỷ lệ báo sai trong môi trường thực tế. Score chưa được calibration, và nhãn model không chứng minh file an toàn/độc hại.
- Chưa phân tích near-duplicate giữa nguồn, chưa kiểm thử nhiều PE ngoài dataset hoặc robustness khi parser gặp PE bất thường. Không tải hay chạy malware.
- Inference mới là CLI nghiên cứu. Chưa có schema/contract được nhóm phê duyệt cho dự đoán LightGBM (contract EMBER hiện hành chỉ nói về **feature extraction**). Chưa nối model vào D5/D7/Agent/CaseState; cần chốt output, model version, threshold và provenance trước khi tích hợp.
- Model trong Git không có; nhóm cần nhận file model qua kênh artifact phù hợp sau khi duyệt, kèm SHA-256 và report. Đừng push dataset/matrix/model lớn lên repo.
