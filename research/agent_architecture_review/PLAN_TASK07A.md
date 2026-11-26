# PLAN — TASK 07A: Diagnostic ablations cho Agent v3.4 (pha P0)

> Plan này dành cho một session Claude Code **khác** thực hiện. Đọc theo thứ tự:
> `CLAUDE.md` → `research/agent_architecture_review/REPORT.md` (§1, §3, §4, §14) → file này.
> Plan **chưa** được thực hiện. Mọi số liệu nêu ở đây lấy từ artifact đã freeze của 06B-J.

## 0. Vì sao bước tiếp theo là ablation, chưa phải xây v4

REPORT.md nêu ba nhóm nguyên nhân cạnh tranh nhau cho việc Agent điều tra kém:

- **(H1) Thiếu bước cân nhắc.** Thinking đang OFF, và `action` là token đầu tiên của JSON.
- **(H2) Thiếu information scent / phễu workflow.** Agent đọc theo offset mù, và tool chỉ được
  offer ở lượt 1.
- **(H3) Giới hạn của model hoặc contract.** Ngay cả khi evidence liên quan đã hiển thị, Agent
  vẫn dùng sai.

Chưa có thí nghiệm nào tách được ba nhóm này. Nếu dựng v4 ngay thì mọi biến sẽ đổi cùng lúc, và
ta lặp lại đúng vấn đề của TASK 06. TASK 07A chạy **4 biến thể nhỏ**, Agent v3.4 giữ nguyên (chỉ
đổi cấu hình, decoding wrapper ở harness, và oracle context), để quyết định TASK 07B làm gì
trước.

**Không thuộc phạm vi 07A:**

- contract v4, retrieval mới, analyzer v0.2, investigation state;
- đổi model, fine-tune;
- rubric hoặc Judge mới;
- sửa README top-level;
- sửa module frozen `investigation_v3/*` (v3.3/v3.4) hay `evaluation/task06b_j/runner.py`.

## 1. Gate G0: quyết định của owner, phải có trước khi code

Session thực hiện **phải hỏi owner** và ghi câu trả lời vào `evaluation/task07a/EVALUATION_LOG.md`:

| # | Quyết định | Đề xuất |
|---|---|---|
| D1 | Dùng lại cohort holdout 06B-J (20 PE đã "tiêu" sau confirmatory run_v1) làm cohort **DEV_DIAGNOSTIC** cho 07A. Ghi rõ cohort này **không bao giờ** được dùng làm confirmatory nữa | Đồng ý. Lý do: có sẵn `relevant_entries` evaluator-only theo từng case và có baseline run_v1 để so |
| D2 | Cho phép biến thể **ORACLE** (V3): harness dùng chỉ số entry evaluator-only để làm hiển thị một trang import **đã commit** (không đưa label hay văn bản evaluator vào prompt) | Đồng ý, gắn nhãn `ORACLE_DIAGNOSTIC`, chỉ dùng ở DEV |
| D3 | Thay đổi **additive** ở `agent/config.py` và `agent/planner.py` (`num_ctx`, `seed`, sampling tùy chọn, ghi lại `thinking`). Mặc định giữ byte-identical với request hiện tại | Đồng ý |
| D4 | Chuỗi authorization cho live Qwen run (runner yêu cầu `--authorized-by`) | Owner cung cấp |
| D5 | Tạo branch `feat/task07a-agent-diagnostic-ablations` từ HEAD hiện tại, rồi commit local `REPORT.md` cùng plan này làm commit đầu tiên | Đồng ý. Không push nếu owner chưa cho |

Nếu D1 hoặc D2 bị từ chối: dừng lại, báo owner, và đề xuất cohort DEV thay thế (ví dụ các mẫu
calibration DEV của 06B-J, nhưng chúng không có `relevant_entries`).

## 2. Thiết kế thí nghiệm

### 2.1 Cohort và arm

- **Cohort:** 20 case, lấy từ `evaluation/task06b_j/results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json`.
  Giữ nguyên alias, SHA và `question_text`.
- **Phân lớp** (`accessibility_class`):
  - IN_INITIAL 2;
  - REACHABLE 6;
  - INACCESSIBLE 4;
  - NOT_STATIC 4;
  - INITIAL_SUFFICIENT 4.
- **Arm:** chỉ chạy **arm C (tool-enabled)**.
  - Arm B không cung cấp thông tin cho H1–H3, vì 13/20 ca của nó kết thúc do
    `REQUEST_MORE_EVIDENCE` là terminal.
  - Arm A là template, không cần chạy lại; dùng lại artifact `*_A.json` mà `prepare` sinh ra.

