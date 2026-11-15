# TASK 06B — Real Multi-Step Evidence-Driven Investigation

Ngày thực hiện: 15/11/2026. **ENGINEERING PASS cho live demonstration cụ thể /
RESEARCH PARTIAL.** Không phải production-readiness PASS: DEV v2 chỉ có **1/4**
tool-enabled cases tạo được final hợp lệ; lỗi và raw outputs còn nguyên.

## 1. Git state và phạm vi bàn giao

Ban đầu working tree sạch trên branch 06A, HEAD `eb34ee4`. Đã fetch origin và xác
nhận PR #13 được owner merge: `origin/main=8011eaf`; `eb34ee4` là ancestor, tree
main giống tree 06A-R. Tạo `feat/task06b-real-multistep-investigation` từ origin/main.
Không tự merge main, không push. Commit bàn giao xem `git log -1 -- evaluation/task06b/REPORT.md`.

Không sửa Agent v1, Node B/C, D1–D9 core, model/threshold, 05A–05D/06A artifacts hoặc
root README. Có hai schema D0 mới, installer/normalizer riêng và opt-in app/CLI.
575 regression tests pass ở source bàn giao; artifacts live v1/v2 có source snapshot
riêng vì sau live còn sửa các terminal/budget guards, được giải thích ở mục 11.

## 2. Source audit — hệ thống đã hỗ trợ gì

Đọc/đối chiếu `agent/{context,controller,loop,planner,schema,report,config}.py`,
`dacn/{application,investigation,cli,config}.py`, `context_collector.py`,
`case_state.py`/`case_manager.py`, D0 schemas/validate, registry, policy, workflow,
executor/execution control, D7 result validator/execution adapter, D8 trust và D9
case bridge. Đối chiếu 06A REPORT/PROTOCOL/schema/assessor/verification/consistency,
05C replay/projection/static template và 05D discovery/validation artifacts.

- Node B ghi rõ không thu imports/entropy/signature trust (`context_collector.py:238`).
  Nó thu identity/SHA/format/PE header, không chạy target.
- `research/independent_static_ml/pe_extractor.py` có raw imports nội bộ, nhưng
  detector adapter chỉ xuất `static-prediction-v1`: raw imports **không** được commit
  vào production CaseState. Numeric model features không phải literal import facts
  mà Agent có thể viện dẫn.
- Projection 05C có sampled imports từ EMBER record; đây là FEATURE_RECORD_REPLAY,
  không phải evidence sẵn có trong đường raw PE. V1/v2.1 stringify/cắt values ở 800
  chars; toàn context khoảng 12.000 chars.
- Controller/loop cũ đã đủ để gọi D1–D9 và đọc lại Node C. Production prompt khi đã
  có prediction lại yêu cầu FINISH; backend thật chỉ có detector chạy trước Agent.
  `_seen_toolcalls` ban đầu rỗng, không seed pre-agent execution.
- **Hiệu chỉnh nhận định từ báo cáo cũ:** source hiện tại
  `agent/schema.py::validate_shape()` đã gọi Draft202012Validator. Không đúng nếu
  mô tả runtime v1 hiện tại chỉ có kiểm shape thủ công hoặc hoàn toàn bỏ nested
  schema. Nó vẫn không giải quyết cross-field review/recommendation hoặc semantic
  grounding. Source là căn cứ, không lặp lại nhận định cũ chưa chính xác.
- D9 tự register tool legacy nếu cần rồi mới commit observation; vì vậy một tool
  mới có thể làm revision tăng **2**, không mặc định đúng 1. Node C không lưu riêng
  commit revision ở từng evidence record; cần join theo run ID với D9 ledger.

## 3. Lý do chọn detailed imports

Chỉ thêm **một** analyzer `static.pe_imports_detail`. Nó đọc declared DLL/symbol/
ordinal, gồm normal/delay imports. Đây là facts chưa nằm trong initial evidence,
không chỉ định dạng lại prediction. Câu hỏi cố định: concrete imported DLL/API nào
hỗ trợ/giới hạn giả thuyết network/process capability, còn điều gì chưa biết?

Không kết luận malware từ Winsock/OpenProcess/VirtualAlloc hay absence. Dữ liệu mới
là thông tin mới **đối với context Agent**, không phải nguồn vật lý/statistical độc
lập với PE hoặc detector: cả hai dùng cùng PE và cùng họ parser LIEF.

Không thêm sections/strings analyzer, REA, Ghidra, sandbox, frontend hoặc fine-tuning.

