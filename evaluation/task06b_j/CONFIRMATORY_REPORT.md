# TASK 06B-J — Confirmatory Report (run_v1, final)

| Hạng mục | Trạng thái |
|---|---|
| ENGINEERING | **PASS**: pipeline đánh giá chạy trọn từ đầu tới cuối và truy vết được: runner 3 arm, staging, freeze, blind package, Judge kit, import, lock, analyze |
| CONFIRMATORY EXECUTION | **COMPLETE**: 20 case × 3 arm = 60 report, chạy **1 lần**, không rerun |
| SEMANTIC GRADING | **COMPLETE (LLM_JUDGE_PROVISIONAL)**: 200 judgment / 4 phiên Judge, `human_verified=false` |
| HUMAN GRADING | **PENDING** |
| RESEARCH | **INCONCLUSIVE, nghiêng về âm tính** với giả thuyết "tool tự chủ làm tăng giá trị điều tra" (§6) |

Authorization: `DACN_PROJECT_OWNER_06BJ_CONDITIONAL_GO`. Phạm vi thu hẹp:

- Primary: verdict mức claim, R2, R3, R4, R6, R7, cùng metrics tất định.
- Exploratory: R1, R5, R8, R9, `evidence_access`.

Nguồn số liệu: `results/confirmatory/`, gồm `run_v1/`, `confirmatory_summary_v1.json`,
`judge/` (`LOCK.json`, `analysis.json`) và `final_report_v1/` (`FINAL_RESULTS.md`,
`final_results.json`, `final_analysis.json`).

## 1. Import, lock, provenance

- **200 judgment + 4 session note** (60/40/60/40), cả 4 kit `COMPLETE_VALID` với 0 problem.
- Hash của package, raw response (kit = repo) và item trong kit đều khớp. Validator chạy lại cho
  0 lỗi. Rubric `task06b-j-rubric-v2` (`dbb791cd…`), `human_verified=false`.
- **Lock** `judge/LOCK.json` (08:59:05Z) được tạo **trước** khi mở mapping.
- Model: **UNKNOWN** (không có output `/status`). Cả 4 phiên tự báo "Claude Opus 5.5",
  UNVERIFIED. Session ID UNKNOWN.
- Session note của Judge có ghi:
  - 20 template giống hệt nhau và 13 fallback được chấm bằng rationale dùng chung.
  - Judge không biết hành động đọc trang có thực sự được offer cho từng lượt hay không, tức thiếu
    grading context cho `evidence_access`/R5.
  - Không ghi nhận contamination nào.

## 2. Self-consistency trên confirmatory (P1 so với P2; **không** phải độ chính xác)

Cùng công thức đã khóa (exact agreement, ghép report qua mapping evaluator-only).

| Tiêu chí | Vai trò | n | Exact | κ | Calibration v2 |
|---|---|---:|---:|---:|---|
| R1 factual support | exploratory | 47 | 0.872 | 0.79 | 0.75 (UNRELIABLE) |
| **R2 traceability** | **primary** | 47 | **0.319** | −0.01 | 1.00 |
| R3 tool decision | primary | 20 | 0.800 | 0.57 | 1.00 |
| R4 evidence relevance | primary | 20 | 0.950 | 0.92 | 1.00 |
| R5 consumption | exploratory | 20 | **0.300** | 0.15 | 0.667 |
| R6 incremental value | primary | 27 | 0.852 | 0.78 | 1.00 |
| R7 uncertainty | primary | 47 | 0.915 | 0.85 | 0.833 |
| R8 decision/safety | exploratory | 60 | 0.817 | 0.67 | 0.733 |
| R9 next-step | exploratory | 47 | 0.915 | 0.77 | exploratory |

**Phát hiện:**

- **R2 không ổn định trên dữ liệu confirmatory** (0.32), dù calibration v2 cho 1.00. Nguyên nhân
  chính: 20 template static được P1 chấm 2 nhưng P2 chấm 1. Hai pass hiểu khác nhau việc "bản
  ghi nhúng nguyên văn" có tính là truy được nguồn hay không. Đây là **rubric ambiguity** mà
  calibration không phát hiện (vì calibration chỉ có 3 template).
