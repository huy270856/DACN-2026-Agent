# Kết quả chạy thực tế — 2026-10-29

- Compiler: Zig cc 0.13.0; target x86_64-windows-gnu; flags/argv/hash đầy đủ trong manifest.json.
- Build: 3/3 thành công. branch.exe 152576 byte; hello.exe 152064 byte; readfile.exe 152576 byte.
- Phân tích tĩnh: pefile 2024.8.26, 3/3 PASS bộ điểm đối chiếu trong expected.json.
- Cả 3 đúng PE32+ AMD64 và đúng SHA-256 đã ghi sau build.
- Tìm thấy 4/4 chuỗi marker/filename dự kiến, 7/7 imports dự kiến (tính riêng theo mẫu),
  3/3 hàm export dự kiến. Đây là kiểm tra tập con biết trước, không phải recall toàn bộ binary.
- Không chạy binary. Không chạy Ghidra/REA, không đánh giá decompiler hay Orchestrator.
- Lần build đầu lỗi quyền rename file tạm trong sandbox. Chạy lại ngoài sandbox thành công.
- Blocker bước tùy chọn: chưa có Ghidra/Java được tìm thấy trong môi trường đã kiểm tra.
- Nguồn ngoài zlib: đã xác minh tag/commit và đọc source/license; chưa tải/build bộ zlib.

Hai file JSON tại đây là snapshot của lần chạy bàn giao. Chạy lại script tạo kết quả mới
trong build/, không tự ghi đè snapshot. Hash binary/source có thể kiểm lại bằng Get-FileHash.
Chi tiết lệnh chạy, nguồn dữ liệu và giới hạn xem ../README.md.
