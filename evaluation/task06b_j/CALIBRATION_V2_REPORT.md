# TASK 06B-J — Calibration v2 Report (rubric `task06b-j-rubric-v2`), lượt tổng hợp cuối

**Loại kết quả:** DEV calibration của LLM-as-Judge, **PROVISIONAL**, `human_verified=false`.
Hai pass đến từ **cùng một họ model**, nên đây là **self-consistency**, không phải
inter-rater reliability giữa hai người, và không chứng minh tính đúng. Dữ liệu là report lịch
sử trên 3 file DEV cộng probe do developer viết. **Không** phải confirmatory, **không** so
sánh arm.

Không có rubric v3, không thêm probe, không thêm phiên Judge. Mọi giới hạn bên dưới được chấp
nhận và báo cáo như hiện trạng.

## 1. Import và lock

| Kit | File J-* trên đĩa | Item | Import | Raw SHA (kit = repo) | Item kit chưa bị sửa | Validate lại |
|---|---|---|---|---|---|---|
| P1-trackA | 23 | 23 | COMPLETE_VALID, 0 problem | khớp | khớp | 0 lỗi |
| P1-trackB | 20 | 20 | COMPLETE_VALID | khớp | khớp | 0 lỗi |
| P2-trackA | 23 | 23 | COMPLETE_VALID | khớp | khớp | 0 lỗi |
| P2-trackB | 20 | 20 | COMPLETE_VALID | khớp | khớp | 0 lỗi |

- Tổng **86 judgment + 4 session note** (đúng như dự kiến).
- Hash của package v2 pass1/pass2 khớp `package_manifest`. Rubric `task06b-j-rubric-v2`
  (`dbb791cd…`).
- Đã đạt:
  - Applicability, verdict cho từng claim và `evidence_access` (bắt buộc với
    UNSUPPORTED/CONTRADICTED) đều được validator kiểm.
  - Additional claims: 42/11/53/9, có tag, evidence và rationale hợp lệ.
  - `human_verified=false` ở cả 4 file.
- **Lock:** `results/dev/judge_cal_v2/LOCK.json` lúc 05:44:42Z, lưu SHA của 4 file
  `judgments.json`. Mapping và calibration key chỉ được mở **sau** lock.
- Kết quả phân tích:
  - `analysis.json`: chuẩn, gộp cả probe.
  - `calibration_v2_summary.json`: áp đúng quy tắc đã khóa, chỉ tính report thật.
- Import đã chạy một lần ở lượt trước, ngay trước khi owner yêu cầu dừng. Lượt này giữ nguyên
  output đó (thư mục đã tồn tại nên không import lại) và kiểm tra lại toàn bộ hash.

## 2. Provenance thực tế của Judge

- Model: **UNKNOWN**. Owner không cung cấp output `/status`. Cả 4 session note **tự báo**
  "Claude Opus 5.5 (claude-opus-5-5)", ghi dưới nhãn `self_reported_model_UNVERIFIED`.
- Session ID: UNKNOWN. Phương thức: `INTERACTIVE_LLM_JUDGE_BLIND_BATCH`,
  `automated_api_inference=false`.
- Session note của P1-A ghi: *"Response files were generated through a local helper script that
  checks claim IDs, applicability and evidence_access, then writes the JSON."*
  - Trong kit **không còn file script nào** (đã kiểm: kit không có file lạ).
  - Không thể xác minh script chỉ ghi file hay còn sinh nội dung. Số rationale khác nhau thấp
    hơn tổng số ở **cả 4** pass (ví dụ P2-A có 77/115 rationale tiêu chí khác nhau, dù P2 không
    nhắc tới script). Lý do hợp lý nhất: 9 item dùng chung một report gốc.
  - Đánh giá: **provenance chưa xác minh**. Không loại P1-A, nhưng ghi nhận như một giới hạn.
- Không có dấu hiệu contamination nào được ghi nhận ở 4 phiên này.

## 3. Agreement theo từng tiêu chí (P1 so với P2, chỉ report thật, ghép qua mapping evaluator-only)

