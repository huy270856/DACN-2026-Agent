# Báo cáo dựng lại tất định (TASK 07C-R, từ trace frozen 07B investigation-v4.0)

**Câu hỏi:** What does the available static evidence indicate about this file's capability for Windows service control (opening the service manager, creating, starting, stopping or configuring services)? State what is observed, what is not, and what remains unknown.

**Trạng thái trả lời (model chọn):** PARTIALLY_ANSWERED

## Nội dung được giữ (nguyên văn do model viết)
- (không còn câu nào)

## Nội dung bị loại (không phải dữ kiện)
- "Static evidence indicates no direct imports for OpenService, CreateService, or StartService were found in the viewed entries (zero matches for SYMBOL_PREFIX queries)." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "However, the import table was not fully enumerated;" — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "only aggregate counts and specific zero-result queries are visible." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "The absence of advapi32.dll in the import index is notable as it typically hosts these APIs, but other DLLs might contain them." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "Without viewing the full list of imported symbols or checking if any entry resolves to service control functions via ordinal resolution, the complete capability cannot be confirmed statically." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "No imports for OpenService, CreateService, or StartService were found in the viewed entries (zero matches)." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "The import table was not fully enumerated;" — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "only aggregate counts and specific zero-result queries are visible." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "The absence of advapi32.dll is noted but does not confirm absence of service APIs in other DLLs." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)
- "Service control capabilities cannot be confirmed without viewing the full list of imported symbols or checking for ordinal imports that might resolve to service functions." — lý do: câu dạng phủ định/vắng mặt (NEGATION_RE)

## Phạm vi đã xem (trusted trace)
- Đã hiển thị cho model 0 entry import; mọi entry khác: CHƯA xem.
- Query SYMBOL_PREFIX `OpenService` trang 0: 0/0 match
- Query SYMBOL_PREFIX `CreateService` trang 0: 0/0 match
- Query SYMBOL_PREFIX `StartService` trang 0: 0/0 match

_Import khai báo là capability tĩnh, không phải hành vi runtime._