# TASK 07A — Diagnostic ablations cho Agent v3.4: kết quả và phân tích

| Hạng mục | Giá trị |
|---|---|
| Loại đánh giá | `DEV_DIAGNOSTIC` — **không** phải confirmatory (`confirmatory: NOT_RUN`) |
| Track | `RAW_PE_E2E` (20 PE benign hệ thống, staged copy, không thực thi) |
| Planner | `LOCAL_QWEN` — `qwen3.5:4b` Q4_K_M, digest `d8b0f5e9…`, Ollama 0.40.16, loopback |
| Agent | investigation v3.4 **không đổi** |
| Loại bằng chứng | **Metric tất định** từ trace + manifest evaluator-only. **Không** phải semantic grading, không Judge, không human grading. Phần M4 rà tay là *developer review* (provisional) |
| Cohort | 20 case 06B-J holdout v2, tái dùng làm DEV_DIAGNOSTIC (owner D1); không bao giờ dùng làm confirmatory nữa |
| Protocol | `PROTOCOL.md`, freeze ở commit `c58d351` trước mọi live run |
| Artifact chính | `results/metrics_v1.json` (frozen metric), `results/supplementary_v1_metrics.json` (deviation), `results/M4_developer_review_v1.json` (deviation), `EVALUATION_LOG.md` |
| Engineering completion | **PASS** (xem §9) |
| Research completion | **PARTIAL** — H1 có hiệu ứng qua V2; H3 yếu (V3, một seed); H2 không được kiểm trực tiếp; V1 PARTIAL (§9) |

---

## 1. Tóm tắt

- **H1 (thiếu bước cân nhắc): được ủng hộ, qua V2 (analysis-first).** Ở cả hai seed, V2 làm tăng
  M3a (đọc trang chứa entry liên quan) từ 1/6 lên 3/6 và 4/6, và tăng M1 (entry liên quan từng hiển
  thị) từ 2–3/8 lên 5–6/8. Cả hai vượt nhiễu của V0. **Nhưng** M2 (gọi tool khi không cần) không
  đổi (6–8/8 so với 7–8/8). Mọi lần đọc của V2 vẫn **tuần tự** (offset 16 rồi 32), không lần nào nhảy
  tới trang có mục tiêu. Nghĩa là cân nhắc trước làm model *kiên trì dùng hết budget đọc* hơn, chứ
  không làm nó *đọc có định hướng*.
- **H3 (model/contract không dùng được evidence đã hiển thị): yếu, ở mức đo được.** Khi oracle
  hiển thị sẵn trang chứa entry liên quan (V3), model trích đúng entry ở 7/8 case (V0: 2–3/8), và
  developer review không thấy câu khẳng định vắng mặt nào thiếu phạm vi (0/7). Vẫn còn 1/7 câu mâu
  thuẫn với entry đang hiển thị, và 1/8 run hỏng vì chép sai ID 32 hex. V3 chỉ có một seed.
- **H2 (thiếu information scent / phễu workflow): không được kiểm trực tiếp** (E3/E5 không thuộc
  07A). Bằng chứng mô tả đều cùng chiều: không biến thể nào đọc có mục tiêu; V2 bị REQUEST_MORE
  (terminal) cắt 3/20 run mỗi seed; V3 chỉ cần *hiển thị đúng trang* là đủ để trích đúng.
- **V1 (thinking native): PARTIAL, không dùng để kết luận H1.** 3/7 trace bị cắt vì thinking dùng hết
  `num_predict = 12288` (42–44k ký tự). Quy tắc toàn vẹn của protocol (truncation > 2 run) đã kích
  hoạt. Owner dừng V1 sau 7 trace. Chi phí: median 190 s/case, gần 10 lần V0.
- **Self-corroboration (M5) không đổi ở mọi biến thể** (85–100% final). Đây là lỗi do contract,
  không do deliberation hay retrieval, đúng như REPORT kiến trúc §3.3.