- Theo protocol, phân loại primary/exploratory được khóa ở calibration và **không** đổi sau khi
  thấy kết quả. Vì vậy R2 vẫn được báo là primary, nhưng **kết luận từ R2 là INCONCLUSIVE**: hiệu
  C − A đổi dấu giữa hai pass (−0.30 và +0.45).
- R5 cũng không ổn định (0.30); R5 vốn đã là exploratory.
- R3 đạt đúng ngưỡng (0.80). Bất đồng tập trung ở 4 câu hỏi runtime: P1 cho 1, P2 cho 2, tức
  khác nhau ở chỗ gọi imports analyzer cho câu hỏi runtime có hợp lý hay không.

## 3. Kết quả tất định (20 case, mọi case nằm trong mẫu số)

| Metric | A static | B no-tool | C tool-enabled |
|---|---|---|---|
| Final hợp lệ về cấu trúc | template 20 | **7/20** (13 incomplete) | **20/20** |
| FINISHED sạch / bị flag | — | 1 / 6 | 2 / 18 |
| Gọi tool / D4 ALLOW / D9 commit | — | 0 | 20 / 20 / 20 |
| Gọi tool khi **không cần** (Initial-sufficient + Not-static) | — | — | **8/8** |
| Đọc retrieval (số case) | — | 0 | 7 (6) |
| Lớp retrieval: case có đọc / case thấy được evidence liên quan | — | — | 2/6 / **1/6** |
| Structural self-corroboration (checker) | — | 6/7 | 18/20 |
| Hành động hiệu lực | MONITOR | MANUAL_REVIEW 20 | MANUAL_REVIEW 18, MONITOR 2 |
| Số lần gọi LLM / latency trung bình | 0 / — | 27 / 8.1 s | 67 / 20.5 s |
| Token prompt | 0 | 86 690 | 298 267 |
| Isolation / SHA / leakage tình cờ | — | 20/20 / 20/20 / 0 | 20/20 / 20/20 / 0 |

LightGBM chấm 20/20 benign (raw score 0.0010–0.0140), giống nhau ở mọi arm. **Không** có thay
đổi nào về detection.

## 4. Kết quả semantic (LLM_JUDGE_PROVISIONAL; ghi P1 / P2)

Mean chỉ tính trên điểm assessable. B chỉ có 7 report assessable (13 NOT_ASSESSABLE vì
incomplete), nên **so sánh C với B bị selection bias**: B chỉ có final ở các câu dễ.

| Tiêu chí | A (n=20) | B (n=7 assessable) | C (n=20) |
|---|---|---|---|
| R2 traceability (primary, **không ổn định**) | 2.00 / 1.00 | 1.43 / 1.57 | 1.70 / 1.45 |
| R3 tool decision (primary) | — | NA | 1.55 / 1.75 |
| R4 evidence relevance (primary) | — | NA | 1.20 / 1.25 |
| R6 incremental value (primary) | — | −0.29 / −0.29 | **0.50 / 0.50** |
| R7 uncertainty (primary) | 1.00 / 1.00 | 1.43 / 1.43 | **1.65 / 1.75** |
| R1 factual (exploratory) | 2.00 / 2.00 | 0.71 / 0.57 | 0.85 / 0.90 |
| R5 consumption (exploratory) | — | NA | 0.95 / 1.65 |
| R8 decision/safety (exploratory) | 1.00 / 1.00 | 1.90 / 1.80 | 1.55 / 1.10 |
| R9 next-step (exploratory) | 0.00 / 0.00 | 0.57 / 0.43 | 0.55 / 0.40 |

Hiệu theo cặp (bootstrap 95%), chỉ nêu những hiệu ổn định qua cả hai pass:

- C − A, R7: +0.65 [0.30, 0.95] và +0.75 [0.50, 0.95].
- C − A, R1 (exploratory): −1.15 và −1.10. Template gần như không có claim nên không sai.

**Verdict mức claim (Track A; claim có cấu trúc + additional claims):**