Công thức đã khóa (RUBRIC_V2 §3): exact agreement ≥ 0.8 trên report thật assessable **và**
probe đi đúng chiều. Within-one và kappa chỉ là thông tin phụ.

| Tiêu chí | n cặp | Exact | Tỷ lệ | Lệch ≤ 1 điểm | κ | Probe (fail / kiểm) | Trạng thái |
|---|---:|---:|---:|---:|---:|---|---|
| R1 factual support | 12 | 9 | **0.75** | 1.00 | 0.63 | 0/16 | **UNRELIABLE** |
| R2 traceability | 12 | 12 | 1.00 | 1.00 | 1.00 | 0/16 | RELIABLE |
| R7 uncertainty | 12 | 10 | 0.833 | 1.00 | 0.67 | 0/16 | RELIABLE |
| R8 decision/safety | 15 | 11 | **0.733** | 1.00 | 0.45 | 0/16 | **UNRELIABLE** |
| R9 next-step | 12 | 10 | 0.833 | 1.00 | 0.43 | 0/16 | EXPLORATORY (sẽ đạt nếu là primary) |
| R3 tool decision | 6 | 6 | 1.00 | 1.00 | 1.00 | 0/16 | RELIABLE (n nhỏ) |
| R4 new-evidence relevance | 3 | 3 | 1.00 | 1.00 | 1.00 | 0/16 | RELIABLE (n=3, rất yếu) |
| R5 new-evidence consumption | 3 | 2 | **0.667** | 1.00 | 0.00 | 0/16 | **UNRELIABLE** (n=3) |
| R6 incremental value | 9 | 9 | 1.00 | 1.00 | 1.00 | 0/16 | RELIABLE |

- Không có cặp nào lệch quá 1 điểm.
- Phân bố điểm từng pass: xem `calibration_v2_summary.json` (`distribution_p1/p2`).
- **Verdict mức claim** (kết quả chính theo v2):
  - Track A: 30/30 claim thật và 40/40 claim probe khớp giữa hai pass.
  - Track B: 29/30 và 39/40.
- **`evidence_access`** (không phải tiêu chí, nhưng đã được dùng): chỉ 2/7 cặp claim âm thật
  khớp, và 6/10 cặp probe khớp. Kết quả: **không ổn định**.

## 4. Probe (8 probe, tách khỏi mẫu thật)

**Mức claim (claim được chèn), 2 pass × 2 view:**

| Probe | Cực | Verdict | Tag kỳ vọng | `evidence_access` |
|---|---|---|---|---|
| unsupported-api | NEG | 4/4 CONTRADICTED | có ở 3/4 (P2-A thiếu UNSUPPORTED_API, chỉ có WRONG_ATTRIBUTION) | AGENT_VISIBLE 4/4 |
| runtime-claim | NEG | 4/4 UNSUPPORTED | 4/4 | NO_STATIC_SOURCE 4/4 |
| score-as-probability | NEG | 4/4 CONTRADICTED | 4/4 | AGENT_VISIBLE 4/4 |
| absence-overclaim | NEG | 4/4 UNSUPPORTED | SCOPE_OVERCLAIM 4/4 | **AGENT_VISIBLE / ACCESSIBLE_NOT_RETRIEVED / INACCESSIBLE ×2** (không thống nhất) |
| semantic-self-corroboration | NEG | 4/4 UNSUPPORTED | 4/4 | AGENT_VISIBLE ×2 / NO_STATIC_SOURCE ×2 |
| wrong-attribution | NEG | SUPPORTED ×3, PARTIALLY ×1 | WRONG_ATTRIBUTION 4/4 | — |
| scoped-observation | POS | 4/4 SUPPORTED, không tag | — | — |
| correct-abstention | POS | 4/4 SUPPORTED, không tag | — | — |

**Mức tiêu chí** (so với report fc v3.4 gốc; base: P1 common R1/R2/R7/R8 = 2/2/2/2, P2 =
2/2/1/2; investigation R3–R6 = 2/2/1/1):