- **Hướng TASK 07B (theo bảng quyết định đã freeze):** retrieval có chỉ mục + workflow (P2/P3), và
  mọi bước dùng **reason-first dạng field `analysis`** (V2), không dùng thinking native ở budget hiện
  tại. Chi tiết và lý do ở §7.

## 2. Thiết kế đã chạy và những gì không chạy

| Thư mục | Variant | Seed | Server Ollama | Trạng thái | Ghi chú |
|---|---|---|---|---|---|
| `V0_s42` | V0 | 42 | app desktop | 20 slot: 16 COMPLETED_FINAL, **4 INFRA_OLLAMA_ERROR** (0013–0016) | resume sau sự cố, case chưa có trace |
| `V0_s7` | V0 | 7 | app desktop | 20 COMPLETED_FINAL | |
| `V2_s42` | V2 | 42 | app desktop | 14 COMPLETED_FINAL, 3 MODEL_INCOMPLETE, **3 INFRA_OLLAMA_ERROR** (0018–0020) | |
| `V2_s7` | V2 | 7 | — | **NOT_RUN_BLOCKED** (freeze ghi Ollama UNAVAILABLE) | giữ nguyên, write-once |
| `V2_s7_r2` | V2 | 7 | headless | 16 COMPLETED_FINAL, 4 MODEL_INCOMPLETE | thay cho V2_s7; không phải rerun ca lỗi |
| `V3_s42` | V3 | 42 | headless | 7 COMPLETED_FINAL, 1 MODEL_INCOMPLETE (0013) | 8 case IN_INITIAL + REACHABLE |
| `V1_s42` | V1 | 42 | headless | **PARTIAL**: 4 COMPLETED_FINAL, 3 MODEL_OUTPUT_TRUNCATION, 1 INFRA_INTERRUPTED (0008), 12 NOT_RUN | owner dừng |
| `V1_s7` | V1 | 7 | — | **NOT_RUN** | owner quyết định |
| V1b | — | — | — | **NOT_RUN** | owner bỏ trước freeze |
| `06B-J run_v1` arm C | (= V0 s42) | 42 | app desktop | 20 COMPLETED_FINAL | baseline frozen, chỉ đọc |

Cấu hình đầy đủ ở `PROTOCOL.md` §2. Cohort, prompt, schema và validator v3.4 giống hệt nhau ở mọi
variant. Isolation check PASS ở **mọi** trace (0 fail).

## 3. Kết quả M1–M7 (frozen metric `task07a-metrics-v1`)

Nguồn: `results/metrics_v1.json`. Mẫu số M1/M1b/M2/M3a/M3b cố định theo lớp; run lỗi hạ tầng có
trace và **được tính** (giá trị 0). Mẫu số M3c/M4/M5 = số run có final (và có relevant entry cho
M4), nên thay đổi theo nhóm.

### 3.1 Bảng chính

| Metric | Mẫu số | 06B-J run_v1 | V0 s42 | V0 s7 | V2 s42 | V2 s7_r2 | V3 s42 |
|---|---|---|---|---|---|---|---|
| M1 relevant_seen | IN_INITIAL+REACHABLE | 3/8 | 2/8 | 3/8 | **5/8** | **6/8** | 7/8 |
| M1b relevant_cited | 8 | 3/8 | 2/8 | 3/8 | 3/8 | 5/8 | **7/8** |
| M2 unnecessary_tool | SUFFICIENT+NOT_STATIC | 8/8 | 7/8 | 8/8 | 6/8 | 8/8 | — (0/0) |
| M2 tool_proposed (mọi case) | tất cả | 20/20 | 17/20 | 20/20 | 18/20 | 20/20 | 8/8 |
| M3a targeted_read | REACHABLE | 1/6 | 1/6 | 1/6 | **3/6** | **4/6** | 0/6 |
| M3b stopped_with_gap | REACHABLE | 6/6 | 5/6 | 6/6 | 2/6 | 1/6 | 2/6 |
| M3c self_ack_gap (REGEX_APPROX) | run có final | 17/20 | 15/16 | 19/20 | 6/14 | 8/16 | 7/7 |
| M4 screen UNSCOPED (RULE_SCREEN) | final + có relevant | 8/12 | 7/9 | 4/12 | 2/8 | 2/9 | 5/7 |
| M4 screen SCOPED (RULE_SCREEN) | như trên | 9/12 | 8/9 | 9/12 | 8/8 | 6/9 | 4/7 |
| M5 prediction_in_support | run có final | 18/20 | 15/16 | 17/20 | 13/14 | 15/16 | 7/7 |