## 4. Tool contract và trust boundaries

Files chính: `investigation_v3/{import_adapter,imports_tool}.py` và
`d0/schemas/pe-imports-{input,output}-v1.schema.json`.

| Thành phần | Contract/control |
|---|---|
| Tool/provider | `static.pe_imports_detail`, version `0.1.0`, provider `dacn_pe_imports` |
| Input | Đúng `{"max_entries":64}`; không path/command/model/threshold/URL arguments |
| Output | SHA target, parser version, library/entry counts, 64 declarations tối đa, truncation/limitations rõ |
| Resource | 8 MiB trước parse; application opt-in hiện cũng preflight trước intake/model; tối đa 100.000 declarations/4.096 libraries, retain tối đa 64 entries |
| Execution | Python `-I` fixed script; pin interpreter, adapter, LIEF Python entrypoint và native `.pyd` |
| Budgets | 10s, output 64 KiB, artifacts 128 KiB, concurrency 1; existing Windows Job ownership/deadline/output controls |
| D7 | Kiểm JSON/schema, count/truncation invariants, symbol XOR ordinal, receipt/result consistency và target SHA bằng requested/observed digests |
| D8/D9 | Dùng signer/CaseBridge hiện có; provider data luôn UNTRUSTED_CONTENT; không tự append evidence |

D4 allowlist chỉ thêm đúng tool/provider/version trên **opt-in backend**. Default
backend vẫn chỉ detector. Discovery kiểm provider availability và pure D4 ALLOW;
authorization thật vẫn chạy lại ở D1. Controller không sửa arguments để vượt DENY.
DENY, unknown tool, altered arguments, duplicate/stale calls bị kiểm soát.

Adapter không có code path shell/network/PE execution. **Không claim OS firewall
isolation hoặc hard RSS cap:** D6 hiện có Job kill-on-close, deadline/output caps,
không có network sandbox/hard memory cap. Native parser vẫn thuộc trusted computing
base; input-size/count limits không chứng minh chống mọi native parser exploit.
Không xử lý malicious PE chưa được phê duyệt trong thí nghiệm này.

## 5. Workflow/Controller/CaseState/projection

Package versioned `investigation_v3` dùng Controller cũ qua conversion rõ ràng từ
action wrapper mới sang proposal v1 hợp lệ. Controller tiếp tục giữ case/revision,
provider/target/arguments/workflow gates, D1–D9 giữ nguyên. Không tự sửa detection
label; assessment v2.1 được reuse nguyên schema trong action contract mới.

- Seed seen calls từ persisted evidence/tool_runs, gồm detector đã chạy trước
  Agent và analyzer đã attempted/completed. Không loop phân tích lại cùng mục tiêu.
- Có TOOL_CALL / FINISH / REQUEST_MORE_EVIDENCE. Không bắt buộc gọi tool mỗi ca.
  C giới hạn một analyzer attempt, tối đa 3 model turns; B một model turn.
- Sau actual execution, đọc lại CaseState, lấy ID mới/revision thật; không dựng sẵn
  result để đưa vào prompt đầu. Audit callbacks ghi actual D4/D5/D7/D9 stages, không
  log signing key. `D1_TOOL_CALL` chứa canonical call thực sự được dispatch.
- Typed projection giữ ID/facet/status/source/tool_run/observed revision, structured
  value, limitations/coverage, truncation và full-detail reference về CaseState.
  `commit_revision=None` phản ánh giới hạn Node C; revision commit thật ở ledger.
- V2 chiếu tối đa 24/64 declarations, giữ counts provider và `projected_entries`
  riêng; không coi missing/truncated là zero. Bỏ 3 facets không phục vụ goal với
  explicit omitted IDs. Full payload 64 entries vẫn trong CaseState.
- Chỉ IDs trong visible evidence list được cite, old/new groups kiểm với initial
  ID set; literal new-fact bindings kiểm đúng `(evidence_id,DLL,symbol)` trong visible
  data. Free prose/semantic relevance vẫn cần review; không claim grounding 100%.
- Reuse guardrail 06A: raw proposal/assessment giữ nguyên; effective recommendation
  tách riêng, human decision và NOT_EXECUTED cho containment.

CLI opt-in:

```powershell
python -m dacn investigate --file C:\Windows\System32\curl.exe --agent-mode multistep
```

Không có flag thì vẫn v1; `--no-agent` vẫn detector/static report. CLI không cho
LLM chọn executable, shell, provider installation, policy hoặc containment.

