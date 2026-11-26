# TASK 06B-J — Questions v2 (`task06b-j-questions-v2`): protocol và manifest accessibility

Thiết kế **độc lập** với mọi output của Agent hay Judge. Chỉ dùng:

- 20 mẫu đã duyệt (giữ nguyên alias và SHA).
- Static parse toàn bộ bảng import.
- Giới hạn thật của hệ thống: analyzer commit 64 entry theo thứ tự trong file; projection hiển
  thị 16 entry sau khi gọi tool; `READ_EVIDENCE` tối đa 2 lần × 16 entry.
- Budget lượt thật của arm C.

Chưa có inference nào trên 20 mẫu này. Nguồn: `questions_v2.py`,
`holdout_audit.make_cases_v2`. Manifest:
`results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json` (evaluator-only, **không** đưa vào
prompt của Qwen).

## 1. Audit budget thực tế (không chỉ dựa vào lý thuyết)

| Thành phần | Giá trị thật | Nguồn |
|---|---|---|
| Evidence ban đầu (Node B + detector) | metadata, file_identity, readable, **pe_header**, **format**, file_unchanged, sha256, **static.pe_malware_prediction** | `staging_smoke_v2/*_initial_state.json` (DEV). Holdout chưa intake, vì intake sẽ chạy detector |
| Agent thấy ở turn 1 | prediction, pe_header, format (`repair_context` bỏ metadata/readable/unchanged) | `repair_context.build` |
| Import trước khi gọi tool | **0** (không có facet imports ban đầu) | — |
| Sau khi gọi tool | entry 0–15 hiển thị; tối đa 64 entry được commit | `imports_tool`, `repair_context` |
| Retrieval | ≤ 2 lần đọc × 16 entry, offset tự chọn (0–64) | `workflow_v34` |
| Budget lượt của C | `max_iterations=5`; token 100k ÷ 12 288 tối thiểu/lượt ≈ 8 lượt, nên **5 lượt** là giới hạn thực tế | `runner.CFG`, `workflow_v34` |
| Chuỗi tối đa | TOOL_CALL → READ → READ → FINISH (chọn) → FINISH (final) = đúng 5 lượt; một lần repair sẽ làm mất một lượt đọc | — |
| Đọc tuần tự tới được | entry **16–47** | — |
| Entry 48–63 | đã commit, nhưng chỉ tới được nếu nhảy offset ngay lần đọc đầu; **không** dùng cho lớp retrieval | — |
| Entry ≥ 64 | không bao giờ được commit, nên không truy cập được | analyzer cap |

Retrieval "có sẵn về lý thuyết" **không** đồng nghĩa "tới được trong budget". Vì vậy lớp
retrieval chỉ tính các ca có entry liên quan đầu tiên nằm trong 16–47.

## 2. Họ capability và lexicon chính xác

NETWORK, FILE, PROCESS, REGISTRY, SERVICE. So khớp **tên chính xác** (có biến thể A/W),
không dùng prefix, nên đã loại các API token mà v1 bắt nhầm (`OpenProcessToken`,
`NtOpenProcessTokenEx`). Riêng NETWORK so theo DLL mạng.

Một entry khớp lexicon chỉ là **tham chiếu tới năng lực được khai báo**, không phải ground
truth semantic. Ví dụ `TerminateProcess` thường dùng để tự kết thúc chính tiến trình; reference
answer chỉ ghi "đã khai báo", không ghi "điều khiển tiến trình khác".

## 3. Mẫu câu hỏi

Câu hỏi không nhắc tên chương trình, path, import hay tool; không dẫn dắt việc gọi tool; không
coi import là hành vi runtime. Cả 3 arm A/B/C của cùng một case nhận cùng câu hỏi.

- **Capability:** "What does the available static evidence indicate about this file's
  capability for {họ}? State what is observed, what is not, and what remains unknown."
- **NOT_STATIC_ANSWERABLE:** "Does this file actually communicate over the network when it
  runs? State what the available evidence can and cannot establish about this."
- **INITIAL_EVIDENCE_SUFFICIENT:** "What kind of PE image is this (executable or DLL,
  architecture), and what did the static detector output? State what remains unknown."

## 4. Phân bổ: target 4/4/4/4/4, khả thi 2/6/4/4/4

- Chỉ **2/20** mẫu có entry liên quan nằm trong trang đầu (0–15), ở bất kỳ họ nào (compact và
  driverquery, đều là FILE). Vì vậy lớp `IN_INITIAL_TOOL_PROJECTION` không thể đạt 4 nếu giữ
  nguyên cohort.
- **Quy tắc thiếu hụt khai báo trước:** phần thiếu (2) được chuyển sang
  `REACHABLE_BY_BOUNDED_RETRIEVAL`, lớp kiểm trực tiếp giả thuyết chính; lớp này có 10 mẫu đủ
  điều kiện.
- Không ép corpus, không đổi mẫu.

