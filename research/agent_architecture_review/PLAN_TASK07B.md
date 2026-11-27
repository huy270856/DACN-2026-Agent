# PLAN — TASK 07B: Investigation v4, lát cắt 1 (contract theo câu trả lời + retrieval có chỉ mục)

> Plan này dành cho một session Claude Code **khác** thực hiện. Đọc theo thứ tự:
> 1. `CLAUDE.md`
> 2. `research/agent_architecture_review/REPORT.md`, các mục §1, §8 và §12
> 3. `evaluation/task07a/REPORT.md`
> 4. file này.
>
> Plan **chưa** được thực hiện. Base: commit `926f3a5`, branch `feat/task07a-agent-diagnostic-ablations`.
>
> **Revision 2 (2026-11-27).** Bản này đã cập nhật theo review khả thi của session `dev`
> (review chỉ đọc code). Thay đổi so với rev 1:
> - payload dùng mã hóa gọn, giới hạn 1024 entry;
> - dùng controller v4 riêng;
> - giữ nguyên chính sách recommendation hiện có (dời policy v4.0 sang 07C);
> - ordinal chỉ resolve cho ws2_32;
> - có module audit cohort mới, kèm ngưỡng phân tầng;
> - thêm arm ablation `V4_NOQ`;
> - `PlannerError` chỉ thêm attribute;
> - G3 kiểm cứng thứ tự `analysis`.
>
> `SYMBOL_PREFIX` được **giữ lại**, dù review đề xuất dời (lý do ở §2.3).

## 0. Vì sao chọn phạm vi này

Kết quả của TASK 07A (DEV_DIAGNOSTIC, metric tất định):

- **V3 oracle.** Khi entry liên quan đã hiển thị, model trích đúng 7/8, so với 2–3/8 ở V0. Nút
  thắt nằm ở **khâu thu thập evidence**, không phải ở năng lực model.
- **V2 analysis-first.** Model chịu đọc tiếp nhiều hơn: M3a tăng từ 1/6 lên 3–4/6 ở cả hai
  seed. Nhưng các lần đọc vẫn **tuần tự** (offset 16, rồi 32), tức là không có định hướng.
- **Self-corroboration** (prediction nằm trong supporting) vẫn ở mức 85–100% ở **mọi** biến thể,
  tức là lỗi do contract.
- `REQUEST_MORE_EVIDENCE` là trạng thái terminal, làm mất khoảng 3/20 final mỗi seed.
- **V1 native thinking:** PARTIAL. Thinking chạy mất kiểm soát ở 3/7 case, và latency tăng khoảng
  10 lần. **Không dùng** native thinking.

**P1 (contract mới) là điều kiện tiên quyết kỹ thuật**, không phải lựa chọn. Contract v3.4 giới
hạn cứng `import_refs.entry_index` trong khoảng 0–63 (`final_v34._REF`). Một analyzer commit bảng
import đầy đủ thì sẽ có entry từ chỉ số 64 trở lên, và v3.4 không trích dẫn được các entry đó.

**Trong phạm vi 07B:**

- (1) contract `investigation-v4.0`, lấy câu trả lời làm trung tâm, dùng handle ngắn,
  `detector_context` không cho trích dẫn;
- (2) field `analysis` đứng trước `action` ở mọi lượt;
- (3) analyzer bảng import đầy đủ, kèm mục lục DLL và resolve ordinal;
- (4) `list_import_index` và `query_imports`;
- (5) không có trạng thái kết thúc kiểu "xin thêm evidence"; tool được offer ở mọi lượt; có một
  lượt final bắt buộc khi hết budget;
- (6) một dòng coverage do trusted code tính;
- (7) sửa lỗi mất raw thinking và raw response khi planner lỗi.

**Để sang 07C, không làm trong 07B:**

- investigation state do model tự viết (giả thuyết, câu hỏi con);
- capability tag;
- `FEATURE_RECORD_REPLAY` trên EMBER;
- so sánh model 4B với 9B;
- semantic Judge;
- tích hợp vào `python -m dacn`;
- sửa README top-level.

## 1. Gate G0: quyết định của owner (phải có trước khi code)

Hỏi owner, rồi ghi câu trả lời vào `evaluation/task07b/EVALUATION_LOG.md`.

