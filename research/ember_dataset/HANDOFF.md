# Bàn giao dataset EMBER và matrix cho LightGBM

Ngày kiểm chứng: 30/10/2026, Asia/Saigon. Hoàn thành chuẩn bị dataset; **chưa train LightGBM**. Chọn EMBER2018 feature v2, tương thích extractor 2.381 features. Không sửa D1–D9, không tải/thực thi PE nguyên bản, không đưa dataset/matrix vào Git.

## Đối chiếu yêu cầu trưởng nhóm

| Yêu cầu | Kết quả | Bằng chứng |
|---|---|---|
| Nguồn, link tải, dung lượng, license, nhãn và train/test | Đã đối chiếu cả 2018 và 2024. Dataset 2018 MIT, code AGPL-v3; dataset card và code 2024 Apache-2.0. | [Nguồn](SOURCES.md), [HEAD/API 2024](results/local_windows/ember2024_download_checks.json) |
| Tương thích extractor | Chọn 2018 v2 2.381 cột; 2024 v3 full PE 2.568 cột không thay trực tiếp. | SOURCES.md và [môi trường](results/local_windows/environment.json) |
| Tải, verify, đọc bằng Python | Archive và bảy JSONL 2018 đã verify; đọc hết một triệu dòng. | [Audit](results/local_windows/audit.json), verify.log |
| Thống kê và feature version | Số đo bên dưới; xác minh release bằng checksum, không suy từ field có mặt. | [Manifest](results/local_windows/dataset_manifest.json) |
| Script tạo và load matrix/nhãn | Matrix hoàn chỉnh, loader chỉ đọc chạy được, independent check đạt. | [Matrix check](results/local_windows/matrix_check.json), [lệnh đã chạy](results/local_windows/COMMANDS.md) |

## Số liệu đo trên máy

| Tập | JSONL | Nhãn 0 | Nhãn 1 | Nhãn -1 | Matrix |
|---|---:|---:|---:|---:|---|
| Train | 800.000 | 300.000 | 300.000 | 200.000 | 600.000 × 2.381 |
| Test | 200.000 | 100.000 | 100.000 | 0 | 200.000 × 2.381 |

0 = benign; 1 = malicious; -1 = chưa có nhãn. Loại -1 khỏi matrix, giữ nguyên JSONL. Nhãn thiếu/null/sai: 0; nhóm feature bắt buộc thiếu/null: 0; SHA-256 sai định dạng: 0; hash trùng trong/giữa hai tập: 0. Chưa kiểm tra near-duplicates.

X float32, y int8 chỉ chứa 0/1. Kiểm tra toàn bộ giá trị X hữu hạn, 800.000 hàng metadata/nhãn khớp JSONL nguồn; tính lại 34 vector tại các vị trí xác định và khớp chính xác. Preflight trước matrix đã thử 140 dòng trên cả bảy shard. Không suy rộng 34 phép tính lại thành kiểm chứng lại công thức cho mọi hàng.

Record không khai báo feature_version. Standalone audit giữ verified_feature_version=null có chủ ý; verify/manifest xác nhận release v2 bằng checksum chính thức. Giữ nguyên official split; metadata của train có nhãn trải từ 2006-12 đến 2018-10, test gồm 100.000 mỗi tháng 2018-11 và 2018-12. Xem chronology.json.

## Dung lượng và checksum

- Archive: **1.696.539.273 byte**.
- Bảy JSONL: **9.946.142.816 byte**.
- Matrix X/y, metadata và COMPLETE.json: **7.712.003.111 byte**.
- Tổng: **19.354.685.200 byte**, không gồm môi trường/installer/log. Đây là độ dài file, không phải số cluster NTFS.
- Archive SHA-256: `b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812`, khớp Python, Get-FileHash và upstream.
- Hash từng JSONL/artifact matrix nằm trong manifest. D còn **120.403.431.424 byte** trống khi chốt số đo.
- EMBER2024: 13 ZIP tổng **24.332.624.240 byte** theo HEAD/API, đều HTTP 200; chưa tải corpus, chưa có checksum hoặc số mẫu đo cục bộ. Publisher counts được ghi riêng trong SOURCES.md.

## Đường dẫn và cách dùng

- Dataset: `D:\datasets\ember2018-v2`
- Audit: `D:\datasets\ember2018-audit.json`
- Matrix: `D:\datasets\ember2018-matrix`
- Manifest: `D:\datasets\ember2018-manifest.json`
- Matrix check: `D:\datasets\ember2018-matrix-check.json`
- Preflight: `D:\datasets\ember2018-preflight.json`
- Python nghiên cứu: `D:\datasets\envs\ember-v2\Scripts\python.exe`
- Worktree: `C:\Users\Admin\Documents\Codex\2026-10-23\h-y-ki-m-th-context\work\ember-dataset-validation`

Từ root worktree:

```powershell
& D:\datasets\envs\ember-v2\Scripts\python.exe research/ember_dataset/load_dataset.py --matrix D:\datasets\ember2018-matrix
& D:\datasets\envs\ember-v2\Scripts\python.exe research/ember_dataset/check_matrix.py --data D:\datasets\ember2018-v2 --matrix D:\datasets\ember2018-matrix --output D:\datasets\ember2018-matrix-check.json --check-vectors
```

prepare.py đọc JSONL, download/verify/audit và tạo X/y/metadata; load_dataset.py dùng NumPy memory mapping chỉ đọc, không train. Toàn bộ lệnh cài/tải/test trong COMMANDS.md. Không chạy lại extraction/matrix vào thư mục đã có output.

## Môi trường và giới hạn

Python 3.7.9 riêng; NumPy 1.21.6; SciPy 1.7.3; scikit-learn 1.0.2; LIEF 0.10.1-bfe5414; pandas 1.3.5; LightGBM 3.3.5 chỉ là dependency import. Extractor official commit `d97a0b523de02f3fe5ea6089d080abacab6ee931`; source Python cài đặt khớp checkout. Chi tiết trong pip-freeze.txt và environment.json. Orchestrator Python 3.15 không thay đổi.

**17 unit test đạt, pip check đạt, preflight/matrix/independent check đạt. Không còn blocker cho phạm vi chuẩn bị dataset.** Python/LIEF legacy được cô lập; cảnh báo LIEF khác 0.9.0 giữ nguyên trong log, upstream ghi nhận 0.10.1 tương thích Windows/Linux. Chỉ vector hóa JSON, chưa kiểm chứng parser trên PE.

Lượt tải đêm trước dừng ở 857.735.168 byte; đã thêm Range resume có test, bắt buộc checksum toàn file trước giải nén. Proxy 403 là blocker lịch sử của cloud, không chặn lượt local. Validation split, near-duplicate analysis, training/calibration/evaluation là giai đoạn sau. Không merge main và chưa push.
