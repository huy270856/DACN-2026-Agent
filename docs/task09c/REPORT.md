# TASK 09C — Báo cáo Thực hiện File & Process Monitoring

**Branch:** `feat/task09c-file-process-monitoring` (tạo từ `main` commit `16eb2e6`)  
**Môi trường kiểm thử:** Windows (`os.name == 'nt'`), Python 3.11.9, **0 external dependencies** (thuần thư viện chuẩn + Win32 `ctypes`).  
**Trạng thái:** Hoàn thành prototype độc lập, unit/integration tests và live Windows lab benchmark đều PASS; **chưa** sửa bất kỳ file core nào (`context_collector.py`, `case_manager.py`, D1–D9, model/README gốc).

---

## 1. Danh sách Files Đã Tạo (Files Changed)

- `docs/task09c/DESIGN.md` — Tài liệu thiết kế, lựa chọn cơ chế Windows, schema dự thảo, threat model và test plan.
- `docs/task09c/REPORT.md` — Báo cáo kết quả, bằng chứng kiểm thử/benchmark và đặc tả bàn giao.
- `monitoring/__init__.py` — Export công khai của module `monitoring`.
- `monitoring/schemas.py` — `ObservationEvent` (`obs-event-v1`), `ScanCandidate` (`scan-candidate-v1`), `MonitorConfig`, `MonitorMetrics`, `build_target_ref` (tương thích `target-ref-v1`).
- `monitoring/pe_probe.py` — `probe_pe_file` (đọc header DOS/PE có giới hạn byte), `observation_sha256` (chỉ phục vụ dedup).
- `monitoring/win32_file_watcher.py` — `Win32FileWatcher` dùng Win32 `ReadDirectoryChangesW` qua `ctypes`, hỗ trợ `CancelIoEx`, phát hiện buffer overflow, kiểm tra scope và `exclude_dirs`.
- `monitoring/win32_process_monitor.py` — `Win32ProcessMonitor` dùng `CreateToolhelp32Snapshot` + `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetProcessTimes` + `QueryFullProcessImageNameW`.
- `monitoring/pipeline.py` — `MonitoringPipeline`, `NodeBSink` (protocol), `MockNodeBIntake` (mock boundary), debounce, bounded retry, dedup TTL cache, bounded queue (`drop_newest`), graceful start/stop.
- `monitoring/cli.py` — CLI `watch` và `benchmark` kèm `make_minimal_pe_bytes` tạo benign fixture tại runtime.
- `tests/task09c/__init__.py`
- `tests/task09c/test_pe_probe.py` — Unit tests cho `probe_pe_file`.
- `tests/task09c/test_pipeline.py` — Unit/integration tests cho pipeline, retry, dedup, queue overflow, exclude_dirs, unknown process path.
- `tests/task09c/test_windows_live.py` — Thử nghiệm Windows thật cho file create/rename, restart và process creation trong lab.

---

## 2. Lệnh Chạy & Kết quả Kiểm thử (Exact Commands & Test Counts)

### 2.1. Chạy toàn bộ test suite (`tests/task09c`)
```powershell
python -m unittest discover -s tests/task09c -v
```
**Kết quả:** `Ran 13 tests in 1.110s` — **OK (13/13 passed, 0 failed, 0 skipped)**

Phân loại rõ phạm vi kiểm chứng:
- **Unit / Mock boundary (`test_pe_probe.py` + `test_pipeline.py`):** **11/11 PASS**
  - `test_valid_pe_fixture`, `test_non_pe_text_file`, `test_empty_or_short_file`, `test_malformed_pe_bad_e_lfanew_and_bad_sig`, `test_missing_and_permission_denied`
  - `test_reject_drive_root_and_excluded_overlap`, `test_valid_pe_and_non_pe_and_deletion`, `test_partial_write_bounded_retry_recovers`, `test_debounce_coalesce_and_dedup`, `test_exclude_dir_filtered_and_queue_overflow`, `test_process_unknown_path_represented_explicitly`
- **Thử nghiệm Windows thật (`test_windows_live.py`):** **2/2 PASS**
  - `test_live_file_create_and_rename_and_restart`: tạo benign fixture trong thư mục tạm, đổi tên `.tmp` → `.exe`, xác minh `ReadDirectoryChangesW` bắt đủ và `stop()`/`start()`/`stop()` không treo.
  - `test_live_process_creation_in_lab`: chạy `python.exe -c "import time; time.sleep(0.4)"`, xác minh `Win32ProcessMonitor` thu được `pid`, `process_start_time_epoch`, và `target_path` kết thúc bằng `python.exe`.

---

## 3. Bằng chứng Benchmark (Lab Workload)

### Lệnh chạy
```powershell
python -m monitoring.cli benchmark --num-files 100 --queue-maxsize 256 --debounce-ms 10
```

