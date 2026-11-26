# OWNER — Lệnh chấm Judge cho calibration v2 (rubric `task06b-j-rubric-v2`)

File này nằm **ngoài** mọi Judge kit. **Không** paste file này vào phiên Judge.
Bạn chỉ paste **đúng một câu** ở bước 3.

Có 4 kit, nên cần **4 phiên mới riêng biệt**. Mỗi phiên chấm đúng một kit:

| Lượt | Kit | Số item |
|---|---|---|
| P1-A | `C:\src\06bj_judge_kits\06BJ-DEV-V2-P1-trackA` | 23 |
| P1-B | `C:\src\06bj_judge_kits\06BJ-DEV-V2-P1-trackB` | 20 |
| P2-A | `C:\src\06bj_judge_kits\06BJ-DEV-V2-P2-trackA` | 23 |
| P2-B | `C:\src\06bj_judge_kits\06BJ-DEV-V2-P2-trackB` | 20 |

P1 và P2 chứa cùng các report nhưng ID ẩn danh và thứ tự khác nhau, dùng để đo
self-consistency. Nên chạy P1-A, P1-B, P2-A, P2-B theo thứ tự này, mỗi phiên mới hoàn toàn.

## Các bước cho MỖI kit (ví dụ P1-A)

1. Mở PowerShell **mới** và chuyển vào thư mục kit, không phải repo:
   ```powershell
   cd C:\src\06bj_judge_kits\06BJ-DEV-V2-P1-trackA
   ```
2. Mở một phiên Claude **mới**:
   ```powershell
   claude
   ```
3. Paste **đúng một câu này**, không thêm gì khác:
   ```text
   Read JUDGE_PROMPT.md and RUBRIC.md in this folder, then grade every file in items/ exactly as instructed, writing one responses/<item_id>.json per item and finally responses/_session_note.json.
   ```
4. Trong lúc phiên chạy: **từ chối** mọi yêu cầu đọc hoặc ghi file ngoài thư mục kit. Không
   trả lời các câu hỏi về mapping, kỳ vọng hay điểm cũ.
5. Khi xong, ghi lại metadata model **đúng như phiên hiển thị**: gõ `/status` (hoặc
   `/model`) trong phiên và chép nguyên văn model ID. Nếu có session ID thì chép luôn. Không
   thấy thì để `UNKNOWN`.
6. Kiểm tra thư mục `responses\` có đủ file:
   ```powershell
   (Get-ChildItem .\responses\J-*.json).Count   # P?-A: 23, P?-B: 20
   Test-Path .\responses\_session_note.json      # True
   ```
7. Thoát phiên. Import (chạy **trong repo**, thay `<MODEL>` và `<SESSION>` bằng giá trị đã
   chép, hoặc `UNKNOWN`):
   ```powershell
   cd C:\src\DACN-2026-Agent
   python -m evaluation.task06b_j.judge_kit import --kit C:\src\06bj_judge_kits\06BJ-DEV-V2-P1-trackA --package evaluation\task06b_j\results\dev\calibration_package_v2_pass1 --out evaluation\task06b_j\results\dev\judge_cal_v2\P1_trackA --pass-id v2-P1-trackA --judge-model <MODEL> --session-id <SESSION>
   ```
   Thay bằng các giá trị tương ứng cho 3 kit còn lại:

   | Kit | `--package` | `--out` | `--pass-id` |
   |---|---|---|---|
   | P1-B | `...\calibration_package_v2_pass1` | `...\judge_cal_v2\P1_trackB` | `v2-P1-trackB` |
   | P2-A | `...\calibration_package_v2_pass2` | `...\judge_cal_v2\P2_trackA` | `v2-P2-trackA` |
   | P2-B | `...\calibration_package_v2_pass2` | `...\judge_cal_v2\P2_trackB` | `v2-P2-trackB` |

   Kết quả mong đợi: `"status": "COMPLETE_VALID"`. Nếu ra `INCOMPLETE_REJECTED`, **không sửa
   file**; gửi output đó cho developer.

## Điều kiện dừng: contamination

Dừng ngay và **không** import phiên đó nếu có bất kỳ dấu hiệu nào sau đây:

- Bạn đã paste nhầm bất cứ thứ gì ngoài câu ở bước 3 (ví dụ file này, runbook, report hay
  điểm số).
- Phiên đã đọc hoặc liệt kê file **ngoài** thư mục kit, hoặc nhắc tới mapping, kỳ vọng,
  "probe", developer hay kết quả trước đó.
- Phiên được mở trong thư mục repo thay vì thư mục kit.

Khi đó: thoát phiên và ghi sự việc vào `evaluation/task06b_j/EVALUATION_LOG.md`. Báo developer
export một kit **mới** (không dùng lại kit cũ), rồi chấm lại trong phiên mới.

## Sau khi cả 4 kit đều COMPLETE_VALID

Developer sẽ chạy `analysis lock` trên 4 file `judgments.json` **trước khi** mở mapping. Sau
đó mới chạy `analysis analyze` (2 package) và tổng hợp calibration v2 theo quy tắc dừng trong
RUBRIC_V2.md §3. Bạn không cần chạy các lệnh này.