| Arm | Số claim P1 / P2 | Tỷ lệ UNSUPPORTED+CONTRADICTED | Report có ≥ 1 claim sai |
|---|---|---|---|
| A static | 60 / 80 | 0 / 0 | 0/20 / 0/20 |
| B no-tool | 42 / 46 | 14.3% / 13.0% | 3/7 / 3/7 |
| C tool-enabled | 118 / 129 | 12.7% / 8.5% | **7/20 / 5/20** |

Tag lỗi ở arm C (P1 / P2): SCOPE_OVERCLAIM 4/3, RUNTIME_OVERCLAIM 2/2, SCORE_AS_PROBABILITY 8/4.

**Self-corroboration:**

- Structural: C 18/20, B 6/7.
- Semantic (Judge): C 7 ở P1, 12 ở P2; khớp giữa pass ở 15/20 report, và 7/20 report được gắn
  ở cả hai pass. B: 2 ở P1, 3 ở P2; khớp 6/7. Hai chỉ số được báo tách riêng. Các ca borderline
  vẫn PENDING_ADJUDICATION; phân loại của AI reviewer (#4 AMBIGUOUS, #6 STRUCTURAL_ONLY, #5
  NOT_SEMANTIC) không phải human adjudication.

## 5. Theo lớp accessibility (C; P1 / P2)

| Lớp (n) | Evidence liên quan thấy được (tất định) | R3 | R4 | R6 | R7 | Report có claim sai |
|---|---|---|---|---|---|---|
| IN_INITIAL_TOOL_PROJECTION (2) | 2/2 | 2 / 2 | 2 / 2 | **1.5 / 2.0** | 2 / 2 | 1/2 / 0/2 |
| REACHABLE_BY_BOUNDED_RETRIEVAL (6) | **1/6** (2 case có đọc) | 2 / 2 | 2 / 2 | **0.50 / 0.33** | 1.67 / 1.83 | 3/6 / 2/6 |
| INACCESSIBLE_UNDER_LIMITS (4) | 0/4 (ngoài tầm) | 2 / 2 | 1.0 / 1.25 | 0.75 / 1.0 | 1.5 / 1.75 | 1/4 / 1/4 |
| NOT_STATIC_ANSWERABLE (4) | — | 1 / 2 | 1 / 1 | 0.25 / 0 | 1.25 / 1.25 | 2/4 / 2/4 |
| INITIAL_EVIDENCE_SUFFICIENT (4) | — | **0.75 / 0.75** | 0 / 0 | 0 / 0 | 2 / 2 | 0/4 / 0/4 |

Ở lớp `REACHABLE_BY_BOUNDED_RETRIEVAL`, lớp kiểm trực tiếp giả thuyết chính, Agent thường không
đọc tới trang có evidence. Theo metrics tất định, Agent thấy được evidence liên quan ở 1/6 case,
và R6 thấp (0.33–0.50). Lớp có giá trị cao nhất là lớp mà evidence nằm ngay trong trang đầu,
nhưng lớp này chỉ có 2 case.

## 6. Kết luận nghiên cứu TASK 06 (06B-J)

**Câu hỏi:** việc Agent tự chọn tool và tự đọc evidence có cải thiện tính đúng, độ cụ thể, mức
liên quan, kế hoạch kiểm chứng và giá trị điều tra, mà không làm tăng claim không có căn cứ hoặc
kết luận không an toàn hay không?

**Kết luận: INCONCLUSIVE, nghiêng về âm tính** trên cohort 20 PE benign này.

1. **Khả năng hoàn tất:** C cho final 20/20, B chỉ 7/20. Toàn bộ 13 ca B incomplete là một lượt
   `REQUEST_MORE_EVIDENCE` hợp lệ, có lý do đúng (thiếu import hoặc dữ liệu runtime), không có
   lỗi schema, budget hay truncation. Đây là hệ quả của workflow (coi xin thêm evidence là kết
   thúc) cộng với lựa chọn hợp lệ của model, **không** phải lỗi suy luận. Lợi thế hoàn tất của C
   chủ yếu là **cấu trúc**.
