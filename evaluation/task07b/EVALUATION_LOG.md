# TASK 07B — EVALUATION_LOG

Nhật ký append-only cho TASK 07B (investigation v4, lát cắt 1). Không sửa các mục cũ.

## 2026-11-27 — G0: quyết định của owner

Nguồn: tin nhắn giao việc từ session `plan` (Planner) ngày 2026-11-27, nêu Owner đã duyệt
`research/agent_architecture_review/PLAN_TASK07B.md` rev 2. Ghi nguyên văn:

> - D1: tạo branch feat/task07b-investigation-v4 từ 926f3a5. Chỉ commit local; KHÔNG push và KHÔNG merge cho tới khi xong toàn bộ TASK 07. Commit đầu tiên gồm PLAN_TASK07B.md. Không commit .claude/ và docs/TASK.md, HANDOFF.md, REVIEW.md, ARCHITECTURE.md: đó là file workflow của Owner.
> - D2: giữ chính sách recommendation hiện có qua ánh xạ detector_relation → safe_recommendation; recommendation-policy-v4.0 dời sang 07C.
> - D3: tool mới static.pe_imports_table 0.1.0 với schema D0 pe-imports-table-input-v1/output-v1, allowlist tường minh. Giữ nguyên static.pe_imports_detail và schema v1.
> - D4: ordinal_table.json sinh một lần, offline, từ export table của ws2_32.dll (parse read-only), commit kèm provenance.
> - D5: cohort mới gồm 20 PE benign có chữ ký Microsoft, dựng bằng cohort_audit.py mới. Danh sách loại trừ tường minh: 05D, 06B-J, 07A. Cohort 06B-J chỉ dùng làm DEV.
> - D6: chưa có chuỗi authorization. Khi tới S8 thì dừng lại hỏi Owner.
> - D7: Ollama chạy headless, runner chạy trong cửa sổ PowerShell riêng ngoài session. Tới S8, đưa Owner lệnh để Owner tự chạy; session chỉ theo dõi artifact.

Ràng buộc kèm theo (nguyên văn):

> - Không sửa investigation_v3/*, evaluation/task06a|06b_j|07a/*, agent/config.py hay artifact frozen.
> - Thay đổi ở dacn/investigation.py và agent/planner.py phải additive, mặc định byte-identical, có test.
> - Không dùng native thinking; field analysis đứng trước action ở mọi lượt.
> - PROTOCOL commit trước live run. Mỗi run chạy một lần; lỗi tính vào mẫu số.
> - Gate FAIL hoặc gặp tình huống ngoài plan: dừng lại, báo Planner (session plan) kèm phương án đề xuất. Không tự đổi thiết kế.

## 2026-11-27 — S0

- Branch `feat/task07b-investigation-v4` tạo từ `926f3a5`. Commit `c22c41b` chỉ chứa
  `PLAN_TASK07B.md`. `.claude/` và `docs/{TASK,HANDOFF,REVIEW,ARCHITECTURE}.md` để untracked.

## 2026-11-27 — S1: ordinal_table.json (D4)

- `python -m investigation_v4.build_ordinal_table` chạy **một lần** (script từ chối ghi đè).
  Nguồn: `C:\Windows\System32\ws2_32.dll`, sha256 `d4dbce9799d1b626…` (đầy đủ trong JSON), parse
  read-only bằng LIEF 0.15.1; OS build 26300.9974 (26H2). 196 ordinal có tên (không có export
  ordinal-only).
- Digest dùng để pin là **canonical JSON digest** (`d0.validate.digest`) =
  `646aa64ecd87299ce4c5643d08db00b6ae3b71c032fdcbc4c5d35c044b3519c2`, không phải byte-SHA của file,
  vì repo có `core.autocrlf=true` (byte của file đổi khi checkout). D5 vẫn pin byte-SHA của file
  lúc install như mọi pin khác.
- Limitation: bảng phản ánh build Windows của host; target có thể bind bản ws2_32 khác.
- Ghi chú hash: `MANIFEST_SHA256.json` ở gốc liệt kê file trong `d0/`, nhưng không code/test nào
  đọc nó; thêm schema mới ở S2 không đổi entry cũ.
