# TASK09B — Plan và rollback guide

## Backend thật đã chọn: NTFS trên benign fixture trong VM

Native demo/commands và prerequisite ở LIVE_BACKEND.md. Đã có phép thử snapshot
restore marker và 20 live checks cho trước/chặn/rollback + control. Không có malware.
CLI `NtfsLab.exe recover` trong guest chỉ đọc manifest lab và thử gỡ owned ACE nếu
identity/actor/DACL vẫn khớp. Không cần thay global AppLocker/WDAC policy.

Khi native apply/rollback lỗi: giữ run manifest và audit, không xóa/reset trạng thái.
Nếu DACL còn đúng after-state thì rollback retry/remove owned ACE; nếu về baseline
thì idempotent recovery; nếu drift/hash/file ID/actor mismatch thì dừng review.
Khi journal không xác minh được, dùng snapshot đã diễn tập, không tự reset ACL lạ.
Sau rollback phải chạy lại target/control và kiểm digest baseline/final, không chỉ
nhìn exit code 0. Native Security/AppLocker events chưa thu; không bịa event 8004.

Snapshot hiện tại: `01-windows-installed-clean`, UUID
`a52ed8f3-1543-44fd-86d2-6d0ac2223a29`. Đã restore/resume và xác minh marker biến mất.
Snapshot này chứa trạng thái sau cài Windows; phải review pending updates và lưu
baseline phù hợp khi tái lập lần khác. Không restore lên host hoặc VM khác.

## Python dry-run/mock — backend kiểm thử riêng

Chạy từ root repo, Python 3.12:

```powershell
python -m response.prevention capabilities
python -m response.prevention demo
python -m response.prevention demo-persistent
python -m response.prevention capabilities-powershell
python -m unittest discover -s tests -p 'test_task09b*.py' -v
```

Nếu Python mặc định là Windows Store alias, dùng interpreter thật. Không cần
cài dependency. Nếu sandbox không ghi được temp mặc định, cấu hình TEMP/TMP vào
thư mục scratch riêng trong workspace trước khi chạy test/demo. Không ghi binary
fixture vào Git. Probe mặc định native đọc registry/token/service bằng Python,
không cần PowerShell. Probe optional `capabilities-powershell` cần quyền thực thi
script hiện hữu; nếu bị policy chặn thì ghi BLOCKED, không bypass/đổi execution policy.

Mock plan không thay policy; apply chỉ thêm rule RAM. Rollback cần harness
authorize riêng cho operation `rollback_block`, kiểm owned rule còn khớp và chỉ
xóa rule đó. Target mất không cản gỡ rule cũ. Rollback lỗi inject giữ rule nguyên
để retry; owned rule bị đổi thì dừng review. Ledger RAM mất khi process thoát.
`PersistentMockPrevention` là lựa chọn journal SQLite cho MOCK: sau restart mở lại
cùng lab root và cấp authorizer mới, verify/rollback tiếp được. Crash trước commit
được kiểm bằng child Python thoát đột ngột; reopen chỉ thấy state đã commit.
Nếu DB hỏng/không đọc được, giữ nguyên file, dừng thao tác và review; không xóa DB
để làm mất receipt. Không coi recovery mock này là rollback policy Windows thật.

## Nếu chọn AppLocker live trong giai đoạn khác — chưa thực hiện

1. Trưởng nhóm xác nhận Git base, contract và Windows VM được phép; không dùng host
   làm việc. Có snapshot và quyền điều khiển recovery từ hypervisor ngoài guest.
2. Người quản lý VM chứng minh revert snapshot hoạt động trên guest thử nghiệm;
   ghi snapshot ID, thời điểm và bằng chứng khôi phục. Không coi “đã có snapshot”
   là recovery đã được kiểm chứng.
3. Đọc/backup policy local và effective, kiểm GPO/MDM/inheritance, AppIDSvc,
   enforcement mode, rule IDs và test user. Ghi digest + metadata vào durable journal.
4. Tạo hai executable benign khác identity trong lab; lưu source/build command,
   byte SHA256 và Authenticode rule identity. Chứng minh cả hai chạy trước test.
5. Review policy delta chỉ nhắm fixture/test principal; phân tích tác động lên bản
   sao cùng hash. Không tự thêm allow-* hay đổi enforcement toàn collection. Nếu
   không bảo toàn policy hiện tại và rollback an toàn thì dừng audit/dry-run.
6. Triển khai backend live, auth boundary, durable journal và recovery handler;
   test failure giữa bước ở VM. Đây là công việc chưa có trong prototype hiện tại.
7. Chỉ sau các gate trên mới apply trong VM; correlate hành vi bị chặn với log
   AppLocker 8004, target/rule/user/time. Event 8003 hoặc exit code 0 không đủ.
8. Rollback chỉ gỡ delta sở hữu nếu state còn đúng; không restore đè snapshot XML
   lên policy mới bị người khác sửa. Kiểm policy sau, chạy lại fixture và đối chứng.
9. Nếu rollback không xác minh được, báo FAILED/PARTIAL, giữ audit và dùng recovery
   đã diễn tập từ hypervisor. Không báo hoàn tất chỉ vì lệnh không lỗi.

Đây là checklist cho AppLocker/WDAC, không phải script áp policy. AppLocker/WDAC
live vẫn NOT_RUN. Native NTFS fixture và snapshot rehearsal đã được kiểm chứng riêng.
