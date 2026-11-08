# Node B → REA / Ghidra boundary

Phạm vi: Node B (Context Collector) cung cấp gì cho bước phân tích tĩnh REA/Ghidra
về sau, và **D5/analyzer phải tự xác minh lại gì** trước khi phân tích. Node B
**không** thực thi target, **không** chạy Ghidra/REA, **không** kết luận
benign/malicious. Tài liệu này mô tả ranh giới, không tuyên bố REA/Ghidra đã tích hợp.

REA upstream tham chiếu: commit `0b028cc75a1bb080e03606fd132b12d11a8dbdc4`
(không sao chép code REA vào repo này).

## 1. Node B cung cấp gì (per collection context)

| Thông tin | Nơi chứa | Ghi chú |
|---|---|---|
| Định danh target (identity) | `context.target_ref` (`bc_contracts.target_ref_from_context`) | `kind`, `observed` (path/pid+start_time), `snapshot` (device/inode/size/mtime), `verified_digest`, `identity_strength`, `revalidation_required=true` |
| Verified SHA-256 | `target_ref.verified_digest.value` và facet `sha256` | Chỉ có khi hash hoàn tất **và** file không đổi trong lúc thu thập; ngược lại `UNAVAILABLE` |
| Byte length | `target_ref.snapshot.size_bytes`, facet `metadata.size_bytes` | — |
| File identity snapshot | facet `file_identity` (`device`,`inode`,`size_bytes`,`mtime_ns`) | Cho D5 so khớp khi mở lại handle |
| Kết quả kiểm tra thay đổi | facet `file_unchanged_during_collection` (bool) | TOCTOU: re-stat before/after hash |
| **Format quan sát được** | facet **`format`** (mới, additive) | `format` ∈ {PE, UNKNOWN, UNSUPPORTED, MALFORMED}; tách `detected` và `analyzer_supported` |
| Chi tiết PE | facet `pe_header` (giữ nguyên) | `pe_kind`, `architecture`, `is_dll`, `machine_code`, … |
| Process context | facets `name/executable_path/ppid/user/session_id/start_time/process_identity_still_present` | PID không còn tồn tại → errors `process_not_found` |
| Backing file (PID) | `context.backing_file_context` | Là một collection FILE đầy đủ (gồm facet `format`, `sha256`, …) của executable |

Mọi facet trên đi vào Node C dưới dạng **evidence** (`case_state.build_case_state`
tạo một evidence record cho mỗi facet) với `trust_level = UNTRUSTED_CONTENT`.
⇒ Format/architecture tới analyzer **mà không cần** thêm field vào TargetRef.

### Facet `format` — ngữ nghĩa
Tách **format quan sát được** khỏi **trạng thái hỗ trợ của analyzer**:
- `format = "PE"`: cấu trúc PE tối thiểu đã được xác minh hợp lệ; `analyzer_supported = true`.
- `format = "UNKNOWN"`: không nhận diện được magic nào.
- `format = "UNSUPPORTED"`: nhận diện được một format đã biết (vd ELF, Mach-O, ZIP) nhưng **ngoài phạm vi analyzer đang cấu hình**. **KHÔNG** có nghĩa Ghidra/REA không phân tích được format đó.
- `format = "MALFORMED"`: có dấu hiệu thuộc format đã biết (vd `MZ`) nhưng cấu trúc không hợp lệ/bị cắt cụt.
- `detected`: tên format quan sát được (vd "PE", "ELF", "ZIP") hoặc `null`.
- `analyzer_supported`: boolean, chỉ phản ánh phạm vi analyzer hiện tại (`ANALYZER_SUPPORTED_FORMATS = {PE}`).
- Phát hiện **chỉ** dựa magic bytes/headers; **không bao giờ** dùng đuôi file.
- Khi file thay đổi giữa lúc thu thập → facet `format` = `UNAVAILABLE` (không giữ giá trị cũ).

## 2. D5 / REA PHẢI tự xác minh lại gì trước khi phân tích

TargetRef và các facet là **quan sát tại thời điểm thu thập**, KHÔNG phải uỷ quyền
và KHÔNG đảm bảo path còn trỏ đúng bytes đó. Trước khi phân tích:

1. **Mở lại handle an toàn** (read-only, no-follow) và **so khớp identity**
   (`device`/`inode`/`size`/`mtime`) với `file_identity`/`snapshot`; từ chối reparse/symlink.
2. **Tính lại SHA-256 trên bytes đã stage** và so với `verified_digest.value`;
   chỉ chấp nhận khi khớp. `identity_strength != STRONG` hoặc thiếu `verified_digest`
   ⇒ không coi là target đã xác minh.
3. **Secure staging**: copy sang vùng do backend sở hữu (ACL, chống reparse), khoá
   ghi/xoá trong lúc phân tích (đã có ở D5 `orchestrator/executor.py`).
4. **Không tin facet `format` như uỷ quyền**: dùng để chọn loader/architecture gợi ý,
   nhưng Ghidra/REA tự xác định lại format/kiến trúc từ bytes đã stage. `MALFORMED`/
   `UNKNOWN`/`UNSUPPORTED` là tín hiệu để admission policy (D4) quyết định, không phải
   verdict.
5. **PROCESS target**: hash backing file **không** chứng minh bytes trong bộ nhớ tiến
   trình khớp đĩa; PID có thể bị tái sử dụng — kiểm `start_time` + `process_identity_still_present`.
6. **PID không tồn tại / backing file không truy cập được**: biểu diễn bằng
   `errors.process_not_found` / facet status `UNAVAILABLE`; không bịa file.

## 3. Những gì KHÔNG thuộc Node B (ranh giới)
- Không chọn/khởi chạy Ghidra, không viết Ghidra adapter (task sau).
- Không decompile, không imports/entropy/signature-trust, không EMBER/LightGBM.
- Không verdict benign/malicious; `UNKNOWN`/thiếu bằng chứng **không** suy ra benign.
- Không thay đổi TargetRef schema hay Node C/D1–D9 (facet `format` là additive).
