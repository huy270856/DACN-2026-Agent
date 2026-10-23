# DACN-2026-Agent

**Đồ án chuyên ngành An ninh mạng:** Nghiên cứu và xây dựng AI Agent phát hiện và ứng phó mã độc trên Windows kết hợp đặc trưng EMBER và mô hình LightGBM.

> **Trạng thái:** Hoàn thành Node B (Context Collector v1.1) và Node C (CaseState Builder / CaseManager v1.1) ở mức kiểm thử chức năng. **Chưa có Agent điều tra, mô hình LightGBM, sandbox hay cơ chế ứng phó mã độc đang hoạt động.**

## 1. Mục tiêu và kiến trúc

Đầu vào MVP là **đường dẫn file** (ưu tiên PE `.exe`/`.dll`) hoặc **PID của process Windows**. Hệ thống dự kiến tổ chức theo vòng lặp điều tra:

```text
File path / PID
       |
       v
[Node B] Context Collector ----------> collections/COL-.../context.json
       |
       v
[Node C] CaseState Builder/Manager --> cases/CASE-.../case_state.json
       |
       v
[Tiếp theo] Trusted Tool Orchestrator + Tool Registry
       |
       v
[Tiếp theo] Local Agent / Decision Loop <----> CaseState
       |                 ^
       v                 |
Analysis tools ---------+  (Static PE, EMBER features + LightGBM,
                           Dynamic sandbox, Process/DLL, ...)
       |
       v
Final Assessment -> Response Policy -> Human Approval -> Verify
```

Agent được thiết kế để **chọn bước điều tra dựa trên evidence, unknowns, rủi ro và chi phí**, thay vì luôn chạy một chuỗi static → dynamic cố định. Không sử dụng API AI bên ngoài trong định hướng đồ án.

### Ranh giới trách nhiệm

| Thành phần | Trách nhiệm | Không làm |
|---|---|---|
| **Node B – Context Collector** | Quan sát file/PID, thu metadata, PE header tối thiểu, SHA-256 tùy chế độ, ghi `context.json` | Không phân loại mã độc, không tạo CaseState, không thực thi target |
| **Node C – CaseState Builder** | Chuyển Context Collection thành evidence, unknowns và `case_state.json` | Không tự phân tích hay quyết định tool |
| **Node C – CaseManager** | Cập nhật evidence, tool history, conflict, assessment và approval audit; kiểm tra quyền theo contract | Không trực tiếp chạy tool hoặc thực thi quarantine/terminate |
| **Trusted Orchestrator (chưa triển khai)** | Xác thực tool/nguồn kết quả, bảo vệ khóa, điều phối tool và approval adapter | Không cho Agent tự xác nhận phê duyệt |
| **Agent / Analysis / Response (chưa triển khai)** | Chọn công cụ, đánh giá evidence và đề xuất phản ứng theo policy | Không tự ý thực hiện hành động nguy hiểm |

`SUCCESS` của Context Collector chỉ nói **thu thập thành công**, không có nghĩa file/process an toàn.

## 2. Môi trường

- Windows 10/11, PowerShell, Python **3.10+** (khuyến nghị Python 3.12).
- Dependencies hiện tại: xem `requirements.txt` (Node B sử dụng `psutil`).
- Không cần Node.js/REA để chạy Node B và Node C.

Tại thư mục gốc repository:

```powershell
.\setup.cmd
```

Hoặc cài thủ công:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Node B – Context Collector v1.1

### Thu thập file

```powershell
.\.venv\Scripts\python.exe context_collector.py --file "C:\Windows\System32\notepad.exe" --hash-timeout 5 --progress
```

### Thu thập process

```powershell
# Chỉ process metadata, không tự hash executable
.\.venv\Scripts\python.exe context_collector.py --pid $PID

# Yêu cầu thu thêm backing executable và SHA-256
.\.venv\Scripts\python.exe context_collector.py --pid $PID --include-backing-file
```

Kết quả: `collections/COL-<uuid>/context.json` (mỗi lần chạy có collection ID riêng). JSON có `target`, `facets` với trạng thái từng phần, `errors`, `limitations` và thông tin thời gian.

**Giới hạn:** SHA-256 đọc theo chunk 1 MiB; `--hash-timeout` là *best effort*, không thể ngắt tức thì I/O bị hệ điều hành chặn. PE header chỉ kiểm tra cấu trúc tối thiểu. Hash của executable trên đĩa không chứng minh nội dung bộ nhớ của process. File có thể thay đổi đồng thời dù có kiểm tra identity/timestamps.

## 4. Node C – CaseState Builder + CaseManager v1.1

### Khởi tạo case từ Context Collection

```powershell
.\.venv\Scripts\python.exe case_manager.py init --context ".\collections\COL-<uuid>\context.json"
```

Lệnh trả `case_id`, `case_state_path`, `revision = 1`. Case mới thành công bắt đầu ở `READY_FOR_INVESTIGATION` (chưa phải `INVESTIGATING`).