- **R1** giảm về 0 với 6/6 probe âm có claim sai, ở cả hai pass. Riêng wrong-attribution giữ
  R1=2; đúng, vì fact là thật.
- **R2** bắt được wrong-attribution (0) ở cả hai pass.
- **R5** giảm về 0 với absence, runtime, api, nhưng **không** giảm với score-as-probability và
  semantic self-corroboration. Đây đúng là primary-criterion rule của v2.
- **R6:** api → −1; absence và runtime → 0. Score-as-probability và semantic self-corroboration
  **không** làm giảm R6. Tranh luận được: claim xác suất có thể gây hiểu sai, nhưng v2 không
  bắt buộc phải giảm.
- **R8** chỉ giảm với semantic self-corroboration (1 ở cả hai pass); unsupported-api cho P1=1,
  P2=2. R8 kém nhạy với probe.
- **Probe dương:** không probe nào bị phạt ở bất kỳ tiêu chí nào.
- **Giới hạn của phép kiểm hướng:** "probe âm không cao hơn base" luôn đạt khi base đã ở điểm
  tối đa. Vì vậy 0/16 fail **không** chứng minh độ nhạy; độ nhạy chỉ thấy được qua các mức
  giảm liệt kê ở trên.

## 5. Tiêu chí UNRELIABLE và hệ quả (theo protocol đã khóa)

**R1, R5, R8 = UNRELIABLE**: vẫn báo cáo nhưng chỉ ở mức exploratory, loại khỏi primary
aggregate. **R9** tiếp tục là exploratory. `evidence_access` chỉ mang tính mô tả. Phân tích
accessibility dùng **metadata tất định** của manifest v2 (`accessibility_class`, chỉ số
entry), không dùng nhãn của Judge.

Ảnh hưởng tới câu hỏi nghiên cứu (correctness, specificity, relevance, verification planning,
utility, unsupported claims, unsafe conclusions):

| Thành phần | Cách đo còn dùng được | Đánh giá |
|---|---|---|
| Correctness / unsupported claims | **Verdict mức claim** (khớp 30/30, 29/30) cùng R2 | **Đo được.** R1 ở mức điểm tổng không ổn định, nhưng verdict từng claim thì ổn định |
| Specificity / utility | R6 (9/9) | Đo được (calibration n=9) |
| Relevance của evidence mới | R4 (3/3) | Đo được nhưng bằng chứng về độ tin cậy rất yếu (n=3) |
| Evidence consumption | R5 UNRELIABLE | **Không đo được bằng Judge.** Thay bằng chỉ số tất định: entry liên quan đã thấy hay đã đọc, số lần đọc (`pipeline_metrics.coverage_diagnostic`) |
| Uncertainty | R7 | Đo được |
| Tool decision | R3 (6/6) | Đo được (n nhỏ) |
| Decision safety | R8 UNRELIABLE | Chỉ mô tả, kèm chỉ số tất định (effective action, fail-safe) |
| Verification planning | R9 exploratory | **Không trả lời được** ở mức primary |

**Kết luận:** primary outcome **vẫn đo được ở dạng thu hẹp**: verdict mức claim, R2, R3, R4,
R6, R7, cộng metrics tất định. Câu hỏi về **verification planning** và **semantic evidence
consumption** **không** thể được trả lời một cách đáng tin cậy.

## 6. Phân tích chi tiết các bất đồng (report thật)

Mọi bất đồng đều chỉ lệch 1 điểm.

- **R1 (3 ca):**
  - findstr, tool có sẵn nhưng không gọi (P1=1, P2=0): cả hai đều xác định claim "65 KB → có
    thể bị packing" là không có căn cứ; P1 coi đó là giả thuyết có rào đón, P2 coi là claim
    quan trọng.
  - findstr no-tool v3.1 (P1=0, P2=1): khác nhau ở cách cân nặng nhẹ câu "SHA matches a known
    system file".
  - findstr v3.4 (P1=2, P2=1): khác nhau ở cách nhìn mức độ lỏng lẻo của các câu phụ.
  - → Bất đồng nằm ở **ngưỡng "material claim"**, không nằm ở verdict từng claim (verdict khớp).