### 2.2 Biến thể

| Variant | Kiểm giả thuyết | Khác với V0 | Seed |
|---|---|---|---|
| **V0** baseline | đo nhiễu giữa các lần chạy | Giống hệt `task06b_j.runner.CFG`: `max_iterations=5`, `max_tool_calls=1`, `max_context_chars=24000`, `num_predict=2048`, `inference_timeout_s=90`, `wall_clock_s=180`, think OFF, temp 0.1, `num_ctx` 8192 | 42, 7 |
| **V1** thinking (E1) | H1 | `think=True`; `num_ctx=16384`; `num_predict=6144`; `inference_timeout_s=240`; `wall_clock_s=900`; `max_tokens=150000`. Sampling theo model card cho thinking-precise: temp 0.6, top_p 0.95, top_k 20, presence_penalty 0.0 | 42, 7 |
| **V2** analysis-first (E2) | H1, rẻ hơn V1 | think OFF, temp 0.1. Decoding schema thêm property `analysis` (string, maxLength 1500) **đứng đầu** mọi nhánh `oneOf`, có trong `required`. `num_predict=3072`; `num_ctx=12288`; `wall_clock_s=300` | 42, 7 |
| **V3** oracle (E4) | H3 so với H2 | Cấu hình V0, cộng một trang (16 entry) **đã commit** chứa entry liên quan đầu tiên, hiển thị sẵn ngay khi imports evidence xuất hiện. Chỉ chạy 8 case IN_INITIAL + REACHABLE | 42 |

**Confound đã biết, phải ghi vào báo cáo:**

- V1 đổi cả thinking lẫn sampling. Nếu còn thời gian, chạy **V1b** (thinking, temp 0.1, seed 42)
  để tách hai yếu tố.
- `num_ctx` lớn hơn không làm đổi hành vi **trừ khi** V0 bị tràn context. Phải kiểm điều này
  (§4, M7).

### 2.3 Số lượng run

| Variant | Số run |
|---|---|
| V0 | 2 seed × 20 = 40 |
| V1 | 2 × 20 = 40 |
| V2 | 2 × 20 = 40 |
| V3 | 8 |
| V1b (tùy chọn) | 20 |
| **Tổng** | **128–148** |

Thời gian ước lượng, chưa đo: V0 và V2 khoảng 10–15 phút mỗi seed; V1 khoảng 30–60 phút mỗi seed.

Mỗi run chạy **đúng một lần** và ghi write-once. **Không** rerun ca lỗi. Truncation, timeout và
lỗi validation đều được tính trong mẫu số.

## 3. Implementation

### 3.1 Thay đổi additive ở production (D3)

**`agent/config.py`**: thêm vào `AgentConfig`:

- `num_ctx: int = 8192`
- `seed: int = 42`
- `top_p: float | None = None`, `top_k: int | None = None`, `presence_penalty: float | None = None`

Validate theo cùng kiểu với các budget hiện có (`num_ctx` trong khoảng 2048–65536). `from_env`
**không** đổi.

**`agent/planner.py` (`OllamaPlanner._decide`)**:

- dùng `cfg.num_ctx` và `cfg.seed` thay cho hằng số 8192 và 42;
- chỉ đưa `top_p`, `top_k`, `presence_penalty` vào `options` khi giá trị **khác None**, để request
  mặc định giữ **byte-identical**;
- khi `payload["message"]` có `thinking`, đưa vào `meta`: `thinking` (nguyên văn) và
  `thinking_chars`. Khi `think=False` thì `meta` không đổi.

**Test bắt buộc** (thêm vào `tests/test_agent.py`, hoặc file test mới):

- (a) body request với config mặc định giống hệt bản trước khi đổi (so sánh dict);
- (b) giá trị mặc định của các field mới;
- (c) giá trị ngoài khoảng bị reject;
- (d) `meta` có `thinking` khi transport trả về field này (dùng fake HTTP, **không** gọi Ollama
  thật).

**Lưu ý:** `task06b_j.runner.AGENT_SOURCES` hash cả `agent/planner.py` và `agent/config.py`.
Artifact frozen của 06B-J **không** bị ảnh hưởng (không rerun). Nếu có test 06B-J nào so hash
nguồn với giá trị cố định thì phải báo trung thực, **không** sửa artifact frozen.

### 3.2 Module mới `evaluation/task07a/`