### Phương pháp đo
- Tạo 100 benign minimal PE files (`benign_0000.exe`..`benign_0099.exe`) tại runtime trong thư mục tạm (`tempfile.TemporaryDirectory`) với `Win32FileWatcher` thật đang chạy.
- Độ trễ (`latency_ms`) đo từ `time.monotonic_ns()` lúc `Win32FileWatcher` nhận notification từ OS đến lúc `MonitoringPipeline` đóng gói xong `ScanCandidate` để đưa vào queue.
- CPU đo bằng `time.process_time()`, RAM đo bằng Win32 `K32GetProcessMemoryInfo` (`WorkingSetSize` và `PeakWorkingSetSize`).

### Kết quả đo thực tế
| Chỉ số | Giá trị đo được |
|---|---|
| Workload | 100 benign PE files (`queue_maxsize=256`, `debounce_ms=10`) |
| `events_emitted` | 200 (OS phát create + modify cho mỗi file) |
| `events_coalesced` | 100 (gộp bởi debounce) |
| `events_deduped` | 0 |
| `candidates_enqueued` / `candidates_delivered` | 100 / 100 |
| `dropped_queue_full` / `watcher_overflows` / `errors` | 0 / 0 / 0 |
| `queue_peak` | 3 |
| Latency `median` / `p95` | **31.0 ms** / **32.0 ms** |
| `wall_time_ms` / `cpu_time_ms` | 198.9 ms / 265.62 ms |
| `rss_mb` / `peak_rss_mb` | 21.39 MB / 27.95 MB |

---

## 4. Hạn chế, Rủi ro Bảo mật & Rollback

### Hạn chế đã biết
1. **Không có đảm bảo zero-loss:** `Win32ProcessMonitor` dùng Toolhelp32 polling nên có thể bỏ lỡ process sống ngắn hơn `process_poll_interval_ms` (mặc định 100ms). `ReadDirectoryChangesW` có thể tràn buffer nếu burst cực lớn (được đếm qua `watcher_overflows`), và `BoundedQueue` dùng `drop_newest` khi đầy (`dropped_queue_full`).
2. **Post-execution telemetry:** `PROCESS_CREATED` chỉ ghi nhận sau khi OS đã tạo process; **không** phải cơ chế chặn trước thực thi.
3. **Quyền truy cập process:** Process hệ thống/PPL trả `ACCESS_DENIED` khi gọi `OpenProcess` dưới quyền user thường; module ghi rõ `path_status = "UNKNOWN"` thay vì suy đoán.

### Rủi ro bảo mật & giảm thiểu
- **TOCTOU:** File có thể bị sửa/tráo sau khi probe PE. Mọi `ScanCandidate` đều gắn `revalidation_required: true` và `identity_trusted: false`; `observation_sha256` chỉ dùng để dedup.
- **Symlink / Path escape:** Kiểm tra `os.path.realpath` nằm trong `watch_dirs` và không thuộc `exclude_dirs`; từ chối watch drive root mặc định.
- **Data minimization:** Không thu command line, username hay biến môi trường của process.

### Quy trình Rollback
Module `monitoring/` hoàn toàn độc lập, không sửa cấu hình hệ thống hay file core của repo. Để rollback:
```powershell
git checkout main
git branch -D feat/task09c-file-process-monitoring
```

---

## 5. Interface Bàn giao cho Core Integration (Node B)

- **Boundary hiện tại (MOCK):** `NodeBSink.submit_candidate(candidate: ScanCandidate)` với implementation mẫu `MockNodeBIntake`.
- **Dữ liệu bàn giao:** `ScanCandidate.to_dict()` chứa:
  - `target_ref`: tuân thủ `target-ref-v1` (`bc_contracts.py`), luôn đặt `verified_digest: null`, `identity_strength: "UNAVAILABLE"` (với `FILE`) hoặc `"PARTIAL"` (với `PROCESS` có `pid` + `start_time_epoch`), và `revalidation_required: true`.
  - `pe_probe`: kết quả lọc sơ bộ (`VALID_PE`, `NON_PE`, `MALFORMED_PE`, `PARTIAL_OR_EMPTY`, `FILE_MISSING`, `PERMISSION_DENIED`, `SKIPPED_UNKNOWN_PATH`).
  - `uncertainty`: gồm `path_status` (`KNOWN` | `UNKNOWN`), `identity_trusted: false`, và `notes`.
- **Yêu cầu khi nối vào Core:** Node B (`context_collector.py`) cần mở handle/process thực tế và tự tính `sha256` + `file_identity` từ `target_ref.observed`, không tin tưởng `observation_sha256` hay `pe_probe` như bằng chứng cuối cùng.