| Lớp | Target | Khả thi |
|---|---:|---:|
| IN_INITIAL_TOOL_PROJECTION | 4 | **2** |
| REACHABLE_BY_BOUNDED_RETRIEVAL | 4 | **6** |
| INACCESSIBLE_UNDER_LIMITS | 4 | 4 |
| NOT_STATIC_ANSWERABLE | 4 | 4 |
| INITIAL_EVIDENCE_SUFFICIENT | 4 | 4 |

Thuật toán: shuffle có seed `task06b-j-questions-v2`, backtracking điền 3 lớp import trước, rồi
chia số còn lại cho 2 lớp không phụ thuộc họ. Kết quả tất định, đã có test.

## 5. Manifest (tóm tắt; chi tiết đầy đủ trong JSON evaluator-only)

| Sample | Lớp | Họ | Tham chiếu liên quan (ví dụ) | Chỉ số entry | Cần retrieval | Có câu trả lời dứt khoát? |
|---|---|---|---|---|---|---|
| 0001 | INITIAL_EVIDENCE_SUFFICIENT | — | pe_header/format/prediction | — | Không | Có |
| 0002 | NOT_STATIC_ANSWERABLE | — | — | — | Không | Không (phải nêu giới hạn) |
| 0003 | REACHABLE_BY_BOUNDED_RETRIEVAL | NETWORK | WS2_32 ordinals | 30–33 (62–66 ngoài tầm) | **Có** | Sự hiện diện: có, nếu đọc đúng trang |
| 0004 | INITIAL_EVIDENCE_SUFFICIENT | — | — | — | Không | Có |
| 0005 | IN_INITIAL_TOOL_PROJECTION | FILE | KERNEL32!WriteFile, CreateFileW | 2, 47, 49… | Không | Sự hiện diện: có; danh sách đầy đủ: không (113 > 64) |
| 0006 | NOT_STATIC_ANSWERABLE | — | — | — | Không | Không |
| 0007 | NOT_STATIC_ANSWERABLE | — | — | — | Không | Không |
| 0008 | INACCESSIBLE_UNDER_LIMITS | PROCESS | TerminateProcess | 192 | Không | Không (phải giới hạn phạm vi) |
| 0009 | INITIAL_EVIDENCE_SUFFICIENT | — | — | — | Không | Có |
| 0010 | INACCESSIBLE_UNDER_LIMITS | NETWORK | WS2_32!FreeAddrInfoW… | 122+ | Không | Không |
| 0011 | INACCESSIBLE_UNDER_LIMITS | NETWORK | WINHTTP!WinHttpConnect… | 229+ | Không | Không |
| 0012 | REACHABLE_BY_BOUNDED_RETRIEVAL | FILE | msvcrt!fopen | 21 | **Có** | Có, nếu đọc trang 16–31 |
| 0013 | REACHABLE_BY_BOUNDED_RETRIEVAL | PROCESS | KERNEL32!TerminateProcess | 40 | **Có** | Có, nếu đọc tới trang 32–47 |
| 0014 | IN_INITIAL_TOOL_PROJECTION | FILE | KERNEL32!CreateFileW, ReadFile | 1, 30 | Không | Sự hiện diện: có |
| 0015 | INITIAL_EVIDENCE_SUFFICIENT | — | — | — | Không | Có |
| 0016 | REACHABLE_BY_BOUNDED_RETRIEVAL | FILE | msvcrt!_open, fopen | 32, 40 (63, 80+ khó hoặc ngoài tầm) | **Có** | Có, nếu đọc tới trang 32–47 |
| 0017 | INACCESSIBLE_UNDER_LIMITS | PROCESS | TerminateProcess | 91 | Không | Không |
| 0018 | REACHABLE_BY_BOUNDED_RETRIEVAL | FILE | WriteFile | 47 | **Có** | Có, nếu đọc trang 32–47 (cần 2 lần đọc) |
| 0019 | REACHABLE_BY_BOUNDED_RETRIEVAL | PROCESS | TerminateProcess, OpenProcess | 43 (89 ngoài tầm) | **Có** | Có, nếu đọc tới trang 32–47 |
| 0020 | NOT_STATIC_ANSWERABLE | — | — | — | Không | Không |

Với mỗi case, JSON còn ghi:

- `program_identity_EVALUATOR_ONLY`
- `question_text`
- `reference_EVALUATOR_ONLY`
- `initial_sufficient`, `tool_useful`, `retrieval_necessary`, `definitive_possible`
- `abstention`: hành vi từ chối kết luận được chấp nhận

## 6. Giới hạn

- n=20, toàn benign (tiện ích Windows có chữ ký). Mỗi lớp chỉ 2–6 case, nên kết quả chỉ mang
  tính **mô tả**, CI rộng. Không suy rộng sang malware, không tuyên bố cải thiện detection.
- Lớp "trong projection" chỉ có 2 case. Không thể kết luận riêng cho lớp này.
- Một số case PROCESS chỉ dựa trên `TerminateProcess`, một tín hiệu năng lực yếu.
- Phân lớp dựa trên vị trí entry liên quan **đầu tiên**. Các entry khác của cùng case có thể
  nằm ở lớp khác (đã ghi trong manifest).
