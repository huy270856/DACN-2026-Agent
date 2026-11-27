# TASK09B — Báo cáo prototype ngăn thực thi Windows

Ngày chốt: **28/11/2026, Asia/Bangkok**. **LIVE PASS trong phạm vi NTFS fixture lab**.
Không dùng malware. Không tuyên bố antivirus/EDR production hoặc AppLocker/WDAC đã chạy.

## Kết quả chính

Đã triển khai backend NTFS: thêm deny ExecuteFile cho SID hiện tại trên **một file
benign tự biên dịch** trong Windows VM. Fixture chạy trước test, bị CreateProcess
từ chối với Win32 native error 5 sau apply, chạy lại sau rollback. Fixture đối chứng
khác identity vẫn chạy trong khi target bị chặn. DACL cuối khớp digest baseline.
Không thay AppLocker/WDAC, Defender, UAC hoặc policy của laptop host.

| Kiểm chứng | Kết quả | Bằng chứng |
|---|---|---|
| Host unit/mock/journal/guard và Windows locked-file test | **42/42 PASS** | evidence/unit_tests.txt |
| Native Windows VM acceptance/negative/failure checks | **20/20 PASS** | evidence/ntfs_live_result.json |
| Chạy target trước apply | Started, exit 0, đúng token benign | before_execution |
| Chặn target sau apply | CreateProcess denied, native_error=5 | verify_block.execution |
| Đối chứng trong khi target bị chặn | Started, exit 0, đúng token khác | control_during |
| Rollback | Gỡ owned ACE, DACL digest trở về baseline | rollback_block + final_dacl_sha256 |
| Chạy target sau rollback | Started, exit 0, đúng token ban đầu | after_execution |
| Snapshot/recovery rehearsal | **PASS**: marker True trước restore, False sau restore; VM resume được | evidence/vm_preflight.json |
| Python RAM/SQLite demo | **MOCK**, tách khỏi live | evidence/*mock_demo.json |
| Host capabilities | Read-only, không cấp phép live trên host | evidence/capabilities.json |
| AppLocker/WDAC enforcement | **NOT_RUN, không chọn làm backend demo** | COMPARISON.md |
| Windows Security/AppLocker event logs | **NOT_ENABLED**; không bịa event 8004/4663 | native result ghi rõ |

42 host checks gồm 41 unit/mock/guard/journal và 1 Windows sharing/locked-file test.
Không cộng hai nhóm test thành một chỉ số accuracy. Live result kèm 19 audit events,
không xuất SID/SDDL/tài khoản cá nhân; manifest recovery đầy đủ chỉ nằm trong guest lab.

## Mốc Git và phạm vi thay đổi

Base main tạm: `16eb2e6a22eac66f7862d3f55aead98fb251a520`.
Branch local `feat/task09b-execution-prevention`. Chí chưa chốt base/contract;
bản này sẵn sàng review, không tự coi đã được nghiệm thu. **Huy đã yêu cầu commit/push
nhánh ngày 28/11/2026; không tự merge main.** Commit cụ thể xem HEAD của nhánh bàn giao.
Không sửa core Detection/Agent/Node B/C/D1–D9, LightGBM, Qwen, README gốc hoặc frozen artifacts.

File mới chính:

- `response/prevention/NtfsLab.cs`: native NTFS backend, trusted benign harness và recovery.
- `response/prevention/prototype.py`, `journal.py`: Python dry-run/RAM mock/SQLite mock.
- `response/prevention/capabilities.py`, `capabilities.ps1`, `__main__.py`, package initializers.
- `tests/test_task09b_{prevention,capabilities,journal,native_guard}.py`.
- `docs/task09b/{DESIGN,COMPARISON,INTERFACE,LIVE_BACKEND,ROLLBACK_GUIDE,REPORT}.md` và evidence nhỏ.

Không đưa ISO/VM disk, executable/fixture, dataset/model, credential hoặc raw SID/SDDL vào Git.
Native binaries và recovery manifests ở guest `C:DACN09B-Lab`; không phải deliverables Git.

## Backend và phạm vi bảo vệ

Chọn **NTFS ExecuteFile DACL** trong các cơ chế Windows được so sánh, vì tác động
đúng file object và có thể remove đúng owned ACE, tránh thay bộ policy toàn máy.
Không phải policy chặn theo hash trên toàn hệ thống: bản copy khác, SID khác,
người có quyền sửa DACL hoặc process đã chạy không được bảo vệ bởi demo này.
Không kiểm chứng mọi loader, interpreter hay bypass technique. Không tải/chạy malware.

VM thật: VirtualBox 7.2.22, 4 GB RAM, 2 CPU, Windows 11 Professional 26H2 (preflight
build 26300), hostname DACN09B-LAB. Snapshot `01-windows-installed-clean`, UUID
`a52ed8f3-1543-44fd-86d2-6d0ac2223a29`, đã diễn tập restore trước ACL mutation.
Windows Update được để hoàn tất khi shutdown; không tắt cưỡng bức trong update.

Quyền cần là READ_CONTROL/đọc và WRITE_DAC trên file do lab sở hữu, không tự nâng
quyền admin. Giữ handle không share write/delete, kiểm SHA256/file ID/hardlink/
reparse/size, dùng GetSecurityInfo/SetSecurityInfo trên cùng handle, chỉ đổi DACL.
Không thay owner/group/SACL. Từ chối null DACL và preexisting actor deny trước apply.

## API và authorization

`LabBackend` công bố PlanBlock/ApplyBlock/VerifyBlock/RollbackBlock; CLI capabilities,
demo và recover. Request gắn request_id/case_id/revision/target_ref/SHA256/action.
Callback trusted harness ràng buộc fingerprint + operation; default deny, rollback
cần phép riêng. Không coi approved=true từ request/Agent là authorization.
CLI không cung cấp path/command execution tùy ý. Guard yêu cầu đúng VM/hostname,
NTFS và fixed lab namespace; đây là chống chạy nhầm, không phải security boundary production.
Chi tiết type/error/side effects ở INTERFACE.md và LIVE_BACKEND.md.

## Lệnh tái lập

Host, từ root repo với Python 3.12 thật:

```powershell
python -m unittest discover -s tests -p 'test_task09b*.py' -v
python -m response.prevention demo
python -m response.prevention demo-persistent
python -m response.prevention capabilities
python -m response.prevention capabilities-powershell
```

Trong session này interpreter host:
`C:Program FilesWindowsAppsOpenAI.CodexPrimaryRuntime.v26-1123-915-0_26.1123.915.0_x64__3k8sg7r9htsxtdependenciespythonpython.exe`.
TEMP/TMP đặt vào scratch workspace `work/task09b-temp` nếu temp mặc định của app bị chặn.
Nguồn exact commands và exit codes ở evidence/checks.json.

Trong VM đã duyệt, copy source + trusted snapshot record theo LIVE_BACKEND.md,
xác minh source SHA256 rồi chạy:

```powershell
& C:WindowsMicrosoft.NETFramework644.0.30319csc.exe /nologo /r:System.Web.Extensions.dll /out:C:DACN09B-LabNtfsLab.exe C:DACN09B-LabNtfsLab.cs
& C:DACN09B-LabNtfsLab.exe capabilities
& C:DACN09B-LabNtfsLab.exe demo
& C:DACN09B-LabNtfsLab.exe recover
```

`demo` tự tạo run GUID và hai chương trình Console.WriteLine benign khác token/hash.
Không có lệnh chạy file người dùng, shell command do LLM cung cấp hay auto-block từ score.
Source/executable SHA256 được export từ guest; source hash đối chiếu lại với source
đóng gói. Lượt test cuối có 0 check fail. Trạng thái ROLLBACK_INTENT được verify bằng
DACL/hành vi thật; không nhầm journal intent với policy đã rollback.

## Audit, failure và rollback

Trước mutate ghi durable intent; manifest temp+Flush(true)+replace, audit append+Flush(true).
Apply/rollback recheck identity và expected DACL. Inject rollback failure trước write:
target vẫn bị chặn; retry remove owned ACE thành công. Inject apply failure:
DACL không đổi, intent được recovery về baseline. Duplicate apply/rollback không lặp mutation;
hash mismatch/path escape/auth thiếu bị reject. Audit native error + DACL readback +
token output là bằng chứng log ở lượt này; không sửa global audit policy để tạo event.

Python SQLite mock có restart/child-crash/transaction failure tests riêng. Điều đó
không chứng minh native ACL/journal atomic chung. Native file DACL và manifest không
phải một transaction; disk/crash sau mutation có thể partial, cần giữ manifest và
recover hoặc snapshot. Không quảng cáo mọi crash/power-loss đều được xử lý tự động.

## Dependency và giới hạn bàn giao

Không có pip/NuGet runtime dependency mới. Python 3.12 stdlib cho mock; .NET Framework
và csc có sẵn trên Windows guest/host cho backend native. Dùng C# vì có Windows ACL/
handle APIs và CodeDOM tạo fixture; không đổi PowerShell execution policy, không
cài antivirus driver/Guest Additions, không tắt bảo vệ.

Temporary token-scoped file transfer chỉ phục vụ source + JSON evidence, không có
command endpoint; helper không thuộc module sản phẩm. Không mở firewall rule hay
đổi policy host. Dịch vụ được dừng sau thu thập evidence.

Giới hạn: lab root do harness kiểm soát, không chống actor cùng quyền sửa binary/
manifest; snapshot record/hardware hint không là authorization production. Vẫn có
residual TOCTOU ở ancestor/admin/filesystem đặc biệt, không tuyên bố hết race.
Timestamp native là UTC của guest, không phải đồng hồ độc lập đã xác minh.
Chưa core integration và chưa schema chính thức. Cần Chí review backend NTFS,
phạm vi quyền và base/contract trước khi tích hợp. Không tự merge/push.