```
evaluation/task07a/
  __init__.py
  PROTOCOL.md          # freeze TRƯỚC live run (§5)
  EVALUATION_LOG.md    # quyết định owner, sai lệch, sự cố
  variants.py          # cấu hình V0–V3, planner wrappers, oracle patch
  ablation.py          # CLI prepare/run (tái sử dụng task06b_j.runner)
  metrics.py           # metric tất định M1–M7 (§4)
  tests/test_07a.py    # MOCK_LLM + unit
  results/             # write-once, một thư mục cho mỗi (variant, seed)
  REPORT.md            # viết sau khi có kết quả
```

#### `variants.py`

- `VARIANTS: dict[str, dict]` chứa cấu hình đầy đủ của từng variant và `seeds`. Hàm
  `make_cfg(variant, seed) -> AgentConfig` dựng config tương ứng.
- **V0, V1, V3** dùng `investigation_v3.workflow_v34.Planner(cfg)`, không đổi gì.
- **V2: class `AnalysisFirstPlanner`** (`is_mock = False`):
  1. `schema = add_analysis(final_v34.contract(ctx))`. Làm trên deepcopy; với mỗi nhánh trong
     `oneOf`, dựng lại `properties` với `analysis` đứng **đầu**, rồi chèn `"analysis"` vào đầu
     `required`. `description`: *"Before choosing the action, reason step by step: what the
     question asks, what visible evidence answers it, what is still missing, and whether a listed
     action can obtain it."*
  2. `resp = OllamaPlanner(cfg).decide_with_schema(ctx, schema)`.
  3. Parse JSON. Nếu parse được: ghi `meta['analysis']`, `meta['analysis_first'] =
     (list(obj)[0] == 'analysis')` và `meta['raw_with_analysis'] = resp.raw`; `pop('analysis')`;
     rồi trả `PlanResult(json.dumps(obj), …)`.
  4. Nếu parse lỗi thì trả nguyên `resp`, để `final_v34.parse` của workflow tự báo lỗi như bình
     thường.
  5. **Không** đổi `final_v34`. Validator của v3.4 vẫn kiểm phần còn lại y như cũ.
- **V3: context manager `oracle_pages(relevant_literals)`**:
  - `mock.patch.object(investigation_v3.repair_context, "build", wrapped)`. `workflow_v34` gọi
    `repair_context.build(...)` qua thuộc tính module, nên patch có tác dụng.
  - `wrapped(...)` **sao chép** dict `pages` (không được mutate dict của workflow). Với imports
    evidence ở trạng thái SUCCESS, tìm index của entry liên quan đầu tiên trong `state` (giá trị
    đã commit), rồi thêm `((idx // 16) * 16, 16)` vào danh sách trang nếu trang đó chưa có.
  - Sau đó gọi `build` gốc. Dữ liệu vẫn đi qua `retrieval.fetch`, nên binding
    case/revision/SHA giữ nguyên.
  - Ghi `oracle_offset` vào trace của run, phần evaluator-only.
  - `relevant_literals` lấy từ `reference_EVALUATOR_ONLY`. Trường này là chuỗi repr Python, nên
    dùng `ast.literal_eval`, **không** dùng `eval`. Định dạng của literal là `LIB.dll!Symbol` hoặc
    `LIB.dll!#ordinal`; so tên lib không phân biệt hoa thường.
  - Ghi chú: nếu model đọc lại đúng trang oracle, guard `RETRIEVAL_NO_INFORMATION_GAIN` của
    workflow sẽ không biết trang đó đã được hiển thị. Đây là sai lệch nhỏ, phải ghi vào log.

#### `ablation.py` (CLI)

- **`prepare --variant V0 --seed 42 --out <dir>`**:
  - gọi `task06b_j.runner.prepare(cases_manifest, out, mode="DEV_DIAGNOSTIC")`. Lệnh này sinh
    initial state, arm A, leakage và `freeze.json`;
  - với V3, lọc manifest còn 8 case trước khi prepare (ghi bản lọc vào `out/EVALUATOR_ONLY/`);
  - sau đó ghi write-once `variant.json` gồm tên variant, seed, `asdict(cfg)`, SHA của
    `variants.py`, `ablation.py`, `metrics.py`, schema đã augment (với V2), và
    `"track": "RAW_PE_E2E"`, `"evaluation_kind": "DEV_DIAGNOSTIC"`.