| # | Quyết định | Đề xuất |
|---|---|---|
| D1 | Tạo branch `feat/task07b-investigation-v4` từ `926f3a5`. Commit local; **không push** cho tới khi xong toàn bộ TASK 07 (quy ước của owner) | Đồng ý |
| D2 | **Recommendation: không đổi chính sách trong 07B.** Tái sử dụng `evaluation.task06a.consistency.safe_recommendation` qua một ánh xạ tất định: `detector_relation` AGREES → CONSISTENT, CONFLICTS → CONFLICT, NOT_INFORMATIVE → INSUFFICIENT_EVIDENCE. Có flag verifier hoặc không có final thì MANUAL_REVIEW. Hệ quả: benign cộng NOT_INFORMATIVE vẫn ra MANUAL_REVIEW, giống v3.4. `recommendation-policy-v4.0` dời sang 07C | Đồng ý. Lý do: recommendation không phải câu hỏi nghiên cứu của 07B, và giữ nguyên chính sách thì M7 so được với BASE |
| D3 | Thêm contract D0 mới: `pe-imports-table-input-v1` / `pe-imports-table-output-v1`. Thêm tool mới `static.pe_imports_table` 0.1.0 (provider mới), allowlist **tường minh** trong backend v4. Analyzer v0.1 `static.pe_imports_detail` và schema v1 **giữ nguyên** cho baseline v3.x | Đồng ý |
| D4 | Bảng resolve ordinal: sinh **một lần, offline**, bằng script trusted. Script parse read-only bảng export của **chỉ `ws2_32.dll`** trong `C:\Windows\System32`; wsock32/oleaut32 dời sang 07C nếu cần. Commit JSON kèm provenance (SHA-256 của DLL nguồn, OS build, version script). Bảng phụ thuộc vào Windows build, nên ghi điều này thành limitation. Analyzer chỉ đọc JSON đã pin, **không** đọc file nào khác | Đồng ý |
| D5 | **Cohort đánh giá mới:** 20 PE benign có chữ ký Microsoft, lấy từ máy local. Dùng **module audit mới** `evaluation/task07b/cohort_audit.py`, có `AUDIT_VERSION` riêng; wrap hoặc copy logic của `task06b_j.holdout_audit`, vì module đó đã frozen và mã hóa access model v3.4. Danh sách loại trừ phải **tường minh**: SHA **và** tên chương trình của 05D, 06B-J (22 `CANDIDATES_V1`, DEV, calibration, holdout) và DEV của 07A (tracert, findstr, whoami, where…). Không dựa vào việc `tracked_sha_set()` tình cờ bắt được. Audit một pool khoảng 80–120 exe rồi mới phân tầng (§4.3). Cohort 06B-J cũ chỉ dùng cho **DEV** của 07B | Đồng ý |
| D6 | Chuỗi authorization cho live run | Owner cung cấp |
| D7 | Ollama chạy **headless** (`ollama serve`) và runner chạy trong cửa sổ PowerShell **độc lập với session Claude**. Owner tắt auto-update của ứng dụng desktop (đang có bản 0.40.18 chờ cài) | Owner tự làm |

## 2. Kiến trúc v4, lát cắt 1

### 2.1 Module

- **Package mới `investigation_v4/`** (opt-in, chưa đưa vào CLI):
  - `contract.py`
  - `projector.py`
  - `query.py`
  - `verifier.py`
  - `recommendation.py` (chỉ chứa ánh xạ D2 sang `safe_recommendation`)
  - `controller.py`
  - `workflow.py`
  - `imports_table_tool.py`
  - `imports_table_adapter.py`
  - `ordinal_table.json`
- **`controller.py`:** controller v4 riêng, subclass `agent.controller.Controller`.
  - Nhận danh sách `(tool_id, facet, arguments)` từ cấu hình trusted.
  - **Không** import `TOOL_ID`/`FACET` của v3.
  - Lý do: `investigation_v3/workflow.py:28-46` hardcode các giá trị này trong cả `__init__` lẫn
    `available_tools`.
  - Controller này dùng các thành phần private `_seen_toolcalls`, `_denied_tools`,
    `_toolcall_key`, `_build_toolcall` của Controller. Phải có test default-deny và test dedupe.
- **Tái sử dụng** (import, không copy):
  - `agent.controller.Controller`;
  - `investigation_v3.audit`;
  - `orchestrator.*`;
  - `case_manager`;
  - `d0.validate.digest`;
  - `evaluation.task05c.agent_replay._assert_no_ground_truth`.
- **Không sửa:**
  - `investigation_v3/*` (đã frozen);
  - `evaluation/task06a/*`, `task06b_j/*`, `task07a/*`;
  - `agent/config.py`. File này bị pin bởi guard `evaluation/task06a/tests/test_controls.py`.
    Mọi tham số mới để trong một dataclass config riêng của v4, cộng
    `agent.planner.DecodingOptions`.
