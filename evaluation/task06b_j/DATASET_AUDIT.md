# TASK 06B-J — Dataset audit

Phạm vi: tìm mẫu raw PE hợp lệ cho một holdout confirmatory 3 arm. Không tải hay tạo mẫu
độc hại. Không dùng EMBER feature record như raw PE. Không dùng EICAR.

## 1. Mẫu đã dùng trước đây (không độc lập)

| Tập | Mẫu | Vai trò cũ | Kết luận |
|---|---|---|---|
| 06B-R/R2 DEV | tracert, findstr, fc | phát triển v3.1–v3.4 + DEBUG v3.4 | **DEV**, không phải holdout |
| 06B DEV v1/v2 | schtasks, curl, wevtutil, reg | DEV 06B | DEV |
| 06B reserve | netstat (`23ca543c…`), route (`ac348f50…`) | ghi là "reserve, NOT_EVALUATED" | Chưa từng chạy (đã kiểm tra mọi artifact), **nhưng** xem §2 |
| 05D | 35 PE System32 (ping, where, whoami, net, attrib, xcopy, …) | RAW_PE_E2E benign | Đã dùng |
| 05C/06A | EMBER feature records | FEATURE_RECORD_REPLAY | Không phải raw PE |

## 2. Phát hiện: Windows Update đã làm trôi SHA

Băm lại các file trên máy (ngày 2026-11-26):

- schtasks, curl, wevtutil, netstat và route **có SHA khác** với SHA trong manifest 06B.
- Hai SHA reserve (netstat, route) **không còn lấy lại được** từ System32.
- Các SHA mới của schtasks, curl, wevtutil, netstat, route là "SHA-disjoint", nhưng thực chất
  là **build mới của cùng chương trình** đã dùng làm DEV. Vì vậy chúng không độc lập ở mức
  chương trình và phải bị loại khỏi holdout.

Quy tắc mới (G2): holdout phải **SHA-disjoint và program-disjoint** (khác tên tiện ích và
khác họ chức năng) với mọi artifact 05C/05D/06A/06B.

## 3. Pool ứng viên trên máy hiện tại (chưa chọn, chưa chạy)

Kiểm tra 40 tiện ích System32 với 1218 chuỗi SHA-256 trong các file được track
(`evaluation/`, `research/`, `docs/`, `benchmarks/`, `examples/`):

- 11 file overlap SHA: where, whoami, tasklist, reg, tracert, findstr, fc, ping, net, attrib,
  xcopy.
- 29 file SHA-disjoint. Sau khi loại program-overlap (schtasks, curl, wevtutil, netstat,
  route, certutil, hostname) còn khoảng 22 ứng viên, ví dụ: compact, more, sort, auditpol,
  bcdedit, bitsadmin, makecab, chcp, dsregcmd, esentutl, expand, ipconfig, nslookup, arp,
  pathping, sc, robocopy, icacls, takeown, systeminfo, driverquery, cmdkey.
- Tiêu chí inclusion/exclusion được đề xuất (cần owner duyệt **trước** inference):
  - PE32+ x64 EXE
  - chữ ký Microsoft `Valid` (kiểm lại bằng `Get-AuthenticodeSignature` lúc freeze)
  - ≤ 8 MiB
  - SHA và program disjoint
  - chọn ngẫu nhiên tất định (seed ghi trước) từ danh sách đã khóa, **không** dựa trên output
    của model

Chưa kiểm tra chữ ký và chưa chạy LightGBM hay Agent trên các ứng viên này. Danh sách trên chỉ
là inventory, chưa phải manifest holdout.

## 4. Giới hạn của cohort

- **Toàn bộ là benign, ký bởi Microsoft, từ System32.** Nhãn dựa trên provenance, không chứng
  minh vô hại tuyệt đối. Thiếu các strata: malicious, packed/obfuscated, unsigned benign của
  bên thứ ba, DLL, PE32 x86, file gần threshold, và detector sai (FP/FN).
- Cohort này đo được chất lượng điều tra **trên benign System32**. Nó **không** cho biết hiệu
  năng điều tra malware nói chung, và không đo được khả năng Agent bắt lỗi detector (không có
  FP/FN raw PE).