- **`run --out <dir> --authorized-by "<owner string>"`**:
  - `runner.validate_freeze(out, allow_mock=False)`; kiểm hash của `variant.json` và hash các file
    07A;
  - với mỗi case, chạy **chỉ arm C**. Vòng lặp tương tự `runner.run`, nhưng `CFG = make_cfg(...)`
    và planner/patch lấy theo variant;
  - lấy lại các helper của 06B-J: `question()`, `isolation_checks()`, `write_new()`,
    `leakage.scan_facts()`;
  - cho phép trùng lặp vòng lặp khoảng 30 dòng, vì **không được sửa** runner 06B-J đã freeze.
    Ghi rõ lý do trong docstring;
  - output: `<alias>_C.json`, kèm thêm các trường `variant`, `seed`, `authorized_by`,
    `runner_version="task07a-ablation-v1"`.
- **`smoke --variant V1|V2 --out <dir> --authorized-by …`**: chạy 1 case DEV **không thuộc
  cohort**, lấy từ `evaluation/task06b_j/results/dev/staging_smoke_cases_v1.json`, dùng cho gate
  G1 và G2.

### 3.3 Test MOCK_LLM (`tests/test_07a.py`)

MOCK_LLM **không** phải bằng chứng hành vi. Các test này chỉ kiểm cơ chế:

1. `add_analysis`:
   - mọi nhánh có `analysis` đứng đầu `properties` và đầu `required`;
   - phần còn lại của schema giống hệt `final_v34.contract`.
2. `AnalysisFirstPlanner` với transport giả:
   - raw trả cho workflow không còn `analysis`;
   - `meta` giữ nguyên `raw_with_analysis`;
   - JSON lỗi được trả nguyên văn.
3. `oracle_pages`:
   - không mutate `pages` của workflow;
   - thêm đúng trang;
   - không thêm gì khi entry nằm ở trang 0;
   - không thêm gì cho evidence không phải imports;
   - `literal_eval` parse đúng tham chiếu ordinal.
4. Chạy `workflow_v34.run` end-to-end bằng `MockPlanner` qua `ablation` trên một case giả. Kiểm
   write-once, kiểm isolation, và kiểm `variant.json` bị đổi thì `run` báo lỗi drift.
5. `metrics.py` trên trace giả lập: tính đúng M1–M7, mẫu số đầy đủ.

## 4. Metric tất định (`metrics.py`)

Mọi metric chỉ tính từ trace cùng manifest evaluator-only. Đây **không phải** semantic grading.
Phải báo **cả** tử số lẫn mẫu số, theo từng variant, từng seed và từng lớp. Tái sử dụng
`task06b_j.pipeline_metrics.run_metrics` cho các trường chung.

| Mã | Định nghĩa | Mẫu số |
|---|---|---|
| **M1 relevant_seen** | Có ít nhất một literal trong `relevant_entries` từng hiển thị (trong `turns[].context.facts.evidence[imports].value.entries` ở bất kỳ lượt nào) | IN_INITIAL + REACHABLE (8) |
| **M1b relevant_cited** | Final có claim mà `import_refs` resolve ra một entry liên quan (dùng `trusted_metadata.resolved_import_refs`) | IN_INITIAL + REACHABLE (8) |
| **M2 unnecessary_tool** | `TOOL_CALL` được đề xuất | INITIAL_SUFFICIENT + NOT_STATIC (8) |
| **M3a targeted_read** | Có ít nhất một READ mà trang của nó chứa entry liên quan | REACHABLE (6) |
| **M3b stopped_with_gap** | Agent chọn FINISH khi `retrieval_attempts < 2` **và** còn entry liên quan đã commit nhưng chưa hiển thị | REACHABLE (6) |
| **M3c self_acknowledged_gap** | Văn bản final hoặc reason (và `analysis`/`thinking` nếu có) khớp regex partial-visibility, đồng thời còn budget đọc. Gắn nhãn `REGEX_APPROX` | tất cả case có final |
| **M4 absence_claim_screen** | Final chứa câu phủ định capability (regex, ví dụ `no (direct|explicit)? … (APIs?|imports?)`, `does not (import|declare)`, `none of`) trong khi bảng import đầy đủ có entry liên quan. Phân loại `SCOPED` (có "visible / in the entries read / of N") và `UNSCOPED`. Gắn nhãn `RULE_SCREEN_CANDIDATE`, và xuất danh sách câu nguyên văn để owner xem tay | case có final và có ít nhất một relevant entry |
| **M5 prediction_in_support** | Cờ `prediction_used_as_own_corroboration` | case có final |
| **M6 cost** | Số lần gọi LLM, latency trung bình và median, prompt/output token, tổng `thinking_chars` | tất cả |
| **M7 integrity** | Status, `failure`, `validation_error`, số ca `done_reason=length`, `analysis_first` (V2), **context-overflow risk**: `prompt_eval_count + eval_count ≥ 0.95 × num_ctx` ở bất kỳ lượt nào | tất cả |