- **Thay đổi additive cho phép:**
  - `dacn/investigation.py::build_detector_backend`: thêm tham số
    `include_imports_table=False`, mặc định không đổi hành vi;
  - `agent/planner.py`: §2.7;
  - `d0/schemas/`: thêm 2 schema mới.

### 2.2 Analyzer `static.pe_imports_table` (read-only, đi qua D1–D9)

- **Adapter:** dựa trên `investigation_v3/import_adapter.py`, nhưng là **file mới**.
  - Thứ tự entry giữ theo khai báo trong file (cả `imports` lẫn `delay_imports`).
  - `MAX_ENTRIES = 1024`. Cohort DEV lớn nhất mới có 360 entry. Vượt mức này thì
    `truncated=true` kèm limitation.
  - Giữ nguyên các budget cũ: 8 MiB, giới hạn độ dài tên, 4096 library.
- **Output `pe-imports-table-output-v1`, mã hóa gọn:**
  - `target_sha256`, `parser`, `total_entries`, `returned_entries`, `truncated`;
  - `libraries[]`: `{name, count, first_index, last_index}` (đây là library index);
  - `entries[]`: mảng `[lib_idx, symbol|null, ordinal|null, delay, resolved_symbol|null]`, trong
    đó `index` chính là vị trí trong mảng;
  - `resolution_source` ghi một lần ở cấp payload;
  - `ordinal_table_version`, `ordinal_table_sha256`, `limitations[]`.
- **Ước lượng kích thước** (review dev): khoảng 40–50 B/entry, tức 1024 entry ≈ 50 KB.
  - Đặt `limits.max_output_bytes = 131072` trong spec của tool mới. Mức này vẫn dưới trần chung
    `budget_caps` 262144 của backend.
  - Có test ở **biên**: 1024 entry với tên dài nhất cho phép phải vừa giới hạn, hoặc phải bị
    reject có kiểm soát (adapter tự giảm hay từ chối, ghi rõ hành vi trong schema).
  - Không nới giới hạn của tool khác hay trần chung.
- Query service và projector v4 **tuyệt đối không** chiếu toàn bộ bảng vào prompt.
- **Resolve ordinal:**
  - chỉ áp dụng khi `library`, sau khi so không phân biệt hoa thường, thuộc allowlist của
    `ordinal_table.json` (D4);
  - `resolved_symbol` là **annotation** của analyzer, có `resolution_source` và limitation "ordinal
    resolved from host export table version X; target may bind a different DLL version";
  - `symbol` gốc vẫn để `null`. Không ghi đè dữ liệu gốc.
- **Đo lại thực tế** trên cohort DEV và cohort mới: tổng số entry lớn nhất, kích thước payload.
  Lưu ý: dùng artifact **không** lách được trần, vì stdout bản thân đã là artifact `stdout.bin`
  bị giới hạn theo `min(max_output_bytes, max_artifact_bytes)` (`executor.py:287`).
- **D7 validator riêng** (tương tự `imports_tool.normalize`). Phải kiểm:
  - schema;
  - binding SHA;
  - count nhất quán (`returned == len(entries)`, `truncated == (total > returned)`);
  - `index` liên tục từ 0;
  - mỗi entry có đúng một trong `symbol` hoặc `ordinal`;
  - `library_index` khớp với `entries`;
  - `ordinal_table_sha256` khớp với bảng đã pin.
- **Spec:**
  - effects read-only: `executes_foreign_code=false`, `writes_filesystem=false`,
    `requires_human_approval=false`;
  - các pin gồm interpreter, script, `lief`, `ordinal_table.json`;
  - D4 allowlist **tường minh** identity mới.

### 2.3 Query service (đọc CaseState đã commit, không chạy analyzer)

- `list_import_index{}`: trả `library_index`, `total_entries`, `truncated`, và coverage hiện tại.
- `query_imports{by, value, page}`:
  - `by ∈ {DLL, SYMBOL_PREFIX}`.
  - `DLL`: so khớp chính xác (không phân biệt hoa thường) với một tên trong `library_index`.
  - `SYMBOL_PREFIX`: literal, dài 3–64 ký tự, `[A-Za-z0-9_?@$]`, so khớp tiền tố không phân biệt
    hoa thường trên `symbol` **hoặc** `resolved_symbol`. **Không dùng regex, không có wildcard.**
  - Prefix rỗng hoặc ngắn hơn 3 ký tự (ví dụ `"C"`) bị reject. Prefix hợp lệ nhưng rất rộng (ví
    dụ `"Get"`) vẫn chỉ trả **tối đa 16 entry mỗi trang**, không bao giờ trả cả bảng. Có test cho
    cả hai trường hợp.
  - `page` ≥ 0. Mỗi trang tối đa 16 entry. Trả về `next_page | null` và tổng số match.