Ghi chú đọc bảng:

- V0 s42: 0014 (IN_INITIAL), 0013, 0016 (REACHABLE), 0015 (SUFFICIENT) là lỗi hạ tầng, nên tử số
  M1/M2 của V0 s42 thấp hơn một cách cơ học (0015 không có proposal nên M2 = 7/8).
- V2 s42: 0018, 0019 (REACHABLE), 0020 (NOT_STATIC) là lỗi hạ tầng.
- **So sánh sạch nhất là V0 s7 với V2 s7_r2** (cả hai 0 lỗi hạ tầng): M1 3 → 6, M1b 3 → 5, M3a 1 → 4,
  M3b 6 → 1, M2 8 → 8.
- **M3b** chỉ được đếm khi model chọn FINISH. Run kết thúc bằng REQUEST_MORE hoặc lỗi hạ tầng tự động
  không bị tính. V2 có 3 REQUEST_MORE mỗi seed (V0: 0), nên một phần mức giảm M3b là do V2 *không
  kết thúc*, không phải do V2 *đọc đủ*. M3a là tín hiệu sạch hơn.
- **M3a ≠ đọc có mục tiêu.** Offset đọc của V2 luôn là `[16]` hoặc `[16, 32]` ở mọi case, kể cả
  INACCESSIBLE và NOT_STATIC (nơi đọc thêm vô ích). Entry 47 (0018) nằm trong trang 32 nhưng V2 s7
  chỉ đọc 16 rồi dừng. Không variant nào có offset khác 16/32. V3 không đọc lần nào (trang đã
  hiển thị sẵn).

### 3.2 Theo lớp (số run có final / có đề xuất tool / thấy relevant / trích relevant / tổng số READ)

| Lớp (số case) | run_v1 | V0 s42 | V0 s7 | V2 s42 | V2 s7_r2 | V3 s42 |
|---|---|---|---|---|---|---|
| IN_INITIAL (2) | 2/2/2/2/0 | 1/1/1/1/1 | 2/2/2/2/0 | 2/2/2/2/4 | 2/2/2/2/4 | 2/2/2/2/0 |
| REACHABLE (6) | 6/6/1/1/2 | 4/5/1/1/2 | 6/6/1/1/4 | 2/6/3/1/7 | 4/6/4/3/10 | 5/6/5/5/0 |
| INACCESSIBLE (4) | 4/4/0/0/1 | 4/4/0/0/0 | 4/4/0/0/1 | 4/4/0/0/5 | 3/4/0/0/5 | — |
| NOT_STATIC (4) | 4/4/0/0/4 | 4/4/0/0/2 | 4/4/0/0/2 | 2/3/0/0/2 | 3/4/0/0/4 | — |
| SUFFICIENT (4) | 4/4/0/0/0 | 3/3/0/0/0 | 4/4/0/0/0 | 4/3/0/0/0 | 4/4/0/0/0 | — |

### 3.3 M6 chi phí và M7 toàn vẹn

