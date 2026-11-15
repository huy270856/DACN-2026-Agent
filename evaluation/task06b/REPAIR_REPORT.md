# TASK 06B-R — finalization reliability và committed-evidence retrieval

## 1. Git và phạm vi

Branch `feat/task06b-real-multistep-investigation`, base reviewed
`bfdfd80a828eb8ce2ce88f8226a6fc7e1298d3bc`; fetch xác nhận origin cùng SHA,
main vẫn `8011eaf1768aae08850d6dd8951a9984fa073be7` và base chứa 06A-R.
Working tree ban đầu sạch. Không merge, rebase, reset, push. Commit delivery xem Git
HEAD (không tự nhúng SHA của chính commit vào nội dung được hash).

Chỉ opt-in `--agent-mode multistep-repair`; default `v1`, đường `multistep` cũ,
detector/model/threshold, D0/D1–D9, Node B/C, analyzer giữ nguyên. Không analyzer mới,
fine-tune, containment, PE execution, hoặc sửa root README/old benchmarks.

## 2. Audit source và raw failures lịch sử

Đã đọc report/protocol/audit và source snapshots 06B, raw turns B/C v1/v2,
`01_final_report.md`, JUnit; workflow/context/schema/grounding/application/imports
adapter/normalizer, agent controller/planner/config/context/loop, dacn investigation,
Node C revision apply, D0 import contracts và D4/D9/trust liên quan.

| Raw trace | Bằng chứng | Root cause |
|---|---|---|
| DEV v1 C cả4 | done_reason=length; prompt+output=8192, JSON unterminated | context/output window, không chỉ parser yếu |
| DEV v1 B 00/01/02 | tool ID không đăng ký | decoder capability mask chưa có |
| DEV v1 B03 / v2 B00 | cite `unknowns` như evidence ID | metadata không phải source ID |
| DEV v2 C00 | import mới trong old IDs, is_new đã hiện trong prompt | model phân loại metadata sai, workflow bắt model lặp lại deterministic phase |
| DEV v2 C02 | thiếu old_evidence_ids | FORMAT decoder required chỉ5 common keys; parse() thêm điều kiện FINISH sau inference |
| DEV v2 C03 | wrong phase, đồng thời ID thiếu ký tự ở claim | phase validation chạy trước nên che lỗi citation kế tiếp |
| DEV v2 C01 | 64 returned vs24 visible; `null` symbol; prediction self-corroboration | coverage/prose và literal semantics sai, FINISHED không đồng nghĩa semantic-grounded |

IDs cite trong failures không được sửa gần đúng; có ID tồn tại state nhưng omit
trong projection, không được coi model đã thấy. V2 có is_new nên không quy toàn bộ
phase failure cho thiếu projection. Provider64 là committed payload, không phải64
facts visible trong prompt24. JSON contract chung còn cho field irrelevant vào
actions khác, gây token waste và sai phase ở REQUEST_MORE không được kiểm đầy đủ.
Production Ollama transport đưa schema cả system text và format; giữ nguyên behavior
này, không tăng num_ctx. Rút ngắn context/action contract thay vì bỏ validation.

## 3. Repair contract và trusted metadata

`repair_schema.py`, `repair_context.py`, `repair_finalization.py`, `repair_workflow.py`
là module versioned riêng. Không reinterpret/revalidate lịch sử thành “success”.

Trusted layer sở hữu revision/target/source/value digest/tool_run/phase và counts;
old/new derivation chỉ từ tập IDs raw model thực sự cite. Agent tự viết assessment,
claim/source/entry selection, uncertainty/raw recommendation, change explanation,
stop reason. `claim_literal_bindings` đính kèm entry đã chọn, không tạo claim mới.
DLL/symbol hoặc #ordinal phải có trong text claim và đúng visible entry/source.
Wrong/unknown/invisible IDs, entry hoặc missing source bị reject; không normalize
`"null"` thành API, không silent drop unsupported claim.

Tách action selection và final authorship từ v3.2: selection FINISH chỉ yêu cầu
chuyển stage, chưa phải accepted report. Final schema required đầy đủ theo branch.
Parse → structural → case/revision → visible refs → source/literal → consistency
→ final rendering. Semantic support rộng hơn literal matching vẫn PENDING.

Một repair trên same evidence, original raw/error/context giữ riêng; không tool
dispatch trong repair/final stage, không retry DENY. Token/time budget chung, không
vòng sửa vô hạn. Hết budget/invalid final → `INVESTIGATION_INCOMPLETE`, trusted
MANUAL_REVIEW/human=true; `final=null`, không pretend Agent FINISH. Flagged final
giữ nguyên semantic text, gắn `FINISHED_FLAGGED`, không gọi fully grounded success.

