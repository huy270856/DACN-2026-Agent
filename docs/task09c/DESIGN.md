# TASK 09C — Thiết kế Module File & Process Monitoring

**Trạng thái:** Bản thiết kế (Prototype nghiên cứu)  
**Branch:** `feat/task09c-file-process-monitoring`  
**Phân công:** Thành viên 3  

---

## 1. Mục tiêu và Phạm vi

Module `monitoring/` đóng vai trò **nguồn sự kiện tự động** quan sát hoạt động tạo/sửa/đổi tên tệp trong thư mục thử nghiệm (lab) và hoạt động tạo tiến trình (process creation) trong môi trường test, từ đó đề xuất `ScanCandidate` cho **Node B (Context Collector)** qua interface mock.

### Trong phạm vi
- Nghiên cứu và lựa chọn cơ chế Windows tối thiểu, không cài driver, không yêu cầu đặc quyền cao mặc định.
- Giám sát **thư mục thử nghiệm được cấu hình** (không quét toàn ổ đĩa mặc định; luôn loại trừ thư mục cách ly, staging, và thư mục output của chính module).
- Xử lý tạo/ghi/đổi tên tệp, debounce, retry có giới hạn cho tệp đang ghi dở (partial write / file lock), lọc PE header có giới hạn byte, xử lý non-PE, PE malformed, tệp biến mất, thiếu quyền.
- Thu thập sự kiện tạo process kèm `pid` và `start_time_epoch` (chống PID reuse). Path không truy cập được biểu diễn rõ là `UNKNOWN`, không suy đoán; không thu command line, username hay dữ liệu nhạy cảm mặc định.
- Hàng đợi giới hạn (`BoundedQueue`), deduplication, backpressure, đếm sự kiện rơi/gộp (`dropped`/`coalesced`), graceful shutdown.
- Xuất sự kiện qua interface mock `MockNodeBIntake` (không sửa `context_collector.py`, Node C, Controller hay D1–D9).

### Ngoài phạm vi (Không thực hiện)
- Không tự phân tích/chấm điểm malware bằng detector riêng (LightGBM/Qwen).
- Không chặn thực thi (pre-execution prevention), không kill process, không cách ly tệp.
- Process creation telemetry là **post-execution observation** (phát hiện sau khi process đã được OS tạo), **không** phải ngăn chặn trước thực thi.
- Không nhận đường dẫn hoặc lệnh shell tùy ý từ LLM.

---

## 2. Nghiên cứu và Lựa chọn Cơ chế Windows

| Tiêu chí | File: `ReadDirectoryChangesW` (Win32 ctypes) | File: `watchdog` (3rd-party) | File: Polling `os.scandir` |
|---|---|---|---|
| **Quyền yêu cầu** | User thường | User thường | User thường |
| **Dependency** | 0 (stdlib `ctypes` + `kernel32.dll`) | Cần cài `watchdog` | 0 |
| **Độ ổn định & tốc độ** | Event-driven ở mức OS, độ trễ thấp | Bọc `ReadDirectoryChangesW` | Tốn CPU/I/O nếu thư mục lớn |
| **Đo event loss** | Phát hiện được `ERROR_NOTIFY_ENUM_DIR` khi kernel buffer tràn | Có nhưng khó kiểm soát trực tiếp | Không bắt được rename/create giữa 2 chu kỳ |

**Lựa chọn File Watcher:** `ReadDirectoryChangesW` qua `ctypes` (không thêm dependency ngoài, kiểm soát trực tiếp buffer và cờ tràn buffer).

| Tiêu chí | Process: ETW Kernel-Process | Process: WMI `Win32_ProcessStartTrace` | Process: Toolhelp32 Snapshot (`CreateToolhelp32Snapshot`) |
|---|---|---|---|
| **Quyền yêu cầu** | Cần quyền Admin / `Performance Log Users` | Thường cần quyền Admin cho trace | User thường (với process cùng user; process hệ thống trả `ACCESS_DENIED` -> `UNKNOWN`) |
| **Cài driver / độ phức tạp** | Không driver, API C/COM phức tạp | Không driver, phụ thuộc WMI service & `pywin32` COM | Không driver, thuần `ctypes` `kernel32.dll`, rất ổn định |
| **Chống PID reuse** | Có timestamp | Có timestamp | Có `GetProcessTimes` (`creation_time`) |
| **Giới hạn** | Cần đặc quyền cao | Độ trễ COM, có thể bị chặn chính sách | Polling theo chu kỳ (`poll_interval_ms`), có thể bỏ lỡ process sống cực ngắn giữa 2 lần quét |

**Lựa chọn Process Monitor:** `CreateToolhelp32Snapshot` + `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetProcessTimes` + `QueryFullProcessImageNameW` qua `ctypes`. Đáp ứng tốt tiêu chí quyền user thường, không driver, zero dependency, an toàn và trung thực về giới hạn (không tuyên bố zero-loss đối với short-lived process).

---

## 3. Kiến trúc & Luồng Dữ liệu

```text
[Lab Watch Dirs] ---> Win32FileWatcher (ReadDirectoryChangesW) --+
                                                                 |
[OS Processes]   ---> Win32ProcessMonitor (Toolhelp32) ----------+--> Debounce & Bounded Retry
                                                                           |
                                                                           v
                                                                   PE Header Probe (bounded)
                                                                           |
                                                                           v
                                                                 Dedup Cache + Bounded Queue
                                                                           |
                                                                           v
                                                                  MockNodeBIntake (Sink)
```