| | run_v1 | V0 s42 | V0 s7 | V2 s42 | V2 s7_r2 | V3 s42 | V1 s42 (7 trace, supplementary) |
|---|---|---|---|---|---|---|---|
| Lần gọi LLM | 67 | 59 | 67 | 73 | 80 | 22 | 21 |
| Latency mean / median (s) | 20.5 / 19.2 | 17.8 / 19.5 | 20.9 / 19.9 | 27.5 / 27.8 | 34.5 / 34.4 | 27.1 / 30.3 | 222.4 / 190.3 |
| Output token | 32 709 | 27 015 | 33 592 | 39 948 | 44 311 | 11 639 | 80 063 (ghi được) |
| analysis / thinking chars | 0 | 0 | 0 | 59 380 (analysis) | 67 989 (analysis) | 0 | 235 605 ghi được + 129 538 ở lượt bị cắt |
| Run có final | 20 | 16 | 20 | 14 | 16 | 7 | 4 |
| Validation error (run) | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| `done_reason=length` (meta) | 0 | 0 | 0 | 0 | 0 | 0 | 0 trong meta; **3 truncation** qua PlannerError |
| Overflow risk (≥ 0.95·num_ctx) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `analysis_first` | — | — | — | 70/70 lượt | 80/80 lượt | — | — |
| Lỗi hạ tầng | 0 | 4 | 0 | 3 | 0 | 0 | 1 INFRA_INTERRUPTED |

- Không variant nào tràn context, nên việc V1/V2 đổi `num_ctx` **không** là nguyên nhân hiệu ứng.
- M7 `done_reason=length` **không** bắt được truncation của V1, vì lượt bị cắt raise `PlannerError`
  trước khi có `meta`. Truncation V1 được đếm trong `supplementary_v1_metrics.json`.

## 4. Nhiễu (PROTOCOL §4)

|Δ| tử số giữa các run cùng cấu hình V0:

| Metric | V0 s42 vs V0 s7 | V0 s42 vs run_v1 | V0 s7 vs run_v1 | **N_m** |
|---|---|---|---|---|
| M1 | 1 | 1 | 0 | **1** |
| M1b | 1 | 1 | 0 | **1** |
| M2 | 1 | 1 | 0 | **1** |
| M3a | 0 | 0 | 0 | **0** |
| M3b | 1 | 1 | 0 | **1** |
| M3c | 4 | 2 | 2 | **4** (mẫu số khác nhau) |
| M4 screen UNSCOPED | 3 | 1 | 4 | **4** (mẫu số khác nhau) |
| M5 | 2 | 3 | 1 | **3** (mẫu số khác nhau) |

Phần lớn chênh lệch V0 s42 so với hai run kia đến từ 4 lỗi hạ tầng. V0 s7 và run_v1 (cùng cấu hình,
khác seed/ngày) gần như trùng khớp ở M1–M3b.

## 5. M4: screen và developer review

Nguồn: `results/M4_developer_review_v1.json` (119 câu ứng viên, nguyên văn + nhãn + lý do).
**PROVISIONAL**: Claude Code tự rà, không phải semantic grading, không phải human adjudication.
Screen gốc và regex không đổi. Đơn vị đếm là số case trong mẫu số M4 có ít nhất một câu thuộc nhãn đó.

| Nhóm | Mẫu số | Screen UNSCOPED | Rà: absence không phạm vi | Rà: mâu thuẫn với entry đang hiển thị | Rà: tổng false-absence |
|---|---|---|---|---|---|
| run_v1 | 12 | 8 | 3 | 0 | 3 |
| V0 s42 | 9 | 7 | 3 | 1 | 3 |
| V0 s7 | 12 | 4 | 2 | 0 | 2 |
| V2 s42 | 8 | 2 | 0 | 0 | 0 |
| V2 s7_r2 | 9 | 2 | 1 | 1 | 2 |
| V3 s42 | 7 | 5 | **0** | 1 | 1 |

