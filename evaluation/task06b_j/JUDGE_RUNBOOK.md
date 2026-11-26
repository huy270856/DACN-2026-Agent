# TASK 06B-J — Runbook chấm Claude-as-Judge (`INTERACTIVE_LLM_JUDGE_BLIND_BATCH`)

Phương thức này **không** phải automated API inference. Owner tự mở một phiên Claude Code
**mới, độc lập**. Phiên đó chỉ đọc kit đã export và ghi từng file JSON response. Kết quả là
LLM-as-Judge **provisional**: `human_verified=false`, không phải ground truth, không thay thế
human grading (vẫn PENDING).

## 0. Kit đã export sẵn (DEV calibration, package `06BJ-DEV-CAL-v1`)

| Track | Kit (ngoài repo) | Số item | View | Blinding |
|---|---|---|---|---|
| A | `C:\src\06bj_judge_kits\06BJ-DEV-CAL-v1-trackA` | 19 | `common` | Ẩn nhãn arm. Không blind hoàn toàn với treatment (báo cáo của C trích evidence của analyzer; template static nhận ra được) |
| B | `C:\src\06bj_judge_kits\06BJ-DEV-CAL-v1-trackB` | 16 | `investigation` | **Không** blind với hành vi tool (có trace) |

Hash prompt và package nằm trong `kit_manifest.json` của từng kit. Bản sao (không có item) ở
`results/dev/judge_kit_exports_v1/track{A,B}/`.

Lưu ý riêng cho DEV: item DEV lấy từ trace lịch sử **chưa stage**, nên vẫn chứa đường dẫn
`System32\<tên>.exe` mà Agent đã thấy. Đây là residual leakage đã biết của bộ calibration.
Bộ confirmatory sẽ được stage tên trung tính.

## 1. Mỗi lần chấm (một track = một phiên mới)

1. Đóng mọi phiên đang mở. Mở terminal mới **tại thư mục kit**, không phải repo:
   ```powershell
   cd C:\src\06bj_judge_kits\06BJ-DEV-CAL-v1-trackA
   claude
   ```
2. Không cung cấp mapping, kỳ vọng, điểm cũ hay bất kỳ file nào của repo. **Từ chối** mọi
   yêu cầu đọc hoặc ghi file nằm ngoài thư mục kit. Nếu phiên tự đọc ra ngoài thì ghi chú lại
   và coi lượt chấm đó là không hợp lệ.
3. Gửi đúng một tin nhắn:
   > Đọc `JUDGE_PROMPT.md` và `RUBRIC.md` trong thư mục này, rồi chấm toàn bộ `items/` đúng
   > theo hướng dẫn, ghi `responses/<item_id>.json` cho từng item và `responses/_session_note.json`.
4. Ghi lại model thật từ `/model` hoặc `/status` (ví dụ `claude-opus-5-5`) và session ID nếu
   có. Không biết thì để `UNKNOWN`. Không đoán.
5. Không sửa file response. Nếu phiên dừng giữa chừng thì cứ import (sẽ bị
   `INCOMPLETE_REJECTED`). Muốn chạy lại thì export một kit **mới** và giữ nguyên kit cũ.

## 2. Import và validate (trong repo)

```powershell
cd C:\src\DACN-2026-Agent
python -m evaluation.task06b_j.judge_kit import `
  --kit C:\src\06bj_judge_kits\06BJ-DEV-CAL-v1-trackA `
  --package evaluation\task06b_j\results\dev\calibration_package_v1 `
  --out evaluation\task06b_j\results\dev\judge_cal_v1\trackA_pass1 `
  --pass-id trackA-pass1 --judge-model <model hoặc UNKNOWN> --session-id <id hoặc UNKNOWN>
```

Output:

- `raw/` chứa bản sao nguyên vẹn mọi response, kèm SHA-256 trong `import_record.json`.
- `import_record.json` ghi `COMPLETE_VALID` hoặc `INCOMPLETE_REJECTED` và liệt kê từng lỗi.
- `judgments.json` **chỉ** được tạo khi import hợp lệ. Không có điểm mặc định, không tự điền.

Làm tương tự cho Track B (`--package` giống, `--kit ...trackB`, `--pass-id trackB-pass1`).

## 3. Lock rồi mới unblind

```powershell
python -m evaluation.task06b_j.analysis lock `
  --judgments evaluation\task06b_j\results\dev\judge_cal_v1\trackA_pass1\judgments.json `
              evaluation\task06b_j\results\dev\judge_cal_v1\trackB_pass1\judgments.json `
  --package evaluation\task06b_j\results\dev\calibration_package_v1 `
  --lock evaluation\task06b_j\results\dev\judge_cal_v1\LOCK.json

python -m evaluation.task06b_j.analysis analyze `
  --lock evaluation\task06b_j\results\dev\judge_cal_v1\LOCK.json `
  --package evaluation\task06b_j\results\dev\calibration_package_v1 `
  --out evaluation\task06b_j\results\dev\judge_cal_v1\analysis.json
```

Chỉ **sau** bước lock mới được mở `EVALUATOR_ONLY/calibration_key.json` để so độ nhạy của
Judge với 4 probe tự dựng và các kỳ vọng của developer. Kỳ vọng đó không phải ground truth.

## 4. Kiểm tra self-consistency (tùy chọn)

Export thêm một kit mới cho cùng track (ví dụ `...-trackA-pass2`). Thứ tự item được tái tạo
khi export; để có thứ tự khác, cần dựng package với seed khác, tức là một package mới. Chấm
trong một phiên **mới**, import với `--pass-id trackA-pass2`, rồi đưa cả hai vào `lock`.
`analysis` ghi kết quả này là `SELF_CONSISTENCY_NOT_CORRECTNESS`: Judge đồng ý với chính nó
không chứng minh điều gì về tính đúng.

## 5. Calibration dùng để làm gì

- Kiểm xem rubric và Judge có phân biệt được: probe bịa API, claim runtime, absence trên
  coverage một phần, score bị coi như xác suất, template boilerplate, và evidence đã commit
  nhưng không được đọc (tracert).
- Nếu rubric có vấn đề thì chỉ sửa trên DEV, tạo `task06b-j-rubric-v2`, rồi dựng lại package
  và kit **trước** khi freeze confirmatory.
- **Không** dùng điểm calibration để kết luận Agent tốt hơn hay kém hơn static-only.