- **R7 (2 ca):**
  - fc v3.4 sạch (P1=2, P2=1): cùng nêu các giới hạn, khác nhau ở mức "constrain the
    conclusion".
  - findstr, tool không gọi (2/1): P2 đòi giới hạn cho giả thuyết packing.
- **R8 (4 ca):**
  - **3 template static: P1=2, P2=1 có hệ thống**, P2 lý luận "justification thin, rests solely
    on model output".
  - tracert, tool không gọi: 1/2.
  - **Safe fallback (v3.3 incomplete): 2/2 ở cả 3 ca, nhất quán.**
  - R8 không phân biệt được "khuyến nghị an toàn" với "lý lẽ của khuyến nghị".
- **R5 (1 ca):** tracert v3.4 (P1=1, P2=0). Cả hai cùng xác định các entry 16–47 (gồm WS2_32
  từ index 26) là truy cập được nhưng không được đọc; P2 coi đó là "partial view treated as
  complete". Với n=3, một ca bất đồng đã đủ làm R5 trượt ngưỡng.
- **R9 (2 ca):** khác nhau ở việc một gợi ý ngầm có được tính là next-step chung chung hay
  không.

### R3–R6 trên report thật (cả hai pass)

| Report | R3 | R4 | R5 | R6 |
|---|---|---|---|---|
| tracert v3.4 | 2/2 | 2/2 | 1/0 | **−1/−1** |
| findstr v3.4 | 2/2 | 2/2 | 1/1 | 0/0 |
| fc v3.4 | 2/2 | 2/2 | 1/1 | 1/1 |
| tool có sẵn nhưng không gọi (v3.1, 3 ca) | 0/0 | NA | NA | −1/−1, −1/−1, 0/0 |
| no-tool v3.1 (3 ca) | NA | NA | NA | 0/0, 0/0, −1/−1 |

- **Gọi tool hay đọc retrieval không tự động mang lại giá trị:**
  - tracert gọi tool, evidence liên quan, nhưng R6 = −1 vì claim "40 KB bất thường / path-hash
    mismatch".
  - findstr gọi tool nhưng R6 = 0.
  - Chỉ fc (có đọc một trang, phạm vi đúng) được R6 = 1.
- **Quan sát giới hạn phạm vi đúng và từ chối kết luận đúng:** không bị phạt, cả ở probe và
  report thật.
- **Không gọi tool khi câu hỏi cần import:** R3 = 0 ở cả hai pass (3/3), nhất quán.

## 7. Giới hạn trong suy luận của Judge

1. **Suy luận vượt năng lực tool (JUDGE_REASONING_ERROR, nhẹ).** Ở P1-B, report findstr có tool
   nhưng không gọi (`J-020809bba1`), claim C3 nói về packing suy từ kích thước file. Judge xếp
   `evidence_access = ACCESSIBLE_NOT_RETRIEVED`, tức ngầm cho rằng nếu gọi imports analyzer thì
   sẽ có evidence quyết định. Thực tế:
   - Imports analyzer chỉ đưa ra bảng import khai báo. Nó có thể cung cấp **quan sát gián
     tiếp** (ví dụ bảng import rất nhỏ là một tín hiệu yếu).
   - Nó **không trực tiếp xác minh packing**; cần entropy hoặc section, mà hệ thống không có.

   Rationale của chính Judge ("could have shown the actual import table") thì đúng; sai nằm ở
   phân loại access. P2 xếp `NO_STATIC_SOURCE`, chính xác hơn. Không ảnh hưởng điểm (R3=0,
   R6=−1 ở cả hai pass). Raw judgment giữ nguyên.
