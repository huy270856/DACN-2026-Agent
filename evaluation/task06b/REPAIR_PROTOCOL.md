# TASK 06B-R — protocol trước live inference

Base reviewed `bfdfd80a828eb8ce2ce88f8226a6fc7e1298d3bc`, branch 06B; main
`8011eaf1768aae08850d6dd8951a9984fa073be7`. Giữ nguyên toàn bộ kết quả cũ.

## Root causes và treatment đã định trước

V1 C: 4 JSON bị cắt, done_reason=length, tổng prompt+output=8192. V2 C:
00/03 phase sai, 02 thiếu old_evidence_ids; decoder không required FINISH fields
nhưng runtime validator yêu cầu. Có phase is_new trong projection nên không thể
quy tất cả lỗi phase cho thiếu dữ liệu. V2 03 còn cite ID sai một ký tự, nhưng
phase check chạy trước và che lỗi citation. 01 được nhận nhưng null API, prediction
self-corroboration và nhầm returned/visible. Đây là lỗi contract/projection/model
khác nhau, không phải bằng chứng Qwen không có khả năng reasoning.

Repair v3.1 opt-in: action-specific required branches trong decoding và runtime;
trusted phase derivation chỉ trên IDs model thực sự cite; model vẫn tự viết claim,
chọn source/entry, uncertainty, change explanation và raw recommendation. Không
chuyển kết quả rejected lịch sử thành accepted. Không bỏ validator.

Retrieval: so sánh trusted keyword selector với model-requested page; chọn page
request vì không hardcode network/curl ranking. Giữ declaration order, initial16,
tối đa2 requests×16 đã commit (tối đa48 distinct visible), không raw PE/reparse,
không D9 commit mới. Ràng buộc case/revision/target/value hash/source ID; offset/limit,
counts phân biệt provider-total/committed/visible. Không hứa truy xuất ngoài64 đã commit.

Một repair cho format/citation/binding, lưu raw+error; không repair policy DENY,
tool error hay retrieval misuse thành execution. Trong repair tắt tool/retrieval;
chỉ same evidence. Max5 turns D (B max2 gồm1repair), one analyzer, shared180s/100k
tokens, output2048/turn, context8192 của transport giữ nguyên. C max3turns legacy.
Số turns là treatment confound được công bố; báo first-pass và after-repair riêng.

## DEV mới và ablation

Chọn trước Qwen: duyệt System32 theo danh sách cố định runner; chỉ Microsoft VALID,
≤8MiB; loại mọi full SHA/12-prefix probe có trong JSON artifacts 05C/05D/06A/06B.
Không chọn dựa Qwen output. Lấy3 rich (>16 imports) đầu,1 small (≤16) đầu nếu có;
nếu không có small trong danh sách ghi thiếu strata, không tạo PE giả thành real.
Chỉ inspect imports read-only để phân tầng DEV, kết quả này evaluator-only, không
đưa vào initial prompt; C/D vẫn phải tự yêu cầu analyzer thật qua D1–D9.
Ordinal nếu corpus không có thì unit synthetic ordinal với nhãn rõ.

A static template; B repair one-shot; C legacy workflow/schema/context tại reviewed
commit (những file này giữ nguyên); D repaired multi-step. C/D riêng CaseState clone
cùng initial bytes/prediction, execution artifact roots riêng; counterbalance C/D theo
index; B đọc immutable initial copy. Goal imports giống nhau. D nhiều turns/retrieval/
contract thay đổi: không tách causal effect từng thay đổi. Thêm no-tool resume chỉ
khi đã commit; không đếm như sample độc lập. Không tái chạy để che failures.

Freeze source bytes/hashes/config/inputs/protocol/model/Ollama/tool pins trước Qwen,
exclusive-create outputs; hash-check không parse evaluator manifest lúc inference.
Public DEV không blinded holdout; confirmatory NOT_RUN, human review PENDING,
malicious RAW_PE_E2E BLOCKED_NO_APPROVED_SAMPLES. Không LLM judge giả.

## Metrics định trước

Strict schema+binding final / all cases; flagged final riêng, không gọi full grounded
success. First-pass vs repair; unknown/not-visible/phase/literal errors; all raw
recommendations vs effective/human decision. Tool proposed/controller validated/D4/
D5/D7/D9/revision/next visible tách riêng. Retrieval requests/new entry indices/zero
new D9/repeated request rate. Literal new-fact use phải map claim/source/index và
DLL/symbol khớp đúng visible value; semantic relevance/coverage completeness cần
review độc lập. ID tồn tại không đủ. Grounding screen suspected/unverified, không
confirmed hallucination. Latency/tokens/retry/failures gồm tất cả attempts.

Không detection improvement/generalization claim. Sau DEV không chỉnh prompt rồi
báo cùng set là holdout. Nếu cần repair code sau kết quả, giữ version cũ và công bố.

## Phiên bản v3.2, trước lượt live tiếp theo

`repair_dev_v2` (v3.1) hoàn tất: C3/3 chọn tool và FINISH, D0/3 chọn tool;
D3/3 structurally complete nhưng2/3 flagged, một final sau repair observed thiếu
source. Đây là thoái lui tool selection, không gọi reliability improvement.
Prepare `repair_dev_v1` trước đó lỗi tạo parent directory, chưa gọi Qwen; không
ghi đè thư mục này. Một unit timeout ban đầu dùng clock quá nhỏ so Windows clock
resolution đã đổi sang mocked clock deterministic, không sửa budget production.

Tiếp theo `repair_dev_v3` dùng lại đúng3 DEV SHA (đã tune, không holdout). Tách
action selection ngắn khỏi final authorship. Model chọn FINISH chỉ chuyển sang
finalization stage; không được coi là accepted final. Mỗi actual call lưu riêng,
token/time/5-turn budget chung giữ nguyên; B tối đa3 turns gồm selection+final+repair.
FINISH/tool đều optional ở selection. Final contract chỉ cho FINISH/request-more;
không gọi tool trong repair hoặc final stage. Không tăng num_ctx. Thêm absence
claim heuristic suspected/unverified cho “no imports declared” khi không có source.
Không gán tool-selection regression chắc chắn cho branch-order nếu chưa có causal
ablation. Không hứa repair này cải thiện trước khi thấy raw results.

## Phiên bản v3.3 — narrow contract repair, lượt DEV cuối

v3.2 đã chạy đủ3 D và3 resume, tất cả final incomplete; tool commit3/3.
Schema cho phép4 evidence_refs nhưng Controller frozen chỉ3, cùng literal binding
errors khiến bounded repair hết. Đây là lỗi implementation repair, không đổ cho
model. V3.3 sửa duy nhất maxItems evidence_refs về3, thêm regression cho selection
và final. Giữ semantic validation, budgets, model, context, prompt và analyzer.
Freeze `repair_dev_v4` dùng cùng3DEV sau feedback, vẫn DEV-only. Chạy toàn bộ cặp
một lần theo freeze, không chọn lại ca có lợi, không tiếp tục prompt tuning sau
lượt này trong TASK06B-R. Báo nguyên kết quả dù không tốt hơn. Không suy causal
effect từ so sánh cohort historical4 với DEV3 mới.