## 6. Exact live trace — curl.exe (DEV v2, accepted final)

[Raw trace](results/dev_v2/01_C.json), [rendered final](results/dev_v2/01_final_report.md),
[D9 ledger](results/dev_v2/audit_ledgers/01_D9.jsonl).

Target SHA:
`73d24149ff289afc49ec41f08918ef9faa727d39ad993e929757dc2ddafab805`.
Case `CASE-c08def6d2a4a40f3ad807a4cce62c212`.

| Stage thực tế | Evidence kiểm chứng |
|---|---|
| Initial context | Revision 3, prediction có thật, không imports evidence |
| Qwen proposal | TOOL_CALL `static.pe_imports_detail`; reason nêu prediction chưa có literal import list để trả lời network/process question |
| Controller | `turns[0].controller_validated=true`; case/revision/refs/spec/args được kiểm trước dispatch |
| D1 | `CALL-agent-949d9317958d483b`, expected_revision=3, max_entries=64; target_ref do controller bind |
| D4 | Actual decision ALLOW, cùng call ID |
| D5/D6 | `RUN-dc4bb225122440b781761a15583cdfa0`, receipt SUCCESS, verified target digest; duration 156ms |
| D7 | `D7_VALIDATED` chứa ToolResult/value sau schema/binding/integrity checks |
| D9 | `AUDIT-dd68e767b3194dcc9a2a08709795df8b`, added_evidence=1, revision=5 |
| New evidence | `EV-d04fe6ce2a4345ec8ad391c9e9b575b2`, provider output UNTRUSTED_CONTENT |
| Qwen next turn | Context revision 5, new ID/value xuất hiện trong visible evidence |
| Final report | FINISH, old/new IDs tách đúng; hai literal facts kiểm khớp trong observed claim và new_fact_uses |

Không suy stage từ outcome trước: auditor join call/run IDs, validate receipt/result,
đối chiếu target SHA, D9 COMMITTED row, final CaseState value và next-turn context.
Portable stdout copy bằng bytes runtime; export hashes được ghi **post-hoc**, không
giả là original D6 stream digests vốn không được lưu đầy đủ trong trace wrapper.

## 7. Evidence before/after và revisions

Before: Node B metadata/identity/format/SHA + committed LightGBM prediction, revision 3.
After: một observation imports mới, 237 declarations đếm được, provider trả 64,
projection hiện 24; revision 5. Intermediate revision 4 là auto-registration tool,
không phải phantom evidence. Target identity/SHA không đổi.

Hai facts mới Agent dùng đúng literal source:

- `WS2_32.dll : WSAEnumNetworkEvents`
- `WS2_32.dll : getaddrinfo`

Old prediction ID `EV-98bdf279fff64f70b9a2e3ba1caff7f4` và new imports ID được phân
biệt trong final. `assessment_changed=false`: detector/alignment không đổi; lời
giải thích/verification plan được bổ sung tên imports. Đây không phải tăng detection.

## 8. Tool selection là của ai?

**Qwen thật** chọn TOOL_CALL trong cả bốn C cases của mỗi DEV version. Controller
không tự gọi analyzer. Preparation chỉ chạy detector deterministic. V2 decoder mask
chỉ loại action không có capability và pin identity đúng registry; **FINISH vẫn
được phép khi tool available**. LLM vẫn có thể chọn không điều tra thêm.

Goal imports được workflow đặt sẵn, khá hẹp và trực tiếp tạo nhu cầu imports. Không
suy từ 4/4 tool selections rằng Agent tự đặt được mục tiêu điều tra mở, hoặc tool
luôn cần thiết trên corpus thực tế. No-tool live case là resume chính case đã có
imports từ actual previous execution, không phải independent sample có sẵn fake result.

## 9. Information gain — tách facts, relevance, use và quality

Định nghĩa trước ở PROTOCOL: literal import tuple chưa có trong initial visible
context; ID mới hoặc execution success riêng không đủ. Post-hoc query-relevance
lexicon chỉ là exploratory heuristic; không gọi là confirmatory metric.

| DEV v2 case | New committed unique facts | New visible facts | Heuristic relevant visible | Literal uses trong accepted final |
|---|---:|---:|---:|---:|
| schtasks.exe | 64 | 24 | 0 | N/A — final rejected |
| curl.exe | 64 | 24 | 24 | 2 |
| wevtutil.exe | 64 | 24 | 0 | N/A — final rejected |
| reg.exe | 64 | 24 | 0 | N/A — final rejected |

