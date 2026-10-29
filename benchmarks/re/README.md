# Tuấn — bộ mẫu kiểm thử Reverse Engineering

Thư mục nghiên cứu độc lập; không thay đổi D1–D9, JSON Schema hay contract D.0.
Đây là mẫu nhỏ có source biết trước, không phải dataset phân loại malware.

## Mẫu và nguồn

| Mẫu | Hành vi viết trong source | Điểm đối chiếu |
|---|---|---|
| hello | In chuỗi cố định | emit_message, WriteFile, GetStdHandle, TUAN_RE_HELLO_v1 |
| branch | Hàm phân loại số âm/0/dương; đầu vào mẫu là 7 | classify_value, TUAN_RE_BRANCH_v1 |
| readfile | Chỉ đọc tối đa 64 byte từ fixture.txt, đóng handle | read_fixture, CreateFileA, ReadFile, CloseHandle, fixture.txt |

Source tự viết tại `src/`, license MIT trong `LICENSE`. Không network, không tạo process,
không sửa registry. Script build/phân tích không chạy các EXE. Binary có CRT của toolchain;
vì vậy có thể xuất hiện nhiều imports/functions hơn các hàm trực tiếp viết trong source.
Các marker dự kiến được khai báo trước trong `expected.json`, không sinh từ kết quả phân tích.

Nguồn ngoài để mở rộng (chưa tải/build trong lần bàn giao này):

- [zlib 1.3.1](https://github.com/madler/zlib/tree/51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf):
  commit `51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf`, tag `v1.3.1` đã đối chiếu bằng git ls-remote.
- [License gốc](https://github.com/madler/zlib/blob/51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf/LICENSE):
  cho phép sử dụng, sửa và phân phối với điều kiện giữ notice, không nhận tác giả gốc,
  đánh dấu source sửa đổi. Phải giữ license khi lấy source này.
- [test/example.c](https://github.com/madler/zlib/blob/51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf/test/example.c):
  ví dụ nén/giải nén và đọc/ghi gzip. Có source để tạo thêm mẫu có nhiều hàm, chuỗi,
  và thư viện. Đây là ứng viên tạo benchmark RE, không phải benchmark đã có đáp án
  functions/imports/strings chuẩn sẵn. Chạy mẫu này sẽ ghi file thử nghiệm; chỉ dùng thư mục test riêng.
- [Ghidra chính thức](https://github.com/NationalSecurityAgency/ghidra): công cụ phân tích cần đánh giá.
- [Zig](https://ziglang.org/learn/overview/): dùng zig cc để biên dịch C cho Windows.
  Bản dùng ở đây là 0.13.0, đóng gói qua PyPI ziglang; manifest lưu hash compiler thực tế.

## Cách chạy trên máy Tuấn

Từ thư mục gốc repository, PowerShell:

```powershell
# Chỉ cần khi máy chưa có các công cụ này. Không đổi requirements của nhóm.
.\.venv\Scripts\python.exe -m pip install --target '..\re-tools' ziglang==0.13.0 pefile==2024.8.26
.\.venv\Scripts\python.exe -X utf8 benchmarks/re/build.py --zig '../re-tools/ziglang/zig.exe'
$env:PYTHONPATH = (Resolve-Path '..\re-tools').Path
.\.venv\Scripts\python.exe -X utf8 benchmarks/re/analyze_pe.py
```

Binary và kết quả nằm ở `benchmarks/re/build/`: 3 EXE, `manifest.json`, `pe-evidence.json`.
`build/` bị gitignore: không commit compiler/cache/binary. Bản bàn giao ZIP được tạo ngoài repo.
Manifest lưu source hash, binary SHA-256, kích thước, version/hash compiler và toàn bộ argv.
Flags: `-target x86_64-windows-gnu -O0 -g -fno-inline -lkernel32`.
Đường dẫn và debug metadata có thể làm hash khác giữa máy; không hứa build byte-identical.

## Cách đánh giá và giới hạn

1. Kiểm tra source/binary hash đúng manifest trước khi đọc PE.
2. Kiểm tra PE32+ AMD64; trích imports và địa chỉ IAT; exports và RVA.
3. Quét ASCII có offset; so với các chuỗi/import/export dự kiến trong `expected.json`.
4. Kết quả PASS chỉ nghĩa là tìm thấy các điểm đối chiếu đó. Export giúp định vị hàm
   tự viết; **không chứng minh Ghidra đã phục hồi tất cả functions**.

Sau khi có Ghidra: import từng EXE, chạy auto-analysis bằng headless, xuất danh sách
functions (entry address), imports, strings (address) ra JSON kèm SHA-256 và version Ghidra.
Đối chiếu địa chỉ hàm với exports của baseline; với strings phải chuyển RVA/VA sang
file offset trước khi so sánh. Không chỉ so tổng số functions vì CRT và cách phân tích
có thể tạo thêm hàm. Sau đó thử build tối ưu hóa để xem hàm bị inline/chuỗi bị loại.

Giai đoạn hiện tại chưa chạy Ghidra headless/REA. Không tìm thấy Java trong PATH hay
Ghidra ở các thư mục cài đặt/tải về đã kiểm tra. Đây là blocker cho bước tùy chọn số 4;
JSON Python hiện tại không phải D.0 ToolResult và chưa được đưa vào Orchestrator.

Rủi ro: ba mẫu quá đơn giản và có export/debug nên dễ hơn binary thực tế; ASCII scan
có false positive; không có oracle cho toàn bộ hàm runtime. Không dùng kết quả này để
kết luận độ chính xác RE trên malware hoặc binary bị pack/obfuscate.