## 4. Retrieval và trust boundary

Chọn model-requested bounded pagination, không keyword rank network/curl. Có so
sánh thiết kế trusted selector: ít lượt hơn nhưng áp sẵn relevance heuristic, khó
kiểm completeness/order bias; không chọn trong repair này. Declaration order ổn
định, initial16 và tối đa2 read requests×16; max48 distinct visible trong64 committed.
Chỉ đọc state đã validate từ trusted case path, không nhận path/file/provider/shell
từ model. `READ_EVIDENCE` là view operation, không raw-target tool và không bypass
D1–D9 analyzer. Không reparse PE, không evidence ID mới hoặc revision/D9 mutation.

`retrieval.fetch`: case/revision/target SHA/source ID/value hash/status/tool_run
ràng buộc; bounded offset/limit, explicit provider_total_entries / committed_entries /
visible_entries, index/offset/next_offset. Không retrieval ngoài64 provider đã commit;
failed/absent evidence không fetch được. Repeated page không thêm indices bị chặn.
Page liên kết original source và hash, giữ UNTRUSTED_CONTENT; không trusted instruction.

Analyzer vẫn read-only pinned cùng tool/version/arguments, Controller/D4/D7/D8/D9
cũ thực thi. Không network/shell code mới trong retrieval; chưa có OS firewall/RSS
isolation cho native parser, không nâng tuyên bố hardening vượt source.

## 5. Dataset và leakage

Quy tắc chọn ghi trước Qwen: danh sách42 System32 cố định, VALID Microsoft,
≤8MiB; loại SHA và probe12-prefix trong JSON artifacts 05C/05D/06A/06B. Có39 rich
candidates, **0 small≤16**. Chọn3 rich đầu, không fabricate small/ordinal samples.

| DEV mới | SHA-256 | Provider total imports |
|---|---|---:|
| tracert.exe | 415e7396bdbde474719b20bb5704489a2333bb45f7f0f2ca677af4d125078a67 |65|
| findstr.exe | 867816f8a714a87f5f573ebbe3a526931fbe787cc03b4ec7ac8a970c9d8c0264 |102|
| fc.exe | f4d29fd93794e50a6740b9692da5dcad119d0f5a68a812357497c69ed6496ce3 |112|

Prepare inspect chỉ để phân tầng evaluator; initial state không có imports và
Qwen không được đọc manifest labels. Inference hash-check manifest, parse cases
sanitized; detector label fallible không ground truth. Labels benign theo OS/signature
không chứng minh vô hại tuyệt đối. Không copy PE/model binary vào Git.

A static template; B repair one-shot; C reviewed legacy module không đổi; D repair.
Mỗi arm riêng state/artifacts cùng initial bytes/prediction; B initial immutable.
Counterbalance C/D theo index. Max C3turns, D5turns, B1final ban đầu hoặc3turns với
selection/final/repair; không budget-equivalent per-turn comparison. New contract,
projection/retrieval/stages là treatment kết hợp, không causal ablation riêng lẻ.

Freeze source snapshot exact bytes/hash, inputs/config/protocol/pins/versions trước
mỗi run. `repair_dev_v1` prepare lỗi parent directory, **chưa Qwen**, không overwrite.
`repair_dev_v2` rồi `repair_dev_v3` dùng cùng3SHA sau feedback, rõ ràng DEV tuning,
không independent holdout. Current config không được resume các freezes source cũ.

## 6. Failures đã giữ và error analysis

`repair_dev_v2`/v3.1: C3/3 có tool+commit+FINISH; D3/3 final structural, nhưng D0/3
tool selection;2/3 flagged,1 final sau repair observed thiếu source. Tracert D nói
“no imports declared” khi chưa có source: semantic regression. Không coi success
count này là cải thiện điều tra. B3/3 final đều suspected/consistency flagged.

`repair_dev_v3`/v3.2: stage separation giúp D chọn analyzer; source/Controller
contract mismatch 4-vs3 evidence_refs làm mất repair budget, literal/source binding
failures còn lại bị chặn. Kết quả chi tiết và phiên bản sửa contract cuối ở phần sau.
Resume là cùng state đã commit, không sample độc lập; tool lặp bị chặn. Không
re-run cho tới may mắn rồi che failures. Không semantic judge/human grading giả.

## 7. Tests và giới hạn interpretation

Unit/integration dùng scripted planner ghi MOCK_LLM, real adapter/D1–D9 riêng;
không nhận mock chọn tool là autonomous live. Tests historical raw giữ nguyên,
missing fields/JSON/enum/phase IDs/source/literal null/numeric/entropy/prediction,
retrieval bounds/stale/foreign/target/hash/missing/failure/order/ordinal/coverage,
no file IO/state mutation, next-turn index20,1 D9, DENY no retry, clock budget,
injection treated data, LLM offline/fallback và repair exhaustion.