Không gộp cùng 4 SHA chạy hai versions thành 8 independent samples. Counts 64/24
không phải 64/24 useful insights. Chỉ hai observed literal uses curl đã đối chiếu
đúng; ý nghĩa/security relevance của diễn giải vẫn human review PENDING.

First-N ordering là hạn chế lớn: 3 ca không có facts thuộc heuristic network/process
trong 24 declarations đầu. Absence không chứng minh không có capability. Thông tin
chưa chiếu không được viện dẫn như đã thấy; tool hiện chưa có pagination/filter.

## 10. Static-only vs one-shot vs tool-enabled

4 PE DEV: schtasks/curl/wevtutil/reg, Microsoft signature VALID, SHA không trùng
artifacts 05C/05D/06A. Đối chiếu thêm 12-char SHA prefixes của probe 16 ca: overlap 0.
Label benign chỉ evaluator/provenance, không vào prompt. Manifest public không là
blinded holdout. Reserve netstat/route chưa chạy model/Agent, đã public nên cũng
không được gọi là blind confirmatory set tương lai.

| DEV v2 metric | A static template | B one-shot | C tool-enabled |
|---|---:|---:|---:|
| Samples | 4 | 4 | 4 |
| Terminal result | Template 4 | REQUEST_MORE 3; rejected 1 | FINISH 1; rejected 3 |
| Model turns | 0 | 4 | 8 |
| Valid tool proposals | N/A | 0 proposals | 4/4 |
| D4 ALLOW / D5 success / D7 success / D9 commit | Detector riêng | 0 analyzer | 4 / 4 / 4 / 4 |
| Revision increment from initial | 0 | 0 | +2 mỗi ca |
| New IDs visible next turn | 0 | 0 | 4/4 |
| Accepted final có source-matched new literal uses | 0 | 0 | 1/4 (2 facts) |
| Semantic grounding/value | Chưa chấm | Chưa chấm | Chưa chấm |

B/C cùng initial CaseState/facts, chỉ khác available tools; auditor assert equality
của initial facts trừ tool list. Khi C chạy trước, B đọc immutable initial copy, không
đọc state post-tool. Shared audit prefix có thể gồm events từ arm trước; chỉ slice
từ `agent_event_start` thuộc arm đang xét. Tool results không được đưa vào B prompt.

B và C cùng schema assessment v2.1 nhưng planning wrapper/projection/decoding mask
mới và C có nhiều turns hơn. Đây là ablation treatment kết hợp, không phân causal
effect riêng của prompt/schema/tool. B được phép thừa nhận cần thêm evidence thay
vì bị ép kết luận. Không chấm template bằng rubric đạt trần rồi gọi nó vượt Agent.

## 11. Failures, repair versions và regression findings

- **DEV v1**: 4/4 C tool proposals/executions/commits thành công, nhưng final JSON
  **4/4 bị cắt**. Ví dụ curl: prompt 7.759 tokens, output 433, tổng=8192; các ca khác
  cũng chạm window. B bịa unavailable tools 3 ca, citation không visible 1 ca.
- Giữ nguyên `results/dev_v1`, freeze/source snapshot. Sau đó sửa engineering trên
  chính DEV, không dùng nó chứng minh generalization: v2 bỏ facets ít liên quan,
  chiếu 24 imports, mask capabilities. Không retry turn cũ hay ghi đè failure.
- **DEV v2 schtasks C**: new ID bị gán vào old group, nói không có evidence mới;
  `EVIDENCE_PHASE_MISMATCH` chặn final. B cite literal `unknowns` như evidence ID,
  bị `EVIDENCE_NOT_VISIBLE` chặn.
- **wevtutil C**: FINISH thiếu `old_evidence_ids`, bị reject. **reg C**: old/new
  group sai, bị reject. Không sửa IDs/nhóm giúp LLM để tạo PASS.
- **curl C**: accepted final còn raw INSUFFICIENT/review=false/MONITOR. Guardrail
  flag `insufficient_evidence_without_review`, effective MANUAL_REVIEW. Prediction
  ID bị dùng như supporting corroboration, cũng được flag.
- Curl có third literal use symbol chuỗi `"null"` không tồn tại: flagged unsupported,
  không tính vào hai uses đúng. LLM còn nói 64 entries “visible” dù prompt có 24;
  projection giữ counts rõ nhưng reasoning vẫn nhầm coverage. Không coi toàn report
  là semantic PASS chỉ vì IDs hợp lệ.