### Chính sách chống Loop & Bảo vệ phạm vi
- Bắt buộc cấu hình ít nhất 1 thư mục giám sát tường minh; từ chối đường dẫn gốc ổ đĩa (`C:\`, `\`) trừ khi test cấu hình cho phép rõ ràng.
- Mọi đường dẫn thuộc `exclude_dirs` (kho cách ly, staging, thư mục output/log của module) bị bỏ qua ngay tại tầng watcher và trước khi enqueue.

---

## 4. Schema Dự thảo (`ObservationEvent` & `ScanCandidate`)

### `ObservationEvent`
```json
{
  "schema_version": "obs-event-v1",
  "event_id": "EVT-<uuid4>",
  "source": "file_watcher | process_monitor",
  "event_type": "FILE_CREATED | FILE_MODIFIED | FILE_RENAMED | PROCESS_CREATED",
  "timestamp_utc": "2026-11-26T09:15:00+00:00",
  "target_kind": "FILE | PROCESS",
  "target_path": "C:\\lab\\sample.exe | null",
  "pid": 12345,
  "process_start_time_epoch": 1795684500.125,
  "path_status": "KNOWN | UNKNOWN | UNSUPPORTED",
  "reason_code": "NEW_FILE | MODIFIED_FILE | RENAMED_FILE | NEW_PROCESS | ACCESS_DENIED | PROCESS_EXITED",
  "uncertainty": {
    "is_uncertain": false,
    "notes": []
  }
}
```

### `ScanCandidate` (Bàn giao cho Node B)
- `observation_sha256` (nếu có) **chỉ phục vụ deduplication trong `monitoring/`**, **không** thay thế `verified_digest` hay trusted identity do Node B (`context_collector.py`) / Node D xác thực lại.
- Luôn gắn `revalidation_required: true` để khớp triết lý `target-ref-v1` trong `bc_contracts.py`.

```json
{
  "schema_version": "scan-candidate-v1",
  "candidate_id": "CAND-<uuid4>",
  "source_event_id": "EVT-<uuid4>",
  "source": "file_watcher | process_monitor",
  "created_at_utc": "2026-11-26T09:15:00.150000+00:00",
  "target_kind": "FILE | PROCESS",
  "target_ref": {
    "schema_version": "target-ref-v1",
    "kind": "FILE",
    "observed": {"path": "C:\\lab\\sample.exe"},
    "identity_strength": "UNAVAILABLE",
    "verified_digest": null,
    "snapshot": {},
    "revalidation_required": true
  },
  "pe_probe": {
    "status": "VALID_PE | NON_PE | MALFORMED_PE | PARTIAL_OR_EMPTY | FILE_MISSING | PERMISSION_DENIED | SKIPPED_UNKNOWN_PATH",
    "is_pe": true,
    "machine": "0x8664"
  },
  "observation_sha256": "optional-hex-for-dedup-only",
  "reason": "FILE_CREATED:VALID_PE",
  "uncertainty": {
    "path_status": "KNOWN | UNKNOWN",
    "identity_trusted": false,
    "notes": ["observation_only_revalidation_required"]
  }
}
```

---

## 5. Threat Model & Giới hạn

1. **TOCTOU (Time-of-Check to Time-of-Use):** Tệp có thể bị thay đổi hoặc xóa sau khi `monitoring/` probe PE và trước khi Node B đọc. *Giảm thiểu:* đánh dấu `revalidation_required = true`, không coi `observation_sha256` là trusted identity.
2. **Symlink / Junction / Reparse Point:** Kẻ tấn công đặt symlink trong thư mục lab trỏ ra file hệ thống. *Giảm thiểu:* kiểm tra `os.path.realpath` phải nằm trong `watch_dirs` được phép; từ chối hoặc gắn cờ ngoài phạm vi nếu escape.
3. **Event Loss / Queue Overflow:** Burst sự kiện lớn có thể làm tràn `ReadDirectoryChangesW` buffer hoặc `BoundedQueue`, hoặc process kết thúc trước chu kỳ Toolhelp32. *Giảm thiểu:* cấu hình buffer hợp lý, debounce gộp sự kiện trùng, backpressure `drop_newest` có đếm `dropped_queue_full` và `watcher_overflows` minh bạch.
4. **Quyền hạn:** `OpenProcess` với process hệ thống/PPL trả `ERROR_ACCESS_DENIED`; module không cố nâng quyền, ghi rõ `path_status = UNKNOWN`.

---

## 6. Kế hoạch Kiểm thử (Test Plan)

- **Unit tests:** `pe_probe` (PE hợp lệ, non-PE, DOS header cụt, `e_lfanew` lỗi, thiếu chữ ký `PE\0\0`, file mất, permission error), `schemas` & `target_ref` contract.
- **Integration tests (Lab fixture):** tạo/đổi tên benign PE fixture, non-PE, partial write / file lock retry có giới hạn, duplicate dedup, queue overflow backpressure, exclude_dirs chống loop, graceful stop/restart.
- **Live Windows tests:** `Win32FileWatcher` với thư mục tạm thật; `Win32ProcessMonitor` bắt process lành tính tạo trong lab với `pid`, `start_time_epoch`, `target_path`.
- **Benchmark:** Workload tạo N benign PE fixtures trong lab, đo `events_emitted`, `candidates_delivered`, `dropped`, `coalesced`, độ trễ `median` / `p95` (ms), `queue_peak`, `cpu_time_ms` và `peak_rss_mb`.