2. **`evidence_access` không ổn định** (2/7 cặp claim thật, 6/10 cặp probe). Đối chiếu với trace
   và budget cho probe absence-overclaim của fc:
   - fc đã dùng 4/5 lượt (TOOL, READ, FINISH, FINISH). Entry 32–47 **truy cập được nhưng không
     đọc** (có thể chọn READ thay vì FINISH). Entry 48–63 chỉ tới được bằng cách nhảy offset.
   - Entry 64–111 **không bao giờ được commit**. Trong 64 entry đã commit chỉ có msvcrt/ulib.
   - Như vậy phần quyết định việc claim "không có API mạng ở đâu cả" không kiểm chứng được nằm
     ở 64–111, tức `INACCESSIBLE_BEYOND_LIMITS` (P2 đúng). P1 chọn AGENT_VISIBLE (vì độ phủ
     một phần đã lộ ngay trong evidence nhìn thấy) hoặc ACCESSIBLE_NOT_RETRIEVED.

   Phân loại: **chủ yếu là RUBRIC_AMBIGUITY** ("deciding evidence" không rõ nghĩa với scope
   overclaim, vì một claim có thể vướng nhiều lớp truy cập cùng lúc), **cộng MISSING_GRADING
   CONTEXT** (Track A không thấy trace nên không biết số lượt còn lại). Với các claim ngoài
   evidence như "40 KB bất thường", chọn AGENT_VISIBLE hay NO_STATIC_SOURCE đều có thể bảo vệ
   được, nên đó là trường hợp **thật sự không xác định duy nhất**.

   **Metadata accessibility tất định** (manifest/trace) được tách khỏi **phán đoán semantic**
   của Judge; chỉ dùng phần tất định.
3. **Ngưỡng "material claim" dao động** giữa các pass (nguồn của bất đồng R1).
4. **R8 lẫn hai construct**: mức độ an toàn của hành động và độ dày của lý lẽ (gây bất đồng có
   hệ thống trên template static).
5. Cùng họ model (Claude), viết probe và chấm probe; thêm vào đó provenance helper script của
   P1-A chưa xác minh được (§2).

## 8. Self-corroboration

Structural và semantic là hai chỉ số **riêng biệt**. Trên 12 report Agent thật ở Track A:

- **Structural (checker tất định):** 8/12 bị flag.
- **Semantic (Judge v2):** 2/12, và **khớp giữa hai pass ở cả 12/12**:
  - tracert v3.4: TRUE ở cả hai pass.
  - fc no-tool v3.1: TRUE ở cả hai pass.
  - Các ca còn lại: FALSE ở cả hai pass.