- Sau live v2, bổ sung fail-safe cho REQUEST_MORE/error/no-final, kiểm nested citations
  của REQUEST_MORE, không inference khi prediction bị context budget loại, recompute
  deadline sau LLM trước dispatch, model-unavailable handling và 8-MiB preflight.
  Đây là guards/API fixes được unit/integration-test, **không có live rerun** cho
  source sau guards. Live trace thuộc exact source snapshot v2; curl FINISH path/
  analyzer/normalizer/prompt/schema/budgets không bị đổi bởi các guards này.
- Current source intentionally khác freeze v1/v2: validator phải từ chối resume
  bằng code mới. Có **79/79 exact source files** archived/matched hashes mỗi version,
  không rebase hashes hoặc relabel historical inference như source mới.

## 12. Test evidence

Final suite: **575 passed, 4 skipped, 81 subtests passed**, 37,85s;
[regression_delivery.xml](results/regression_delivery.xml). Gồm Node B/C, D0/D1–D9,
Agent, DACN, 05A/05B/05C/R2/05D/06A và **32 ca 06B** (unit + integration).
Các integration cases chạy adapter/native parser/D1–D9 thật với benign PE; planner
test double được gắn MOCK_LLM, không được tính autonomous demonstration.

Coverage: invalid PE/8MiB limits/determinism, no Python-network calls; SHA mismatch,
target changed, unknown tool/invalid args, D4 DENY + altered args, duplicates/persisted
completed calls, stale revision, unavailable provider, remaining-budget failure,
malformed output/trust/count fields, tampered stdout digest, failed D9/no phantom
evidence, correct revision/next-turn visibility, prompt-injection-as-data, FINISH
không tool, malformed model JSON/action, repeated tool selection, fail-safe decision,
deadline after inference, missing model, API report writing và CLI default compatibility.
D6 timeout/process ownership và D8 approvals cũng được regression suite cũ kiểm tra.

4 skip được giữ: hai legacy gated live-Qwen tests, symlink privilege test, optional
512-MiB streaming test. Không gọi SKIP là PASS. Legacy STATIC_FIRST live failure cũ
không được coi là đã sửa bằng live test mới của path opt-in.

Giữ cả các kết quả phát triển trung gian. Một lượt sandbox lỗi quyền temp; chạy lại
ngoài sandbox pass. Một failure fixture dùng `unused.exe` không tồn tại xuất hiện
sau thêm preflight; sửa fixture tạo metadata-only target đúng mục tiêu missing-model
test. `regression_release.xml` giữ failure đó; delivery suite ở trên là lần đầy đủ
sau sửa. Không che những failures live v1/v2 trong kết quả xanh của unit suite.

## 13. No-tool / DENY / failure cases

Live resume curl: FINISH, tool_attempts=0, revision **5→5**, imports là old evidence
đã commit thật từ run trước. Qwen tự dừng; decoder vẫn cho REQUEST_MORE, không ép
FINISH. Đây là một no-tool example, không là independent held-out case.

D4 DENY, provider unavailable, target change, D9 abort và deadline cases thuộc
unit/integration với trace/test assertions; không gán chúng là live Qwen decisions.
No phantom evidence được kiểm khi D7/D9 thất bại; registration metadata có thể tăng
revision mà không có new observation, không dùng revision riêng làm proof commit.

## 14. Latency, tokens và overhead

DEV v2 mean end-to-end (bao gồm Node B/detector preparation): **A 1,265s, B 8,519s,
C 16,281s**, mẫu số 4/arm, kể cả failures. Không bỏ ca xấu để báo speed/quality.
B prompt/output tokens **15.998 / 2.466**; C **38.676 / 4.925**. Resume riêng:
10,406s, **5.186 / 910** tokens, không gộp làm sample thứ năm.

D5/D6 analyzer mean **156,25ms**. Chênh D1 requested_at tới D9 COMMITTED timestamp
mean **213,789ms**, post-hoc wall-clock estimate, không phải monotonic instrumentation.
Phần lớn overhead C so B là thêm LLM turn/context, không phải chỉ thời gian parser.
Local USD/energy cost N/A, không bịa số tiền hoặc token billing.

