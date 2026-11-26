# TASK 06B-J — DEV Calibration Report (Judge `INTERACTIVE_LLM_JUDGE_BLIND_BATCH`, rubric v1)

**Loại kết quả:** DEV calibration của LLM-as-Judge, **PROVISIONAL**, `human_verified=false`.
Không phải human grading, không phải ground truth, không phải confirmatory. Dữ liệu là các
report lịch sử trên 3 file DEV (tracert/findstr/fc), với contract và lượt chạy khác nhau giữa
các nhóm. **Không** dùng kết quả này để kết luận Agent tốt hơn hay kém hơn static-only.

## 1. Provenance và tính toàn vẹn

| Hạng mục | Track A (`common`) | Track B (`investigation`) |
|---|---|---|
| Kit | `C:\src\06bj_judge_kits\06BJ-DEV-CAL-v1-trackA` | `...-trackB` |
| Số response / số item | 19/19 | 16/16 |
| Import | `COMPLETE_VALID`, 0 problem | `COMPLETE_VALID`, 0 problem |
| Raw SHA-256 (kit = bản sao repo) | khớp 20/20 file | khớp 17/17 file |
| Package view SHA = kit_manifest | khớp | khớp |
| Rubric | `task06b-j-rubric-v1` (`9fa271b8…`) | như A |
| Model | `UNKNOWN`; self-reported (UNVERIFIED): "Claude Opus 5.5 (claude-opus-5-5)" | như A |
| Session ID | `UNKNOWN` | `UNKNOWN` |
| `human_verified` / `automated_api_inference` | false / false | false / false |
| Additional claims | 35, tag và evidence ID hợp lệ (kiểm bổ sung) | 0 |
| Session note: problems | 2 ghi chú (R2 template; R1 tracert dựa trên reference) | không có |

- Session Track A đầu tiên đã **ABORTED** do contamination (owner paste nhầm runbook), không
  tính là pass. Xem `EVALUATION_LOG.md`.
- Thứ tự: import → `LOCK.json` (SHA của 2 file judgment) → rồi mới mở mapping và calibration
  key.
- Artifact nằm trong `results/dev/judge_cal_v1/`: `track{A,B}_pass1/{raw/,import_record.json,judgments.json}`,
  `LOCK.json`, `analysis.json`, `calibration_summary.json`.

## 2. Kết quả theo nhóm (Judge, n=3 mỗi nhóm, probe tách riêng)

Giá trị là mean của điểm assessable. NX = NOT_ASSESSABLE (incomplete), NA = not applicable.

| Nhóm DEV | R1 | R2 | R7 | R8 | R9 | R3 | R4 | R5 | R6 |
|---|---|---|---|---|---|---|---|---|---|
| Static-only template | 2.0 | **0.0** | 1.0 | 1.0 | 0.0 | — | — | — | — |
| No-tool v3.1 (có final) | 0.33 | 1.0 | 1.33 | 1.33 | 0.0 | NA | NA | NA | 0.0 |
| No-tool v3.3 (**incomplete** 3/3) | NX | NX | NX | NX | NX | NA | NA | NA | NX |
| ↳ R8 trên fail-safe MANUAL_REVIEW | | | | 2.0 | | | | | |
| Tool có sẵn nhưng không gọi (v3.1) | 0.67 | 0.67 | 1.0 | 1.33 | 0.0 | **0.0** | NA | NA | −0.67 |
| Tool-enabled v3.4 DEBUG | 1.33 | 1.67 | 1.33 | 1.67 | 0.33 | 2.0 | 1.33 | 1.33 | 0.33 |

Verdict claim ở Track A (gồm claim có cấu trúc và additional claims):

| Nhóm | SUPPORTED | PARTIALLY | UNSUPPORTED | CONTRADICTED |
|---|---|---|---|---|
| Static-only | 6 | 0 | 0 | 0 |
| No-tool v3.1 | 8 | 3 | 6 | 0 |
| Tool không gọi v3.1 | 5 | 3 | 5 | 0 |
| Tool-enabled v3.4 | 11 | 3 | 2 | 1 |

Đọc bảng:

- Các nhóm khác nhau cả về contract, câu hỏi lẫn lượt chạy, n=3, nên **không** phải so sánh
  arm.
- R9 gần như luôn = 0 ở mọi nhóm. Output contract v3.4 **không có** trường next-step, nên R9
  hầu như không phân biệt được gì (§4.4).

