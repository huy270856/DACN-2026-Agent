# Context Collector v1

Node B / minimum context trong SOT-TECH: nhận file hoặc PID, đọc thông tin, trả JSON có trạng thái từng phần. Không chạy target, không score malware, không thu entropy/imports/strings, không gọi cloud/LLM, không sửa/xóa file nguồn. Chưa phải CaseState Builder hoặc toàn bộ ToolResult wrapper.

## Windows / VS Code

Cần Python 3.10+ (khuyến nghị 3.12; Node.js/REA không cần cho tool này).

1. Giải nén ZIP, mở đúng thư mục chứa `setup.cmd` bằng VS Code.
2. Terminal → New Terminal:

```powershell
.\setup.cmd
```

3. Thu file:

```powershell
.\.venv\Scripts\python.exe context_collector.py --file "C:\Windows\System32\notepad.exe" --output collections --progress
```

Thu PID (thay 1234 bằng PID thật từ Task Manager):

```powershell
.\.venv\Scripts\python.exe context_collector.py --pid 1234 --output collections --progress
```

Hoặc Ctrl+Shift+B để nhập đường dẫn; Tasks: Run Task → Collect process context để nhập PID. Không cần kích hoạt virtualenv hoặc sửa execution policy PowerShell.

## Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest -v
.venv/bin/python context_collector.py --file /path/to/sample --output collections --progress
```

## Kết quả và lịch sử

Mỗi lượt tạo `collections/COL-<uuid>/context.json` riêng; terminal in đường dẫn đầy đủ. JSON UTF-8 gồm collector/schema version, collection ID, target, timestamps UTC, runtime, facets, limitations và errors. Không ghi đè lần trước. Context là dữ liệu quan sát; SUCCESS chỉ có nghĩa thu thành công, không nghĩa benign. Một file text có thể SUCCESS với is_pe=false.

`facets` chứa `status`, `value` và `reason` nếu thiếu/lỗi. Trạng thái tổng thể FAILED khi không thu được facet nào; DEGRADED nếu chỉ thu được một phần; SUCCESS khi các facet đã thử thành công. Node này dùng SUCCESS/UNAVAILABLE/FAILED/DEGRADED; UNKNOWN/NOT_APPLICABLE dành cho tình huống/tool tương ứng về sau. Các phép chưa thử không được tự ghi như đã chạy. File không có creation time theo OS trả null, created_at_status=UNAVAILABLE bên trong metadata.

File facets: metadata, readable, PE header tối thiểu, SHA-256 và file-change check. PE classification=PE_IMAGE khi không có DLL flag; không dựa vào đuôi để khẳng định EXE. Không xác nhận đầy đủ tính hợp lệ PE hay khả năng chạy Win10/11.

Process facets: PID+start time, name, executable path, parent PID, user, session, running, identity recheck. Nếu có executable path, lưu thêm `backing_file_context` bằng cùng Collector file. Hash file trên disk không đại diện bộ nhớ process, DLL hay các bytes đang thực thi. Access denied/exit giữ dữ liệu đã có và đánh dấu giới hạn. PID không có quyền xác minh start time sẽ không được coi là identity đáng tin.

## File lớn và hủy

Không đặt giới hạn dung lượng hoặc timeout hash. SHA-256 đọc theo khối 1 MiB; header chỉ đọc số byte nhỏ cần thiết. Chạy tuần tự một target mỗi lệnh, không nạp toàn file vào RAM. Đọc toàn nội dung vẫn cần thời gian/I/O tương ứng. File đặc biệt, symlink hoặc reparse point ở target cuối được từ chối; các thành phần cha của đường dẫn không được sandbox hóa.

`--progress` hiển thị bytes đã hash trên stderr. Ctrl+C một lần khi đang hash sẽ lưu context một phần, sha256=null với lý do cancelled; không trả hash của một đoạn. Không bảo đảm lưu được nếu bị force kill, tắt máy hoặc ngắt đúng lúc ghi JSON; I/O đang bị OS block có thể chậm phản hồi Ctrl+C. Lượt ghi hoàn tất dùng temporary file + atomic rename; không có journal đảm bảo mọi crash.

Kiểm tra identity/size/times trước và sau giúp nhận ra thay đổi, nhưng không phải snapshot bất biến. Không hứa phát hiện mọi kiểu thay đổi đồng thời hoặc bảo vệ TOCTOU tuyệt đối. Kết quả không dùng làm quyền quarantine/terminate.

Exit code: 0=SUCCESS hoặc DEGRADED đã lưu; 1=FAILED đã lưu; 2=CLI sai; 3=lưu thất bại; 130=người dùng hủy và đã cố lưu. Code tích hợp phải đọc status trong JSON, không chỉ exit code.

## Kiểm chứng

Kiểm thử bằng unittest; PE fixtures chỉ là header nhân tạo, không thực thi. Bản phát hành được kiểm tra trên Linux, chưa thực thi trên Windows. Windows session adapter và setup.cmd cần xác minh trên máy Windows; gửi terminal output nếu lỗi. Tests không thể chứng minh bao phủ mọi PE hoặc mọi protected process.

Không sao chép file nguồn vào thư mục collections. Kết quả chứa đường dẫn/user local; xem lại trước khi chia sẻ. Khi nối vào hệ thống, CaseState Builder đọc JSON này và tạo evidence IDs theo contract chung.