- **Binding:** `case_id`, `revision`, `target_sha256`, `value_sha256` do **trusted code** điền từ
  state, model không phải chép. Evidence không đúng facet hoặc không ở trạng thái SUCCESS thì báo
  lỗi.
- Mọi entry trả về được gắn `UNTRUSTED_CONTENT`, và `new_evidence_created=false`.
- **Giữ `SYMBOL_PREFIX`** dù review đề xuất dời:
  - Nếu chỉ query theo DLL, một DLL như KERNEL32 có thể có hơn 100 entry. Khi đó model lại phải
    đọc theo trang bên trong DLL, tức quay về đúng kiểu đọc tuần tự mà 07A cho thấy là nút thắt.
  - Truy vấn theo tiền tố chính là phần question-driven của retrieval.
  - Chi phí nhỏ: lọc tiền tố literal trên dữ liệu đã có, cộng test.

### 2.4 Projector v4 (context gọn)

- Mỗi run, trusted code cấp **handle** cho từng evidence:
  - `E1…En` cho evidence không phải imports;
  - `I<index>` cho entry import, ví dụ `I123`;
  - trusted code tự giữ bảng ánh xạ handle → ID thật và ghi bảng này vào trace.
- Gói facts mỗi lượt gồm:
  - `question`;
  - `detector_context`: label, raw score, threshold, câu "raw score is NOT a probability; this is
    context, not evidence; it cannot be cited". **Không có handle**;
  - `evidence`: chỉ các trường cần cho câu hỏi. **Bỏ** model SHA, extractor, `full_detail_ref`,
    limitations lặp, `unknowns` có path/inode và `omitted_evidence_ids` thô. Thay bằng một dòng
    "N collector facets omitted as not relevant";
  - `viewed_imports`: các entry đã xem qua query;
  - `coverage` (trusted): mỗi DLL có `viewed/count`, danh sách query đã chạy, số query còn lại, số
    lượt còn lại;
  - `available_actions`.
- **Giới hạn ký tự.** Bỏ ở đâu thì ghi rõ là đã bỏ, không âm thầm cắt. Có test kiểm rằng không
  trường evaluator-only nào xuất hiện.

### 2.5 Contract `investigation-v4.0`

**Lượt chọn hành động.** JSON, trong đó `analysis` là **property đầu tiên** và nằm trong
`required` (theo V2 của 07A):

| `action` | Tham số | Ghi chú |
|---|---|---|
| `RUN_ANALYZER` | `tool` (const) | Offer ở **mọi lượt** cho tới khi đã chạy. Đi qua Controller.validate → D4 → D5/D6 → D7 → D8 → D9. Tối đa 1 lần |
| `LIST_IMPORT_INDEX` | — | Chỉ có sau khi analyzer đã commit |
| `QUERY_IMPORTS` | `by`, `value`, `page` | Tối đa 6 lần mỗi run. Query trùng hệt một query trước được ghi là `NO_INFORMATION_GAIN` (không lỗi, nhưng vẫn tốn budget) |
| `ANSWER` | — | Chuyển sang lượt final (giữ cách tách 2 stage đã có tác dụng ở v3.4) |
| `READ_TABLE` | `offset` (bội của 16) | **Chỉ có ở arm ablation `V4_NOQ`.** Arm này thay `LIST_IMPORT_INDEX` và `QUERY_IMPORTS` bằng cách đọc 16 entry theo offset trên bảng đầy đủ. Budget đọc bằng budget query (6 lần) |

**Lượt final:**

```json
{"analysis": "...",
 "answer_status": "ANSWERED | PARTIALLY_ANSWERED | NOT_STATICALLY_ANSWERABLE",
 "answer": "...",
 "findings": [{"kind": "OBSERVED|INFERENCE|LIMITATION", "text": "...", "sources": ["I47", "E2"]}],
 "evidence_needed": ["..."],
 "next_verification": ["..."],
 "detector_relation": {"value": "AGREES|CONFLICTS|NOT_INFORMATIVE", "basis_sources": ["I47"]}}
```

