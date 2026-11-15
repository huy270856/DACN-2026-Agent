# TASK 06A — Evidence-Driven Agent Investigation v2

Ngày thực hiện: 15/11/2026. **TASK 06A: PARTIAL**.
Engineering: assessment prototype, kiểm tra nhất quán, DEV runner và regression đã
triển khai/chạy thật; chưa promotion vào production. Research: **PARTIAL**, chưa có
bằng chứng v2 cải thiện chất lượng điều tra tổng thể hoặc khả năng bắt lỗi detector.
Không coi việc tăng abstention/review là thành công nghiên cứu.

## 1. Repository, phiên bản và phạm vi

- Ban đầu working tree sạch, đã ở branch `feat/task06a-evidence-driven-agent-v2`,
  HEAD `6b418d347dffdb5535f715360ea82e53f203f327`. Khác context bàn giao: đã có một
  commit 06A core, chưa có DEV ablation. Tiếp tục commit này, không tạo/ghi đè branch.
- `git fetch origin` đã chạy; `origin/main = edd0a255cddcc40499f988cf806ed78505dbca8a`.
  Local `main = 16b9fc1` còn cũ (PR #10); không checkout/reset/merge cập nhật local main.
  `git diff edd0a25 ba22e78` rỗng: hai mốc có cùng tree, không giả chúng là cùng commit.
- Production v1, `dacn/`, D0/D1–D9, model, threshold, artifacts 05C/05D và top-level
  README không đổi. Có hash trước/sau trong `results/dev_v2_1/freeze.json` và
  `validate_freeze()`. Không push/merge/force-push/reset/clean.
- Báo cáo core kế thừa được giữ tại `REPORT_INHERITED_6b418d3.md` để truy nguyên;
  các kết luận đã sửa bên dưới thay thế nhận định trong báo cáo đó. Lượt live 1 record
  do báo cáo cũ kể lại không có raw artifact ở thư mục results ban đầu: không tính
  là inference được kiểm chứng ở lượt này. Có 48 responses mới để kiểm chứng độc lập.

Môi trường xác minh trước inference: Windows 11 `10.0.26300`, Python `3.12.10`,
LightGBM `4.5.0`, NumPy `2.5.4`, jsonschema `4.26.0`, pytest `9.2.0`, Ollama
`0.40.16`; `qwen3.5:4b` digest
`d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`.
Model binary 05A có thật; SHA kiểm lại khớp
`5db192ec1bda850d0e1873af705b57d05aad414aa35e8520c8315ece1c509609`.
Threshold giữ nguyên `0.8321860386013389`; không retrain/calibrate.

## 2. Source và artifacts đã đọc

- `agent/{context,controller,loop,planner,schema,report,config}.py`.
- `dacn/{application,investigation}.py`; D0 tool-call schema;
  `orchestrator/{core,registry,workflow,policy_engine,trust}.py` và các tests D1–D9.
- `evaluation/task05c/{runner,agent_replay,evidence_projection,metrics,sampling}.py`;
  repair `agreement_bias.py`, `annotation_v2.py`, `triage.py`, báo cáo repair;
  `repair/results/agreement_bias.json`, locked audit manifest và saved sample outputs.
- `evaluation/task05d/{pilot,claude_judge}.py`, REPORT, grading method audit,
  validation aggregate/samples và pilot evidence sheets/branch mapping.
- 05A model manifest, dataset audit, dataset loader, chronological split source;
  binary model và dataset files local; toàn bộ 200.000 SHA test được quét trực tiếp.
- Core 06A kế thừa và tests; sau đó đọc lại đủ 24 cặp responses mới để phân tích
  cờ và chọn ví dụ minh họa. Không chấm điểm semantic cho chính implementation này.

## 3. Trả lời tám câu hỏi audit và root causes

1. **Prediction có bắt buộc đồng thuận không?** `agent/context.py:97–110` gọi
   static **label** AUTHORITATIVE và yêu cầu không override. Nhưng câu ngay sau
   cho phép cả CONSISTENT, CONFLICT và INSUFFICIENT_EVIDENCE. Vì thế không đúng nếu
   kết luận source *bắt buộc alignment CONSISTENT*. Có anchoring mạnh về cách trình
   bày; label giữ nguyên và alignment là hai vấn đề khác nhau.
2. **Có thể trả CONFLICT không?** Có, trong prompt và decode schema
   (`agent/schema.py:45`), controller không cấm alignment CONFLICT. Probe đã lưu
   đổi prompt cho 16/16 CONFLICT nhưng alternative outputs không đạt strict schema;
   không có bằng chứng prompt này đúng hơn. 120/120 CONSISTENT là quan sát đầu ra,
   không phải luật bắt buộc của schema hay chứng minh mỗi ca sai về alignment.
3. **Có phân supporting/contradicting/unknown không?** V1 chỉ có alignment,
   review_required, recommendation, explanation tự do; không có claim-level binding
   hay list hai chiều. `validate_shape()` cũng không strict-validate nested assessment
   như JSON Schema đầy đủ; constrained decoding không thay thế validation runtime.
4. **CONSISTENT có thể chỉ là thiếu phản chứng?** Có nguy cơ và có câu trả lời chỉ
   viện prediction/PE thông thường làm căn cứ. Nhưng một FN + CONSISTENT không đủ
   chứng minh evidence được cung cấp có phản chứng mà Agent đã bỏ qua. Ground truth
   không được dùng để ép Agent bất đồng. DEV cho thêm ví dụ cụ thể ở mục 7.
5. **Vì sao review/recommendation trái nhau?** Model sinh các field độc lập;
   `dacn/investigation.py:206–237` nhận structured assessment, bool-coerce review flag,
   không cross-check recommendation. Final application recommendation còn được derive
   riêng (`derive_recommendation`): raw Agent suggestion và đề xuất trusted có thể khác.
   Repair 05C đã chuẩn hóa review hậu kiểm nhưng không sửa reasoning production.
   Cần luôn báo raw bool, action-normalized review và effective guardrail riêng.
6. **Có evidence bị cắt không?** Có. `context.py:32–51` cắt JSON-string value ở
   800 ký tự, có inline `[truncated]`; `54–96` pop cả evidence để giữ 12.000 chars.
   Cờ `context_truncated` chỉ cho trim toàn context. Các `limitations`/provenance
   của projection không được chuyển đầy đủ qua `_summarize_evidence`. `has_real_prediction`
   được tính trước khi pop nên có thể true ngay cả khi prediction observation bị drop.
   Controller kiểm ID trong **toàn state** (`controller.py:72`), không riêng phần nhìn
   thấy. Đây là vấn đề projection/provenance, không chỉ lỗi LLM.
7. **Production loop khác replay?** Production `loop.py` kiểm budget/revision,
   validate bằng controller, gọi orchestrator, rồi đọc lại Node C sau D9 (`:130`).
   05C `run_agent_once()` chỉ parse action một lượt, không đi qua controller hay D1–D9,
   tools=[]; substantive own verdict có thể lọt replay nhưng bị controller production
   chặn khi thiếu trusted reputation (`controller.py:95–102`). DEV mới cũng là replay.
8. **Đã chứng minh tự chọn analyzer bổ sung trên real PE chưa?** Chưa. Backend thật
   `dacn/investigation.py:89–140` chỉ register/allowlist `static.pe_malware_predict`.
   Application chạy tool đó trước agent (`application.py:344–362`), prompt yêu cầu
   FINISH khi có prediction. Controller loop vẫn có khả năng dispatch tool theo
   contract; không được suy rằng module loop luôn one-step. Lịch sử pre-agent call
   không seed vào `_seen_toolcalls` của controller mới: chưa có bảo đảm riêng chống
   gọi lại detector đã chạy trước Agent. Không có evidence mới từ analyzer bổ sung.

Root causes được chứng minh: prompt anchoring; schema thiếu cấu trúc evidence;
runtime validation thiếu cross-field checks; projection mất dữ liệu/ngữ cảnh;
replay không tương đương production; và rubric/judge có sai sót thực chất.

## 4. Kiểm lại những cáo buộc lỗi trong 05D-J

Script tái lập: `python -m evaluation.task06a.analysis.audit_legacy`.
Artifact: [legacy_reaudit.json](results/legacy_reaudit.json). Không thay điểm/outputs cũ.

| Pilot ID | Đối chiếu source/evidence | Kết luận audit |
|---|---|---|
| S-7c2ea2e8f0 | `crm*.bpl` có trong original imports, sheet và reconstructed prompt | Không được gọi riêng tên CRM là hallucination; suy luận “standard/benign” và “exports” vẫn cần căn cứ riêng |
| S-37cfb6694f | `MFC42.DLL` có ở cả ba lớp; count entropy≥7 = 1 | Cáo buộc tên MFC không có trong sheet là sai |
| S-bf43ef03ff | `ExitProcess`, `MoveFileA` có ở cả ba lớp | Cáo buộc hai API bị bịa là sai; MONITOR trên malicious prediction vẫn là vấn đề theo policy |
| S-5327b8b93a | Claim “high entropy sections”; count≥7 = 0 | Claim không được hỗ trợ theo định nghĩa entropy≥7 của protocol |

Ở cả bốn phiếu còn có cited prediction ID thiếu trong annotation evidence sheet,
nhưng có thật trong reconstructed CaseState. `annotation_v2._evidence_sheet()` chỉ
nhận projection không gồm prediction observation. Đây là lỗi annotation/provenance;
không thể phạt tất cả những ID ấy như LLM bịa ID. Reconstructed prompt không phải
HTTP payload lịch sử đã lưu, nên kết luận được giới hạn đúng ở source reconstruction.

`claude_judge.py` vẫn default điểm 2 + overrides được hard-code, không gọi API/model.
Không có đủ traces repository xác minh inference độc lập từng phiếu. Kết quả đó
chỉ là PROVISIONAL EXPLORATORY FEEDBACK, không human evaluation hay reproducible
independent LLM benchmark. Những sửa sai audit ở trên cũng không phải một lượt chấm mới.

## 5. Implementation v2.1 và compatibility

Toàn bộ additive trong `evaluation/task06a/`; không thay production v1:

- `schema_v2.py`: contract `task06a-assessment-v2.1`; supporting/contradicting IDs,
  uncertainty notes, qualitative assessment confidence và claims có type OBSERVED /
  HYPOTHESIS / LIMITATION / NEXT_VERIFICATION. Không thêm own detection verdict;
  prediction bất biến, chỉ đánh giá mức evidence hỗ trợ. Strict schema, extra fields
  bị reject. Mỗi claim OBSERVED phải có nguồn để qua claim screen.
- `assessor_v2.py`: protocol trung lập, không default CONSISTENT hay ép CONFLICT;
  không dùng prediction để tự corroborate; phân unknown/failed/truncated với
  contradiction. Dùng chính facts v1 sau cắt context, cùng cấu hình Ollama.
  Bind case ID/revision, giữ full raw responses kể cả malformed, lỗi timeout rõ ràng.
- `verification.py`: chỉ kiểm IDs/values trong **facts thực sự đã đưa cho LLM**;
  nhận biết JSON value không hoàn chỉnh; kiểm specifics của OBSERVED trên các nguồn
  claim trích; gắn cờ self-corroboration. Output ghi rõ
  `semantic_grounding=NOT_ESTABLISHED_RULE_SCREEN_ONLY`.
- `grounding.py`: giữ heuristic kế thừa làm screen chung; sửa missing/truncated
  section count từ zero giả thành UNKNOWN. Lexicon/regex chỉ bắt một lớp lỗi, có
  false positive/negative; `grounded=true` cũ chỉ nghĩa là screen không phát hiện lỗi.
- `consistency.py`: kiểm nhãn/score/threshold hữu hạn, enum, near-threshold trong
  raw-score space, malicious+MONITOR, conflict/insufficient thiếu review. Invalid hoặc
  inconsistent output → MANUAL_REVIEW có lý do; không silent MONITOR. Effective
  review được derive từ action, requires_human_decision=true, NOT_EXECUTED.
  Raw suggestion/flags còn nguyên để audit. Không thay label/score, không containment.
- `experiment.py`: prepare/freeze/run/resume/summarize; config/source/data/model drift
  bị reject, artifacts inference không overwrite. Ghi alternating arm order và cả
  parser acceptance lẫn strict decoding-schema acceptance. Analysis scripts riêng
  đọc artifacts sau DEV, có source hash; không phải inference/judge.

Không cần migration D0/CaseState hay sửa CLI: v2.1 là assessment prototype riêng,
chưa được gọi trong `python -m dacn investigate`. Schema core v2.0 trong commit kế
thừa đã đổi thành v2.1 rõ version; consumers prototype phải dùng schema mới có
claims. Không drop-in một assessment v2.1 thành ToolCall hay production Finding v1.

Security boundaries: D4 vẫn deny-by-default, D5 chỉ pinned adapter/target,
D7 validates result, D8 giữ key/approval, D9 revision-bound commit. Core gọi D3/D4
trước execute và sign/commit sau result validation (`orchestrator/core.py:129–212`).
Không thực thi PE, shell từ LLM, bypass policy, tải malware, quarantine/kill process,
fake tool result, fake model inference hay fake human score.

## 6. DEV và leakage controls

[PROTOCOL.md](PROTOCOL.md) được viết trước inference; code/config được hash/freeze
trong [freeze.json](results/dev_v2_1/freeze.json).

- Nguồn local đã có quyền sử dụng từ nghiên cứu 05A: EMBER2018 v2 train shard 1;
  chọn 12 label 0 + 12 label 1 đầu tiên sau dòng 1000, bỏ trùng SHA. Không chọn bằng
  score hoặc đầu ra Agent. Ghi source file digest, line, canonical-record hash,
  appeared, prediction và provenance. Không tải dữ liệu mới.
- Quét trực tiếp toàn `test_features.jsonl`: 200.000 unique SHA; overlap DEV = **0**.
  SHA với mọi JSON artifacts 05C/05D = **0**; các probe 12-char thuộc official test
  cũng được loại nhờ kiểm toàn test. Pilot/05D-J được bao phủ trong artifacts cũ.
- DEV là **detector-related convenience sample**, không độc lập với quá trình fit /
  validation detector. Chưa chứng minh disjoint với những lần inference không lưu.
  Ground truth chỉ ở `manifest_EVALUATOR_ONLY.json`, không nằm trong state/prompt.
  Runner đọc `inputs.json`, chỉ kiểm digest manifest, không mở nội dung nhãn khi inference.
- Sau selection/inference: TN 12, TP 11, FN 1, FP 0. Không sửa selection để làm đẹp strata.
  Không dùng DEV này báo detection benchmark hoặc tune threshold. Chỉ đọc ground truth
  trong supplementary evaluator diagnostics, sau khi responses đã lưu.
- Cùng evidence facts, model digest/threshold, config, tools=[], 1 attempt/arm,
  temperature 0.1, seed 42, think=false, num_predict=1536, num_ctx=8192, timeout=180s.
  Schema/prompt thay đổi nên đây là ablation **gói protocol**, không tách causal effect
  của từng thành phần. Không retune prompt sau khi xem DEV rồi chạy lại chính set.

48 raw responses và exact context nằm ở `results/dev_v2_1/responses/`; projection /
prediction tại `inputs.json`. Không có D9 commit mới trong replay; nguồn là feature
record, không giả signed tool evidence. Artifacts cũ được hash kiểm lại sau regression.

## 7. Kết quả paired DEV (Qwen thật)

Nguồn máy đọc: [summary.json](results/dev_v2_1/summary.json). Các metric có chữ
“screen” là heuristic chưa adjudicate semantic; không gọi chúng là error rate đã xác nhận.

| Metric | Frozen v1 | V2.1 |
|---|---:|---:|
| Parser accepted / attempts | 24/24 | 24/24 |
| Strict decoding schema valid | 24/24 | 24/24 |
| Cases có structured citations | 24/24 | 24/24 |
| Valid visible IDs / refs | 72/72 | 105/105 |
| Cases invalid IDs | 0 | 0 |
| Common prose grounding screen có cờ | 6/24 | 8/24 |
| Suspected unsupported specifics, heuristic count | 7 | 7 |
| Decision inconsistency theo pre-defined checks | 5/24 | 1/24 |
| Raw review_required | 24/24 | 23/24 |
| Effective guardrail review load | 11/24 | 24/24 |
| Invalid/missing recommendation | 0 | 0 |
| Non-FINISH action | 0 | N/A: assessment-only contract |
| Alignment CONSISTENT / CONFLICT / INSUFFICIENT | 24 / 0 / 0 | 1 / 0 / 23 |
| Latency trung bình / attempt | 4,613s | 6,370s |
| Tổng prompt tokens do Ollama báo | 64.073 | 62.273 |
| Tổng output tokens do Ollama báo | 9.167 | 13.497 |
| Tool calls executed / validity | 0 / N/A | 0 / N/A |

17/24 cases mỗi nhánh có value bị cắt. Claim-specific screen của v2 có cờ ở 18/24
cases, nhiều cờ do nguồn không hoàn chỉnh; v1 không có claim structure nên metric
này **N/A** cho v1, không dùng số zero trong JSON summary làm so sánh chất lượng.
Valid IDs 100% không chứng minh nội dung claim đúng; v2 có nhiều refs hơn nên không
so counts trực tiếp như evidence quality.

Latency tăng khoảng **38%**, output tokens tăng khoảng **47%**. Chi phí USD N/A vì
inference local; không ước tính năng lượng hoặc chi phí tiền không được đo.

Diagnostic bổ sung sau DEV theo mapping review 05C-R2 tại
[supplemental_audit_EVALUATOR_ONLY.json](results/dev_v2_1/supplemental_audit_EVALUATOR_ONLY.json):
raw review bool khác action-normalized review ở **18/24 v1**, **1/24 v2**. Đây là
metric bổ sung hậu kiểm, không lẫn vào metric decision flags đã đăng ký trước.
Effective output đã derive review từ action nên không giữ hai giá trị trái nhau.
SUSPICIOUS own verdict xuất hiện **7/24 v1**; replay parser chấp nhận nhưng không
được suy thành production controller sẽ chấp nhận khi không có trusted reputation.

Với đúng **1 FN**, raw review bool v1 flag FN và cả 23 correct (specificity=0);
v2 flag FN và 22/23 correct (specificity=1/23). Action-normalized review sensitivity
v1=0/1, v2=1/1; specificity v1=17/23, v2=2/23. Effective v2 review **mọi ca** nên
error-review specificity=0. Không có bằng chứng Agent đã nhận ra *đúng lỗi detector*;
review bao phủ FN ở đây chủ yếu do abstention/review rộng. Không suy detection gain.

## 8. Error analysis: cải thiện, thoái lui và lỗi của checker

All-pair flags được giữ trong summary và supplementary audit, không chỉ các ví dụ tốt.
Theo pre-defined screens: decision flags biến mất ở 5 cặp, mới xuất hiện ở 1 cặp;
grounding-screen flags biến mất ở 3 cặp, xuất hiện ở 5 cặp. Đây là thay đổi cờ,
không phải kết luận semantic thắng/thua.

| Case / response index | Quan sát có thể kiểm tra |
|---|---|
| `73f7e703b11d…` / 005 | V1 malicious prediction nhưng MONITOR; v2 MANUAL_REVIEW, không còn decision flag. V1 nói high-entropy sections trong khi count≥7=0; v2 không lặp claim đó trong explanation. Claim header/TLS của v2 vẫn cần nguồn riêng; không gọi toàn phiếu đã đúng |
| `cf74f8750866…` / 012 | V1 MONITOR trên malicious → v2 MANUAL_REVIEW. Nhưng v2 OBSERVED claim nói “high probability” từ raw score: vẫn sai về giải thích và screen chung bỏ lọt vì chỉ đọc prose, chưa quét đủ claim semantics |
| `135fd5c9d6eb…` / 006 | V2 INSUFFICIENT nhưng review=false/MONITOR; guardrail ép MANUAL_REVIEW có lý do. Cả hai nhánh còn diễn giải low raw score như thiếu confidence: không được dùng như probability/confidence |
| `f6b277d80f95…` / 004 | V2 gọi `.neolit=6.608`, `.rsrc=3.611` là high entropy; count≥7=0. V1 không có claim cụ thể này. V2 đã có claim type nhưng vẫn trộn fact với hypothesis |
| `66784c4dfc31…` / 009 | Screen đánh cờ runtime “command-and-control” khi prose v2 nói **không tìm thấy** chỉ dấu đó. Đây là false-positive heuristic, không thể báo v2 bịa runtime chỉ vì regex có cờ |
| `3d24293d08d8…` / 019 | Ca CONSISTENT duy nhất v2 vẫn dùng prediction ID trong supporting list; bị `prediction_used_as_own_corroboration`. Standard PE/no debug/imports không đủ tự chứng minh benign |
| `2d5ec1bff4b4…` / 015 (FN) | V1 CONSISTENT, v2 INSUFFICIENT/review. Không có targeted detector-error discovery: v2 cũng abstain trên 22 ca khác |

Xem đầy đủ response theo index ở `responses/NNN_v1.json` và `NNN_v2.json`.
Các prefix ở bảng chỉ để đọc; trường sha256 đầy đủ trong artifact là khóa dữ liệu.
Numeric/string/source-specific mistakes
ngoài lexicon, claim phủ định và nguồn bị cắt vẫn cần semantic review độc lập.

## 9. Tests thực tế và kết quả live

- Initial sandbox regression: **512 passed, 1 failed, 4 skipped**, 79 subtests.
  Failure D8 DPAPI `CryptProtectData`; giữ tại `results/regression.xml`.
- Chạy lại riêng DPAPI ngoài sandbox: **1 passed**, `dpapi_unrestricted.xml`.
- Final regression ngoài sandbox, sau thêm tests artifacts: **515 passed, 4 skipped**,
  79 subtests; `regression_unrestricted.xml`. Phạm vi Node B, Node C, D0/D1–D9,
  Agent, DACN, 05A, 05B, 05C, repair/R2, 05D và 06A. Không gọi 4 skip là pass.
- 06A riêng: **44 passed**, `task06a_controls_final.xml`. Bao gồm supported/wrong-source
  specifics, entropy contradiction/insufficient/truncated/failed evidence, unknown
  IDs, injection framing, unknown recommendation, review mismatch, raw score/threshold,
  false-confidence pattern, malformed JSON, stale binding, transport timeout, provider
  unavailable, DENY altered-arguments không retry, no GT và frozen baseline preservation.
  Mock/unit tests được gắn đúng vai trò; không tính là real inference.
- Live Qwen tests bật bằng `DACN_AGENT_LIVE=1`: **1 passed, 1 failed** tại
  `live_regression_valid.xml`. `tests/test_task05b.py::LiveQwenE2E` với benign PE thật
  qua detector/D1–D9/CaseState/Qwen pass. `tests/test_agent.py::LiveQwenE2E` đường
  legacy với minimal PE fixture fail: Qwen chọn FINISH liên tiếp trước static follow-up,
  controller chặn STATIC_FIRST và trả ERROR/repeated_rejection sau 3 iterations.
  Giữ `live_legacy_trace.json`; không nới security policy hoặc rerun tới khi may mắn pass.
  Production source đường này không thay, chưa đủ căn cứ quy failure cho code v2.
- Một lệnh thử sai tên test class tạo `live_regression.xml` (no tests ran); giữ để
  minh bạch nhưng **không** tính nó vào test evidence. Lệnh đúng và kết quả nằm ở file
  `live_regression_valid.xml` nêu trên.

Không chạy lại benchmark 200.000 model predictions hay 35-PE suite để giả có số mới;
05A/05D metrics cũ giữ nguyên provenance. DEV 48 inference là thật. Human grading
cũ/mới vẫn **PENDING**. Malicious RAW_PE_E2E vẫn **BLOCKED_NO_APPROVED_SAMPLES**.

## 10. Giá trị Agent, limitations và quyết định về 06B

V2 cho representation có thể audit hơn và giảm một lớp decision inconsistencies
trên DEV; guardrails bắt được một số raw LLM mistakes. Đây là giá trị **engineering**
đã quan sát. Chưa chứng minh Agent tạo investigative insight có ích hơn template,
phát hiện đúng detector errors, hoặc cải thiện semantic explanation. Phần reasoning
vẫn có lỗi và abstention gần đồng nhất; detector không đổi nên detection metrics
không đổi. Không gán công của deterministic checks cho năng lực Agent.

Rubric v1 05D giữ nguyên; rubric v2 investigation value/actionable specificity mới
chỉ **đề xuất, chưa chấm**, xem PROTOCOL. Rule screen không phải judge ngữ nghĩa.
Không có tín hiệu grounding/value đủ tin cậy để chạy rồi tuyên bố confirmatory win;
confirmatory **NOT_RUN**, research PARTIAL. Nếu phát triển tiếp phải dùng freeze mới
và holdout chưa dùng tune, không sửa prompt rồi báo chính DEV này là tổng quát hóa.

Blockers ưu tiên trước promotion/06B thực nghiệm:

1. Projection giữ typed fields quan trọng, provenance/limitations, truncation rõ ràng;
   kiểm đúng nguồn từng claim, phục hồi cited prediction trong annotation sheet.
2. Kiểm semantic claim/numeric/API/probability trên tất cả claim types; evaluator
   độc lập đánh cả false positives của checker, tránh regex phạt giả thuyết/phủ định.
3. Khắc phục failure planning STATIC_FIRST trên đường legacy mà vẫn giữ policy;
   seed lịch sử pre-agent tool run và dừng lặp công cụ không tạo evidence mới.
4. Sau đó, nếu cần 06B: chọn **một analyzer tĩnh read-only** hữu ích (imports/sections
   hoặc strings sâu hơn), contract/provider pinned + allowlist qua D1–D9; không thêm
   node, không Ghidra/REA/sandbox trong 06A. Chứng minh proposal hợp lệ → execute →
   validated result → D9 revision tăng → context vòng sau thấy evidence mới. Đo cả
   FINISH khi hết tool hữu ích và đề xuất xác minh còn thiếu thay vì loop.
5. Đóng băng cấu hình, chọn holdout được phép và independent human rubric v2 trước
   inference; không dùng lại 120/16/pilot hay DEV hiện tại làm confirmatory evidence.

**Sẵn sàng thiết kế phạm vi 06B từ findings: có. Sẵn sàng tuyên bố multi-step
autonomous investigation hoặc mở rộng mạnh production: chưa.** TASK 06A được bàn
giao với kết quả DEV mixed, live legacy failure và hạn chế semantic nêu rõ, không
gắn PASS nghiên cứu để che những phần chưa được chứng minh.

## 11. Tái lập

```powershell
python -m evaluation.task06a.experiment prepare --out evaluation/task06a/results/new_dev_version
python -m evaluation.task06a.experiment run --out evaluation/task06a/results/new_dev_version
python -m evaluation.task06a.experiment summarize --out evaluation/task06a/results/new_dev_version
python -m pytest evaluation/task06a/tests -q -p no:cacheprovider
```

Không chạy prepare/summarize đè `dev_v2_1`; writer dùng exclusive create. Run có
resume, bao gồm giữ nguyên failures, từ chối drift source/model/data. Paths model /
dataset local hiện tại được ghi trong code/manifest; model binary không nằm trong
Git. Xem commit chứa báo cáo này bằng `git log -1 -- evaluation/task06a/REPORT.md`.
