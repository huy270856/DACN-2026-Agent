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

## 2026-11-27 — S2: analyzer `static.pe_imports_table` 0.1.0

- Schema D0 mới `pe-imports-table-input-v1` (`max_entries` const 1024) và
  `pe-imports-table-output-v1` (mã hóa gọn `[lib_idx, symbol, ordinal, delay, resolved_symbol]`,
  library index theo **từng block khai báo** gồm cả block nằm ngoài phần trả về,
  `truncation_reason ∈ {null, MAX_ENTRIES, OUTPUT_BYTES}`).
- Adapter mới `investigation_v4/imports_table_adapter.py`; tool/validator
  `investigation_v4/imports_table_tool.py`; controller `investigation_v4/controller.py`
  (`V4Controller` + `ToolBinding`, không import TOOL_ID/FACET của v3).
- Hành vi biên (ghi trong `$comment` của schema): tối đa 1024 entry; nếu bản mã hóa gọn vượt
  `OUTPUT_BUDGET = 120000` byte thì adapter **tự giảm** số entry một cách tất định (binary search),
  đặt `truncation_reason = OUTPUT_BYTES` và thêm limitation. Spec `max_output_bytes = 131072`,
  `max_artifact_bytes = 262144`; trần chung của backend (262144) không đổi.
- Đo thực tế trên cohort DEV 06B-J (20 PE): lớn nhất 360 entry / 22 442 byte (sample_0011);
  không case nào truncated. Cohort mới sẽ đo lại ở S7.
- `dacn/investigation.py::build_detector_backend` thêm `include_imports_table=False` (additive;
  mặc định không đăng ký tool mới — có test). Allowlist D4 tường minh chỉ khi bật cờ.
- Test: `tests/test_task07b_imports_table.py` (27 test: adapter, mỗi luật D7, schema, E2E D1–D9 thật
  trên whoami.exe, default-deny, dedupe, tamper). Unit/integration, không có model.
- Full regression: `774 passed, 0 failed, 4 skipped` (+83 subtests).

## 2026-11-27 — S3: query service và projector v4

- `investigation_v4/query.py`: `list_import_index`, `query_imports{DLL|SYMBOL_PREFIX, page}`,
  `read_table` (chỉ cho V4_NOQ), `coverage`. Theo lưu ý của Planner sau S2: query theo DLL **gộp
  mọi block cùng tên** (imports + delay, so không phân biệt hoa thường), phân trang 16 trên danh
  sách đã gộp; `list_import_index` trả tổng theo DLL (kèm `blocks`, `has_delay_block`); coverage
  tính theo DLL đã gộp. SYMBOL_PREFIX: 3–64 ký tự `[A-Za-z0-9_?@$]`, so tiền tố literal trên
  `symbol` hoặc `resolved_symbol`; prefix rộng vẫn chỉ 16 entry/trang. Binding do trusted code
  điền; `expected_binding` sai case/revision/SHA bị reject.
- `investigation_v4/projector.py` + `config.py` (`V4Config`): handle E1..En / I<index>,
  `detector_context` không handle, bỏ nhiễu provenance, đếm facet bị bỏ, không cắt ngầm
  (`V4_CONTEXT_BUDGET`). V4_NOQ không thấy index hay coverage theo DLL (chỉ số entry đã xem).
- Chi tiết thực hiện: `viewed_imports` bỏ trường null/false (symbol XOR ordinal; `resolved_symbol`,
  `delay` chỉ khi có) để 96 entry tên dài (6 query × 16) vẫn vừa `max_context_chars = 16000`
  (đo: 13 267 ký tự).
- Test: `tests/test_task07b_query_projector.py` (18 test, có test DLL nằm ở cả hai block).
- Full regression: `792 passed, 0 failed, 4 skipped` (+83 subtests).

## 2026-11-27 — S4: contract, verifier, recommendation, workflow v4, sửa planner

