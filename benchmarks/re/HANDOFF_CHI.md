# Chí đọc trước — bàn giao phần Tuấn

**Nhánh chung: `feat/tuan-re-benchmark`. Phạm vi: dataset/benchmark Reverse Engineering.**
Không chỉnh D1–D9, không sửa schema/contract của nhóm. Không merge vào main.

| Yêu cầu | Kết quả | File cần xem |
|---|---|---|
| 1. Nguồn lành tính có source/license | 3 mẫu tự viết, MIT; nguồn ngoài zlib 1.3.1 có license | README.md, LICENSE, src/ |
| 2. Build ít nhất 3 binary + flags/SHA-256 | 3 EXE Windows x64 đã build; manifest ghi compiler, argv, hash source/binary | build.py, results/manifest.json |
| 3. Tìm thêm bộ mẫu RE | Chọn source test/example.c của zlib 1.3.1, pin commit; chưa build zlib | README.md mục nguồn |
| 4. Ghidra headless + JSON | Đã chạy hello.exe; xuất functions/external symbols/strings, checker PASS | ghidra/ExportEvidence.java, results/ghidra-hello.json, results/ghidra-check.json |

## Xem kết quả trong 2 phút

1. Đọc `results/RESULTS.md`: kết quả thực tế và giới hạn.
2. Xem `results/ghidra-check.json`: PASS các điểm đã biết trong hello.exe.
3. Nếu cần bằng chứng đầy đủ, xem `results/ghidra-hello.json` và log cùng tên.

Kiểm tra lại snapshot ngay, chỉ cần Python chuẩn, chưa cần cài Ghidra:

```powershell
python benchmarks/re/check_ghidra.py --evidence benchmarks/re/results/ghidra-hello.json --baseline benchmarks/re/results/pe-evidence.json
```

Build lại và chạy Ghidra thật: lệnh đầy đủ trong `README.md`. Binary nằm local tại
`benchmarks/re/build/`, hoặc trong ZIP `TUAN_RE_BENCHMARK.zip` bàn giao riêng ngoài repo.
Không commit toolchain/cache/binary lớn lên Git. JSON và log đã commit để review trực tiếp.

## Hiểu đúng kết quả

- Python: cả 3 binary PASS marker/import/export dự kiến.
- Ghidra: hello.exe có 525 functions, 49 external symbols, 80 defined strings.
  Có nhiều hàm runtime của compiler; không có nghĩa chương trình tự viết có 525 hàm.
- Hàm emit_message có địa chỉ khớp export PE; hai imports và chuỗi marker đều tìm thấy.
- Đây là dữ liệu phân tích thật từ binary tự build, không phải JSON mock.
- Không chạy EXE, không chạy malware. Chưa dùng REA hay nối Orchestrator, chưa đánh giá
  tính đúng của toàn bộ functions/decompiler. JSON này không phải contract D.0 mới.
- zlib là nguồn bổ sung phù hợp để tạo benchmark, không phải bộ benchmark chuẩn có đáp án sẵn.

## Commit và phạm vi review

- `c705b2c`: source 3 mẫu, build script, baseline Python và nguồn ngoài (mục 1–3).
- Commit bổ sung tiếp theo trên cùng nhánh: Ghidra headless, JSON/log thật, checker và tài liệu này.
- Nhánh kế thừa commit D3/D7 trước đó `e71ef34`. Để xem riêng phần benchmark, dùng:
  `git diff e71ef34..HEAD -- benchmarks/re`.
  Nếu main chưa có D3/D7, khi mở PR cần chọn phạm vi/commit phù hợp, không gộp nhầm review cũ.
- Blocker mục 4 đã xử lý. Chí chạy máy khác cần Ghidra/JDK ở đường dẫn không dấu;
  runtime trong TEMP trên máy Tuấn có thể bị hệ điều hành dọn, khi đó giải nén lại.