- Không còn `REQUEST_MORE_EVIDENCE`. Khi thiếu evidence, model trả lời `PARTIALLY_ANSWERED` hoặc
  `NOT_STATICALLY_ANSWERABLE`, kèm `evidence_needed`.
- LLM **không** chọn `recommendation`, `alignment` hay `supporting_evidence_ids`.
- Giới hạn: findings ≤ 6, sources ≤ 4 mỗi finding, text ≤ 400, answer ≤ 900, analysis ≤ 1500.
- **Repair:** tối đa 1 lần, chỉ dùng cho lỗi định dạng. Giữ ý định của v3.4.
- **Budget:**
  - 8 lượt;
  - lượt cuối luôn dành cho final: khi chỉ còn 1 lượt, chỉ offer lượt final;
  - nếu đã hết budget mà vẫn không có final hợp lệ, status = `INVESTIGATION_INCOMPLETE` và
    recommendation = MANUAL_REVIEW.

### 2.6 Verifier v4 (tất định) và recommendation (D2)

**Verifier** (ghi đủ các flag, không tự sửa claim):

- Mọi handle trong `sources` và `basis_sources` phải tồn tại và đã hiển thị cho model ở một lượt
  nào đó.
- `OBSERVED` phải có ít nhất 1 source.
- `detector_relation.basis_sources` không được rỗng khi value là `AGREES` hoặc `CONFLICTS`.
  Detector không có handle, nên **không thể** bị trích làm bằng chứng. Self-corroboration dạng
  structural bị loại bỏ từ chính cấu trúc contract.
- **Rule screen về absence:** câu phủ định capability (giữ regex của 07A M4 để so sánh được) mà
  coverage của DLL hoặc query liên quan **chưa** đầy đủ → flag
  `absence_beyond_coverage_suspected`.
- Giữ các flag của v3.4: entropy, xác suất, score.
- **Resolve:** đưa literal của entry (library!symbol, hoặc resolved ordinal) vào
  `trusted_metadata`, đặt cạnh lời của model. Chỉ resolve, **không** viết lại claim.

**Recommendation:** dùng ánh xạ D2 sang `safe_recommendation` hiện có, không đổi chính sách. Trong
trace ghi rõ chuỗi suy diễn (`derivation`). Trạng thái `NOT_EXECUTED_CONTAINMENT` giữ nguyên.

### 2.7 Sửa lỗi provenance ở `agent/planner.py` (additive)

- Khi Ollama trả content rỗng hoặc lỗi sau khi đã có payload, `PlannerError` mang theo payload
  thô (`thinking`, `content`, `done_reason`, `eval_count`, `prompt_eval_count`) dưới dạng
  **attribute mới** (ví dụ `exc.payload`).
- **Giữ nguyên type và `str(exc)`.** Hai file `tests/test_task07a_planner.py` và
  `evaluation/task06a/tests/test_reviewer_repair.py` so `(type name, str(exc))` với source đã pin.
- Workflow v4 ghi payload đó vào `turn['error_payload']`.
- Request mặc định **giữ nguyên byte-identical**, có test.
- Hash nguồn của 07A sẽ đổi. Artifact 07A không bị chạy lại, nên điều này chấp nhận được. Nếu có
  test nào của 07A so hash nguồn thì báo trung thực, **không** sửa artifact.

## 3. Test (MOCK_LLM và unit; không phải bằng chứng hành vi)

1. **Adapter.**
   - Fixture PE đã có trong `tests/fixtures`. **Không** tạo hay tải mẫu malicious.
   - Kiểm thứ tự entry, `library_index`, truncation ở 1024 (dùng PE giả lập trong bộ nhớ nếu có
     fixture sẵn; nếu không thì unit test trên hàm dựng index), resolve ordinal và giới hạn độ
     dài tên.
2. **D7 validator:** mỗi điều kiện ở §2.2 có ít nhất một test fail tương ứng.
3. **Query service:**
   - DLL so khớp hoa thường đúng; prefix hợp lệ và không hợp lệ (ký tự lạ, quá ngắn, quá dài);
   - phân trang; query trùng;
   - binding sai case, revision hoặc SHA bị reject;
   - không truy cập file.
4. **Projector:**
   - handle ổn định, ánh xạ ngược đúng;
   - `detector_context` không có handle;
   - không có trường evaluator-only;
   - đúng giới hạn ký tự.
5. **Contract:**
   - `analysis` đứng đầu mọi nhánh;
   - `RUN_ANALYZER` chỉ có khi chưa chạy;
   - lượt cuối chỉ có final;
   - không có `REQUEST_MORE_EVIDENCE`.
