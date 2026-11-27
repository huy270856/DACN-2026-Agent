# TASK09B — So sánh cơ chế và capability matrix

Tra cứu Microsoft Learn ngày 27/11/2026; không suy edition từ tên máy.
Thông tin là tài liệu tham khảo, capability live phải xác minh ở VM cụ thể.

| Cơ chế | Edition/build, quyền, phạm vi | Audit/enforce và rollback | Quyết định |
|---|---|---|---|
| AppLocker | Windows 10 2004+ theo điều kiện KB5024351; Windows 11 không còn giới hạn edition để enforce theo [S1]. Bản cũ phụ thuộc edition/cách triển khai. Có rule theo user/group; quản lý policy cần quyền phù hợp. Cmdlet có sẵn không chứng minh enforcement hoạt động. | Có audit/enforce theo collection. Deny ưu tiên allow; implicit deny nếu thiếu allow [S3]. Cần inspect local/effective/inheritance trước khi add/remove rule. Rollback chưa kiểm chứng. | Đã nghiên cứu; không chọn làm backend live, không apply policy AppLocker. |
| App Control for Business (WDAC) | Windows 10/11 và Server 2016+; policy device-wide. PowerShell cmdlets không có trên Home dù policy có thể hiệu lực. Nhiều tính năng tùy build [S2]. Quản trị triển khai cần quyền thích hợp. | Audit/enforce; unsigned policy removal/reboot phụ thuộc build; signed policy khó gỡ hơn [S5]. Phạm vi device-wide và recovery phức tạp hơn mục tiêu lab hẹp. | Chưa chọn cho lượt prototype. |
| Software Restriction Policies | Công nghệ cũ, phụ thuộc phiên bản Windows/Group Policy. Microsoft ghi deprecated từ Windows 10 build 1803 [S6]. | Có security levels/rules nhưng không coi là tương đương workflow audit/enforce của AppLocker. Cần tự kiểm khả năng recovery theo môi trường. | Không ưu tiên cho module mới. |
| NTFS ExecuteFile DACL | Phạm vi đúng file object + SID; thực đo Windows 11 Pro guest có NTFS. Cần READ_CONTROL/WRITE_DAC trên fixture tự tạo, không tự nâng quyền. Không yêu cầu AppLocker cmdlet/service để chặn. | Plan không đổi DACL. Enforce bằng deny ExecuteFile; verify CreateProcess bị từ chối error 5. Rollback gỡ owned ACE và kiểm baseline digest. Không có mode audit-only của engine; dry-run do module triển khai. | **Backend live đã chọn, 20/20 kiểm tra VM PASS**. Không bảo vệ bản copy/SID khác hoặc thay antivirus. |
| In-memory MOCK | Python 3.12 stdlib; không quyền admin; root fixture có quyền đọc/ghi trong test | Mô phỏng thêm/xóa rule, verify trạng thái RAM; không chặn Windows | Backend được triển khai hiện tại; kết quả luôn ghi MOCK. |

## Prerequisite/capability matrix — cập nhật 28/11/2026

| Điều kiện | Cách xác minh / trạng thái hiện tại | Khi thiếu |
|---|---|---|
| OS edition/build/UBR | Host ban đầu CoreSingleLanguage 26200.9711 25H2; guest preflight Professional 26300 26H2 | Chỉ suy từ môi trường và test đã đo, không mọi edition/build |
| Quyền token/file | Host token admin=false; guest dùng quyền trên fixture do mình sở hữu. Native apply mở WRITE_DAC trên đúng file | Nếu WRITE_DAC thiếu thì reject; không tự nâng quyền |
| AppLocker cmdlets | Optional PS probe bị script policy chặn; UNKNOWN | Dry-run/mock |
| AppIDSvc | Host STOPPED; guest Running trong preflight | Không tự đổi service; NTFS backend không phụ thuộc AppIDSvc |
| Effective app policy | Guest đọc được policy rỗng; không thay AppLocker/WDAC | Không coi sự có mặt cmdlet là chứng minh AppLocker enforce |
| Local/GPO/MDM/inheritance review | Không triển khai global app policy backend | Không claim quản lý AppLocker/WDAC; native chỉ kiểm DACL fixture |
| VM và snapshot | Huy xác nhận tự tạo VM; snapshot installed-clean đã lưu | Không apply ngoài VM guard |
| Recovery rehearsal + journal | Snapshot marker restore PASS; native intent/manifest/audit đã có | Không claim ACL+journal atomic hoặc mọi crash/power-loss |
| Identity/scope | Byte SHA256 + file ID + SID trên target.exe tự compile; không dùng Authenticode rule hash | Reject mismatch/reparse/hardlink; không tạo policy app-control |
| Trước/chặn/sau rollback + đối chứng | **20/20 live VM checks PASS**, baseline/final DACL khớp | Chỉ claim NTFS fixture scope |

## Nguồn chính thức

- [S1 — Requirements to use AppLocker](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/applocker/requirements-to-use-applocker). Trang ghi cập nhật 2024-10-01.
- [S2 — App Control/AppLocker feature availability](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/feature-availability). Trang ghi cập nhật 2026-03-31.
- [S3 — Allow and deny actions](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/applocker/understanding-applocker-allow-and-deny-actions-on-rules). Trang ghi cập nhật 2024-10-01.
- [S4 — AppLocker file hash rule](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/applocker/understanding-the-file-hash-rule-condition-in-applocker). Authenticode hash, không phải byte SHA256 của prototype.
- [S5 — Remove App Control policies](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/windows-defender-application-control/deployment/disable-wdac-policies). Phải đọc theo build, loại policy và phương thức deploy; không đưa lệnh gỡ policy lên host.
- [S6 — Software Restriction Policies](https://learn.microsoft.com/en-us/windows-server/identity/software-restriction-policies/software-restriction-policies).
- [S7 — AppLocker Event Viewer](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/applocker/using-event-viewer-with-applocker). Event 8003 là would-block trong audit; 8004 ghi nhận prevented. Vẫn cần correlate với hành vi fixture.
- [S8 — CheckTokenMembership](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-checktokenmembership). Native probe kiểm nhóm Administrators enabled, không tự elevation.
- [S9 — QueryServiceStatus](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-queryservicestatus). Native probe chỉ hỏi trạng thái service.
- [S10 — Service access rights](https://learn.microsoft.com/en-us/windows/win32/services/service-security-and-access-rights). Dùng SC_MANAGER_CONNECT và SERVICE_QUERY_STATUS, không quyền start/stop/change config.
- [S11 — FileSystemRights](https://learn.microsoft.com/en-us/dotnet/api/system.security.accesscontrol.filesystemrights). ExecuteFile và quyền truy cập file.
- [S12 — SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo). DACL mutation theo handle; không dùng null DACL.

Nguồn bổ sung cho backend NTFS tra ngày 28/11/2026; chi tiết và giới hạn ở LIVE_BACKEND.md.