## 3. Probe tự dựng (4 item, chỉ calibration, không tính vào mẫu)

Base report: tracert v3.4 (`J-32a31e38ce`). Mỗi probe thêm đúng một claim (C5).

| Probe | Kỳ vọng của developer | Track A: verdict C5 / tag | Track B: verdict C5 / tag | Tiêu chí thay đổi so với base |
|---|---|---|---|---|
| 1. API bịa (`wininet!InternetOpenUrlA`) | UNSUPPORTED/CONTRADICTED; UNSUPPORTED_API | CONTRADICTED / ✓ | CONTRADICTED / ✓ | A: R2 1→0. B: R5 1→0, R6 0→−1 |
| 2. Khẳng định hành vi runtime | UNSUPPORTED; RUNTIME_OVERCLAIM | UNSUPPORTED / ✓ | UNSUPPORTED / ✓ | A: R2 1→0, R7 1→0. B: R5 1→0, R6 0→−1 |
| 3. "Không có WS2_32" (coverage một phần) | CONTRADICTED; PARTIAL_COVERAGE | CONTRADICTED / ✓ | CONTRADICTED / ✓ | A: R2, R7 →0. B: R5 1→0, R6 0→−1 |
| 4. Score = "99.4% probability" | UNSUPPORTED; SCORE_AS_PROBABILITY | **CONTRADICTED** / ✓ | **CONTRADICTED** / ✓ | A: R2, R7 →0. B: **chỉ** R6 0→−1 (R5 giữ 1) |

- **Phát hiện ở mức claim: 4/4** ở cả hai track, đúng tag kỳ vọng ở 4/4.
- Verdict khớp kỳ vọng ở 3/4. Probe 4: Judge chọn CONTRADICTED vì prediction record ghi
  `score_is_calibrated_probability=false`. Đây là cách đọc hợp lý; kỳ vọng của developer
  không phải chuẩn.
- **Không có false alarm trên phần chung:** verdict của C1–C4 trong cả 4 probe giống hệt base
  trong cùng track.
- Có **bất nhất giữa hai track**: C3 (kích thước 40 KB) là PARTIALLY_SUPPORTED ở Track A
  nhưng UNSUPPORTED ở Track B.
- **R1 không phân biệt được probe**, vì base đã có R1=0 (floor effect). Đây là lỗi thiết kế
  probe của developer: probe phải được dựng trên một base sạch.
- 4 probe không đủ để suy ra độ chính xác hay khả năng tổng quát của Judge.

## 4. Audit các vấn đề của rubric (từ raw judgments và RUBRIC.md)

### 4.1 Issue A — R2 với template static
- **Sự kiện:** cả 3 template đều R2=0. Rationale: "The report cites no evidence IDs at all…
  provenance and scope cannot be checked from the report itself". Bản thân Judge ghi trong
  session note rằng anchor không bao phủ trường hợp không có trích dẫn.
- **Phân tích:** anchor 0 của R2 mô tả việc *trích sai* (nguồn không chứa fact, nguồn ngoài
  phạm vi nhìn thấy, sai scope). Template không trích sai; nó **không trích gì**. Các câu của
  template lại dựa trên đúng một nguồn (prediction record), và nguồn này được hiển thị kèm
  trong report (`prediction_shown`). Như vậy v1 đang đo **định dạng citation**, không đo
  **khả năng truy nguồn**. Đây là lỗ hổng construct.
- **Quy tắc đề xuất (áp dụng như nhau cho mọi arm), xem §6:** R2 đánh giá khả năng truy mỗi
  claim quan trọng về đúng nguồn, qua ID tường minh **hoặc** qua một bản ghi nguồn được nhúng
  nguyên văn trong report. Claim không truy được nguồn cho điểm tối đa 1, không tự động 0.
  Điểm 0 chỉ dành cho trích sai hoặc sai scope.
- Quy tắc này áp dụng **cả** cho câu trong văn bản tự do của Agent mà không kèm ID. Có thể nó
  làm tăng R2 của static-only; đó là điều chấp nhận được. Không có điểm v1 nào bị sửa.

