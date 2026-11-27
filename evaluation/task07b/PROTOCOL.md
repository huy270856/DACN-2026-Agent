# TASK 07B — PROTOCOL (frozen trước live run S8)

| Hạng mục | Giá trị |
|---|---|
| Loại đánh giá | `DEV_EVALUATION_FRESH_COHORT`, **không** phải confirmatory của dự án (n = 20, chỉ benign). `confirmatory: NOT_RUN` |
| Track | `RAW_PE_E2E` (PE benign hệ thống có chữ ký Microsoft; staged copy; không thực thi PE) |
| Planner | `LOCAL_QWEN`: `qwen3.5:4b` Q4_K_M, digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`, Ollama **0.40.16 headless** (`ollama serve`, loopback). Lệch version hoặc digest → run bị chặn (`QWEN_DRIFT`) |
| Metric | Tất định, `task07b-metrics-v1` (`evaluation/task07b/metrics.py`). **Không** phải semantic grading. Không Judge |
| Nguồn thiết kế | `research/agent_architecture_review/PLAN_TASK07B.md` rev 2, quyết định G0 trong `EVALUATION_LOG.md` |
| Authorization S8 | `DACN_OWNER_07B_EVAL_GO` (Owner, 2026-11-27; khác chuỗi DEV). Chỉ dùng sau commit freeze |

## 1. Cohort (D5)

- Manifest: `evaluation/task07b/results/cohort/cases_v2_EVALUATOR_ONLY.json` (canonical digest
  `f984cc7f38bdb150c0ea63380e06bbd3bf636a37dab4f34e92c0ef6da345673a`, allocation
  `task07b-allocation-v2`). `cases_v1_EVALUATOR_ONLY.json` (digest `141726dd…`, 8/8 ≥ 48) bị
  **thay thế trước mọi inference** theo quyết định Owner (cân lại 5 ≥ 48 + 3 < 48); giữ nguyên
  file, không dùng để chạy. Audit:
  `results/cohort/audit_v1_EVALUATOR_ONLY.json` (canonical digest
  `344fe168f45db6679fa446f6600452293e7c29d379aee1e6ed544ba15965146e`). Cả hai được ghi write-once
  **trước** mọi inference trên cohort này.
- Module `evaluation/task07b/cohort_audit.py` (`task07b-cohort-audit-v1`, seed `task07b-cohort-v1`).
  - Loại trừ tường minh cả tên lẫn SHA của: 05D, 06B, 06B-J (CANDIDATES_V1, holdout, DEV smoke,
    calibration), 07A DEV/test PE, mọi tên exe có đường dẫn System32 và mọi SHA xuất hiện trong file
    tracked.
  - Bỏ near-duplicate (Jaccard ≥ 0.85).
  - Xét 132 exe để có pool 120 (tất cả đều đã ký Microsoft hợp lệ).
- Lớp (accessibility của v4, bảng đầy đủ, không giới hạn 64):

| Lớp | Số case | Ghi chú |
|---|---|---|
| RELEVANT_PRESENT | 8 | **5** case có entry liên quan đầu tiên ở index ≥ 48 (ngoài tầm v3.4) và **3** case < 48 (trong tầm 0–47 của BASE). Họ: REGISTRY 2, FILE 2, PROCESS 2, SERVICE 1, NETWORK 1 |
| RELEVANT_ABSENT | 4 | Bảng đầy đủ không có API của họ được hỏi (SERVICE, FILE, NETWORK, REGISTRY) |
| NOT_STATIC_ANSWERABLE | 4 | Câu hỏi về hành vi mạng khi chạy |
| INITIAL_EVIDENCE_SUFFICIENT | 4 | Loại PE, kiến trúc, output detector |

- Hai tầng, ghi trước. Tầng **≥ 48** (5 case): BASE (v3.4 chỉ thấy tối đa entry 0–47) gần như
  không thể thấy entry liên quan theo thiết kế; V4 so với BASE ở tầng này chủ yếu đo giới hạn truy
  cập của v3.4. Tầng **< 48** (3 case): evidence nằm trong tầm của cả hai engine; tầng này kiểm xem
  V4 có **kém** v3.4 không (Owner, 2026-11-27). M1/M1b luôn báo **tách riêng theo hai tầng** ngoài
  tổng 8. So sánh **V4 với V4_NOQ** là phép đo đóng góp riêng của retrieval có chỉ mục.
- Payload đo trước: lớn nhất 458 entry, khoảng 25 KB; không case nào truncated.
- Câu hỏi: dùng template và lexicon v2 của 06B-J (họ FILE/NETWORK/PROCESS/REGISTRY/SERVICE, khớp tên
  chính xác). `relevant_entries` lấy từ full parse; là evaluator-only, không bao giờ vào prompt.

## 2. Arm và cấu hình (`evaluation/task07b/harness.py`, ghi trong `arm.json` của từng run)

| Arm | Engine | think | temp | num_predict | num_ctx | max_iterations / turns | wall_clock_s | max_tokens | Retrieval |
|---|---|---|---|---|---|---|---|---|---|
| BASE | v3.4 (`workflow_v34`, = 07A V0) | off | 0.1 | 2048 | 8192 | 5 | 180 | 100000 | 1 analyzer `pe_imports_detail` (64 entry), ≤ 2 READ offset |
| V4_NOQ | v4 (`investigation-v4.0`) | off | 0.1 | 3072 | 12288 | 8 turns (lượt cuối chỉ final) | 420 | 160000 | `pe_imports_table`; READ_TABLE theo offset (≤ 6); không index, không query |
| V4 | v4 | off | 0.1 | 3072 | 12288 | 8 turns | 420 | 160000 | `pe_imports_table`; LIST_IMPORT_INDEX + QUERY_IMPORTS{DLL, SYMBOL_PREFIX} (≤ 6) |

- Seed: 42 và 7 cho mỗi arm, tổng **120 run** (3 arm × 2 seed × 20 case).
- Mọi arm: Controller → D4 (default-deny; allowlist tường minh) → D5/D6 → D7 → D8 → D9; không thực
  thi PE; không native thinking; không REQUEST_MORE terminal ở v4.
- Recommendation không đổi chính sách (D2). V4 dùng ánh xạ `detector_relation` sang
  `safe_recommendation`.
- Confound đã biết: V4 và V4_NOQ khác BASE đồng thời ở contract, workflow, analyzer, num_ctx,
  num_predict và số lượt. V4 so với BASE là so sánh **gói tổng**.

## 3. Metric (`task07b-metrics-v1`)

Báo tử số/mẫu số theo từng (arm, seed) và theo lớp. Run không có final, lỗi hạ tầng, truncation và
`HARNESS_EXCEPTION`, `INFRA_INTERRUPTED`, `TARGET_DRIFT` và cả slot **không có trace** (`MISSING_TRACE`,
ví dụ run bị dừng giữa chừng) **luôn nằm trong mẫu số**, và tính là **không đạt** cho mọi metric "tốt"
(M1b, M8, M9, M10). Mẫu số lấy từ `cohort_aliases` của `arm.json`, không phải từ số trace có trên đĩa.

| Mã | Định nghĩa | Mẫu số |
|---|---|---|
| M1 | Entry liên quan từng hiển thị cho model (BASE: evidence imports trong prompt; V4: `viewed_literals`) | RELEVANT_PRESENT (8) |
| M1b | Final trích entry liên quan (BASE: `resolved_import_refs`; V4: `resolved_sources`) | RELEVANT_PRESENT (8) |
| M1/M1b beyond_v3 | Như trên, chỉ tính case có entry liên quan đầu tiên ở index ≥ 48 | 5 |
| M1/M1b within_v3 | Như trên, chỉ tính case có entry liên quan đầu tiên ở index < 48 | 3 |
| M8 | Có ít nhất một QUERY_IMPORTS trả về entry liên quan, kèm số thứ tự query đầu tiên trúng. **Chỉ V4.** V4_NOQ có chỉ số riêng `M8_read_hit_reference` (hit từ READ_TABLE), chỉ để tham khảo, **không** so như M8 | RELEVANT_PRESENT |
| M2 | Có đề xuất analyzer (TOOL_CALL hoặc RUN_ANALYZER) | INITIAL_SUFFICIENT + NOT_STATIC (8); thêm chỉ số riêng cho INITIAL_SUFFICIENT (4) |
| M4 | Absence screen (`RULE_SCREEN_CANDIDATE`): regex M4 của 07A (`ABSENCE_RE`, `LIMITATION_RE`, `SCOPE_RE`) áp **trực tiếp trên văn bản final**, như nhau cho BASE, V4_NOQ và V4. Phân SCOPED/UNSCOPED. Developer review rà tay câu nguyên văn, áp như nhau cho 3 arm, ghi riêng | run có final |
| M5 | Structural self-corroboration. BASE: flag `prediction_used_as_own_corroboration`. V4: bằng 0 **do cấu trúc** (detector không có handle). Báo là structural, **không** so như cải thiện hành vi | run có final |
| M9 | NOT_STATIC → `NOT_STATICALLY_ANSWERABLE` hoặc `PARTIALLY_ANSWERED`; INITIAL_SUFFICIENT → `ANSWERED` và không gọi analyzer. Chỉ v4 (BASE: NOT_APPLICABLE) | NOT_STATIC + INITIAL_SUFFICIENT (8) |
| M6 | Số lần gọi LLM, latency mean/median, prompt/output token, prompt lớn nhất | tất cả |
| M7 | Status; truncation (`done_reason=length` và cả lượt PlannerError có `error_payload` hoặc "empty content"); tràn context (≥ 0.95 × num_ctx); lỗi hạ tầng; validation error; isolation | tất cả |
| M10 | Final hợp lệ | 20 |

**M4 độc lập với verifier v4 (Planner, 2026-11-27).** M4 **không** dùng flag hay quy tắc miễn trừ
coverage của verifier v4, nên V4 không được lợi từ chính logic của nó. Flag của verifier (gồm
`absence_beyond_coverage_suspected`) chỉ được báo cáo riêng, như một chỉ số mô tả.

## 4. Nhiễu và quy tắc hiệu ứng

- Nhiễu của một arm = |Δ tử số| giữa seed 42 và seed 7 của **chính arm đó**, theo từng metric.
- Một hiệu ứng "X hơn Y" chỉ được tính khi:
  - nó xuất hiện ở **cả hai seed** (X_s42 so với Y_s42 **và** X_s7 so với Y_s7);
  - và ở mỗi seed, |Δ| **lớn hơn** max(nhiễu X, nhiễu Y) của metric đó.
- n nhỏ, nên đây là quy tắc ưu tiên công việc, **không** phải kiểm định thống kê. Không phân biệt
  được với nhiễu thì ghi **INCONCLUSIVE**.

## 5. Bảng quyết định (ghi trước; PLAN §4.5)

| Quan sát (cả hai seed, vượt nhiễu) | Diễn giải | Bước tiếp theo |
|---|---|---|
| V4 vượt BASE ở M1b và M8; M4-UNSCOPED không tăng; M10 ≥ BASE; latency ≤ 3× | Lát cắt 1 có tác dụng | TASK 07C: investigation state; `FEATURE_RECORD_REPLAY` trên EMBER (malicious, FP/FN) |
| V4 **kém** BASE ở M1b tầng < 48 (cả hai seed, vượt nhiễu) | V4 làm hỏng trường hợp evidence nằm trong tầm của v3.4 | Không mở rộng V4 trước khi tìm nguyên nhân (contract/projector/turn budget) ở 07C |
| V4 vượt V4_NOQ ở M1b | Retrieval có chỉ mục đóng góp riêng | Giữ query service; mở rộng sang facet khác ở 07C |
| V4 ≈ V4_NOQ, cả hai vượt BASE | Lợi ích đến từ contract, workflow và bảng đầy đủ, không phải từ query | 07C ưu tiên state/kế hoạch; xem lại có giữ query không |
| M8 cao nhưng M1b thấp | Model tìm được entry nhưng không dùng | Xem lại contract final/projector; cân nhắc E7 (9B) |
| M8 thấp | Model không biết hỏi gì (thiếu kiến thức miền) | 07C: capability tag như **ablation**, hoặc 9B |
| M2 hoặc M9 không cải thiện | Quyết định gọi tool vẫn phản xạ | 07C: investigation state hoặc bước kế hoạch rõ ràng |
| Truncation > 2 run hoặc tràn context ở một arm | Arm đó không diễn giải được | PARTIAL; **không** chạy lại để cứu |

"V4 vượt BASE ở M8" không định nghĩa được, vì BASE không có M8. Dòng 1 sẽ dùng M8 của V4 so với
hit theo READ của V4_NOQ và BASE (nếu có), kèm giải thích. M2 và M9 so V4 với V4_NOQ (cùng contract)
và M2 với BASE.

## 6. Quy tắc dừng và vận hành (S8)

- Mỗi run chạy **đúng một lần**, write-once (`runner.write_new`). Không rerun ca lỗi, không xóa run,
  không thêm seed. Lỗi hạ tầng, timeout, validation, truncation đều tính vào mẫu số.
- **Lỗi theo case, ghi trace và đi tiếp** (không dừng arm):
  - lỗi model, validation, truncation, query, lỗi Ollama trong lúc inference (`HARNESS_EXCEPTION`
    hoặc `failure`);
  - CaseState đã đổi mà không có trace → ghi trace `INFRA_INTERRUPTED`
    (`STATE_CHANGED_WITHOUT_SAVED_TRACE_NO_RETRY`);
  - file staged đổi → ghi trace `TARGET_DRIFT`.
  Các trace này không bao giờ được chạy lại.
- **Lỗi làm dừng toàn bộ S8** (script `run_s8.ps1` throw, **không** chạy các arm sau):
  - drift của nguồn Agent/v4 (`V4_SOURCES`), harness, `metrics.py`, `cohort_audit.py`, `arm.json`,
    model LightGBM;
  - Qwen sai digest/version so với hằng số PROTOCOL (`EXPECTED_QWEN` ở cả prepare lẫn run);
  - Ollama không phản hồi **trước khi bắt đầu** một case. Case đó chưa bắt đầu nên không có trace.
  Khi bị dừng, Owner báo Planner. Chạy lại script **sau khi** sự cố hạ tầng được khắc phục sẽ tiếp
  tục đúng chỗ: thư mục đã có `arm.json` không bị prepare lại, case đã có trace bị bỏ qua. Không xóa
  hay prepare lại thư mục nào. Mọi lần dừng ghi vào `EVALUATION_LOG.md`.
- Guard của `run_s8.ps1`: tham số bắt buộc `-FreezeCommit` phải bằng `HEAD`; tracked tree sạch
  (`git status --porcelain --untracked-files=no` rỗng); Ollama 0.40.16; digest `qwen3.5:4b` bằng
  digest PROTOCOL. Harness cũng từ chối prepare kind `DEV_EVALUATION_FRESH_COHORT` khi tracked tree
  bẩn, và ghi `git.head` vào `arm.json`.
- Owner chạy S8 trong cửa sổ PowerShell **riêng ngoài session** (D7), với Ollama headless 0.40.16.
  Session Developer chỉ theo dõi artifact:
  `powershell -ExecutionPolicy Bypass -File evaluation\task07b\run_s8.ps1 -FreezeCommit <SHA freeze>`
  (authorization mặc định `DACN_OWNER_07B_EVAL_GO`).
- Thứ tự: BASE s42, V4_NOQ s42, V4 s42, BASE s7, V4_NOQ s7, V4 s7.

## 7. Thay đổi đã chốt từ DEV trước freeze

Xem `EVALUATION_LOG.md` S5. Các thay đổi đều chung cho mọi case, không theo họ API:

- hint cố định cho lỗi query;
- hướng dẫn SYMBOL_PREFIX, next_page, không lặp query;
- query 0 match không có handle để trích;
- quy tắc coverage của verifier: chỉ miễn flag câu absence nằm **trong** phạm vi một query hoặc DLL
  đã xem hết, có từ chỉ phạm vi, và không khái quát thành cả một họ capability.

G3 PASS (`results/g3/V4_s42_g3_r1`).
