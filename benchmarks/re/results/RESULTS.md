# Kết quả chạy thực tế — 2026-10-29

- Compiler: Zig cc 0.13.0; target x86_64-windows-gnu; flags/argv/hash đầy đủ trong manifest.json.
- Build: 3/3 thành công. branch.exe 152576 byte; hello.exe 152064 byte; readfile.exe 152576 byte.
- Phân tích tĩnh: pefile 2024.8.26, 3/3 PASS bộ điểm đối chiếu trong expected.json.
- Cả 3 đúng PE32+ AMD64 và đúng SHA-256 đã ghi sau build.
- Tìm thấy 4/4 chuỗi marker/filename dự kiến, 7/7 imports dự kiến (tính riêng theo mẫu),
  3/3 hàm export dự kiến. Đây là kiểm tra tập con biết trước, không phải recall toàn bộ binary.
- Không chạy binary. Kết quả Python ở trên không đánh giá decompiler hay Orchestrator.
- Lần build đầu lỗi quyền rename file tạm trong sandbox. Chạy lại ngoài sandbox thành công.
- Blocker Ghidra/Java ban đầu đã xử lý trong bước bổ sung bên dưới.
- Nguồn ngoài zlib: đã xác minh tag/commit và đọc source/license; chưa tải/build bộ zlib.

Hai file JSON tại đây là snapshot của lần chạy bàn giao. Chạy lại script tạo kết quả mới
trong build/, không tự ghi đè snapshot. Hash binary/source có thể kiểm lại bằng Get-FileHash.
Chi tiết lệnh chạy, nguồn dữ liệu và giới hạn xem ../README.md.

## Bổ sung mục 4 — bàn giao 2026-10-30

- Đã chạy Ghidra 12.2 headless với Temurin JDK 25.0.5+8 trên hello.exe.
- SHA-256: `48eda1c7f194a05b5889ca1bc512ed218d937e423a49c8c06537425a0f680871`.
- Auto-analysis thành công, không timeout; log báo tổng thời gian analyzer khoảng 18 giây
  (không gồm thời gian khởi động/import/biên dịch script).
- JSON thực tế: 525 functions, 49 external symbols, 80 defined strings.
- Checker PASS: emit_message đúng địa chỉ export PE; WriteFile, GetStdHandle và
  TUAN_RE_HELLO_v1 đều được tìm thấy. Chỉ đánh giá các điểm biết trước, không phải toàn bộ hàm.
- Kiểm tra âm: checker từ chối cả 5 trường hợp sửa evidence: sai SHA-256, timeout,
  thiếu functions, thiếu external symbols, thiếu strings. Các bản sửa chỉ là test checker,
  không thay thế evidence thật đã bàn giao.
- File: ghidra-hello.json, ghidra-hello.log, ghidra-check.json, tool-downloads.json.
- Log gốc giữ nguyên timestamp máy chạy; ngày tiêu đề là ngày bàn giao theo phiên làm việc.
- Đã khắc phục launcher với đường dẫn không dấu và cache/settings riêng. API timeout thực tế
  của Ghidra 12.2 là analysisTimeoutOccurred(); có đoạn README upstream còn ghi tên API cũ.
- Ghidra không tìm thấy PDB/DWARF và có cảnh báo analyzer trong log; không tuyên bố phân tích
  hoàn hảo. Việc tìm hàm mẫu đối chiếu theo địa chỉ export PE, không dựa vào PDB.
- Chỉ chạy mẫu hello bằng Ghidra; hai mẫu còn lại mới có baseline Python.
- Chưa chạy REA, chưa tích hợp D.0, chưa đánh giá độ chính xác decompiler. Không còn blocker
  cho yêu cầu số 4 là chạy ít nhất một mẫu và xuất JSON evidence.