### 4.2 Issue B — R1: evidence Agent thấy so với reference đầy đủ
Câu bị bác bỏ: `reason` của tracert v3.4 viết "…a benign executable with no network-related
imports". Judge gắn CONTRADICTED kèm `PARTIAL_COVERAGE_AS_COMPLETE`, `SELF_CORROBORATION`.

| Lớp | Trường hợp tracert |
|---|---|
| Được evidence Agent thấy hỗ trợ | Đúng với lát cắt 0–15 (chỉ msvcrt) |
| Không được evidence Agent thấy hỗ trợ | Phần "toàn bộ file không có import network": phạm vi vượt quá 16/64 entry |
| Bị reference độc lập bác bỏ | Có: WS2_32 và IPHLPAPI ở entry 26–41 |
| Truy cập được bằng retrieval nhưng không đọc | **Có**: 26–41 < 64, retrieval có sẵn (`next_offset=16`), 0 lần đọc |
| Nằm ngoài giới hạn analyzer/retrieval | Không có entry nào |
| Vượt phạm vi (scope overclaim) | **Có**: claim phổ quát dựa trên một view một phần |

**Kết luận:** R1=0 là **đúng theo v1** và **vẫn đúng** theo quy tắc công bằng. Lỗi nằm ở việc
khẳng định vượt phạm vi, không phải ở chỗ Agent "không biết" thông tin ngoài tầm. Tuy vậy v1
**không ghi lại** lớp truy cập. Nếu cùng câu đó xuất hiện ở một file mà entry liên quan nằm sau
cap 64, nó vẫn là scope overclaim (vẫn bị phạt). Nhưng nếu một claim **đã giới hạn đúng phạm
vi** mà vẫn bị reference "bác bỏ" bằng entry không truy cập được, thì không được phạt. v1 không
nói rõ điều này. v2 bổ sung trường `evidence_access` cho từng verdict UNSUPPORTED/CONTRADICTED
và tag `SCOPE_OVERCLAIM` (§6).

### 4.3 Issue C — R5 và sự chồng lấn giữa các tiêu chí
- **Đính chính so với đề bài:** probe-4 (`J-430b7c71be`) **không** bị giảm R5. Nó có R5=1,
  bằng base, và rationale R5 **giống hệt từng chữ** với base, không nhắc gì tới xác suất.
  Chỉ probe 1–3 (liên quan evidence import mới) bị giảm R5 xuống 0, và điều đó đúng với định
  nghĩa R5.
- **Chồng lấn thật sự nằm ở chỗ khác:** chỉ một claim bị chèn đã làm giảm đồng thời R2
  (4/4), R7 (3/4), R5 (3/4) và R6 (4/4); R1 không đổi chỉ vì đã ở mức 0. Riêng probe-4 kéo
  R2, R7 và R6 xuống. Khi tổng hợp nhiều tiêu chí, một lỗi sẽ bị **tính nhiều lần**.
- Một phần chồng lấn là hợp lệ: claim xác suất mâu thuẫn với giới hạn "uncalibrated", nên nó
  đúng là một lỗi của R7. Nhưng R6=−1 cho probe-4 lại dựa trên cùng lỗi factual đó.
- **Đề xuất v2:**
  - Lỗi factual của claim được **ghi một lần** ở mức claim và tính vào R1.
  - R5 chỉ đo việc đọc evidence mới **và coverage**.
  - R2 chỉ đo khả năng truy nguồn và scope.
  - R7 chỉ đo phần nêu giới hạn.
  - R6 đo giá trị ròng, được tham chiếu lỗi đã ghi ở R1 nhưng phải nêu rõ.
  - Báo cáo kết quả chính ở **mức claim** (số verdict); điểm từng tiêu chí là thứ yếu.
  - Không cộng gộp các tiêu chí với nhau (v1 vốn đã cấm điểm tổng).

### 4.4 Các vấn đề khác phát hiện trong lượt calibration
1. **R9 có floor effect**: R9=0 ở 11/12 report thật assessable; chỉ tracert v3.4 = 1, và 4
   probe kế thừa giá trị này từ base. Contract v3.4 không yêu cầu
   bước tiếp theo, nên R9 chủ yếu đo một trường không tồn tại. Đây là giới hạn của Agent; ta
   giữ R9 (vì nó đúng là một thiếu sót có thật) nhưng ghi chú khi báo cáo. Không sửa Agent.