**Nhiễu:**

- so V0 seed 42 với V0 seed 7, và V0 với run_v1 của 06B-J, trên M1–M5;
- khác biệt giữa hai variant **nhỏ hơn hoặc bằng** khác biệt giữa hai seed của V0 thì báo là
  **không phân biệt được**.

## 5. Protocol freeze (trước live run)

`evaluation/task07a/PROTOCOL.md` phải gồm:

- cohort (D1);
- variant và cấu hình đầy đủ;
- metric M1–M7 cùng mẫu số;
- quy tắc nhiễu;
- **bảng quyết định (§7) được ghi trước**;
- quy tắc dừng: mỗi run chạy một lần, không rerun, lỗi tính vào mẫu số;
- trạng thái `DEV_DIAGNOSTIC`, `confirmatory: NOT_RUN`.

Commit protocol cùng code và test **trước** khi chạy live.

## 6. Thứ tự thực hiện và gate

| Bước | Việc | Gate để đi tiếp |
|---|---|---|
| S0 | G0 (§1); tạo branch; commit `REPORT.md` cùng plan | Owner đã trả lời D1–D5 |
| S1 | §3.1 cùng test; chạy `python -m pytest -q` (full regression) | Regression xanh, hoặc báo rõ test nào fail và lý do. Báo riêng số passed/failed/skipped |
| S2 | §3.2 và §3.3; full regression lần nữa | Xanh |
| S3 | **G1:** `smoke --variant V1` trên 1 case DEV ngoài cohort. Kiểm: Ollama 0.40.16 trả `thinking` **và** `content` là JSON hợp lệ theo schema; không có content rỗng; không truncation. Nếu thinking cùng `format` không chạy được: V1 = **BLOCKED**, ghi lý do và raw response, rồi tiếp tục với V2 | Kết quả được ghi vào log |
| S4 | **G2:** `smoke --variant V2`. Kiểm `analysis_first = true` và v3.4 parse được phần còn lại. Nếu Ollama không giữ thứ tự property: V2 = **BLOCKED** (ghi raw), **không** tự đổi thiết kế | Kết quả được ghi vào log |
| S5 | Viết `PROTOCOL.md`; commit `[TASK 07A] Protocol, ablation harness and tests (pre-run freeze)` | Commit có trước run |
| S6 | Live run theo thứ tự V0 s42, V0 s7, V2 s42, V2 s7, V3, V1 s42, V1 s7, (V1b). Mỗi thư mục: `prepare`, rồi `run` | Mỗi run một lần; mọi sự cố ghi vào `EVALUATION_LOG.md` |
| S7 | `metrics.py` trên toàn bộ results, ghi write-once `results/metrics_v1.json` | — |
| S8 | `REPORT.md` (tiếng Việt), áp bảng quyết định §7; commit `[TASK 07A] Diagnostic ablation results and analysis` | Không push khi chưa có phép của owner |

Lệnh mẫu (PowerShell, `.venv` đã kích hoạt, Ollama loopback đang chạy; không tự khởi động lại
nếu owner chưa đồng ý):

```powershell
python -m evaluation.task07a.ablation smoke   --variant V1 --out evaluation\task07a\results\smoke_V1 --authorized-by "<owner>"
python -m evaluation.task07a.ablation prepare --variant V0 --seed 42 --out evaluation\task07a\results\V0_s42
python -m evaluation.task07a.ablation run     --out evaluation\task07a\results\V0_s42 --authorized-by "<owner>"
python -m evaluation.task07a.metrics --results evaluation\task07a\results --out evaluation\task07a\results\metrics_v1.json
```

## 7. Bảng quyết định (ghi trước trong PROTOCOL)

n rất nhỏ, nên đây là quy tắc **ưu tiên công việc**, **không** phải kiểm định thống kê. Một
hiệu ứng chỉ được tính khi nó xuất hiện ở **cả hai seed** và lớn hơn nhiễu giữa hai seed của V0.

