# TASK09B — Thiết kế cuối cho prototype nghiên cứu

Ngày 28/11/2026. Backend live được chọn: **NTFS deny ExecuteFile trên một benign fixture
và SID hiện tại trong VM**. Python RAM/SQLite mock là backend kiểm thử riêng.
Không gọi đây là AppLocker/WDAC enforcement; hai cơ chế đó được so sánh trong COMPARISON.md.

## Phạm vi và quyết định

Module độc lập, không sửa core/model/threshold/README/frozen artifacts. Base main tạm
16eb2e6a22eac66f7862d3f55aead98fb251a520, branch local feat/task09b-execution-prevention;
Chí chưa chốt base/contract. Đã đọc README, source/tests D4 và đề 09A/B/C; không có
CLAUDE.md/AGENTS.md trong snapshot repo.

NTFS được chọn để giữ tác động trên đúng file object thay vì tạo policy toàn máy.
Đây là phương án phù hợp khác được đề cho phép nghiên cứu. Phạm vi: không chạy được
file đó bởi SID bị deny ExecuteFile. Không chặn bản copy/SID khác, process đã chạy
hoặc mọi cách load nội dung. Xem LIVE_BACKEND.md cho API, nguồn Microsoft và lệnh.

## Hai đường chạy tách biệt

1. Python `Prevention` default dry-run; mọi apply bị reject. Mode mock chỉ thay RAM;
   `PersistentMockPrevention` dùng SQLite atomic snapshot/receipt/audit, luôn MOCK.
2. Native `NtfsLab.cs`: guard Windows/NTFS/VirtualBox/hostname/fixed lab root,
   chỉ trusted benign harness; plan không đổi DACL, apply/verify/rollback thật.
   C#/.NET Framework có sẵn, không pip/NuGet, không đổi execution policy.

## Binding và state machine native

Request gắn request_id, case_id, revision, relative target_ref, byte SHA256, action.
Callback auth từ trusted harness ràng buộc fingerprint và operation; không đọc
approved boolean. Host guard chỉ tránh chạy nhầm, không được coi là auth production.
Snapshot record mô tả recovery đã diễn tập, không thay authorization.

State: PLANNED -> APPLY_INTENT -> APPLIED -> ROLLBACK_INTENT -> ROLLED_BACK.
Trước mutation persist intent + audit. Sau mutation đọc lại DACL rồi mới cập nhật
status; verify luôn cần thử CreateProcess, không chỉ nhìn state/exit code cmdlet.
Nếu ROLLBACK_INTENT nhưng DACL vẫn after-state, verify vẫn thử hành vi thật để
chứng minh target còn blocked. Intent không đồng nghĩa mutation đã/ chưa xong.
Duplicate/conflict/retry/partial có reason code và manifest để review.

## Identity và rollback

Lab target/control tự compile từ Console.WriteLine, hash khác nhau. Reject path ngoài
namespace, reparse/ancestor, directory, hardlinks, file quá lớn. Pin handle không share
write/delete; kiểm file ID + SHA256. Chỉ DACL_SECURITY_INFORMATION trên cùng handle;
không owner/group/SACL, không null DACL. Trước apply không chấp nhận preexisting actor
deny để tránh merge nhầm ACE. Rollback chỉ remove owned ExecuteFile deny khi state
khớp, phần còn lại phải khớp baseline. Drift -> dừng review, không reset bừa.

## Threat model và giới hạn

Xét hash/file ID đổi, path escape/reparse/hardlink, quyền thiếu, auth thiếu, retry,
policy drift, apply/rollback failure và journal lỗi. Không xử lý attacker có admin/
cùng quyền sửa trusted harness/root/binary. Không tuyên bố hết TOCTOU, tamper-proof
journal, mọi power-loss recovery hoặc native ACL/journal atomic chung.

Manifest native bền vững nhưng disk/crash giữa ACL và journal vẫn có thể partial.
Giữ intent/manifest/audit và dùng recover hoặc snapshot đã diễn tập. Python SQLite
crash tests chỉ chứng minh mock transaction, không thay native recovery evidence.
SID/SDDL chỉ ở guest internal store; evidence public dùng digest, không credential.

## Kiểm chứng và ranh giới integration

42 host checks; 20 live VM checks; target trước/chặn/rollback, control không bị ảnh hưởng,
DACL baseline/final khớp. Snapshot đã diễn tập marker True/False. Xem REPORT.md và JSON
evidence. Không thu event 8004/4663, không thay audit policy; bằng chứng log là native
CreateProcess error 5, DACL readback, fixture/control output và audit của harness.

09A quản lý quarantine/restore, 09C chỉ xuất candidate. Không nối chúng vào native
backend, không auto-block từ LightGBM/Agent, không bypass D4/D8. Trưởng nhóm khóa
contract/schema/authorization và review rồi mới tích hợp. Prototype chưa production.