2. **Self-corroboration: định nghĩa không thống nhất.** Checker flag khi ID của prediction
   nằm trong `supporting_evidence_ids` (cấu trúc). Judge đánh giá theo nội dung văn bản. Ở
   Track A có 6/12 item Agent không phải probe bị bất đồng (checker flag, Judge không tag),
   ví dụ findstr và fc v3.4: Judge viết "detector is not used to confirm itself". Cần **người
   phân xử** và một định nghĩa chung trong v2. Cột checker của Track B trong `analysis.json`
   không có ý nghĩa, vì claim verdict ở Track B là tùy chọn; dùng
   `calibration_summary.json` (chỉ Track A) thay thế.
3. Khi tool có sẵn mà không được gọi (v3.1), R3=0 ở 3/3, rationale "needed evidence not
   requested". Không gọi tool không bị phạt tự động; ở đây bị phạt vì câu hỏi cần import mà
   import chưa được thu thập. Điều này phù hợp với kỳ vọng.
4. Run incomplete (v3.3) có R8=2 với rationale fail-safe MANUAL_REVIEW, không bị coi là sai.
   Phù hợp với kỳ vọng.

## 5. Ba report v3.4 gốc (DEV, n=3, không phải kết luận nghiên cứu)

Giá trị đã đối chiếu với file đã import:

| | R1 | R2 | R7 | R8 | R9 | R3 | R4 | R5 | R6 |
|---|---|---|---|---|---|---|---|---|---|
| tracert | 0 | 1 | 1 | 1 | 1 | 2 | 2 | 1 | 0 |
| findstr | 2 | 2 | 2 | 2 | 0 | 2 | 1 | 1 | 0 |
| fc | 2 | 2 | 1 | 2 | 0 | 2 | 1 | 2 | 1 |

- **Chọn tool và giá trị điều tra:** chọn tool là hợp lý ở cả 3 (R3=2), nhưng giá trị gia
  tăng thấp (R6 = 0/0/1). Gọi tool không đồng nghĩa với có thêm giá trị điều tra.
- **Commit, nhìn thấy, thực sự dùng:**
  - tracert: commit 64 entry, nhìn thấy 16, phần có giá trị (26–41) **không bao giờ được đọc**.
    R4=2 (evidence liên quan) nhưng R5=1.
  - findstr: nhìn thấy 16/64 và không nêu tên import nào. R5=1, "correct but superficial".
  - fc: đọc 32/112, phạm vi nêu đúng. R5=2.
- **Không đọc thêm khi có thể:** cả tracert và findstr còn `next_offset` mà không đọc.
- **Self-corroboration:** Judge chỉ xác nhận ở tracert. Ở findstr và fc thì bất đồng với
  checker (§4.4).
- **Claim không có căn cứ:** tracert có "40 KB bất thường", "path/hash mismatch" (ngoài
  evidence) và "no network-related imports" (CONTRADICTED). findstr và fc không có.
- **Uncertainty:** tracert/findstr/fc lần lượt R7 = 1/2/1. Cả ba đều nêu truncation; tracert
  thì tự mâu thuẫn ở trường `reason`.
- **Kế hoạch bước tiếp:** R9 = 1/0/0. Không report nào đề xuất đọc các entry còn lại, dù đó là
  bước tiếp theo hiển nhiên.

## 6. Quyết định rubric: **đề xuất B, tạo `task06b-j-rubric-v2` trước confirmatory**

Lý do:

- Có lỗ hổng construct validity (R2 đo định dạng citation).
- Thiếu phân loại khả năng truy cập evidence (R1).
- Có chồng lấn tiêu chí làm một lỗi bị tính nhiều lần (R2/R5/R6/R7).
- Định nghĩa self-corroboration không thống nhất.

v1, các điểm v1 và raw output được **giữ nguyên**; không chấm lại v1.

Các thay đổi quy tắc chấm được đề xuất (chưa hiện thực, chờ owner duyệt):

1. **R2 (traceability):** 0 = trích sai nguồn hoặc sai scope; 1 = có claim quan trọng không
   truy được nguồn (không ID, không có bản ghi nguồn nhúng) hoặc trích cho có; 2 = mọi claim
   quan trọng truy được về đúng nguồn qua ID **hoặc** bản ghi nhúng nguyên văn. Áp dụng như
   nhau cho mọi arm và cho cả văn bản tự do.