Intermediate failures: prelive timeout test dùng Windows coarse clock dưới1tick,
đổi sang deterministic mocked monotonic; prepare parent folder thiếu được sửa
trước inference; preserve JUnit và thư mục lỗi, không fake PASS. Regression output
ghi riêng cho mỗi vòng; final test evidence ở phần kết quả cuối.

Semantic relevance/actionability, claims trong prose không có literal typed binding,
false positives/negatives của heuristic, coverage completeness cần reviewer. Không
gọi “grounded 100%” hay “hallucination confirmed” từ regex. Missing small/ordinal-live,
homogeneous signed benign corpus, fixed goal và3samples giới hạn rất lớn.
Human grading PENDING; confirmatory NOT_RUN; malicious RAW_PE_E2E
BLOCKED_NO_APPROVED_SAMPLES. Không detection improvement/generalization claim.

## 8. Kết quả phiên bản cuối v3.3 / repair_dev_v4

| Metric, mẫu số3 mỗi arm | A Static | B One-shot | C Legacy tool-enabled | D Repair tool-enabled |
|---|---:|---:|---:|---:|
| Accepted Agent final | N/A (template3) |0/3|1/3|0/3|
| First-pass accepted final |N/A|0/3|1/3|0/3|
| REQUEST_MORE kết thúc an toàn |N/A|3/3|0/3|0/3|
| Analyzer requested/executed/committed |N/A|0/3|3/3|3/3|
| New evidence visible next turn |N/A|0/3|3/3|3/3|
| Revisions |initial3|3→3|3→5|3→5|
| Bounded repair attempts |0|1 tổng|0|3 tổng|
| Model-requested retrieval |0|0|N/A|0/3|
| Accepted new-literal uses |N/A|0|3 (legacy literal-only check)|0|
| Effective review load |template policy|3/3|3/3|3/3|
| Mean E2E, giây |1.792|7.125|23.542|40.125|
| Prompt/output tokens tổng |0/0|11428/976|28685/4212|49992/7930|

Mẫu số accepted final tính trên tất cả cases, không bỏ failures. C/D validators
khác nhau: D thêm claim-index/literal-source binding, nên accepted-final totals
không là một semantic quality metric ngang bằng. C cũng có suspected/consistency
flags dù status FINISHED. Không so0/3 với historical1/4 rồi suy generalization.

Tổng actual Qwen calls ở cả repair versions = **72**: v3.1 13, v3.2 28, v3.3 31
(bao gồm C/B/D và các resume). Không phải72 independent samples. Cùng Qwen digest
`d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`, Ollama0.40.16,
Python3.12.10, thinking OFF, temperature0.1, seed42, num_ctx8192, num_predict2048.
Model hash/threshold giữ nguyên. Local money/energy cost N/A. Một số regression
chạy đồng thời inference (v3.1/v3.2, cuối v3.3 resume), nên latency là observed DEV
wall time, không dedicated performance benchmark. Tool count thấp không tự tốt;
nhanh hơn do failure sớm không là success.

## 9. Exact trace, thất bại từng ca và literal accuracy

Tracert D: [00_D.json](results/repair_dev_v4/00_D.json), case
`CASE-8d973aaae72348c1bfa9894ed517ca57`. Qwen nhận prediction nhưng chưa imports;
tự nêu gap “Current evidence lacks declared imports…”, TOOL_CALL qua Controller,
actual D1/D4 ALLOW/D5-D6 receipt/D7 validated/D9 committed. Run
`RUN-57fb4141cd21425ca11a0db14dc4e63b`, evidence
`EV-189e330fdc6d4fa2808012616911d0f5`. Một D9 commit, registration revision4 rồi
commit revision5, không hai evidence commits. Next actual Qwen context revision5
thấy16/64 committed declarations, provider total65. Sau FINISH selection là final
authorship và1 repair, cuối cùng `final=null`/MANUAL_REVIEW. Không gọi đây là complete
autonomous-final success.

| Case | C cuối | D cuối và nguyên nhân |
|---|---|---|
| tracert |phase new-fact không nằm new group|first final bind memcpy/fwprintf với claim1/2 thay vì claim0; repair bỏ literal nhưng vẫn bind entries → reject|
| findstr |FINISHED, legacy literal uses3|bind free với claim không nêu free/DLL; còn bind prediction evidence như imports → reject|
| fc |wrong old/new group|bind entry0 _fmode với general DLL claim; repair chọn memmove nhưng text _exit/sprintf; source mismatch ở claim prediction → reject|