- Đối chiếu với 6 ca trong đề xuất của developer: Judge v2 cho **FALSE ở cả hai pass** với cả
  6 (#1–#6), nhất quán với đề xuất "0/6 semantic rõ ràng". Các ca borderline (#2, #4, #5, #6)
  vẫn **PENDING_ADJUDICATION**. Kết quả của Judge **không** thay thế phán quyết của người;
  human adjudication **chưa** hoàn tất.

**Ba câu hỏi để owner phân xử (trích nguyên văn từ SELF_CORROBORATION_ADJUDICATION.md):**

> - (a) Câu "score supports the classification" (#4) có tính là semantic không?
> - (b) `alignment=CONSISTENT` cộng với prediction trong supporting (#6) có tính không?
> - (c) Assessment dựa chủ yếu vào prediction để chọn khuyến nghị (#5) có tính không?

Ngữ cảnh cho từng câu:

- **#4:** findstr v3.4, câu *"The low raw score supports benign classification but lacks
  runtime confirmation."*
- **#6:** fc v3.4, `alignment=CONSISTENT`, `supporting_evidence_ids` = [prediction, imports],
  văn bản trung tính.
- **#5:** fc, tool không gọi, change_explanation *"assessment based on existing low-risk
  prediction and lack of import data."*

## 9. Checklist cuối cho confirmatory

| # | Điều kiện | Trạng thái | Bằng chứng |
|---|---|---|---|
| 1 | Phân bổ questions v2 = 2/6/4/4/4 | PASS | Đếm lại từ manifest v2 |
| 2 | 20 PE đủ điều kiện, SHA và chương trình khác nhau | PASS | 20 SHA khác nhau, 20 chương trình khác nhau |
| 3 | Độc lập mức chương trình | PASS | Audit v1 (tên, OriginalFilename, Jaccard) |
| 4 | SHA hiện tại khớp | PASS | Băm lại lúc này: 0 drift |
| 5 | Neutral staging | PASS | Test + DEV smoke (0 token identity) |
| 6 | Retrieval thực sự tới được | PASS (theo thiết kế) | Lớp retrieval = entry đầu tiên ở 16–47, phù hợp budget 5 lượt |
| 7 | Questions và reference đóng băng | PASS | `questions_sha256` khớp code; manifest v2 |
| 8 | Freeze Agent/model/config | READY_NOT_FROZEN | Freeze được ghi khi `runner prepare`; 19 source hash; CFG giống 06B-R2 |
| 9 | Runner isolation | PASS | MOCK integration + live DEV smoke |
| 10 | Ollama | AVAILABLE lúc này (digest `d8b0f5e9…`) | Phải kiểm lại lúc chạy |
| 11 | Judge reliability | **PARTIAL** | R2, R3, R4, R6, R7 và verdict mức claim ổn định; R1, R5, R8 UNRELIABLE; `evidence_access` không ổn định |
| 12 | Primary outcome khả thi | **PARTIAL** (dạng thu hẹp) | §5 |
| 13 | Không leakage | PASS (mitigated); residual: nhận diện qua import | |
| 14 | Self-corroboration | Structural và semantic tách riêng; adjudication **PENDING** | §8 |
| 15 | Owner authorization | **NOT_GRANTED** | |

## 10. Khuyến nghị: **CONDITIONAL GO** (không phải GO đầy đủ)

**Lý do có thể tiến hành:**

- Hạ tầng, dữ liệu và câu hỏi đã sẵn sàng và đóng băng.
- Theo đúng protocol đã khóa, primary outcome vẫn đo được ở dạng thu hẹp: verdict mức claim
  (rất ổn định), R2, R3, R4, R6, R7, cùng metrics tất định về pipeline, coverage và
  accessibility.
- Không cần sửa rubric hay thêm phiên Judge để tiến hành.

**Điều kiện, owner phải chấp nhận trước khi chạy:**

1. Primary aggregate chỉ gồm: verdict mức claim, R2, R3, R4, R6, R7. R1, R5, R8 và R9 chỉ là
   exploratory. `evidence_access` chỉ mô tả. Accessibility dùng metadata tất định. Đây là hệ
   quả trực tiếp của quy tắc đã khóa, không phải thay đổi mới.
2. Báo cáo trước rằng nghiên cứu **không** trả lời được một cách đáng tin cậy các câu hỏi về
   *verification planning* và *semantic evidence consumption*. Consumption chỉ được báo qua
   chỉ số tất định.
3. Chấp nhận các giới hạn:
   - Judge reliability dựa trên self-consistency của cùng một model, với n nhỏ (R4 và R5 chỉ
     n=3).
   - Provenance helper script của P1-A chưa xác minh.
   - Human grading PENDING.
   - Cohort benign n=20 (mỗi lớp 2–6 case).
4. Self-corroboration: báo hai chỉ số tách riêng; các ca borderline PENDING_ADJUDICATION (không
   chặn việc chạy).
5. Cấp authorization với chuỗi `--authorized-by`. Chạy **một lần duy nhất**. Không đổi mẫu,
   câu hỏi, model hay analyzer sau khi đã thấy output.

**NO_GO** nếu owner yêu cầu trả lời đầy đủ câu hỏi nghiên cứu gốc, gồm cả planning và semantic
consumption, với độ tin cậy của Judge. Phương pháp hiện tại không đủ cho các phần đó, và theo
yêu cầu của owner sẽ không mở rubric v3 hay thêm phiên Judge.

Confirmatory **CHƯA CHẠY**.