Qwen digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`,
Ollama `0.40.16`, Python `3.12.10`, LIEF `0.15.1-`, LightGBM `4.5.0`. Thinking OFF,
temperature 0.1, seed 42, num_ctx 8192, output cap 2048/turn, timeout 90s, wall 180s,
max 3 iterations/1 analyzer attempt. Model hash/threshold giữ nguyên 05A.

## 15. Research integrity và limitations

Có **25 actual Qwen calls**: v1 12, v2 12 + resume 1. Không mock inference, không LLM
judge, không human grading giả. Tất cả 317 protected paths từ audit 06A-R không đổi;
Git diff xác nhận old source/artifacts/README được giữ, model hash vẫn khớp.

Giới hạn: chỉ 4 fresh homogeneous benign files, cùng DEV reused sau repair, goal
imports được đặt sẵn, cùng LIEF backend với detector, cap 64/visible 24, phase/citation
failures lớn, chưa đánh giá diversity/packed PE/third-party/malicious. Published labels
không là blind holdout. Heuristic suspected flags có false positives/negatives; literal
matching không chấm completeness/semantic support/actionability. Human grading PENDING,
confirmatory NOT_RUN, malicious RAW_PE_E2E BLOCKED_NO_APPROVED_SAMPLES.

Dataset, contracts, source/config/input/model/tool pins được freeze trước mỗi lượt
live. Sau khi xem v1 mới sửa v2: đó là DEV repair, không “independent improvement”.
Archived source snapshots để tái lập lịch sử, không tự chạy source archive như trusted
tool code. Runtime staging chứa PE copies được `.gitignore` bảo vệ; chỉ publish text
artifacts/metadata/provider JSON/receipts/ledger, không PE hoặc model binaries.
`.gitattributes` chỉ scope 06B results `-text`: repo bật core.autocrlf, nên cần tránh
Git tự đổi line endings làm hỏng byte hashes của frozen artifacts khi publish/clone.

## 16. Engineering outcome

**ENGINEERING PASS cho required live demonstration**: Qwen proposal → Controller →
D1–D9 real execution/validation/commit → new revision → next turn visible evidence →
final có old/new IDs và hai facts khớp source. Read-only/security regression PASS.
Không gọi toàn workflow robust hoặc production-ready: valid final chỉ 1/4 C v2 và
current post-live guards chỉ có unit/integration evidence. Default production v1 giữ nguyên.

## 17. Research outcome

**RESEARCH PARTIAL.** Có một minh họa Agent trả lời câu hỏi imports cụ thể hơn static
template/one-shot thiếu data. Chưa có bằng chứng cải thiện investigation value tổng
thể trên tập chưa tune, đúng mức uncertainty hoặc recommendation quality. Alignment
vẫn insufficient, classifier label không đổi. Không suy detection accuracy gain.

## 18. TASK 06C đề xuất và tái lập

Ưu tiên phase-aware/citation-constrained contract và typed numeric coverage, nhưng
không dùng constraint ép reasoning/corroboration. Bổ sung retrieval/pagination có
information budget rõ để Agent đọc phần detail đã commit khi cần, tránh thêm nhiều
analyzer chỉ để tăng tool count. Hardening native-parser/network/memory isolation cần
security design riêng trước malicious raw PE. Không triển khai các phần đó ở 06B.

Confirmatory tương lai: fresh authorized corpus, goals đa dạng và no-tool cases được
định nghĩa trước; freeze config trước inference; labels/mapping ở evaluator storage
tách quyền khỏi Agent, không public trước grading. Human rubric mới tách observed
fact support / query relevance / changed verification plan / proportionate decision,
độc lập với template rubric cũ. Không reuse 4 DEV, 2 reserve đã public, 120/16/20/24
cases cũ làm blinded confirmatory proof.

```powershell
python -m evaluation.task06b.experiment prepare --out evaluation/task06b/results/new_dev_version
python -m evaluation.task06b.experiment run --out evaluation/task06b/results/new_dev_version
python -m evaluation.task06b.experiment summarize --out evaluation/task06b/results/new_dev_version
python -m pytest evaluation/task06b/tests -q -p no:cacheprovider
```

Không resume/overwrite dev_v1/v2 bằng current source: freeze phải reject source drift.
Auditor `evaluation/task06b/tests/audit_results.py` kiểm source snapshots/initial
hashes/receipts/ledger/literal use; output đã lưu ở `results/artifact_audit.json`.
Writer exclusive-create bảo toàn artifacts, nên audit/summary cũng cần output version
mới nếu muốn chạy lại. Báo cáo này và các rendered views không phải model inference.
