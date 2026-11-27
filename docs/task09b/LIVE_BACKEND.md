# TASK09B — Backend thật có phạm vi file NTFS

Ngày 28/11/2026. Backend được chọn để demo: **NTFS deny ExecuteFile cho SID hiện tại,
chỉ trên executable benign do harness tự biên dịch trong VM lab**.
AppLocker/WDAC giữ vai trò so sánh, không tuyên bố đã triển khai hai backend đó.

## Vì sao chọn cơ chế này

Đề yêu cầu so sánh AppLocker, WDAC và phương án phù hợp khác, rồi chọn một backend
tối thiểu có thể kiểm chứng/rollback. NTFS là phương án thứ ba: thay DACL của đúng
file, không thêm bộ quy tắc application control toàn máy. Khi AppLocker collection
rỗng, việc thêm rule có thể kích hoạt implicit deny cho các file khác; vì vậy không
tự tạo policy allow-* hoặc thay enforcement mode để demo.

Đây là thực thi quyền Windows thật, không phải mock, nhưng có phạm vi hẹp:

- Nhắm **đúng file object + byte SHA256 + file ID + SID**, không nhắm mọi bản sao.
- Một bản copy mới, tài khoản khác hoặc người có quyền sửa DACL có thể không bị chặn.
- Không dừng process đã chạy, không chặn mọi loader/interpreter và không là antivirus.
- Không thay AppLocker/WDAC, Defender, UAC, audit policy hoặc quyền file người dùng.

## Implementation và quyền

`response/prevention/NtfsLab.cs` dùng .NET Framework có sẵn trên Windows, không cần
NuGet hoặc Python trong guest. C# dùng native Windows handle/security APIs để thay
DACL của file; giữ nguyên backend Python dry-run/mock cho kiểm thử độc lập.
Lý do dùng C#: Windows ACL và handle APIs có sẵn qua .NET/Win32, dễ tạo executable
benign tại runtime, không phải đổi PowerShell execution policy để chạy script.

Guard trước mọi thao tác: Windows + NTFS + VirtualBox hardware hint + hostname
DACN09B-LAB. Root cố định `C:\DACN09B-Lab\LiveRuns\<GUID>`, chỉ target.exe/control.exe
do harness tạo; không endpoint nhận command/path tùy ý. Đây là gate lab nhằm tránh
chạy nhầm host, **không phải** xác thực production. Snapshot record trong harness là
bằng chứng chuẩn bị môi trường, **không** thay authorization của trusted backend.

Quyền cần: đọc fixture/READ_CONTROL; khi apply/rollback cần WRITE_DAC trên đúng file
fixture. Owner có thể có quyền này ngay cả khi session không elevated. Không tự nâng
quyền. Thiếu quyền -> native error/reject, không thử bypass hoặc bật privilege.

Mỗi request có request_id, case_id, case_revision, target_ref, target_sha256, action.
Authorization là callback do trusted harness cấu hình, ràng buộc fingerprint request
và operation; mặc định deny. Rollback cần phép riêng. Không nhận approved=true từ LLM.

## API và journal

| API / CLI | Hành vi |
|---|---|
| CLI `capabilities` | Kiểm guard, không đổi ACL/không tạo fixture |
| `LabBackend.PlanBlock` | Read identity/DACL, persist kế hoạch trong lab; DACL không đổi |
| `ApplyBlock` | Recheck binding/hash/file ID/DACL, persist APPLY_INTENT, thêm owned deny ExecuteFile, readback |
| `VerifyBlock` | Recheck identity/DACL rồi thật sự thử CreateProcess trên fixture; chỉ LIVE_BLOCK_VERIFIED khi bị từ chối với native error 5 |
| `RollbackBlock` | Auth riêng, đọc journal/state, remove đúng ACE sở hữu nếu state khớp, verify DACL trở về baseline |
| CLI `demo` | Harness benign-only: trước/chặn/đối chứng/rollback, negative tests và fault injection |
| CLI `recover` | Trusted operator yêu cầu recovery từ manifest các lab run, không reset ACL khi drift |