| Quan sát | Diễn giải | TASK 07B ưu tiên |
|---|---|---|
| V3: M1b ≥ 6/8 **và** M4-UNSCOPED thấp | Model dùng được evidence khi evidence đã hiển thị, nên H3 yếu; nút thắt nằm ở thu thập | Retrieval có chỉ mục + workflow (P2/P3 trong REPORT) |
| V3: M1b ≤ 3/8 **hoặc** M4-UNSCOPED vẫn cao | Model hoặc contract là nút thắt (H3) | Contract v4 tập trung vào câu trả lời (P1), và đưa E7 (so sánh 9B) lên sớm. Cần owner đồng ý pull model |
| V1 hoặc V2: M2 giảm ≥ 3/8 **hoặc** M3a tăng ≥ 2/6 so với V0 | H1 đúng; deliberation có tác dụng | Mọi bước của v4 dùng reason-first. Nếu V2 ≈ V1 thì chọn V2 (rẻ hơn) |
| V1 và V2 không đổi M2/M3 | H1 yếu; phễu và scent là nguyên nhân (H2) | Tool ở mọi lượt, REQUEST_MORE không terminal, chỉ mục DLL |
| V1 BLOCKED | Chưa kết luận được về thinking native | Dựa vào V2; ghi việc cần xác minh thinking cùng `format` |
| Bất kỳ variant nào có M7 overflow hoặc truncation > 2 ca | Kết quả của variant đó không diễn giải được | Báo PARTIAL; không chạy lại để "cứu" kết quả |

## 8. Ràng buộc (nhắc lại từ CLAUDE.md, áp dụng nghiêm)

- Không sửa `investigation_v3/*`, `evaluation/task06a/*` hay `evaluation/task06b_j/*` (kể cả
  results), và không sửa artifact frozen.
- Mọi live run chỉ gọi Ollama loopback; không gọi API LLM ngoài; không pull hay tải model mới.
- PE staging nằm dưới `evaluation/task06b/runtime/` (gitignored). Không commit, không publish.
- `relevant_entries`, `program_identity`, label và mọi trường `*_EVALUATOR_ONLY` **không** được
  vào prompt. V3 chỉ dùng chúng để **chọn trang** evidence đã commit. Leakage scan vẫn chạy ở
  mọi lượt.
- Không rerun ca lỗi; không xóa run; không dùng cohort này làm confirmatory.
- Gọi đúng tên loại bằng chứng: `DEV_DIAGNOSTIC`, `RAW_PE_E2E`, `LOCAL_QWEN` hoặc `MOCK_LLM`. Đây
  là metric tất định, không phải semantic grading.
- Commit theo convention `[TASK 07A] …`, có dòng `Co-Authored-By` theo quy định của session.
  Không push, merge hay rebase khi chưa có phép.

## 9. Definition of done cho TASK 07A

- **Engineering completion (PASS khi):**
  - thay đổi additive có test;
  - harness 07A có test MOCK_LLM;
  - full regression được báo đủ passed/failed/skipped;
  - protocol được commit trước run;
  - mọi run được ghi write-once kèm `variant.json`.
- **Research completion (PASS khi):**
  - có bảng M1–M7 đầy đủ mẫu số cho V0–V3 (biến thể nào BLOCKED thì ghi BLOCKED);
  - có so sánh nhiễu giữa hai seed;
  - bảng quyết định §7 được áp dụng và chọn được hướng cho TASK 07B.
- Nếu kết quả không phân biệt được với nhiễu, đó là kết quả hợp lệ. Báo **INCONCLUSIVE**, không
  chạy thêm để ép ra kết luận.

## 10. Phác thảo TASK 07B (chỉ để định hướng, chưa lên plan chi tiết)

TASK 07B dựng **lát cắt đầu tiên của investigation v4** theo hướng mà §7 chọn. Mỗi phần là
contract hoặc module **mới, có version, opt-in**:

- projector v4: nén context, handle ngắn, `detector_context` tách khỏi evidence citable;
- contract `investigation-v4.0` tập trung vào câu trả lời (REPORT §8.4);
- reason-first nếu H1 được xác nhận;
- và **một trong hai**:
  - (a) imports analyzer v0.2 (bảng đầy đủ dưới dạng artifact, DLL table of contents, resolve
    ordinal) cùng `query_imports`;
  - (b) vòng lặp có state với REQUEST_MORE không terminal.

Đánh giá trên một **cohort DEV mới**, kèm bản ghi EMBER (`FEATURE_RECORD_REPLAY`, có malicious và
FP/FN; label và avclass là evaluator-only). Confirmatory dùng holdout mới, để ở pha sau.