- Screen đếm dư nhiều: phần lớn câu "UNSCOPED" thực chất là câu giới hạn ("absence of other
  file-system APIs is unknown", "lacks … full import visibility"). Ở V3, toàn bộ 5 case bị screen
  gắn UNSCOPED đều là câu giới hạn.
- Các lỗi thật đáng chú ý:
  - **mâu thuẫn ngay trong cùng một final:** V2 s7_r2/0012 trích `msvcrt.dll!fopen` qua `import_refs`
    nhưng viết "no file-system APIs in the visible import list"; V3/0005 trích `KERNEL32!WriteFile`
    (entry 2) nhưng viết "no explicit file system APIs in the first 16 entries"; V0 s42/0005 tương
    tự.
  - **ordinal chưa resolve:** 0003 (WS2_32 #115/#11/#52) được viết là "no explicit socket
    functions" ở run_v1 và V3. Gắn nhãn `DEBATABLE_ORDINAL`, không tính là false-absence, nhưng đây
    là giới hạn kiến thức miền đã biết (REPORT kiến trúc §3.2).

## 6. V1 (thinking native) — PARTIAL

Nguồn: `results/supplementary_v1_metrics.json`.

| Case | Lớp | Kết quả | Lượt | Ghi chú |
|---|---|---|---|---|
| 0001 | SUFFICIENT | MODEL_OUTPUT_TRUNCATION | 1 | thinking 42 912 ký tự, `eval_count = 12288`, content rỗng |
| 0002 | NOT_STATIC | MODEL_OUTPUT_TRUNCATION | 1 | thinking 44 044 ký tự |
| 0003 | REACHABLE | COMPLETED_FINAL | 5 | đọc [16, 32], trích relevant; 374 s |
| 0004 | SUFFICIENT | COMPLETED_FINAL | 2 | **FINISH ngay, không gọi tool** |
| 0005 | IN_INITIAL | COMPLETED_FINAL | 4 | |
| 0006 | NOT_STATIC | COMPLETED_FINAL | 4 | gọi tool |
| 0007 | NOT_STATIC | MODEL_OUTPUT_TRUNCATION | 4 | 3 lượt hợp lệ, bị cắt ở lượt viết final (thinking 42 582) |
| 0008 | INACCESSIBLE | INFRA_INTERRUPTED | — | CaseState rev 5, không có trace |
| 0009–0020 | — | NOT_RUN | — | owner dừng |

- **Kết luận chính của V1:** thinking native ở budget `num_predict = 12288` chạy mất kiểm soát ở 3/7
  trace (2 ngay lượt 1, 1 ở lượt final). Chi phí khoảng 10 lần V0 (median 190 s). Smoke G1 lần 2
  (trên DEV tracert) đã PASS, nhưng không đại diện được cho cohort.
- Metric hành vi trên 7 trace chỉ là **EXPLORATORY**, mẫu số không phải mẫu số protocol:
  - gọi tool ở lượt 1: 4/5 trace có proposal lượt 1;
  - M2: 2/5;
  - M1 / M1b: 2/2;
  - M3a: 1/1;
  - M5: 3/4.

  Không dùng các số này để kết luận.
- Confound đã biết vẫn còn: V1 đổi cả thinking lẫn sampling (temp 0.6, top_p 0.95, top_k 20,
  presence_penalty 0.0 so với 1.5 ngầm định từ Modelfile ở V0/V2/V3). V1b không chạy.

## 7. Áp bảng quyết định (PROTOCOL §5, đã freeze)

Quy tắc hiệu ứng: có ở cả hai seed của variant, và |Δ so với V0 cùng seed| > N_m. V3 có một seed,
nên so với cả hai seed V0 và run_v1 trên cùng 8 case.

**V2 so với V0 (cùng seed):**

| Metric | s42: V2 − V0 | s7: V2 − V0 | N_m | Kết luận |
|---|---|---|---|---|
| M1 | 5 − 2 = +3 | 6 − 3 = +3 | 1 | **hiệu ứng ↑** |
| M1b | 3 − 2 = +1 | 5 − 3 = +2 | 1 | không phân biệt được (s42 ≤ N) |
| M2 | 6 − 7 = −1 | 8 − 8 = 0 | 1 | **không hiệu ứng** |
| M3a | 3 − 1 = +2 | 4 − 1 = +3 | 0 | **hiệu ứng ↑ (≥ 2/6 cả hai seed)** |
| M3b | 2 − 5 = −3 | 1 − 6 = −5 | 1 | hiệu ứng ↓ (có confound REQUEST_MORE, §3.1) |
| M4 screen UNSCOPED | 2 vs 7 | 2 vs 4 | 4 | không phân biệt được (s7 ≤ N) |
| M5 | 13/14 vs 15/16 | 15/16 vs 17/20 | 3 | không hiệu ứng |

**V3 so với V0 (8 case, seed 42):** M1b 7/8 so với V0 s42 2/8, V0 s7 3/8, run_v1 3/8 → Δ = +4..+5 >
N = 1: **hiệu ứng**. M4 screen UNSCOPED 5/7 (71%) nằm trong khoảng của V0 (33–78%); developer review
0/7 thấp hơn V0 (2–3 case).

| Dòng bảng quyết định | Điều kiện | Quan sát | Áp dụng? |
|---|---|---|---|
| V3: M1b ≥ 6/8 **và** M4-UNSCOPED thấp (≤ mức V0) | | M1b 7/8; M4 screen 71% ≤ V0 s42 (78%) nhưng > V0 s7 (33%); review 0/7 | **Có**: M1b đạt rõ; M4 không cao hơn V0 theo screen (trong khoảng nhiễu), và thấp hơn theo review → H3 yếu; nút thắt ở thu thập |
| V3: M1b ≤ 3/8 **hoặc** M4-UNSCOPED vẫn cao | | M1b 7/8; M4 không cao hơn V0 | Không |
| V1/V2: M2 giảm ≥ 3/8 **hoặc** M3a tăng ≥ 2/6 (cả hai seed, vượt nhiễu) | | V2: M3a +2 và +3, N = 0 | **Có (qua V2)**: H1 đúng; deliberation có tác dụng lên hành động theo gap |
| V1 và V2 không đổi M2/M3 | | M3 đổi | Không |
| V1 BLOCKED | | V1 PARTIAL (không BLOCKED) | Áp tinh thần dòng này: dựa vào V2 cho H1 |
| Variant có overflow hoặc truncation > 2 run | | V1: 3 truncation | **Có cho V1** → V1 không diễn giải được, PARTIAL, không chạy lại |
| V3 nằm giữa (M1b 4–5/8) | | 7/8 | Không |

**Kết luận theo giả thuyết:**

| Giả thuyết | Kết luận | Căn cứ |
|---|---|---|
| H1 thiếu bước cân nhắc | **Được ủng hộ một phần (DEV, n nhỏ)** | V2: M3a và M1 tăng ở cả hai seed, vượt nhiễu. M2 không đổi. Đọc vẫn tuần tự |
| H2 thiếu scent / phễu workflow | **NOT_DIRECTLY_TESTED**; bằng chứng mô tả cùng chiều | 0 lần đọc có mục tiêu ở mọi variant; REQUEST_MORE terminal cắt 3/20 run V2 mỗi seed; V3 cho thấy chỉ cần hiển thị đúng trang |
| H3 giới hạn model/contract khi evidence đã hiển thị | **Yếu với việc dùng evidence (một seed)**; contract vẫn là nút thắt cho self-corroboration | V3 M1b 7/8, review UNSCOPED 0/7. Còn lại: 1 mâu thuẫn trong final, 1 lỗi chép ID 32 hex, ordinal chưa resolve. M5 85–100% ở mọi variant |
| Thinking native (E1) | **PARTIAL / không kết luận** | Thinking mất kiểm soát 3/7, chi phí khoảng 10 lần |

**Hướng TASK 07B được chọn (theo bảng):** *Retrieval có chỉ mục + workflow (P2/P3)*, với
*reason-first dạng field `analysis` ở mọi bước* (V2, vì V1 PARTIAL và đắt hơn nhiều). Trong hai lựa
chọn của PLAN §10, đề xuất ưu tiên:

1. **(a) imports analyzer v0.2 + `query_imports`** (DLL TOC, resolve ordinal, query theo DLL/symbol).
   Lý do: V2 cho thấy cân nhắc chỉ làm model đọc *thêm* theo thứ tự file, không đọc *đúng chỗ*; với
   INACCESSIBLE (entry ngoài 64 đầu) không cách đọc nào trong v3.4 tới được. V3 cho thấy hiển thị
   đúng trang là đủ để trích đúng.
2. Kèm một thay đổi nhỏ thuộc (b): **REQUEST_MORE không terminal**. V2 mất 3/20 final mỗi seed vì nó.

Đề xuất ngoài bảng, để owner cân nhắc, không tự mở rộng phạm vi: M5 không đổi ở mọi variant, nên
contract tập trung vào câu trả lời, với detector tách khỏi evidence citable (P1/E6), vẫn cần làm sớm.
Đây là kết luận của REPORT kiến trúc, không phải của bảng 07A.

## 8. Deviation, sự cố hạ tầng và limitation

**Sự cố hạ tầng (chi tiết trong `EVALUATION_LOG.md`):**

1. 2026-11-26, V0 s42: Ollama reset rồi từ chối kết nối ở 0013–0016; session kết thúc. Các case
   0017–0020 được tiếp tục sau đó (case chưa có trace, protocol cho phép).
2. 2026-11-27 04:51, V2 s42: HTTP 500, RemoteDisconnected, rồi connection refused ở 0018–0020.
   `app.log` ghi ứng dụng desktop Ollama tự tắt server; updater đã tải sẵn v0.40.18. Nguyên nhân gốc
   chưa xác minh chắc chắn.
3. `V2_s7` được prepare trong lúc Ollama tắt (freeze ghi UNAVAILABLE), nên bị BLOCKED. V2 seed 7 chạy
   ở thư mục mới `V2_s7_r2`.
4. Từ khoảng 04:53 chạy Ollama headless (`ollama.exe serve`, cùng binary 0.40.16). Session kết thúc
   lần nữa sau V1 s42 / 0007, kéo theo runner và server headless (tiến trình con của session).
   0008 bị INFRA_INTERRUPTED (CaseState rev 5, không có trace).

**Confound hạ tầng:** V0 s42, V0 s7 và V2 s42 chạy dưới server của ứng dụng desktop; V2 s7_r2, V3 và
V1 chạy dưới server headless. Chưa kiểm khác biệt biến môi trường giữa hai cách khởi chạy. Hiệu ứng
V2 xuất hiện ở cả seed chạy dưới app (s42) lẫn headless (s7_r2), nên confound này không giải thích
được hiệu ứng V2. V3 chỉ chạy headless.

**Deviation so với PLAN/PROTOCOL:**

| # | Deviation | Ai duyệt | Ảnh hưởng |
|---|---|---|---|
| 1 | Knob decoding đặt trong `agent/planner.py` (`DecodingOptions`), không trong `agent/config.py` (guard frozen-baseline 06A) | Trong phạm vi D3 | Không; request mặc định byte-identical (test) |
| 2 | V1 budget nâng sau G1 FAIL (`num_predict` 6144 → 12288, `num_ctx` → 24576, `max_tokens` → 200000); bỏ V1b | Owner, trước freeze | V1 vẫn truncation 3/7 trong cohort |
| 3 | Lỗi hạ tầng giữ trong mẫu số, không rerun; V2 seed 7 ở thư mục mới | Protocol §6 | Tử số V0 s42 / V2 s42 bị giảm cơ học |
| 4 | V1 dừng ở 7 trace; V1 s7 NOT_RUN | Owner (dựa trên quy tắc toàn vẹn, không dựa trên kết quả) | V1 PARTIAL |
| 5 | `metrics.py` chạy trên view junction gồm 5 nhóm đầy đủ | Owner (mục B) | Tránh mẫu số thu nhỏ sai; code không đổi |
| 6 | Script `supplementary_v1.py` sau freeze | Owner (mục B) | Chỉ phân loại trạng thái và chi tiết V1; gắn nhãn SUPPLEMENTARY |
| 7 | M4 developer review sau freeze | Owner (mục C) | Bổ sung; screen gốc giữ nguyên |
| 8 | Đã xem kết quả sơ bộ V0/V2/V3 trong lúc V1 chạy | Ghi minh bạch | Không có cấu hình, ngưỡng hay regex nào bị đổi sau đó (`git diff c58d351` rỗng với harness và protocol) |

**Limitation:**

- **Provenance thinking:** với lượt trả content rỗng, `agent/planner.py` raise `PlannerError` trước
  khi gắn `meta`, nên raw thinking bị mất, chỉ còn `thinking_chars` trong chuỗi lỗi (129 538 ký tự ở
  3 lượt). Không sửa trong 07A (sẽ gây SOURCE_DRIFT). **Việc cần làm của TASK 07B.**
- n rất nhỏ (6–8 case cho M1/M3), cohort chỉ gồm PE benign hệ thống đã ký, và là cohort đã "tiêu" ở
  06B-J. Các con số là mô tả, không phải kiểm định thống kê, và không khái quát hóa được.
- M3c là regex xấp xỉ. M4 là rule screen; developer review là đọc tay của chính Claude Code,
  provisional, cần owner xem.
- M1/M1b chỉ đo việc *thấy* và *trích* entry liên quan, không đo câu trả lời có đúng về ngữ nghĩa hay
  không (semantic grading PENDING / NOT_RUN trong 07A).
- V3 chỉ có một seed và gần như cơ học với M1. Kết luận H3 dựa vào M1b và M4.
- `relevant_entries` lấy từ manifest 06B-J (lexicon FILE/NETWORK/PROCESS). CRT stream I/O như
  fputs/fflush không được đánh dấu relevant, nên M1/M4 có thể đánh giá thấp hoặc cao một số câu
  (ghi chú ở câu #13).

## 9. Completion

### Engineering completion: **PASS**

- Thay đổi additive `DecodingOptions` ở `agent/planner.py`, có test (21 test); request mặc định
  byte-identical với `e31ee31`.
- Harness `evaluation/task07a/` (variants, ablation CLI, metrics) có test unit + MOCK_LLM. MOCK_LLM
  chỉ kiểm cơ chế, không phải bằng chứng hành vi.
- Protocol commit trước mọi live run (`c58d351`). Mọi run ghi write-once kèm `variant.json` và
  `variant_lock.json`. Drift guard hoạt động: chặn `V2_s7` và chặn resume V1 (0008).
- Supplementary script và M4 review builder có test hoặc ghi rõ provenance.
- Full regression: xem §10.

### Research completion: **PARTIAL**

| Yêu cầu (PLAN §9) | Trạng thái |
|---|---|
| Bảng M1–M7 đủ mẫu số cho V0–V3 | **PASS** cho V0, V2, V3; V1 **PARTIAL** (supplementary, EXPLORATORY) |
| So sánh nhiễu giữa hai seed V0 (+ run_v1) | **PASS** (§4) |
| Áp bảng quyết định và chọn hướng 07B | **PASS** (§7): P2/P3 + reason-first dạng `analysis` |
| H1 | Ủng hộ một phần qua V2 (DEV, n nhỏ) |
| H2 | **NOT_DIRECTLY_TESTED** |
| H3 | Yếu (một seed) |
| E1 thinking native | **PARTIAL** — không kết luận |
| Semantic grading / human review | **NOT_RUN** trong 07A; M4 developer review **PENDING** owner xem |

## 10. Regression

Full regression (`python -m pytest -q`, Python 3.12.10 hệ thống, không có `.venv`) chạy lại ngày
2026-11-27 sau khi thêm `supplementary_v1.py`, `m4_developer_review.py` và
`tests/test_supplementary.py`:

| Thời điểm | Passed | Failed | Skipped |
|---|---|---|---|
| Trước 07A (baseline) | 695 | 0 | 4 |
| Sau S1/S2 (pre-run freeze) | 740 | 0 | 4 |
| Sau S7/S8 (báo cáo này) | **743** | **0** | **4** |

Cả ba lần đều có thêm 81 subtest pass. 4 test skipped không được tính là pass.