Manifest chứa SID/SDDL để recovery chỉ ở **guest lab nội bộ**, không commit/publish.
Evidence xuất ra chỉ chứa digest DACL và mã lỗi, không chứa SID/tài khoản cá nhân.
Manifest dùng temp+Flush(true)+replace; audit.jsonl append+Flush(true); operation lock
FileShare.None. Đây không phải distributed transaction: file DACL và journal không
atomic chung. Intent trước mutation hỗ trợ review/retry; disk error sau mutation có
thể để partial state và bắt buộc dùng manifest/recover hoặc snapshot đã diễn tập.
Không tuyên bố chống tamper, mọi trường hợp power loss hoặc attacker có quyền sửa lab.

## Identity và phạm vi mutation

Reject reparse points ở path/ancestor, directory, hardlink count khác 1, file >16 MiB.
Pin handle mở đọc, không share write/delete; kiểm file ID + SHA256. GetSecurityInfo
và SetSecurityInfo sử dụng cùng handle, chỉ DACL_SECURITY_INFORMATION; không thay
owner/group/SACL. Từ chối null DACL. ACL trước/sau phải khớp, không ghi đè policy máy.
Trước apply từ chối nếu đã có deny của actor để tránh merge nhầm ACE của người khác.
Rollback chỉ remove owned ExecuteFile deny rồi xác nhận phần còn lại bằng baseline.
Drift làm dừng để review, không tự restore cả DACL bất chấp thay đổi bên ngoài.

Pin handle giảm race trên file, không chứng minh hết TOCTOU đối với mọi thay đổi
ancestor/name, external admin hoặc filesystem bất thường. Lab root phải do harness
kiểm soát, không nhận nội dung do đối thủ ghi đồng thời.

## Tái lập trong VM đã duyệt

1. Tạo snapshot sau cài Windows, chứng minh restore bằng marker trước thử ACL.
2. Copy source và trusted snapshot record vào `C:\DACN09B-Lab` qua kênh nhóm kiểm soát;
   xác minh SHA256 source trước compile. Record của lượt này gắn snapshot UUID
   a52ed8f3-1543-44fd-86d2-6d0ac2223a29; môi trường mới phải review/cập nhật harness.
3. Trong PowerShell guest, biên dịch bằng compiler có sẵn:

```powershell
& C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /r:System.Web.Extensions.dll /out:C:\DACN09B-Lab\NtfsLab.exe C:\DACN09B-Lab\NtfsLab.cs
& C:\DACN09B-Lab\NtfsLab.exe capabilities
& C:\DACN09B-Lab\NtfsLab.exe demo
```

4. Đọc report.json trong run và `C:\DACN09B-Lab\latest-report.json`. Exit code 0 không
   đủ: phải có từng check thành công, fixture output trước/sau, CreateProcess bị
   chặn error 5, control vẫn chạy, DACL baseline/final khớp.
5. Nếu lỗi/partial: giữ manifest/audit, gọi `NtfsLab.exe recover`. Khi state drift
   hoặc journal không xác minh được thì dừng, review hoặc restore snapshot, không
   tự xóa ACE/policy không thuộc module. Binary fixture/executable build không push Git.

Không thu Windows Security events vì chưa bật SACL/audit policy, không giả AppLocker
event 8004. Log bằng chứng là CreateProcess native error + DACL readback + kết quả
fixture/control. Báo cáo phải ghi đúng loại bằng chứng và giới hạn này.

## Nguồn chính thức

- [FileSystemRights.ExecuteFile](https://learn.microsoft.com/en-us/dotnet/api/system.security.accesscontrol.filesystemrights): quyền thực thi file.
- [File access rights](https://learn.microsoft.com/en-us/windows/win32/fileio/file-access-rights-constants): FILE_EXECUTE, READ_CONTROL, WRITE_DAC.
- [GetSecurityInfo / SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-operations): thao tác theo handle.
- [SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo): phạm vi DACL và nguy cơ null DACL.
- [Get-Acl](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/get-acl): phân biệt DACL và SACL/audit.
- [AppLocker rule behavior](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/applocker/understanding-applocker-rule-behavior): collection rỗng so với có allow/deny rule.

Tra cứu ngày 28/11/2026. Giới hạn enforcement thực tế dựa trên evidence VM, không
suy rộng từ tài liệu hay một lần thử sang bảo vệ production.