Audit **tất cả original+repair final attempts D**:1/18 bindings literal-match;
resume3/18,0/3 accepted, không additional tool/D9 commit, revision5→5. Đây là
association check của typed raw claims với actual visible source, **không** chỉ
đếm valid IDs; chưa semantic accuracy tổng thể. Không suy17 confirmed invented
APIs: có names đúng nhưng model gắn sai claim_index/source, hoặc chỉ viết general
claim rồi chọn entry không nêu literal. Không tự đổi claim_index về0 dù suy đoán
model định làm vậy. Correct raw binding vẫn giữ để audit, không được silent drop
invalid bindings rồi báo final success.

Observed new facts từ analyzer:64 committed declarations/case chưa có initial;
chỉ16 visible/case. Chưa có accepted new-fact use của D, không chứng minh query
relevance/semantic value từ tool success. Qwen chọn FINISH thay READ_EVIDENCE0/3,
không giả retrieval live PASS. Với fake planner, integration thật chứng minh đọc
indices16–31 sau D9 và final cite index20; đó là **INTEGRATION PASS / MOCK_LLM**.

## 10. Final verification, preservation và tái lập

41 repair tests pass trước live cuối. Full regression cuối:
**616 passed,4 skipped,81 subtests,71.99s**, artifact
[repair_v4_regression_delivery.xml](results/repair_v4_regression_delivery.xml).
4 skipped thuộc gated legacy live2, symlink privilege và optional memory test;
không claim chúng live PASS. Không rerun legacy STATIC_FIRST live test rồi báo fixed.

Auditor [repair_audit.py](results/repair_audit.py) là deterministic post-hoc,
không inference/judge; output [repair_artifact_audit_v2.json](results/repair_artifact_audit_v2.json).
Kiểm source snapshots exact bytes/hashes, initial freeze hashes, cùng initial
state B/C/D, receipt/result/runID/target joins, actual D9 evidence/new visibility,
typed claim/source/entry literals,317 protected paths không đổi và Git diff old
modules/artifacts sạch. `repair_artifact_audit.json` trước đó đặt tên metric
`unflagged_status` sai cho legacy C; v2 sửa tên `status_FINISHED_count`, giữ original
audit, không sửa raw inference. FINISHED cũ không đảm bảo không grounding flags.

Precommit screen kiểm binary magic/NUL, extension allowlist và known credential
patterns: không hit; runtime PE staging bị ignore, không model/raw dataset binaries
được stage. Đây không phải full DLP guarantee. Kiểm36 initial artifact hashes của
3 repair freezes trực tiếp trên Git index đều khớp, giữ CRLF nguyên byte nhờ results
`-text`; whitespace check dùng `cr-at-eol`, không sửa artifact để làm sạch diff.

```powershell
python -m pytest evaluation/task06b/tests -q -p no:cacheprovider
python -c "from pathlib import Path; from evaluation.task06b.repair_experiment import validate; validate(Path('evaluation/task06b/results/repair_dev_v4'))"
```

Validate programmatically bằng `repair_experiment.validate(Path(out))` cho version
cuối khi source hiện hành khớp freeze; old freezes phải từ chối source drift. CLI
chỉ prepare/run/summarize, không giả có validate action. Không dùng prepare/run vào
thư mục đã frozen; exclusive outputs bảo vệ failures lẫn successes. Muốn chạy
auditor lại cần output filename mới; không overwrite audit cũ.

## 11. Kết luận kỹ thuật và nghiên cứu

**ENGINEERING PARTIAL / RESEARCH PARTIAL.** Contract/retrieval/fail-safe implementation
có unit+real-adapter integration evidence; live Qwen proposal→D9→next-turn hoạt động,
nhưng accepted final0/3 và live retrieval0/3. Không đạt finalization reliability
improvement, không promotion production. Safety fallback minh bạch hơn không đồng
nghĩa investigation quality tốt hơn. Bộ mã cung cấp prototype có thể review, không
phải production-ready hoàn chỉnh.

Không mở rộng06C trong lượt này. Nếu tiếp tục, ưu tiên giảm cross-array association
burden (nested per-claim references thay claim_index), thiết kế câu hỏi dừng/retrieval
cụ thể hơn và semantic human review độc lập. Phải freeze version/dataset mới trước
inference, không biến3DEV này hoặc corpus public cũ thành confirmatory holdout.
Future holdout: blind inputs và evaluator labels tách quyền/storage, không labels
trong prompt/repo trước grading; rubric riêng fact support/query relevance/uncertainty/
verification plan/proportional action, công bố negative/regression cases. Human
grading vẫn PENDING. Chờ technical review, không tự push hoặc merge.
