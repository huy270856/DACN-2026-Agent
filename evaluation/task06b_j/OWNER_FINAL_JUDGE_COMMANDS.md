# OWNER — Lệnh chấm Judge cuối cho confirmatory (rubric `task06b-j-rubric-v2`)

File này nằm **ngoài** mọi Judge kit. **Không** paste file này vào phiên Judge. Bạn chỉ paste
**đúng một câu** ở bước 3.

Cần **4 phiên Claude mới, riêng biệt**, mỗi phiên chấm đúng một kit (2 pass × 2 track, theo
PROTOCOL §6):

| # | Kit (đường dẫn đầy đủ) | Số item = số file `J-*.json` cần có | Package dùng khi import |
|---|---|---:|---|
| 1 | `C:\src\06bj_judge_kits\06BJ-CONF-P1-trackA` | 60 | `evaluation\task06b_j\results\confirmatory\package_conf_p1` |
| 2 | `C:\src\06bj_judge_kits\06BJ-CONF-P1-trackB` | 40 | `evaluation\task06b_j\results\confirmatory\package_conf_p1` |
| 3 | `C:\src\06bj_judge_kits\06BJ-CONF-P2-trackA` | 60 | `evaluation\task06b_j\results\confirmatory\package_conf_p2` |
| 4 | `C:\src\06bj_judge_kits\06BJ-CONF-P2-trackB` | 40 | `evaluation\task06b_j\results\confirmatory\package_conf_p2` |

Mỗi kit cần thêm `responses\_session_note.json`.

## Các bước cho MỖI kit (ví dụ kit 1)

1. Mở PowerShell **mới**:
   ```powershell
   cd C:\src\06bj_judge_kits\06BJ-CONF-P1-trackA
   ```
2. Mở phiên mới:
   ```powershell
   claude
   ```
3. Paste **đúng một câu này**:
   ```text
   Read JUDGE_PROMPT.md and RUBRIC.md in this folder, then grade every file in items/ exactly as instructed, writing one responses/<item_id>.json per item and finally responses/_session_note.json.
   ```
4. Từ chối mọi yêu cầu đọc hoặc ghi file **ngoài** thư mục kit.
5. Khi xong, gõ `/status` (hoặc `/model`) trong phiên và chép **nguyên văn** model ID; chép
   session ID nếu có. Không có thì dùng `UNKNOWN`.
6. Kiểm tra số file:
   ```powershell
   (Get-ChildItem .\responses\J-*.json).Count   # track A: 60, track B: 40
   Test-Path .\responses\_session_note.json      # True
   ```
7. Thoát phiên rồi import (chạy trong repo):
   ```powershell
   cd C:\src\DACN-2026-Agent
   python -m evaluation.task06b_j.judge_kit import --kit C:\src\06bj_judge_kits\06BJ-CONF-P1-trackA --package evaluation\task06b_j\results\confirmatory\package_conf_p1 --out evaluation\task06b_j\results\confirmatory\judge\P1_trackA --pass-id conf-P1-trackA --judge-model <MODEL hoặc UNKNOWN> --session-id <SESSION hoặc UNKNOWN>
   python -m evaluation.task06b_j.judge_kit import --kit C:\src\06bj_judge_kits\06BJ-CONF-P1-trackB --package evaluation\task06b_j\results\confirmatory\package_conf_p1 --out evaluation\task06b_j\results\confirmatory\judge\P1_trackB --pass-id conf-P1-trackB --judge-model <MODEL hoặc UNKNOWN> --session-id <SESSION hoặc UNKNOWN>
   python -m evaluation.task06b_j.judge_kit import --kit C:\src\06bj_judge_kits\06BJ-CONF-P2-trackA --package evaluation\task06b_j\results\confirmatory\package_conf_p2 --out evaluation\task06b_j\results\confirmatory\judge\P2_trackA --pass-id conf-P2-trackA --judge-model <MODEL hoặc UNKNOWN> --session-id <SESSION hoặc UNKNOWN>
   python -m evaluation.task06b_j.judge_kit import --kit C:\src\06bj_judge_kits\06BJ-CONF-P2-trackB --package evaluation\task06b_j\results\confirmatory\package_conf_p2 --out evaluation\task06b_j\results\confirmatory\judge\P2_trackB --pass-id conf-P2-trackB --judge-model <MODEL hoặc UNKNOWN> --session-id <SESSION hoặc UNKNOWN>
   ```
   Mỗi lệnh phải in ra `"status": "COMPLETE_VALID"`. Nếu ra `INCOMPLETE_REJECTED`: **không sửa
   file response**; giữ nguyên output và báo lại.

## Điều kiện contamination: dừng, không import phiên đó

- Bạn đã paste bất cứ thứ gì ngoài câu ở bước 3 (file này, runbook, report, điểm số…).
- Phiên đã đọc hoặc liệt kê file ngoài thư mục kit, hoặc nhắc tới mapping, kỳ vọng,
  calibration, developer hay "confirmatory".
- Phiên được mở trong repo thay vì thư mục kit.
- Phiên tạo script để **sinh** điểm thay vì tự đọc từng item.

  Calibration v2 đã có một ghi nhận về helper script ở P1-A. Nếu phiên đề xuất dùng script,
  chỉ chấp nhận script **chỉ để kiểm tra định dạng hoặc ghi file**, và ghi rõ trong session
  note.

Khi có contamination: ghi sự việc vào `evaluation\task06b_j\EVALUATION_LOG.md`, rồi yêu cầu
export một kit **mới** (không tái dùng kit cũ).

## Sau khi cả 4 kit đều `COMPLETE_VALID`: lock, analyze, báo cáo

Chạy theo đúng thứ tự. Lock **trước**, vì lock là bước trước khi mở mapping.

```powershell
cd C:\src\DACN-2026-Agent
$J = "evaluation\task06b_j\results\confirmatory\judge"
$P1 = "evaluation\task06b_j\results\confirmatory\package_conf_p1"
$P2 = "evaluation\task06b_j\results\confirmatory\package_conf_p2"

python -m evaluation.task06b_j.analysis lock --judgments $J\P1_trackA\judgments.json $J\P1_trackB\judgments.json $J\P2_trackA\judgments.json $J\P2_trackB\judgments.json --package $P1 $P2 --lock $J\LOCK.json

python -m evaluation.task06b_j.analysis analyze --lock $J\LOCK.json --package $P1 $P2 --out $J\analysis.json

python -m evaluation.task06b_j.final_report --lock $J\LOCK.json --package $P1 $P2 --deterministic evaluation\task06b_j\results\confirmatory\confirmatory_summary_v1.json --out evaluation\task06b_j\results\confirmatory\final_report_v1
```

Kết quả nằm ở `results\confirmatory\final_report_v1\FINAL_RESULTS.md` và
`final_results.json`. Kết luận nghiên cứu TASK 06 được viết dựa trên file này, dùng primary
outcomes (verdict mức claim, R2, R3, R4, R6, R7 cùng metrics tất định); R1, R5, R8, R9 và
`evidence_access` chỉ là exploratory.