### Xem trạng thái case

```powershell
.\.venv\Scripts\python.exe case_manager.py show --case ".\cases\CASE-<uuid>\case_state.json"
```

CaseState gồm các trường chính: `case_id`, `revision`, `lifecycle_status`, `target`, `collection_ids`, `evidence`, `residual_unknowns`, `tool_runs`, `evidence_conflicts`, `action_history`, `assessment`, `response_history`, `authorization_audit`.

### Cơ chế bảo vệ và kiểm toán

- Giữ provenance của từng evidence; phát hiện các observation `SUCCESS` mâu thuẫn, không tự chọn một kết quả làm chân lý.
- Assessment tham chiếu evidence bị conflict sẽ bị đánh dấu stale; cần giải quyết conflict có kiểm soát rồi đánh giá lại.
- Chống trùng `collection_id`/`tool_run_id`; kiểm tra PID + creation time để giảm rủi ro PID reuse.
- Atomic JSON replace và lock khi cập nhật; giới hạn artifact JSON **8 MiB**.
- `tool-result`, `response`, `resolve-conflict` là **protected operations**: public CLI từ chối. API nội bộ yêu cầu HMAC-SHA256 proof, phân vai khóa tool/approval, ràng buộc nội dung và chống replay.

**Ranh giới tin cậy:** HMAC hiện mới được xác minh tại Node C. Đây **không phải** hệ thống xác thực người dùng hay cách ly khóa hoàn chỉnh. Orchestrator/approval service độc lập phải xác thực nguồn tool và người duyệt, quản lý khóa bền vững, áp ACL trên Windows và không để Agent/tool tự cung cấp khóa tin cậy. Node C không thực thi response.

## 5. Kiểm thử

Chạy toàn bộ unit/integration test có trong repository:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Chạy riêng các bài liên quan Node C/security:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_case_state test_case_manager test_security_resilience test_node_c_hardening
```

Chạy kiểm thử Windows nâng cao với file lớn 512 MiB (tùy chọn, tạo file tạm):

```powershell
.\.venv\Scripts\python.exe test_windows_advanced.py --large
```

**Kết quả được người phát triển ghi nhận trên Windows (2026-10-23):** 82 test được liệt kê, **80 `ok`, 2 `skipped`, 0 failure/expected failure**. Hai bài skip: symlink cần quyền Windows và bài hash 512 MiB chỉ chạy khi thêm `--large`. Các test P0 về conflict, stale assessment, unsigned/tampered/replayed ToolResult và unsigned approval đã chuyển thành PASS. Kết quả này không chứng minh toàn bộ bảo mật end-to-end hoặc hiệu quả phát hiện malware.

## 6. Trạng thái triển khai và kế hoạch tiếp theo

| Hạng mục | Trạng thái |
|---|---|
| Node B – File/PID context, optional backing-file, best-effort hash timeout | **Đã triển khai / kiểm thử** |
| Node C – CaseState Builder, CaseManager, evidence conflict, stale assessment, signed ingestion contract | **Đã triển khai / kiểm thử** |
| Trusted Orchestrator + Tool Registry + ToolResult adapter + key/approval boundary | **Tiếp theo** |
| Agent Decision Loop chạy local, đọc CaseState và chọn tool | **Chưa triển khai** |
| Static PE analysis, EMBER feature extraction, LightGBM scoring | **Chưa triển khai** |
| Dynamic sandbox, Process/DLL inspection | **Chưa triển khai** |
| Final Assessment, Response Policy, Human Review, Verify response | **Chưa triển khai end-to-end** |

Các hướng đánh giá dự kiến theo Source of Truth: so sánh **fixed pipeline**, **rule-based workflow** và **agentic workflow**; đo chất lượng classifier bằng Precision, Recall, F1, FPR; đo hiệu quả quyết định tool, thời gian và chi phí điều tra.

## 7. An toàn, dữ liệu và giới hạn

- Chỉ kiểm thử mẫu không tin cậy trong môi trường cô lập phù hợp; không chạy malware trực tiếp trên máy làm việc.
- `collections/` và `cases/` có thể chứa đường dẫn local, tên tài khoản, process metadata và evidence nhạy cảm. **Không commit các thư mục này lên Git.**
- Không commit khóa HMAC, token, `.env`, artifact phân tích hay mẫu mã độc.
- Không xóa `.lock` khi chưa kiểm tra có tiến trình nào đang cập nhật; crash có thể để lại stale lock.
- Chưa có quản lý khóa/ACL/IPC production, chưa có cơ chế khôi phục mọi loại crash, chưa có phản ứng tự động an toàn.

## 8. Tài liệu thiết kế

Kiến trúc và phạm vi dự án được điều phối theo **Source of Truth (SoT)** và **SOT-TECH** của nhóm. README này mô tả **trạng thái code đã triển khai**, không thay thế tài liệu SoT. Khi thay đổi kiến trúc, cần cập nhật SoT trước hoặc cùng với thay đổi code.