6. **Verifier và recommendation:**
   - source không hiển thị;
   - `OBSERVED` không có source;
   - `AGREES` mà basis rỗng;
   - absence vượt coverage;
   - bảng chính sách D2, đủ từng nhánh.
7. **E2E bằng MOCK_LLM qua D1–D9 thật** (dùng `tests/fixtures`):
   - RUN_ANALYZER → D4 ALLOW → D9 commit, rev tăng;
   - LIST_IMPORT_INDEX → QUERY_IMPORTS → ANSWER → final;
   - kiểm binding, `UNTRUSTED_CONTENT`, D4 DENY khi identity không có trong allowlist.
8. **Planner:**
   - request mặc định byte-identical;
   - `PlannerError` mang payload.
9. **Full regression** `python -m pytest -q`. Báo đủ passed/failed/skipped. Theo memory của 07A,
   máy này không có `.venv` và dùng Python 3.12 của hệ thống; kiểm lại trước khi chạy.

## 4. Đánh giá

### 4.1 DEV (phát triển, debug)

- Cohort 06B-J đã dùng, gồm 20 case và có `relevant_entries`.
- Dùng tự do để debug prompt và contract, không giới hạn số lần chạy. Mọi lần chạy có ghi artifact
  thì phải ghi vào thư mục mới, gắn nhãn `DEV_DEBUG`.
- **Không** dùng kết quả DEV để kết luận.

### 4.2 Gate G3: smoke

- Chạy 1 case DEV có entry liên quan ở chỉ số từ 64 trở lên (ví dụ case INACCESSIBLE của 06B-J).
- Đạt khi:
  - analyzer commit qua D9;
  - query thấy được entry đó;
  - final hợp lệ và trích được entry đó;
  - không truncation, không tràn context.
- **Kiểm cứng thêm:**
  - `analysis` là key đầu tiên ở **mọi** lượt, với oneOf v4. 07A mới chỉ kiểm cho oneOf v3.4;
  - `prompt_eval_count` dưới 0.8 × `num_ctx`;
  - có test giới hạn ký tự facts, kiểu `COMPACT_CONTEXT_BUDGET`.
- Nếu `analysis` không đứng đầu thì ghi **BLOCKED** và hỏi owner. Không tự đổi thiết kế.

### 4.3 Evaluation run (frozen, chạy một lần)

- **Cohort mới (D5):** 20 case. Câu hỏi theo `questions_v2` (cùng mẫu câu).
- **Phân lớp mới** cho v4 (không còn giới hạn 64):
  - `RELEVANT_PRESENT` (khoảng 8);
  - `RELEVANT_ABSENT` (khoảng 4): bảng đầy đủ không có API của họ đó; câu trả lời đúng là "không
    thấy trong bảng import đã khai báo, nhưng có thể resolve động";
  - `NOT_STATIC_ANSWERABLE` (4);
  - `INITIAL_EVIDENCE_SUFFICIENT` (4).
- `relevant_entries` lấy từ full parse, evaluator-only, theo lexicon v2. Manifest được ghi
  write-once **trước** inference.
- **Ngưỡng phân tầng, định nghĩa trước:**
  - trong `RELEVANT_PRESENT`, cần **≥ 5 case** có entry liên quan đầu tiên ở index ≥ 48. Đây là
    ranh giới của v3.4: BASE chỉ thấy được entry 0–47 (trang đầu 0–15 cộng tối đa 2 lần đọc 16
    entry), nên các case này phân biệt được BASE với V4;
  - nếu pool khoảng 80–120 exe không đủ: dùng số có được, ghi rõ trong PROTOCOL **trước** run,
    và không đổi pool sau khi đã thấy kết quả.
- **Arm (cùng cohort, cùng câu hỏi):**
  - **BASE:** v3.4 tool-enabled, cấu hình V0 của 07A;
  - **V4_NOQ:** v4 với contract, projector và workflow mới, nhưng chỉ đọc theo offset trên bảng
    đầy đủ (`READ_TABLE`), không có index hay query;
  - **V4:** investigation v4 lát cắt 1 đầy đủ, think OFF, temp 0.1, `num_ctx` 12288.
  - Mỗi arm chạy 2 seed (42, 7), tổng **120 run**. Arm A static được sinh sẵn khi prepare.
- **Cách quy đóng góp:**
  - V4_NOQ so với BASE đo hiệu ứng của contract, workflow và bảng đầy đủ;
  - V4 so với V4_NOQ đo hiệu ứng của retrieval có chỉ mục;
  - V4 so với BASE là so sánh gói tổng.