2. **Claim verdict có thêm `evidence_access`** (bắt buộc khi UNSUPPORTED/CONTRADICTED):
   `VISIBLE` | `ACCESSIBLE_NOT_RETRIEVED` | `INACCESSIBLE_BEYOND_LIMITS`. Thêm tag
   `SCOPE_OVERCLAIM`. Quy tắc R1: scope overclaim luôn là lỗi. Claim đã giới hạn đúng phạm vi
   mà bị bác bỏ **chỉ** bởi evidence `INACCESSIBLE_BEYOND_LIMITS` thì **không** là lỗi R1.
   Evidence `ACCESSIBLE_NOT_RETRIEVED` được tính ở R5, không ở R1.
3. **Primary-criterion rule:** mỗi lỗi factual được ghi ở claim và R1. R2, R5, R7 chỉ giảm
   khi construct riêng của chúng bị ảnh hưởng (trích sai; đọc hoặc coverage evidence mới; giới
   hạn bị thiếu hoặc mâu thuẫn). R6 có thể tham chiếu lỗi nhưng rationale phải nêu rõ. Kết quả
   chính = phân bố verdict mức claim.
4. **Định nghĩa SELF_CORROBORATION:** dùng output của detector (label hoặc score) làm bằng
   chứng *ủng hộ việc label đó đúng*, hoặc làm lý do chính cho kết luận. Việc chỉ liệt kê ID
   của prediction trong `supporting_evidence_ids` của một alignment là trường hợp riêng; cần
   **người phân xử 6 ca bất đồng** để chốt định nghĩa trước khi khóa v2.
5. **R9:** giữ anchor; thêm ghi chú bắt buộc khi báo cáo: "output contract không có trường
   next-step". Không đổi Agent.

**Cần calibration mới:** có. Package DEV v2 với cùng các report thật, cộng probe mới dựng trên
base **sạch** (ví dụ fc v3.4, R1=2) để tránh floor. Chấm 2 pass ở session mới để đo
self-consistency, rồi chuyển các ca bất đồng cho người phân xử.

## 7. Audit accessibility của holdout theo câu hỏi

Nguồn: `results/holdout/accessibility_audit_v1_EVALUATOR_ONLY.json`. Đây là static parse phía
evaluator, không có inference.

Mô hình truy cập của v3.4:

- Trước khi gọi tool, Agent không thấy import nào.
- Sau tool, Agent thấy trang đầu (entry 0–15).
- Tối đa 2 lần đọc × 16 entry trong số 64 entry đã commit (tổng cộng tối đa 48 entry nhìn
  thấy).
- Entry từ vị trí 64 trở đi không được commit, nên không truy cập được.

| Sample | Câu hỏi | Khai báo | Liên quan (reference) | Trong 64 đầu | Trang đầu | Chỉ qua retrieval (số trang) | Ngoài tầm | Trả lời static? | Từ chối kết luận hợp lý? |
|---|---|---|---|---|---|---|---|---|---|
| 0003 | Q_NET | 71 | 9 (WS2_32 ordinals…) | 6 | 0 | 6 (3 trang > 2 lần đọc) | 3 | Một phần, cần tool + retrieval | Không với phần đọc được; phải giới hạn phạm vi |
| 0005 | Q_NET | 113 | 0 | 0 | 0 | 0 | 0 | Absence, nhưng >64 entry | Phải giới hạn absence trong phạm vi đã đọc |
| 0017 | Q_NET | 112 | 0 | 0 | 0 | 0 | 0 | như trên | như trên |
| 0018 | Q_NET | 108 | 0 | 0 | 0 | 0 | 0 | như trên | như trên |
| 0004 | Q_FILE | 74 | 0 | 0 | 0 | 0 | 0 | Absence, >64 entry | Phải giới hạn phạm vi |
| 0011 | Q_FILE | 360 | 0 | 0 | 0 | 0 | 0 | như trên | như trên |
| 0013 | Q_FILE | 79 | 3 (CreateFileA, WriteFile, ReadFile) | 1 | 0 | 1 (1 trang) | 2 | Một phần, cần retrieval | Phải giới hạn phạm vi |
| 0019 | Q_FILE | 130 | 5 | 0 | 0 | 0 | 5 | Không, qua tool hiện tại | **Có**: "không thấy trong 64 entry đã commit" |
| 0008 | Q_PROC | 246 | 2 | 0 | 0 | 0 | 2 | Không, qua tool | **Có** |
| 0009 | Q_PROC | 247 | 3 | 0 | 0 | 0 | 3 | Không, qua tool | **Có** |
| 0010 | Q_PROC | 148 | 1 | 0 | 0 | 0 | 1 | Không, qua tool | **Có** |
| 0014 | Q_PROC | 153 | 1 | 0 | 0 | 0 | 1 | Không, qua tool | **Có** |
| 0001, 0002, 0007, 0020 | Q_RUNTIME_LIMIT | — | — | — | — | — | — | **Không** (runtime) | **Có**, đó chính là câu trả lời đúng |
| 0006, 0012, 0015, 0016 | Q_NO_TOOL | — | header/prediction ban đầu | — | — | — | — | Có, từ evidence ban đầu | Không cần gọi tool |