- `investigation_v4/contract.py` (`investigation-v4.0`): `analysis` là property đầu tiên và
  required ở mọi nhánh action lẫn final; action RUN_ANALYZER / LIST_IMPORT_INDEX / QUERY_IMPORTS /
  READ_TABLE (chỉ V4_NOQ) / ANSWER; không có REQUEST_MORE_EVIDENCE; final theo câu trả lời
  (answer_status, answer, findings có `sources` là handle, evidence_needed, next_verification,
  detector_relation). LLM không chọn recommendation/alignment/supporting IDs. Theo lưu ý của Planner
  sau S3, system prompt nêu quy ước "thiếu symbol = import theo ordinal; thiếu delay = không
  delay-load; trường vắng không bao giờ nghĩa là không biết", có test.
- `verifier.py`: source không hiển thị, OBSERVED không source, AGREES/CONFLICTS không basis,
  absence vượt coverage (dùng lại regex M4 + LIMITATION_RE của 07A, import không sửa),
  entropy/xác suất. Chỉ resolve handle → literal, không sửa claim.
- `recommendation.py` (D2): ánh xạ detector_relation → alignment → `safe_recommendation` hiện có;
  flag hoặc không có final → MANUAL_REVIEW. Hệ quả đã biết: benign + NOT_INFORMATIVE → MANUAL_REVIEW.
- `workflow.py`: tool offer mọi lượt tới khi đã chạy; lượt cuối luôn chỉ có final
  (`FORCED_FINAL`); query trùng → `NO_INFORMATION_GAIN` (tốn budget); lỗi query/D4 DENY không
  terminal; ControllerReject (integrity) vẫn terminal như v3.4; một lần repair định dạng.
  `V4Planner` gửi đúng schema của lượt qua `OllamaPlanner(cfg, DecodingOptions)`.
- `agent/planner.py` (additive): `PlannerError(..., payload=...)`, `payload=None` mặc định; khi
  content rỗng, payload thô (`content`, `thinking`, `done_reason`, `eval_count`,
  `prompt_eval_count`) được gắn; `str(exc)` và type không đổi. Workflow v4 ghi vào
  `turn['error_payload']`. Test pin `e31ee31` (07A) và `test_reviewer_repair` (06A) vẫn pass.
- Ghi chú hash: `agent/planner.py` đổi nên `source_hashes` của 06B-J/07A đổi; không resume thư mục
  cũ nào.
- Test: `tests/test_task07b_workflow.py` (28 test: contract, verifier, bảng D2, payload planner,
  MOCK_LLM E2E qua D1–D9 thật). MOCK_LLM không phải bằng chứng hành vi.
- Full regression: `820 passed, 0 failed, 4 skipped` (+83 subtests).

## 2026-11-27 — Quyết định owner (qua Planner): authorization DEV và Ollama

- Chuỗi authorization cho S5 (DEV_DEBUG) và S6 (smoke G3), Owner đã duyệt:
  `DACN_OWNER_07B_DEV_DEBUG_2026-11-27`. **Chỉ** dùng cho DEV_DEBUG và smoke G3. S8 (run frozen)
  dùng chuỗi khác, Planner sẽ hỏi Owner khi tới bước đó.
- Owner tự bật Ollama headless ngoài session; session Developer **không** khởi động Ollama và chờ
  xác nhận `127.0.0.1:11434` chạy 0.40.16.
- Xử lý rủi ro `pattern`/`multipleOf` trong schema decode: Ollama bỏ qua → ghi log (parse sau
  decode vẫn validate đủ schema); Ollama báo lỗi/làm sai output → dừng, báo Planner kèm raw error.
  Phương án "bỏ keyword không hỗ trợ khỏi schema gửi Ollama, giữ schema validate" **chưa** làm,
  chờ Owner duyệt.
- Thứ tự: viết `cohort_audit.py` + test trước; chỉ chạy audit chọn cohort sau khi G3 PASS.

## 2026-11-27 — S5: DEV_DEBUG (cohort 06B-J, chỉ để debug; không dùng để kết luận)

- Ollama: Planner xác nhận chỉ còn `ollama.exe serve` headless (PID 16860, con của PowerShell do
  Owner mở), app desktop đã tắt. `freeze.json` của mọi thư mục DEV ghi `AVAILABLE`, 0.40.16,
  digest `d8b0f5e9…`. Session không khởi động/dừng Ollama.