- Malicious raw-PE vẫn **BLOCKED**: chưa có mẫu được cấp phép và môi trường được duyệt.
- Tiện ích System32 rất phổ biến, nên Qwen có thể "biết" chúng từ dữ liệu huấn luyện. Neutral
  staging (PROTOCOL §4) giảm cue từ đường dẫn, nhưng không loại được việc nhận diện qua import
  đặc trưng.

## 5. Kết luận

- Có thể dựng một **candidate holdout benign-only** khoảng 20 mẫu program-disjoint từ máy
  hiện tại, sau khi owner duyệt tiêu chí và kiểm tra chữ ký.
- Không có holdout độc lập nào được chạy trong TASK 06B-J. Hai SHA reserve cũ không còn khả
  dụng.

---

## 6. Holdout audit v1 (continuation): kết quả thật

Nguồn: `holdout_audit.py`. Output evaluator-only:

- `results/holdout/candidate_audit_v1_EVALUATOR_ONLY.json`
- `results/holdout/candidate_cases_v1_EVALUATOR_ONLY.json`

Không chạy detector hay Agent trên các file này. Audit gồm:

- Authenticode: PowerShell `Get-AuthenticodeSignature`, chỉ đọc.
- Version resources: OriginalFilename, InternalName, FileDescription, ProductName,
  CompanyName.
- Kiến trúc, size, số import khai báo.
- Overlap SHA với 1218 chuỗi SHA trong các artifact được track.
- Overlap tên chương trình với 36 chương trình đã đánh giá hoặc reserve (05D, 06B DEV,
  reserve), so cả theo tên file lẫn OriginalFilename.
- Near-duplicate: Jaccard tập import ≥ 0.85, so với 25 chương trình cũ còn trên đĩa và với
  các candidate trước đó.

| Kết quả | Chi tiết |
|---|---|
| Đủ điều kiện | **20/22**. Tất cả là PE32+ x64 EXE, chữ ký Microsoft `Valid` (Catalog) |
| Loại `ipconfig.exe` | Đã đánh giá ở 05D. Build hiện tại có SHA khác (Windows Update) nhưng import set trùng 100% (Jaccard 1.0). Audit lần trước chỉ dựa trên SHA nên đã xếp nhầm vào nhóm "disjoint" |
| Loại `pathping.exe` | Near-duplicate của `tracert.exe` (DEV): Jaccard 0.941 |
| Jaccard cao nhất trong số còn lại | `chcp.com`/`find.exe` 0.628; `driverquery`/`tasklist` 0.60. Dưới ngưỡng nhưng có liên quan chức năng, ghi nhận là limitation |

Manifest candidate (`CANDIDATE_PENDING_OWNER_APPROVAL`):

- 20 alias `sample_0001…0020` (thứ tự seeded, alias không tiết lộ tên).
- Seed `task06b-j-holdout-v1`.
- Mỗi loại câu hỏi 4 case.

Strata answerability của câu hỏi đã gán:

| Stratum | n |
|---|---:|
| NOT_ANSWERABLE_STATICALLY (Q_RUNTIME_LIMIT) | 4 |
| ANSWERABLE_FROM_INITIAL_EVIDENCE (Q_NO_TOOL) | 4 |
| NO_RELEVANT_DECLARED_IMPORTS | 5 |
| RELEVANT_ONLY_AFTER_RETRIEVAL | 2 |
| RELEVANT_ONLY_BEYOND_COMMIT_CAP | 5 |

**Phát hiện thiết kế:** analyzer chỉ commit 64 entry đầu theo thứ tự file. Trong 20 candidate,
có 14 file mà API process liên quan chỉ nằm **sau** entry thứ 64. Với những case này, kể cả
một Agent hoàn hảo cũng không thấy được bằng chứng đó qua tool hiện tại. Điều đúng ở đây là
nêu giới hạn coverage. Đây là giới hạn của analyzer (không thay đổi trong task này), cần báo
cáo kèm kết quả.

n=20, mỗi loại câu hỏi 4 case, toàn benign. Cỡ mẫu này chỉ đủ cho **mô tả** và so sánh theo
cặp có CI rộng. Không đủ cho tuyên bố ý nghĩa thống kê hay tổng quát hóa sang malware.