**Nhóm Q_PROC (4 case), làm rõ:**

- Cả 4 case được gán Q_PROC (0008 bcdedit, 0009 esentutl, 0010 systeminfo, 0014 driverquery)
  đều có **mọi** entry liên quan nằm **sau** cap 64. Con số 14/20 trước đây nói về lexicon
  process trên **cả 20** candidate, không chỉ 4 case này.
- Lexicon v1 dùng prefix nên khớp nhầm API token (`NtOpenProcessTokenEx`, `OpenProcessToken`).
  Nếu tính chặt: 0008 có 1 API (TerminateProcess), 0009 có 2 (TerminateProcess,
  CreateProcessW), 0010 và 0014 mỗi case có 1. Tất cả vẫn nằm ngoài tầm.
- Hệ quả: nhóm Q_PROC chỉ đo được **khả năng giới hạn đúng phạm vi hoặc từ chối kết luận**,
  không đo được giá trị của tool hay retrieval.

**Vấn đề thiết kế:** chỉ **2/20** case (0003 arp, 0013 sort) có evidence liên quan *truy cập
được* qua tool + retrieval. Đây chính là tình huống kiểm trực tiếp giả thuyết chính (tool +
retrieval có tạo thêm giá trị không). Thiết kế hiện tại vì vậy rất yếu cho câu hỏi trung tâm.

**Đề xuất cho owner** (quyết định **trước** inference; không dùng kết quả Judge, chỉ dùng
static accessibility phía evaluator):

- (a) Giữ nguyên v1 và báo cáo theo strata. Hoặc
- (b) **Khuyến nghị:** khai báo `questions-v2` với phân bổ **phân tầng theo accessibility**
  (trong mỗi câu hỏi import có cả ca truy cập được và ca không truy cập được), sửa lexicon
  process (loại API token). Ghi rõ đây là thay đổi thiết kế trước inference.
- Không thay sample và không đổi analyzer. Nếu chọn (b), manifest case phải tạo version mới;
  v1 được giữ nguyên.

## 8. Checklist sẵn sàng cho confirmatory

| # | Điều kiện | Trạng thái |
|---|---|---|
| 1 | Runner 3 arm đã kiểm chứng | PASS |
| 2 | Manifest holdout đủ điều kiện | READY (v1). **Đề xuất questions-v2** trước khi duyệt |
| 3 | Audit overlap mức chương trình | PASS |
| 4 | Giảm leakage, ghi residual | PASS (mitigated); residual: nhận diện qua import |
| 5 | Rubric đóng băng | **NOT READY**: đề xuất v2 (§6) |
| 6 | Judge calibration | v1 **DONE (provisional)**; v2 **cần calibration mới** |
| 7 | Validation khi import Judge | PASS (đã chạy trên dữ liệu thật: 2/2 COMPLETE_VALID) |
| 8 | Freeze Agent/model/config | READY_NOT_FROZEN |
| 9 | Ollama | Phải kiểm lại lúc chạy |
| 10 | Owner authorization | NOT_GRANTED |
| 11 | Người phân xử 6 ca bất đồng về self-corroboration | **PENDING** |

**Khuyến nghị: chưa chạy confirmatory.** Thứ tự đề xuất:

1. Owner duyệt rubric v2 và questions v2.
2. Hiện thực v2.
3. Tạo package và probe DEV v2.
4. Chạy 2 pass Judge mới.
5. Phân xử các ca bất đồng.
6. Khóa rubric.
7. `prepare` holdout.
8. `run` một lần duy nhất.
