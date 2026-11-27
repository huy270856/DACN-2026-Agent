# Huy — Bàn giao TASK09B cho Chí

Branch: `feat/task09b-execution-prevention`.
Base tạm: `16eb2e6a22eac66f7862d3f55aead98fb251a520` (cần Chí review/chốt).

Chí ơi, Huy đã hoàn thành prototype 09B và demo chặn thật trong VM Windows.
Backend Huy chọn là NTFS deny ExecuteFile cho đúng file benign và SID thử nghiệm.
Đã kiểm chứng file chạy trước, bị Windows từ chối CreateProcess error 5 sau apply,
rollback xong chạy lại; file đối chứng vẫn chạy, DACL cuối khớp baseline.

- 42/42 kiểm thử host đạt; 20/20 kiểm tra live VM đạt.
- Có snapshot và đã thử restore trước khi áp quyền chặn.
- Không dùng malware, không đổi policy laptop, không sửa core/model hoặc tự nối Agent.
- AppLocker và WDAC có trong bảng so sánh; không phải backend đã triển khai.
- Giới hạn NTFS: nhắm đúng file object/SID, không chặn mọi bản copy hoặc process đã chạy.

Nhờ Chí review source, phạm vi NTFS, base và contract trước khi tích hợp/merge.
Tài liệu chính: REPORT.md, DESIGN.md, LIVE_BACKEND.md, INTERFACE.md,
COMPARISON.md, ROLLBACK_GUIDE.md. Evidence native ở evidence/ntfs_live_result.json;
không đưa ISO, VM disk hay binary fixture lên Git.

Commit/push nhánh được Huy yêu cầu ngày 28/11/2026; không tự merge main.