- Trạng thái ghi: `DEV_EVALUATION_FRESH_COHORT`, `RAW_PE_E2E`, `LOCAL_QWEN`, metric tất định.
  **Không** gọi là confirmatory của dự án: n = 20, chỉ có benign.

### 4.4 Metric (tất định)

Tái sử dụng định nghĩa của 07A khi áp dụng được.

| Mã | Định nghĩa | Mẫu số |
|---|---|---|
| M1 | Entry liên quan từng hiển thị | RELEVANT_PRESENT |
| M1b | Final trích được entry liên quan (resolve qua handle hoặc `import_refs`) | RELEVANT_PRESENT |
| **M8 query_hit** (mới, chỉ V4) | Có ít nhất một query trả về entry liên quan; `first_query_hit` = query đầu tiên đã trúng | RELEVANT_PRESENT |
| M2 | Gọi analyzer khi không cần | INITIAL_SUFFICIENT + NOT_STATIC |
| M4 | Absence screen (SCOPED / UNSCOPED) cộng developer review riêng. Ở `RELEVANT_ABSENT`, nói "không thấy" có phạm vi là **đúng** | có final |
| M5 | Structural self-corroboration (V4 kỳ vọng bằng 0 do cấu trúc contract; vẫn đo) | có final |
| **M9 answer_status_fit** (mới) | NOT_STATIC → `NOT_STATICALLY_ANSWERABLE` hoặc `PARTIALLY`; INITIAL_SUFFICIENT → `ANSWERED` và không gọi tool | lớp tương ứng |
| M6 | Chi phí: số lần gọi LLM, latency, token | tất cả |
| M7 | Toàn vẹn: status, truncation (đếm cả từ `error_payload`), tràn context, lỗi hạ tầng | tất cả |
| M10 | Final hợp lệ / 20 | tất cả |

**Nhiễu:** so seed 42 với seed 7 trong cùng arm. Một hiệu ứng chỉ được tính khi nó xuất hiện ở cả
hai seed và lớn hơn nhiễu.

**Run không có final (lỗi hoặc incomplete)** luôn được tính là **không đạt** cho mọi metric có tử
số "tốt" (M1b, M8, M9, M10). Với metric kiểu "dừng khi còn thiếu" (M3b), run đó được tính là
**có dừng**. Run thất bại không bao giờ được làm metric trông tốt hơn. M5 của V4 và V4_NOQ bằng 0
do cấu trúc contract. Báo M5 là structural và **không** so trực tiếp với BASE như một cải thiện
hành vi.

### 4.5 Bảng quyết định (ghi trước trong PROTOCOL)

| Quan sát (ở cả hai seed, vượt nhiễu) | Diễn giải | Bước tiếp theo |
|---|---|---|
| V4 vượt BASE ở M1b và M8; M4-UNSCOPED không tăng; M10 ≥ BASE; latency ≤ 3× | Lát cắt 1 có tác dụng | TASK 07C: thêm investigation state; `FEATURE_RECORD_REPLAY` trên EMBER (malicious, FP/FN) |
| V4 vượt V4_NOQ ở M1b | Retrieval có chỉ mục đóng góp riêng | Giữ query service; mở rộng sang các facet khác ở 07C |
| V4 ≈ V4_NOQ, cả hai vượt BASE | Lợi ích đến từ contract, workflow và bảng đầy đủ, không phải từ query | 07C ưu tiên state và kế hoạch; xem lại có nên giữ query hay không |
| M8 cao nhưng M1b thấp | Model tìm được entry nhưng không dùng | Xem lại contract final hoặc projector; cân nhắc E7 (so sánh 9B) |
| M8 thấp (query không trúng) | Model không biết hỏi gì (thiếu kiến thức miền) | 07C: thử capability tag như **ablation**, hoặc so sánh 9B |
| M2 hoặc M9 không cải thiện | Quyết định gọi tool vẫn mang tính phản xạ | 07C: thêm investigation state hoặc một bước kế hoạch rõ ràng |
| Truncation > 2 ca hoặc tràn context ở một arm | Arm đó không diễn giải được | PARTIAL; không chạy lại để cứu |

## 5. Thứ tự thực hiện và gate

