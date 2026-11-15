# TASK 06B-R2 — Thiết kế lại gốc rễ khâu finalization: evidence-native claims (v3.4)

> Kết quả tóm tắt: **ENGINEERING PARTIAL↑ / RESEARCH PARTIAL.** Hợp đồng v3.4 loại
> bỏ *từ thiết kế* lớp lỗi association đã chặn mọi final v3.3. DEBUG live (đúng 3 file
> phát triển, **không** confirmatory): structural-accepted first-pass **3/3, 0 repair**
> (v3.3 D: 0/3), lần đầu có **live retrieval 1/3** (v3.3: 0/3). Nhưng **cả 3 là
> FINISHED_FLAGGED → MANUAL_REVIEW** (clean grounded **0/3**) do Qwen-4B đưa prediction
> vào supporting_evidence_ids (self-corroboration) — screen bắt đúng. Accepted-structural
> ≠ grounded. Chưa có holdout/human grading.

## 1. Branch + commit
`feat/task06b-real-multistep-investigation`, HEAD vào việc `97744288e872ff320a4c4f0f6bfacb1f4874f845`.

## 2. Git initial state
`git status` sạch; `git fetch origin` xác nhận local HEAD = remote branch =
`97744288`; `origin/main` = `8011eaf1768aae08850d6dd8951a9984fa073be7` (chứa 06A-R
qua PR #13). Không reset/clean/force/merge/push. Working tree sạch trước khi sửa.

## 3. Source files audited
`REPAIR_REPORT.md`, `REPAIR_PROTOCOL.md`, `PROTOCOL.md`, `REPORT.md`; raw turns
`results/repair_dev_v4/{00,01,02}_D.json` + `_resume.json` + contexts; `repair_schema.py`,
`repair_finalization.py`, `repair_context.py`, `repair_workflow.py`, `retrieval.py`,
`imports_tool.py`, `import_adapter.py`, `schema.py`, `workflow.py`, `context.py`,
`grounding.py`, `application.py`; `agent/{controller,planner,schema,config}.py`;
`evaluation/task06a/{schema_v2,verification,grounding}.py`; `repair_experiment.py`.
Git state khớp bàn giao → source dùng làm căn cứ.

## 4. Historical failures verified (raw)
3/3 ca D v3.3 cùng quỹ đạo: TOOL_CALL ✓ → D9 commit ✓ (rev 3→5) → chọn FINISH ✓ →
**final-authorship reject → 1 repair → reject → `final=null`/MANUAL_REVIEW**
(`failure=VALIDATION_REPAIR_EXHAUSTED`). Trích raw:
- **tracert 00_D turn2**: `CLAIM_SOURCE_BINDING`. claim[1] (prediction, `ev=EV-2147…`)
  bị gắn `import_bindings[1]={claim_index:1, evidence_id:EV-189e…(imports), entry 1}`
  → binding trỏ imports nhưng claim chỉ cite prediction.
- **tracert 00_D turn3 (repair)**: model *tổng quát hoá* claim[0] (“standard C runtime
  functions”, bỏ literal) nhưng binding vẫn trỏ entry 0 (`exit`) → `CLAIM_LITERAL_MISMATCH`.
- **fc 02_D turn3**: claim nêu `_exit/sprintf_s` nhưng binding `entry_index=14` (symbol
  khác) → literal mismatch.
- Audit REPAIR_REPORT §9: **1/18** binding literal-match trên mọi final attempt D.

## 5. Bảng root-cause (đã xác minh bằng raw)
| # | Nguyên nhân gốc (kiến trúc, không phải triệu chứng) | Raw evidence |
|---|---|---|
| RC1 | **Parallel-array over-binding**: `import_bindings` là mảng cấp cao giải mã tách khỏi `claims`; Qwen phát ~1 binding/claim, kể cả claim prediction/limitation vốn không có import. | 00_D turn2 `CLAIM_SOURCE_BINDING` (prediction claim bị gắn import entry) |
| RC2 | **Literal-in-text coupling**: validator (`repair_finalization.py:35`) buộc library+symbol xuất hiện nguyên văn trong `text`, *xung đột* với chính yêu cầu claim tổng quát/trung thực của prompt. | 00_D turn3 tổng quát hoá → mismatch; 02_D turn3 nhồi literal vẫn mismatch |
| RC3 | **entry_index guessing**: model phải vừa chọn index 0–63 vừa phản chiếu literal của đúng entry đó vào prose; không map được symbol→index. | 02_D turn3 prose `_exit/sprintf_s` vs binding entry 14 |
| RC4 | **Repair không hội tụ**: 1 lượt sửa trên cùng facts → viết lại cả cụm, đổi lớp lỗi này sang lớp lỗi khác. | cả 3 ca turn2→turn3 đổi error class, 0 accepted |
| RC5 | **Retrieval không được chọn (0/3)**: coverage 16/64 có hiển thị nhưng affordance chưa đủ; model khẳng định absence thay vì đọc thêm. | 0/3 `READ_EVIDENCE` |
| RC6 | **Trùng lặp ID list**: evidence_refs + per-claim evidence_ids + supporting/contradicting + import_bindings cùng mang ID → overhead token/nhất quán. | contract v3.3 |

Join 3 chiều `claim_index ↔ evidence_id ↔ entry_index` + literal-in-text vượt khả
năng duy trì quan hệ của model 4B ở đây (1/18 literal-match). Giả thuyết của đề bài
được xác nhận bằng raw, không phải suy đoán.

## 6. Schema v3.3 vs v3.4
| | v3.3 | v3.4 (`final_v34.py`) |
|---|---|---|
| Liên kết claim–import | mảng `import_bindings[]` cấp cao + `claim_index` | `import_refs[]` **bên trong** từng claim, không `claim_index` |
| Literal trong prose | **bắt buộc** library+symbol trong `text` | **bỏ**; trusted layer resolve để hiển thị |
| Claim prediction/limitation | vẫn bị model gắn binding | không có `import_refs` (đúng cấu trúc) |
| Kiểm tra ref | claim_index→evidence_id→entry + literal | ref.evidence_id ∈ chính evidence_ids của claim + imports-facet + entry visible (kiểm 1 object) |
| new_fact_uses | model tự chép library/symbol | trusted layer dẫn xuất từ ref (bỏ bề mặt chép-chuỗi) |
| Giữ nguyên | — | evidence visible, OBSERVED-có-nguồn, self-corroboration/absence/entropy flags, 1 repair, MANUAL_REVIEW, Controller/D1–D9, retrieval 2×16, tách 2 stage decoding |

## 7. Vì sao redesign tốt hơn về cấu trúc
RC1 biến mất *bằng cấu trúc*: ref sống trong claim → không có mảng song song để nhồi;
claim prediction/limitation đơn giản không có ref. RC2/RC3 biến mất: không còn ràng
buộc literal-in-text, model chỉ *trỏ* vào entry nó đang nói tới; việc chọn entry là
*hành vi ngữ nghĩa của model*, trusted layer chỉ tra cứu (vd fc: prose “exit” vs resolve
`msvcrt.dll!_exit` — v3.3 sẽ hard-reject, v3.4 chấp nhận và đưa cả hai ra cho người
review). RC4 giảm vì số lớp hard-reject giảm mạnh. Đây đúng là “contract mới loại bỏ
một lớp lỗi association từ thiết kế”, kiểm chứng được bằng test, không cần live.

## 8. Cơ chế LLM chọn claims/sources
Prompt v3.4 (`final_v34.SYSTEM`) nêu thứ tự suy luận 7 bước và quy tắc grounding; model
tự viết `text`, tự chọn `evidence_ids` (nguồn thật visible) và tùy chọn `import_refs`
(trỏ entry imports của chính claim). Không có keyword-ranker, không hard-code network/curl.

## 9. Trusted metadata vs LLM reasoning
Trusted ĐƯỢC: xác định phase INITIAL/COMMITTED_DURING_RUN; resolve entry→library/symbol/
#ordinal; gắn value_sha256/phase; kiểm reference visible & thuộc claim; dẫn xuất
new_fact_uses; chạy screen grounding/consistency; đặt MANUAL_REVIEW. Trusted KHÔNG:
bịa claim, tự quyết một import = malicious, tự viết supporting/contradicting, sửa text
model, chọn API thay model. `resolved_import_refs` là **source resolution**, tách bạch
khỏi semantic assertion; `llm_assessment` giữ nguyên văn model.

## 10. Tool execution trace (DEBUG live)
3/3: `D1_TOOL_CALL → D4(ALLOW) → D5_D6_RECEIPT → D7_VALIDATED → D9_COMMITTED →
ORCHESTRATOR_RETURN`; fc thêm `COMMITTED_EVIDENCE_READ`. `planner_kind=LOCAL_QWEN`
(không mock). Analyzer read-only pinned `static.pe_imports_detail` v0.1.0, không execute/
network/shell/containment.

## 11. Evidence commit / revision
Mỗi ca: registration rev 4 rồi commit rev 5 (3→5), **đúng một** D9 commit, không commit
kép, không D9 cho retrieval. 16/64 visible sau tool; fc đọc thêm 1 trang → 32/112 visible.

## 12. Finalization validity (DEBUG live) — con số trung thực
| File | status | final | first-pass | repairs | tools | reads | resolved_refs | new-fact uses | action |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| tracert | FINISHED_FLAGGED | ✓ | ✓ | 0 | 1 | 0 | 2 | 2 | MANUAL_REVIEW |
| findstr | FINISHED_FLAGGED | ✓ | ✓ | 0 | 1 | 0 | 0 | 0 | MANUAL_REVIEW |
| fc | FINISHED_FLAGGED | ✓ | ✓ | 0 | 1 | 1 | 2 | 2 | MANUAL_REVIEW |

- **Structural/parser accepted first-pass: 3/3, 0 repair** (v3.3 D: 0/3, 3 repair tổng).
- **Clean grounded (unflagged): 0/3.** Cả 3 FINISHED_FLAGGED → MANUAL_REVIEW.
- Không có `CLAIM_SOURCE_BINDING`/`CLAIM_LITERAL_MISMATCH`/`claim_index` nào xảy ra
  (`turn_errors=[]`). Lớp lỗi association đã biến mất trong lượt này.

## 13. Claim/source/literal accuracy
Ref resolve đúng nơi dùng: tracert claim[0]→`msvcrt.dll!exit`, `msvcrt.dll!memcpy`
(entry 0,1); fc claim[1]→`msvcrt.dll!_exit`, `msvcrt.dll!sprintf_s` (entry 7,13), đều
`COMMITTED_DURING_RUN`. fc cho thấy giá trị thiết kế: prose “exit” vs resolve “_exit”
được chấp nhận và phơi bày cho review thay vì hard-fail. **Semantic accuracy tổng thể =
PENDING_INDEPENDENT_REVIEW** (rule screen không phải semantic judge).

## 14. Retrieval behavior
**Lần đầu có live retrieval: fc reads=1** (đọc entry 16–31, bounded ≤2×16, không D9,
không reparse PE, UNTRUSTED_CONTENT). tracert/findstr chọn FINISH không đọc thêm. Không
ép retrieval; báo trung thực 1/3. Chưa đủ dữ liệu để kết luận “biết cách vs không cần”.

## 15. First pass vs repair
First-pass accepted (structural) 3/3; **repair dùng 0/3** — khác hẳn v3.3 (repair cạn
3/3, 0 accepted). Repair bounded vẫn còn trong code cho lỗi cấu trúc thật; test phủ.

## 16. Latency / tokens (DEBUG live)
| File | agent latency | E2E | prompt tok | output tok | LLM calls |
|---|---:|---:|---:|---:|---:|
| tracert | 23.1s | 24.4s | 12491 | 1682 | 3 |
| findstr | 17.3s | 18.6s | 12383 | 1388 | 3 |
| fc | 25.1s | 26.3s | 18382 | 2018 | 4 |
| **Tổng/TB** | TB 21.8s | **TB 23.1s** | **43256** | **5088** | **10** |

**Confound (bắt buộc công bố)**: lượt v3.4 chạy **độc lập một mình**, trong khi v3.3 D
trong frozen eval chạy xen kẽ B/C/D + resume trên cùng một Ollama → mean E2E thấp hơn
(23.1s vs 40.1s) **một phần do môi trường**, không thuần do thiết kế. Không coi đây là
performance benchmark.

## 17. Regressions / failures
Không `turn_errors`, không `failure`, không repair. 10 lần gọi Qwen thật — không phải
10 mẫu độc lập. Flag duy nhất: `prediction_used_as_own_corroboration` (3/3).

## 18. Unit / integration / live results
- Unit + MOCK_LLM: `test_v34.py` **26 passed** (structural, resolution, honesty, bounded
  repair/fail-safe, D1–D9-thật-rồi-final evidence-native). MOCK ≠ autonomous.
- task06b suite: **99 passed**. Full repo regression: **649 passed, 4 skipped, 81
  subtests** (4 skip = gated legacy-live/symlink/optional, không claim live PASS). Không
  drift module v3.3.
- Live Qwen: 3/3 structural-accepted first-pass, 3/3 FLAGGED, 1/3 retrieval (DEBUG).

## 19. Frozen artifact integrity
Không chạm `repair_dev_v4` và mọi frozen 05/06. Chỉ thêm file mới:
`investigation_v3/final_v34.py`, `workflow_v34.py`; `evaluation/task06b/{tests/test_v34.py,
r2_debug.py, R2_PROTOCOL.md, R2_REPORT.md}`; output mới `results/r2_debug_v34/` (exclusive,
freeze.json ghi base commit + source/prompt/model hash). Không sửa root README, model
binary, threshold.

## 20. Generalization limitations
DEBUG dùng **đúng 3 file phát triển** tracert/findstr/fc → **không** independent,
**không** confirmatory (NOT_RUN), **không** suy rộng real-world. 1 lượt, benign đồng nhất,
goal cố định, model 4B. Treatment là *kết hợp* (contract + prompt + chạy độc lập), không
phải ablation nhân quả riêng lẻ. Human grading PENDING; malicious RAW_PE_E2E
BLOCKED_NO_APPROVED_SAMPLES.

## 21. Engineering outcome
**PARTIAL, cải thiện có bằng chứng.** Hợp đồng evidence-native loại bỏ lớp lỗi
association *từ thiết kế* (chứng minh bằng 26 test + regression không drift), và trong
DEBUG live nâng structural-accepted first-pass từ 0/3 → 3/3 với 0 repair, lần đầu có
live retrieval. Vẫn là prototype review được, chưa production-ready: clean-grounded 0/3.

## 22. Research outcome
**PARTIAL.** Chưa chứng minh Agent tạo giá trị điều tra *grounded* bổ sung: cả 3 final
bị flag self-corroboration → MANUAL_REVIEW; semantic relevance PENDING; không holdout,
không human grading. “3/3 structural-accepted” **không** phải research win; đó là bằng
chứng engineering về độ tin cậy *cấu trúc* của khâu finalization.

## 23. Có nên tiếp 06C hay dừng đánh giá lại?
**Dừng để đánh giá lại trước khi mở 06C.** Lỗi gốc cấp cấu trúc đã xử lý; blocker còn
lại là **model-semantic 4B** (self-corroboration, abstain/over-claim) và thiếu
**semantic human review + independent holdout** — không giải được bằng thêm analyzer/schema.
Đề xuất kế tiếp (phiên sau, freeze mới, không đụng 3 file DEV này): (a) human grading
rubric (fact support / query relevance / uncertainty / proportional action); (b) holdout
mù, label tách prompt/repo; (c) khảo sát prompt chống self-corroboration *đo được* (không
tuning để che flag); (d) cân nhắc so sánh model lớn hơn cho nghiên cứu — **không** âm thầm
đổi Qwen rồi gán cải thiện cho schema.

---
*Phân biệt nhất quán: parser/structural-accepted ≠ clean-grounded ≠ semantic-verified.
Rule screen ≠ human grading. MOCK_LLM ≠ live autonomy. DEBUG-trên-DEV ≠ confirmatory.
Không che negative; không `success=true` khi validation reject; chờ review, không tự push/merge.*