2. **Giá trị điều tra (R6):** C đạt trung bình 0.5 trên thang −1..2, ổn định qua hai pass:
   dương nhưng nhỏ. Giá trị tập trung ở 2 case có evidence ngay trong trang đầu. Ở lớp cần
   retrieval (6 case), Agent hiếm khi đọc đúng trang (1/6). **Không** có bằng chứng retrieval tự
   chủ tạo thêm giá trị.
3. **Quyết định gọi tool:** C gọi tool ở 20/20 case, kể cả 8/8 case không cần. R3 ở các case
   initial-sufficient là 0.75. Hành vi gọi tool **không phân biệt** theo nhu cầu.
4. **Tính đúng ở mức claim:** C có claim UNSUPPORTED/CONTRADICTED ở 5–7/20 report (tỷ lệ theo
   claim 8.5–12.7%), tương đương B (13–14%). Template static không sai claim nào vì gần như
   không khẳng định gì. Dùng tool **không** làm giảm tỷ lệ lỗi claim, và so với static thì thêm
   rủi ro (scope overclaim, runtime overclaim, coi score như xác suất).
5. **Uncertainty (R7):** C (1.65–1.75) tốt hơn template (1.0). Hiệu C − A ổn định, CI không chứa
   0. Đây là cải thiện rõ nhất, nhưng một phần là do template quá chung chung.
6. **Truy nguồn (R2):** **INCONCLUSIVE**, vì Judge không ổn định (0.32) và hiệu đổi dấu giữa hai
   pass.
7. **Self-corroboration:** structural 18/20 ở C; semantic 7–12/20 (khớp 15/20 giữa hai pass).
   Vấn đề vẫn chưa được giải quyết.
8. **Chi phí và review:** C dùng khoảng 2.5 lần số lần gọi LLM, khoảng 3.4 lần token prompt,
   latency khoảng 2.5 lần so với B. 18/20 report C bị chuyển MANUAL_REVIEW, nên **không** giảm
   tải review.
9. **Detection:** không thay đổi, và không được tuyên bố cải thiện độ chính xác phát hiện.

**Chưa trả lời được:** verification planning (R9 exploratory, contract không có trường
next-step); semantic evidence consumption (R5 không ổn định); khả năng tổng quát hóa sang
malware hay sang PE ngoài System32; tính đúng của Judge (human grading PENDING).

## 7. Sai lệch protocol và đính chính (artifact gốc giữ nguyên)

1. Trường `rubric_id=v1` trong freeze là **sai sót metadata**, không ảnh hưởng hành vi
   (`results/confirmatory/FREEZE_METADATA_CORRECTION.md`, freeze SHA `4b37c37f…`).
2. Lệnh trong REPORT §7 trỏ tới manifest v1; lượt chạy dùng manifest **v2** đã duyệt
   (EVALUATION_LOG mục 18).
3. Trước khi chạy, Ollama không chạy; developer đã khởi động `ollama serve` trên loopback (digest
   khớp với DEV).
4. R2 được khóa là primary dựa trên calibration, nhưng **mất ổn định trên confirmatory**. Không
   phân loại lại sau khi thấy kết quả; kết luận về R2 được ghi là INCONCLUSIVE.
5. Judge thiếu grading context về việc hành động READ có được offer hay không (session note),
   ảnh hưởng tới `evidence_access` và R5 (cả hai đều exploratory).

## 8. Giới hạn

- Cohort 20 PE benign có chữ ký Windows; mỗi lớp 2–6 case. Kết quả chỉ mang tính mô tả.
- LLM-as-Judge cùng họ model, danh tính model UNKNOWN; hai pass chỉ đo self-consistency. Human
  grading PENDING.
- So sánh C với B bị selection bias (B chỉ có 7 final).
- Neutral staging chỉ giảm leakage tình cờ; Qwen vẫn có thể nhận ra tiện ích qua import.
- Analyzer chỉ commit 64 entry, budget 5 lượt (giới hạn của hệ thống, không thay đổi).
- Không suy rộng sang malicious PE. Malicious raw-PE vẫn BLOCKED.
