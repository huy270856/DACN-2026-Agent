# TASK 06B — protocol DEV v1, trước live inference

Base: `origin/main=8011eaf` (PR #13 đã merge, chứa 06A-R `eb34ee4`).
Mục tiêu: xác minh một vòng điều tra thật qua D1–D9; không tăng detection accuracy.

## Gap audit và lựa chọn analyzer

Node B (`context_collector.py:238`) tuyên bố không thu imports/entropy/signature
trust. Detector adapter 05B trả prediction + extractor/model metadata, **không**
commit `pe_extractor.raw['imports']` vào CaseState. Projection 05C chỉ thuộc feature
replay (30 libs, 60 functions), không phải evidence production. V1 stringifies/cắt
value ở 800 chars; v2.1 dùng cùng facts đó. Chọn **một** analyzer detailed imports:
đọc PE staged một lần qua LIEF, cung cấp DLL/symbol/ordinal và coverage rõ ràng.
Không gọi feature extractor/model lần nữa, không sections/strings analyzer thứ hai.

Câu hỏi điều tra cố định cho B/C: “Những DLL/API import cụ thể nào hỗ trợ hoặc giới
hạn giả thuyết về khả năng network/process của PE? Điều gì vẫn chưa biết?” Imports
chỉ là khả năng tĩnh; không chứng minh đã chạy hoặc malware. Đây là goal do workflow
tin cậy đặt ra, không phải lời nhắc bắt buộc gọi tool. FINISH/request thiếu evidence
được phép; không inject sẵn tool result vào initial prompt.

## Security và workflow dự kiến

Opt-in workflow mới, giữ mặc định CLI v1. Dùng lại Controller/D1–D9/Node B/C hiện có.
Tool `static.pe_imports_detail`, input cố định `max_entries=64`, không nhận path,
command hoặc provider override từ LLM. Native parser đọc tối đa 8 MiB, output cap
64 KiB, timeout 10s, max artifacts 128 KiB; D5 pinned Python/adapter/parser binary,
verified staging/target binding, Windows process resource budgets. Không execute PE,
không code path network, không shell/containment. D4/D8 không được nới lỏng. Không
claim có OS network isolation nếu executor hiện tại không cung cấp firewall boundary.

Typed projection: evidence ID/facet/status/source/provider/CaseState revision,
structured value/limitations/coverage/truncation/full-detail ref. Budgeted explicit
omission, không biến missing thành 0. Chỉ cited visible IDs mới được chấp nhận.
Vòng lặp seed các tool đã thực thi từ persisted state; không gọi lại detector hoặc
analyzer đã hoàn tất. Chỉ offer provider khả dụng và D4 ALLOW. Tool proposal vẫn
đi qua controller và D4 thật, không dùng discovery như authorization thay thế.

Trace tách LLM proposal / controller acceptance / D4 authorization / D5 receipt /
D7 validated result / D9 commit / revision change / next context visibility /
final assessment. Không suy consumption/semantic use chỉ từ commit hoặc citation.

## Ablation và data

A = static prediction + fixed template, B = one-shot Agent, C = tool-enabled Agent.
B/C cùng initial CaseState/typed projection/question/model/config; C có thêm tool
availability và tối đa một analyzer attempt. C có nhiều inference turns nên budget
và token/latency overhead phải báo, không gán tác động riêng cho prompt/schema.
Schema assessment v2.1 được tái sử dụng trong action contract version mới; không đổi
v2.1/schema hay outputs lịch sử. Planning/loop/projection mới là treatment kết hợp.

DEV: chọn 4 PE Microsoft-signed VALID mới từ danh sách System32 định trước trong
runner, bỏ mọi SHA có trong JSON artifacts 05C/05D/06A. Ghi source/signature/SHA/size,
file digest và overlap audit. Không label/strata/signature-derived benign truth vào
prompt; evaluator label benign theo provenance, không chứng minh tuyệt đối vô hại.
Reserve 2 SHA kế tiếp chưa chạy model/Agent làm ứng viên holdout; không gọi đây là
confirmatory benchmark trước khi có rubric độc lập và protocol xác nhận riêng.
No-tool resume: sau C thành công, đọc chính CaseState đã commit, chạy Agent thêm
một lượt với tool đã completed bị loại; giữ initial state và run riêng, không tính
là independent paired sample. Failure/DENY cases dùng test fixtures, gắn MOCK/INTEGRATION.

Freeze trước inference: source/config/prompt/schema/analyzer pins/model digest,
initial cases/projections/manifest, Qwen digest/version. Một attempt mỗi model turn;
max 3 iterations C, 1 iteration B; không retry model/schema failures đến khi may mắn.
Không sửa prompt sau DEV rồi dùng chính set đó chứng minh generalization. Nếu cần
version mới phải giữ nguyên trace cũ và ghi exploratory/dev-only.

## Metrics và information gain

- Valid proposal / tool proposals; D4 ALLOW/DENY; D5 success; D7 validation;
  D9 commit và số revision increment (auto-registration có thể tăng thêm revision).
- Distinct **literal import facts** `(DLL, symbol/ordinal, normal/delay)` trong tool
  result chưa nằm trong initial visible context. ID mới/nội dung duplicate không là gain.
- Query relevance: facts liên quan câu hỏi network/process chỉ là heuristic flag
  (API family lexicon), không là evidence malware hay semantic value đã xác nhận.
- Grounded new use: trích ID mới **và** literal claim được đối chiếu đúng DLL/API
  trong cited new visible evidence. Báo hỗ trợ literal riêng, hypothesis/actionability
  và assessment update cần semantic review độc lập; citation đơn thuần không là gain.
- Repeats/no-new-facts; unavailable/error/timeout/DENY; report whether assessment
  actually changed, why stopped; raw vs trusted effective decision consistency.
- Latency từng turn/end-to-end/tool execution, prompt/output tokens, tool overhead;
  local USD cost N/A. Grounding flags suspected/unverified. Human grading PENDING.

Acceptance engineering chỉ khi actual Qwen đề xuất tool, actual read-only execution,
D7/D9 success, revision tăng, next turn thấy evidence mới và final report phân biệt
old/new; thiếu bất cứ bước nào → PARTIAL. Không mock thành autonomous demonstration.
Research PASS cần independent semantic/confirmatory evidence, không suy từ 4 DEV
benign hay một demo. Malicious RAW_PE_E2E BLOCKED_NO_APPROVED_SAMPLES.

## DEV v2 — sửa engineering sau kết quả v1 (không confirmatory)

V1 đã chạy đủ 4 cặp, giữ nguyên trong `results/dev_v1`: C chọn đúng tool và commit
4/4, nhưng final JSON đều bị cắt do chạm num_ctx=8192; B bịa tool khi tools=[].
Source snapshot exact bytes của v1 được giữ cùng freeze, không rewrite hashes.

V2 dùng lại chính 4 DEV SHA; không tuyên bố independence/generalization. Trước live
v2: projection bỏ 3 facets không phục vụ câu hỏi (metadata/readable/unchanged), có
omitted IDs rõ; chỉ chiếu tối đa 24 import declarations trong khi CaseState/provider
vẫn giữ 64. Counts gốc không bị sửa, có projected_entries/projection_truncated và
full-detail ref. Giới hạn value 4000 chars, không string-cut JSON. Muốn khẳng định
absence cần coverage đầy đủ, không được dùng phần đã cắt. New facts committed và
facts visible/use phải báo riêng.

Schema-aware decoding mask bỏ TOOL_CALL khi tools=[], pin identity tới registry khi
chỉ có một tool. Khi tool có mặt **FINISH vẫn được phép**: không có deterministic
forcing gọi analyzer. Controller/D3/D4 vẫn kiểm độc lập, không tin decoder là policy.
Giữ nguyên schema assessment v2.1, prompt SYSTEM, budgets/model/threshold. Freeze
source/config/input mới ở `results/dev_v2`. Cải thiện completion nếu có chỉ là DEV
engineering repair, không phải nghiên cứu confirmatory. Không chạy reserve.
