# TASK 07A — PROTOCOL (frozen trước live run)

| Hạng mục | Giá trị |
|---|---|
| Loại đánh giá | `DEV_DIAGNOSTIC` — **không** phải confirmatory. `confirmatory: NOT_RUN` |
| Track | `RAW_PE_E2E` (PE benign hệ thống, staged copy; không thực thi PE) |
| Planner | `LOCAL_QWEN` — `qwen3.5:4b` Q4_K_M, digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`, Ollama 0.40.16, loopback |
| Agent | investigation v3.4 **không đổi** (`investigation_v3/workflow_v34.py`, `final_v34.py`, `repair_context.py`) |
| Metric | Tất định (M1–M7), tính từ trace + manifest evaluator-only. **Không** phải semantic grading, không Judge |
| Authorization | `DACN_OWNER_TASK07A_DEV_DIAGNOSTIC` (owner, D4) |
| Nguồn thiết kế | `research/agent_architecture_review/PLAN_TASK07A.md`, `REPORT.md` §14 |

## 1. Cohort (D1)

- 20 case từ `evaluation/task06b_j/results/holdout/candidate_cases_v2_EVALUATOR_ONLY.json`
  (sha256 `file_sha` được ghi trong `variant.json` của mỗi run). Alias, SHA và `question_text` giữ
  nguyên.
- Cohort này đã "tiêu" ở confirmatory 06B-J run_v1; từ nay **chỉ** là DEV_DIAGNOSTIC và **không
  bao giờ** được dùng làm confirmatory.
- Phân lớp `accessibility_class`: IN_INITIAL_TOOL_PROJECTION 2 (0005, 0014);
  REACHABLE_BY_BOUNDED_RETRIEVAL 6 (0003, 0012, 0013, 0016, 0018, 0019); INACCESSIBLE_UNDER_LIMITS 4
  (0008, 0010, 0011, 0017); NOT_STATIC_ANSWERABLE 4 (0002, 0006, 0007, 0020);
  INITIAL_EVIDENCE_SUFFICIENT 4 (0001, 0004, 0009, 0015).
- Chỉ chạy **arm C** (tool-enabled).

## 2. Variant (cấu hình đầy đủ trong `evaluation/task07a/variants.py`, ghi lại trong `variant.json`)

Chung cho mọi variant: `max_iterations=5`, `max_tool_calls=1`, `max_context_chars=24000`,
`max_value_chars=800`, model/host như trên. Prompt, schema, validator v3.4 không đổi.

| Variant | Giả thuyết | think | temp | num_predict | num_ctx | inference_timeout_s | wall_clock_s | max_tokens | Sampling khác | Planner | Seed | Case |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **V0** | nhiễu / baseline (= `task06b_j.runner.CFG`) | off | 0.1 | 2048 | 8192 | 90 | 180 | 100000 | — (Modelfile) | `V34Planner` | 42, 7 | 20 |
| **V1** | H1 thinking native (E1) | **on** | 0.6 | 12288 | 24576 | 240 | 900 | 200000 | top_p 0.95, top_k 20, presence_penalty 0.0 | `V34Planner` | 42, 7 | 20 |
| **V2** | H1 analysis-first (E2) | off | 0.1 | 3072 | 12288 | 90 | 300 | 100000 | — | `AnalysisFirstPlanner` | 42, 7 | 20 |
| **V3** | H3 vs H2, ORACLE_DIAGNOSTIC (E4) | off | 0.1 | 2048 | 8192 | 90 | 180 | 100000 | — | `V34Planner` + `oracle_pages` | 42 | 8 (IN_INITIAL + REACHABLE) |

- **V2:** schema giải mã = `final_v34.contract(ctx)` cộng property `analysis` (string,
  1..1500 ký tự) **đứng đầu** và đứng đầu `required` ở mọi nhánh `oneOf`. Harness bỏ `analysis`
  trước khi `final_v34.parse` kiểm phần còn lại; analysis chỉ nằm trong `turn.meta`, không đưa lại
  vào prompt.
- **V3:** khi imports evidence đã commit (SUCCESS), harness thêm trang `((idx//16)*16, 16)` chứa
  entry liên quan đầu tiên (theo `relevant_entries` evaluator-only) vào danh sách trang mà
  `repair_context.build` chiếu ra. Dữ liệu vẫn đi qua `retrieval.fetch` (binding
  case/revision/SHA). **Không** đưa label, `relevant_entries`, reference answer hay văn bản
  evaluator nào vào prompt (D2). Với 0005 và 0014 entry liên quan nằm ở trang 0 nên V3 không thêm
  trang.
- **V1b** đã bị loại (owner, 2026-11-26).

**Confound đã biết (phải ghi trong báo cáo):**

1. V1 đổi cùng lúc thinking **và** sampling (temp, top_p, top_k, presence_penalty 0.0 so với giá
   trị ngầm 1.5 từ Modelfile ở V0/V2/V3). Hiệu ứng V1 không quy riêng cho thinking được.
2. V1 và V2 đổi `num_ctx`/`num_predict`. `num_ctx` chỉ có ý nghĩa nếu V0 bị tràn context (kiểm
   bằng M7 overflow).
3. Budget V1 được nâng sau smoke G1 (DEV, ngoài cohort), trước freeze.

## 3. Metric (`evaluation/task07a/metrics.py`, `task07a-metrics-v1`)

Báo **tử số / mẫu số** theo từng (variant, seed) và theo lớp. Run lỗi, truncation, timeout,
`HARNESS_EXCEPTION` **đều nằm trong mẫu số**.

| Mã | Định nghĩa | Mẫu số |
|---|---|---|
| M1 relevant_seen | ít nhất một literal `relevant_entries` từng hiển thị trong prompt (`turns[].context.facts.evidence[imports].value.entries`) | IN_INITIAL + REACHABLE (8) |
| M1b relevant_cited | `trusted_metadata.resolved_import_refs` có entry liên quan | 8 |
| M2 unnecessary_tool | có `TOOL_CALL` được đề xuất | INITIAL_SUFFICIENT + NOT_STATIC (8) |
| M3a targeted_read | có READ mà trang trả về chứa entry liên quan (trang oracle **không** tính là READ) | REACHABLE (6) |
| M3b stopped_with_gap | ở lượt chọn FINISH: số READ < 2 **và** còn entry liên quan đã commit nhưng chưa hiển thị | REACHABLE (6) |
| M3c self_acknowledged_gap | `REGEX_APPROX`: văn bản model (final, reason, analysis, thinking) nhắc visibility một phần, trong khi còn budget đọc | run có final |
| M4 absence_claim_screen | `RULE_SCREEN_CANDIDATE`: câu phủ định capability trong final (trừ câu giới hạn kiểu "cannot prove the absence"); `SCOPED` nếu câu có phạm vi (visible/of N/first N/…), ngược lại `UNSCOPED`. Xuất nguyên văn để owner xem tay | run có final và case có ≥ 1 relevant entry |
| M5 prediction_in_support | flag `prediction_used_as_own_corroboration` | run có final |
| M6 cost | số lần gọi LLM, latency mean/median, prompt/output token, `thinking_chars`, `analysis_chars` | mọi run |
| M7 integrity | status, failure, run có validation error, run có `done_reason=length`, `analysis_first` (V2), overflow risk (`prompt_eval_count + eval_count ≥ 0.95 × num_ctx` ở bất kỳ lượt nào), isolation | mọi run |

Baseline tham chiếu chỉ đọc: arm C của `evaluation/task06b_j/results/confirmatory/run_v1/`
(cùng cấu hình V0 s42).

## 4. Quy tắc nhiễu

- So V0 s42 với V0 s7, và V0 (mỗi seed) với 06B-J run_v1, trên M1, M1b, M2, M3a, M3b, M3c,
  M4-UNSCOPED, M5. Nhiễu `N_m` của metric m = max |Δ| giữa các cặp đó.
- Một hiệu ứng của variant X chỉ được tính khi xuất hiện ở **cả hai seed** của X (V3 chỉ có
  seed 42) và |Δ so với V0 cùng seed| **lớn hơn** `N_m`. Nếu ≤ `N_m`: **không phân biệt được**.
- n rất nhỏ: đây là quy tắc ưu tiên công việc, **không** phải kiểm định thống kê.

## 5. Bảng quyết định (ghi trước khi có kết quả)

| Quan sát | Diễn giải | TASK 07B ưu tiên |
|---|---|---|
| V3: M1b ≥ 6/8 **và** M4-UNSCOPED thấp (≤ mức của V0) | Model dùng được evidence khi evidence đã hiển thị; H3 yếu; nút thắt ở thu thập | Retrieval có chỉ mục + workflow (P2/P3) |
| V3: M1b ≤ 3/8 **hoặc** M4-UNSCOPED vẫn cao | Model hoặc contract là nút thắt (H3) | Contract v4 tập trung vào câu trả lời (P1); đưa E7 (9B) lên sớm, cần owner đồng ý pull model |
| V1 hoặc V2: M2 giảm ≥ 3/8 **hoặc** M3a tăng ≥ 2/6 so với V0 (cả hai seed, vượt nhiễu) | H1 đúng; deliberation có tác dụng | Mọi bước v4 dùng reason-first; nếu V2 ≈ V1 chọn V2 (rẻ hơn) |
| V1 và V2 không đổi M2/M3 | H1 yếu; phễu/scent là nguyên nhân (H2) | Tool ở mọi lượt, REQUEST_MORE không terminal, chỉ mục DLL |
| V1 BLOCKED | Chưa kết luận về thinking native | Dựa vào V2 |
| Variant có M7 overflow hoặc truncation > 2 run | Kết quả variant đó không diễn giải được | Báo PARTIAL; **không** chạy lại để cứu |
| V3 nằm giữa (M1b 4–5/8) | Không kết luận được về H3 | Ghi INCONCLUSIVE cho H3 |

## 6. Quy tắc dừng và write-once

- Thứ tự: V0 s42, V0 s7, V2 s42, V2 s7, V3 s42, V1 s42, V1 s7. Mỗi thư mục: `prepare` rồi `run`.
- Mỗi run chạy **đúng một lần**. Không rerun ca lỗi, không xóa run, không thêm seed để ép kết
  quả. Lỗi Ollama/timeout/validation tính vào mẫu số.
- Nếu tiến trình bị ngắt giữa chừng, `run` tiếp tục với case **chưa có** trace; case có
  CaseState đã đổi mà không có trace bị dừng với `STATE_CHANGED_WITHOUT_SAVED_TRACE_NO_RETRY` và ghi
  vào log.
- Mọi output qua `write_new`; drift của nguồn Agent, harness 07A, `variant.json`, model LightGBM
  hoặc digest Qwen làm `run` dừng.
- Kết quả không phân biệt được với nhiễu là kết quả hợp lệ: báo **INCONCLUSIVE**.

## 7. Smoke gate (đã chạy trước freeze, DEV ngoài cohort, không tính vào kết quả)

- G1 V1: lần 1 FAIL (truncation ở `num_predict` 6144) → owner nâng budget → lần 2 PASS
  (`results/smoke_V1_r2`).
- G2 V2: PASS (`results/smoke_V2`).
