# TASK09B — Interface bàn giao dự thảo

Đây là contract module nghiên cứu để review, chưa phải schema core được phê duyệt.
Không có endpoint live, không nhận command do Agent/LLM sinh. Chỉ trusted test harness.

## Backend native đã bổ sung

`NtfsLab.cs` triển khai NTFS file ExecuteFile deny trong VM, khác backend Python
mock bên dưới. `LabBackend` có PlanBlock/ApplyBlock/VerifyBlock/RollbackBlock, CLI
capabilities/demo/recover, result có evaluation_type=WINDOWS_VM_NTFS_LIVE. Request
gắn ID/case/revision/target_ref/hash/action; callback auth từ harness, default deny.
LIVE_BLOCK_VERIFIED chỉ khi DACL khớp và CreateProcess thật bị native error 5.
APPLIED chỉ xác nhận DACL readback, không tự coi là chặn đã kiểm chứng.
Rollback gỡ owned ACE, kiểm baseline. SID/SDDL chỉ trong manifest nội bộ guest;
evidence public chỉ digest. Scope cố định trên fixture tự compile, không endpoint
chạy file bất kỳ hoặc core integration. Xem LIVE_BACKEND.md cho đủ quyền/side effects,
lỗi/partial/journal/giới hạn và lệnh tái lập. Các phần tiếp theo chỉ mô tả Python mock.

## Request

Python `BlockRequest` frozen dataclass; request_id/case_id dùng `[A-Za-z0-9_-]{1,80}`,
revision là integer >=0 (bool không hợp lệ). target_ref tương đối trong lab đã cấu hình,
target_sha256 là SHA256 byte file lowercase 64 hex. action hiện duy nhất `block_execution`.

```json
{
  "request_id": "lab-request-1",
  "case_id": "lab-case-1",
  "case_revision": 1,
  "target_ref": "fixture.exe",
  "target_sha256": "<64 lowercase hex from trusted lab harness>",
  "action": "block_execution"
}
```

Ví dụ JSON trên có placeholder, không phải request hợp lệ để thực thi.
Production cần target handle/ref và authorization do trusted backend xác thực,
không dùng boolean approved=true. `authorize(request, operation)` chỉ MOCK callback
inject từ harness, default deny; operation rollback phải được phép riêng. Restart
persistent mock không lưu lại callback/quyền cho instance tiếp theo.

## Constructors và side effects

| Entry point | Điều kiện | Side effects |
|---|---|---|
| `Prevention(root)` | Root hiện hữu, không reparse | Chỉ đọc fixture khi plan; audit RAM; apply luôn reject |
| `Prevention(root, mode='mock', authorize=...)` | Harness tin cậy, lab fixture | Đổi dictionary RAM, không policy Windows |
| `PersistentMockPrevention(root, authorize=...)` | Root lab private có quyền đọc/ghi | Tạo SQLite `.task09b-mock.sqlite3` trong lab, journal transaction; luôn MOCK |
| CLI `capabilities` | Windows để lấy native facts | Read registry, token, query service; không shell, không policy writes |
| CLI `capabilities-powershell` | Script execution hiện hữu cho phép | Probe optional read-only; bị chặn thì BLOCKED, không retry bypass |

Constructor có thể ném PrototypeError/OSError/sqlite3.Error nếu lab/journal không
hợp lệ. Caller phải dừng fail-closed; không xóa/reset DB hỏng để coi như chưa apply.
Không dùng persistent constructor cho dry-run cam kết zero disk writes.

## Result và trạng thái

Result operation: request_id, operation, status, reason_code, timestamp ISO8601 UTC,
evaluation_type (`MOCK`/`DRY_RUN`), live_execution_verified=false, policy_state
(digest MOCK hoặc null nếu journal không đọc được), rollback_reference (hoặc null),
audit_metadata. Plan có field plan; apply có identity_before/after + policy_before.
Không có field `success=true` có thể gây hiểu nhầm đã chặn Windows.

| Status / reason | Ý nghĩa |
|---|---|
| PLANNED | Chỉ tạo ý định; windows baseline/subject SID/Authenticode hash còn UNKNOWN |
| MOCK_APPLIED | Rule mô phỏng được thêm, không phải execution prevented |
| MOCK_VERIFIED | Identity và rule mô phỏng khớp, không có bằng chứng event/hành vi thật |
| MOCK_ROLLED_BACK | Owned rule mô phỏng đã gỡ |
| REJECTED | Input/auth/identity/state không hợp lệ; không apply policy thật |
| FAILED / MOCK_TRANSACTION_ABORTED | Transaction SQLite không commit, state mock trở về lần commit cuối; failure audit ghi nếu DB còn ghi được |
| FAILED / MOCK_JOURNAL_UNAVAILABLE | Không thể xác minh/ghi journal; audit_metadata=UNAVAILABLE_NOT_RECORDED, không báo thành công |
| DUPLICATE_APPLY_USE_VERIFY | Request đã apply thành công trước đây; không apply lại |
| POLICY_STATE_CHANGED_REPLAN_REQUIRED | State khác plan; review và tạo request ID mới |
| OWNED_RULE_CHANGED_REQUIRES_REVIEW | Không gỡ rule đã bị thay đổi |

Mode `live` bị constructor từ chối. Capabilities luôn live_supported=false, có danh
sách blockers. Không infer hỗ trợ live chỉ từ edition/build/admin hoặc VM hint.

## Ví dụ persistent mock

```python
from response.prevention import BlockRequest, PersistentMockPrevention

# root, digest và authorizer do lab harness cấu hình, không lấy từ LLM.
request = BlockRequest('r1', 'case1', 1, 'fixture.exe', digest)
engine = PersistentMockPrevention(root, authorize=mock_authorizer)
engine.plan_block(request)
engine.apply_block(request)
reopened = PersistentMockPrevention(root, authorize=mock_authorizer)
reopened.verify_block(request)
reopened.rollback_block(request)
```

SQLite transaction lưu snapshot + receipt + audit cùng commit, synchronous=FULL;
BEGIN IMMEDIATE serialize writers và mỗi operation reload committed state.
Journal phục vụ workload lab, tăng theo số event, không tự rotate/xóa audit.
Không bảo đảm chống sửa DB, disk corruption, mất điện mọi loại storage,
TOCTOU hay Windows policy recovery. Crash test chỉ chứng minh ở process/SQLite MOCK.

## Bàn giao cho integration sau này

Trưởng nhóm cần khóa authorization/target reference/error schema; map kết quả mock
thành trạng thái nghiên cứu, không map MOCK_VERIFIED thành blocked. 09C chỉ xuất
candidate; 09A quản lý quarantine riêng. Không module nào tự gọi apply từ score/Agent.
Native NTFS được bổ sung sau VM+snapshot+recovery rehearsal; AppLocker/WDAC không
được triển khai. Không yêu cầu sửa core trong thay đổi này.