- Authorization: `DACN_OWNER_07B_DEV_DEBUG_2026-11-27`.
- **r1** (`results/dev_debug/V4_s42_r1`, 1 case sample_0012):
  - Ollama **chấp nhận** schema có `pattern` (handle) và `multipleOf` (offset): không lỗi, không
    output sai. Ghi lại theo hướng dẫn của Planner.
  - `analysis` đứng đầu 8/8 lượt; prompt lớn nhất 2 826 token (≈ 0.23 × 12 288).
  - Hành vi: hỏi `kernel32.dll` (không có trong index; file dùng api-set), lặp lại sau lỗi; không
    dùng SYMBOL_PREFIX, không lật `next_page`; kết thúc FORCED_FINAL.
- **Chỉnh DEV 1** (chung, không theo case/họ API): last_result của lỗi query kèm `hint` cố định
  theo mã lỗi (`QUERY_HINTS`); system prompt nói rõ DLL phải đúng tên trong import_index,
  SYMBOL_PREFIX tìm trên mọi DLL, dùng `next_page`, không lặp query đã có.
- **r2** (`V4_s42_r2`, 6 case 0001/0002/0003/0010/0012/0013): model dùng SYMBOL_PREFIX và lật
  trang; 0010 (entry liên quan ở index 122, ngoài tầm v3.4) được thấy và trích. Hai vấn đề:
  - model trích handle chưa hiển thị (I0..I3) cho query 0 match → verifier flag đúng
    (`source_not_visible`);
  - câu "không có X" sau một SYMBOL_PREFIX 0 match (đã phủ toàn bảng) vẫn bị flag
    `absence_beyond_coverage_suspected` vì verifier chỉ xét "đã xem toàn bảng".
  - 0001: model ghi `CONFLICTS` vì đọc sai score/threshold — lỗi suy luận, **không** chỉnh.
- **Chỉnh DEV 2**: prompt nói query 0 match không có handle để trích; verifier áp đúng spec §2.6
  ("coverage của DLL hoặc query liên quan"): câu absence được coi là trong coverage nếu nêu một DLL
  đã xem hết, hoặc một giá trị query mà mọi match đã xem (kể cả 0 match), trên bảng không
  truncated. Có test.
- **r3**: 20 case DEV × {V4, V4_NOQ} seed 42 (đang chạy).
- **r3** xong: 20 case DEV × {V4, V4_NOQ}, seed 42 (`results/dev_debug/{V4,V4_NOQ}_s42_r3`). Cơ chế ổn
  định: 40/40 có final, 0 lỗi hạ tầng, 0 validation/repair exhausted, `analysis` đứng đầu mọi lượt,
  prompt lớn nhất 5 042 token (< 0.8 × 12 288). Mô tả DEV (không kết luận): IN_INITIAL+REACHABLE
  thấy/trích entry liên quan V4 7/8, V4_NOQ 6/8; INACCESSIBLE thấy V4 3/4, V4_NOQ 1/4; V4 không gọi
  analyzer ở 4/4 INITIAL_SUFFICIENT. Ghi nhận: verifier flag `absence_claim_without_imports_source_suspected`
  ở INITIAL_SUFFICIENT khi model nói "không có thông tin imports" (rule screen; không chỉnh).
  Kết luận S5: hành vi đủ ổn định để thử G3.

## 2026-11-27 — S6: G3 smoke — PASS

- Case chọn **trước khi chạy**: `sample_0010` (06B-J DEV, INACCESSIBLE_UNDER_LIMITS, NETWORK; entry
  liên quan đầu tiên WS2_32.dll!#115 ở index 122, ngoài tầm v3.4). Thư mục `results/g3/V4_s42_g3_r1`,
  kind `DEV_SMOKE_G3`, authorization DEV.
- `g3_gate.json`: **PASS** — analyzer commit qua D9; query thấy entry liên quan; final hợp lệ và trích
  entry liên quan; không truncation; `analysis` đứng đầu mọi lượt (oneOf v4); prompt lớn nhất 3 051
  token (< 0.8 × 12 288); không tràn context; isolation PASS.
- `pattern` (handle) và `multipleOf` (offset) trong schema decode: Ollama 0.40.16 chấp nhận, không
  lỗi, không output sai (từ S5 r1 tới G3). Validate sau decode vẫn dùng đủ schema.
