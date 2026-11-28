# Báo cáo dựng lại tất định (TASK 07C-R, từ trace frozen 07B investigation-v4.0)

**Câu hỏi:** What does the available static evidence indicate about this file's capability for Windows service control (opening the service manager, creating, starting, stopping or configuring services)? State what is observed, what is not, and what remains unknown.

**Trạng thái trả lời (model chọn):** PARTIALLY_ANSWERED

## Nội dung được giữ (nguyên văn do model viết)
- "Static evidence indicates the file has capability to open the service manager (OpenSCManagerW) and start services (StartServiceW)." *(model-authored)*
- "The import table is fully viewed for the relevant DLL." *(model-authored)*
- [OBSERVED] "File can open the service manager and start services via OpenSCManagerW and StartServiceW." — nguồn: I153 = api-ms-win-service-management-l1-1-0.dll!OpenSCManagerW, I152 = api-ms-win-service-management-l1-1-0.dll!StartServiceW *(model-authored)*
- [OBSERVED] "File can close service handles via CloseServiceHandle." — nguồn: I150 = api-ms-win-service-management-l1-1-0.dll!CloseServiceHandle *(model-authored)*

## Nội dung bị loại (không phải dữ kiện)
- "It lacks observed imports for creating services (CreateService), stopping services, or configuring services." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "No static evidence for creating, stopping, or configuring services;" — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "CreateService import not found in fully viewed table." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)

## Phạm vi đã xem (trusted trace)
- Đã hiển thị cho model 4 entry import; mọi entry khác: CHƯA xem.
- Query SYMBOL_PREFIX `OpenService` trang 0: 1/1 match
- Query SYMBOL_PREFIX `CreateService` trang 0: 0/0 match
- Query SYMBOL_PREFIX `StartService` trang 0: 1/1 match
- Query DLL `api-ms-win-service-management-l1-1-0.dll` trang 0: 4/4 match

_Import khai báo là capability tĩnh, không phải hành vi runtime._