| Bước | Việc | Gate để đi tiếp |
|---|---|---|
| S0 | G0 (D1–D7); tạo branch; commit `PLAN_TASK07B.md` | Owner trả lời |
| S1 | Script sinh `ordinal_table.json` (D4), chạy một lần, commit kèm provenance | Test bảng: định dạng, SHA nguồn |
| S2 | Schema D0, adapter, D7 validator, spec và install, backend `include_imports_table`; test §3.1–3.2 | Regression xanh |
| S3 | Query service và projector; test §3.3–3.4 | Xanh |
| S4 | Contract, verifier, recommendation, workflow v4, sửa planner; test §3.5–3.8 | Xanh |
| S5 | DEV debug trên cohort 06B-J (`DEV_DEBUG`) | Hành vi đủ ổn định để thử |
| S6 | G3 smoke (§4.2) | PASS. Nếu FAIL thì sửa rồi smoke lại ở thư mục mới; ghi log |
| S7 | Dựng cohort mới bằng `cohort_audit.py` (D5): audit pool, phân tầng theo §4.3, manifest evaluator-only. Viết `PROTOCOL.md` (cohort, 3 arm, metric, nhiễu, bảng quyết định, quy tắc dừng). Commit `[TASK 07B] Protocol and v4 slice-1 harness (pre-run freeze)` | Commit có trước run |
| S8 | Live run 120 lần (3 arm × 2 seed × 20), chạy **ngoài session** (D7). Mỗi run một lần; không rerun. Lỗi hạ tầng tính vào mẫu số | Mọi sự cố ghi vào log |
| S9 | Tính metric, viết `evaluation/task07b/REPORT.md` (tiếng Việt, áp bảng §4.5). Commit `[TASK 07B] v4 slice-1 evaluation results and analysis` | **Không push** |

**Effort** (ước lượng của review dev, một người cùng Claude):

| Bước | Ước lượng |
|---|---|
| S1 | 0.5 ngày |
| S2 | 1.5–2 ngày |
| S3 | 1 ngày |
| S4 | 2–3 ngày |
| S5 | 0.5–1 ngày |
| S6 | 0.5 ngày |
| S7 | 1–1.5 ngày |
| S8 | khoảng 3–4 giờ máy (thêm arm V4_NOQ) |
| S9 | 0.5–1 ngày |
| **Tổng** | **khoảng 9–12 ngày làm việc** |

Ghi log về hash: sửa `agent/planner.py` làm đổi source hash của 06B-J và 07A. Điều này chấp nhận
được vì không resume các thư mục cũ. `dacn/investigation.py` không nằm trong guard hay hash pin
nào, trừ `evaluation/task06b/experiment.py:sources()` (06B cũ, không rerun).

## 6. Ràng buộc (theo CLAUDE.md)

- Default-deny D4; allowlist tool mới một cách tường minh; không nới rule hay budget cap của
  tool khác.
- Model không cung cấp path. Query chỉ đọc CaseState đã commit, đầu vào có kiểu, không regex,
  binding do trusted code điền.
- PE không bao giờ được thực thi. Mọi analyzer là read-only. Không tạo, không tải mẫu malicious.
- Nội dung lấy từ PE giữ nhãn `UNTRUSTED_CONTENT`. Trường `*_EVALUATOR_ONLY` và label không được vào
  prompt. Leakage scan chạy ở mọi lượt.
- Trusted code chỉ **resolve** handle và ordinal. Annotation ordinal phải ghi rõ nguồn và
  limitation. Trusted code không viết claim thay model.
- Contract hay chính sách mới đều có version: `investigation-v4.0`,
  `pe-imports-table-*-v1`. Giữ v3.x và baseline frozen.
- Chỉ dùng Ollama loopback, không gọi API LLM ngoài, không pull model mới.
- Không sửa module hay artifact đã frozen. Mọi output ghi write-once. Không rerun ca lỗi.
- Commit `[TASK 07B] …` kèm dòng `Co-Authored-By` theo quy định của session. **Không push, không
  merge**: owner chỉ push khi xong toàn bộ TASK 07.

## 7. Definition of done

- **Engineering PASS:**
  - analyzer, query, projector, contract, verifier, recommendation và workflow v4 đều có test;
  - full regression được báo đủ passed/failed/skipped;
  - G3 PASS;
  - protocol commit trước run;
  - mọi artifact ghi write-once.
- **Research PASS:**
  - đủ 120 run, hoặc ghi rõ phần nào thiếu và vì sao;
  - bảng M1–M10 có tử số và mẫu số theo arm, seed và lớp;
  - có phân tích nhiễu;
  - đã áp bảng §4.5 và chọn được hướng 07C.
- Nếu không phân biệt được với nhiễu thì ghi **INCONCLUSIVE**. Đó là kết quả hợp lệ.
