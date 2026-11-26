# TASK 06B-J — Confirmatory Report (run_v1)

**ENGINEERING:** PASS cho execution và handoff. Lượt confirmatory duy nhất đã chạy trọn, 4 kit
Judge đã export.

**CONFIRMATORY EXECUTION:** COMPLETE. 20 case × 3 arm = 60 report; 40 lượt Agent chạy với
Qwen thật, không lỗi runner.

**SEMANTIC EVALUATION:** **SEMANTIC_GRADING_PENDING**. Chưa có điểm Judge. TASK 06B-J
**chưa** hoàn tất về mặt research.

Authorization: `DACN_PROJECT_OWNER_06BJ_CONDITIONAL_GO` (CONDITIONAL GO, phạm vi thu hẹp; xem
CALIBRATION_V2_REPORT §10, EVALUATION_LOG mục 17–20).

## 1. Thực thi

| Hạng mục | Giá trị |
|---|---|
| Freeze | `results/confirmatory/run_v1/freeze.json` (SHA-256 `4b37c37f…`), mode CONFIRMATORY, base `60f58b97` |
| Model / runtime | `qwen3.5:4b` digest `d8b0f5e9…`, Ollama 0.40.16 (loopback 127.0.0.1); LightGBM `5db192ec…`, threshold 0.83219 |
| Câu hỏi | `task06b-j-questions-v2` (c70aa8a6…), phân bổ 2/6/4/4/4 |
| Số lần thực thi | **1**. Không chạy lại case nào; runner exit 0; stdout lưu ở `run_v1_stdout.log` |
| Prediction của detector | 20/20 benign, raw score 0.0010–0.0140 (giống nhau ở cả 3 arm; không phải xác suất) |
| Isolation | B: 0/20 vi phạm. C: 0/20. Target SHA khớp 40/40 |
| Leakage (mọi turn, token identity) | 0 run có leak tình cờ. Residual: có thể nhận diện chương trình qua import |

## 2. Metrics tất định theo arm (KHÔNG phải điểm semantic)

| Metric | A static | B no-tool | C tool-enabled |
|---|---|---|---|
| Report | 20 template | 20 | 20 |
| Final được chấp nhận về cấu trúc | — (template) | **7/20** | **20/20** |
| Incomplete (REQUEST_MORE_EVIDENCE → MANUAL_REVIEW) | — | **13/20** | 0/20 |
| FINISHED (sạch theo rule screen) / FINISHED_FLAGGED | — | 1 / 6 | **2 / 18** |
| Đề xuất gọi tool / D4 ALLOW / D9 commit | — | 0 / — / 0 | **20 / 20 / 20** |
| Lượt đọc retrieval (số case có đọc) | — | 0 | 7 (6 case) |
| Repair / turn error | — | 0 / 0 | 0 / 0 |
| Structural self-corroboration (checker) | — | 6/7 final | 18/20 final |
| Khuyến nghị của Agent | — | MONITOR 7 (13 không có) | MONITOR 20 |
| Hành động hiệu lực (trusted) | MONITOR (template) | MANUAL_REVIEW 20 | MANUAL_REVIEW 18, MONITOR 2 |
| Số lần gọi LLM | 0 | 27 | 67 |
| Latency mean / median (s) | — | 8.06 / 4.21 | 20.53 / 19.20 |
| Token prompt / output | 0 | 86 690 / 12 647 | 298 267 / 32 709 |

## 3. Theo lớp accessibility (B / C)

| Lớp | n | Final B / C | C gọi tool | C có đọc | Evidence liên quan đã thấy (C) | Hành động hiệu lực C |
|---|---:|---|---:|---:|---|---|
| IN_INITIAL_TOOL_PROJECTION | 2 | 1 / 2 | 2 | 0 | **2/2** | MANUAL_REVIEW 2 |
| REACHABLE_BY_BOUNDED_RETRIEVAL | 6 | 2 / 6 | 6 | 2 | **1/6** | MANUAL_REVIEW 6 |
| INACCESSIBLE_UNDER_LIMITS | 4 | 0 / 4 | 4 | 1 | 0/4 (đúng như dự kiến: ngoài tầm) | MANUAL_REVIEW 4 |
| NOT_STATIC_ANSWERABLE | 4 | 0 / 4 | 4 | 3 | — | MANUAL_REVIEW 4 |
| INITIAL_EVIDENCE_SUFFICIENT | 4 | 4 / 4 | **4** | 0 | — | MONITOR 2, MANUAL_REVIEW 2 |

"Đã thấy" là sự kiện tất định: chỉ số entry tham chiếu (lexicon tên chính xác) có xuất hiện
trong prompt của Agent hay không. Đây **không** phải phán định là Agent đã *dùng đúng* evidence
đó.

**Quan sát tất định (chưa phải kết luận semantic):**

1. C gọi tool ở **20/20** case, kể cả 4 case mà evidence ban đầu đã đủ và 4 case static không
   thể trả lời. Việc tool có cần thiết hay không sẽ do R3 (Judge) đánh giá.
2. Với lớp retrieval (6 case), C chỉ đọc thêm trang ở 2 case và chỉ ở **1/6** case evidence
   liên quan từng hiển thị cho Agent.
3. B không có final ở 13/20 case. Hệ thống fail-safe chuyển sang MANUAL_REVIEW, và đây không
   phải lỗi grounding.
4. Structural self-corroboration rất phổ biến (C 18/20). Semantic self-corroboration chưa được
   chấm.

## 4. Tình trạng đánh giá semantic

- Package `package_conf_p1` và `package_conf_p2` (rubric v2 `dbb791cd…`, seed khác nhau, mỗi
  package 60 common + 40 investigation, leakage scan PASS).
- 4 kit ngoài repo, `kit_audit=PASS`.
- Lệnh chạy: `OWNER_FINAL_JUDGE_COMMANDS.md`.
- Primary: verdict mức claim, R2, R3, R4, R6, R7, cộng metrics tất định. Exploratory: R1, R5,
  R8, R9, `evidence_access`.

## 5. Sai lệch protocol và đính chính

1. **Metadata freeze `rubric_id=v1`**: chỉ là metadata, không ảnh hưởng hành vi; **không** phải
   protocol deviation. Xem `results/confirmatory/FREEZE_METADATA_CORRECTION.md`.
2. **Lệnh REPORT §7 trỏ tới manifest v1**: lượt chạy dùng manifest **v2** đã duyệt (EVALUATION_LOG
   mục 18).
3. **Ollama UNAVAILABLE trước khi chạy**: developer đã khởi động `ollama serve` trên loopback.
   Digest khớp với DEV.

## 6. Giới hạn đã được chấp nhận

- Cohort 20 PE benign có chữ ký Windows; mỗi lớp 2–6 case.
- Không suy rộng sang malware hay độ chính xác detection; nhãn LightGBM không thay đổi giữa các
  arm.
- Judge là LLM cùng họ model; danh tính model UNKNOWN; provenance helper script (calibration)
  chưa xác minh; human grading PENDING.
- Neutral staging chỉ giảm leakage, không bảo đảm ẩn danh.
- R1, R5, R8 UNRELIABLE ở calibration; R9 exploratory. Không thể đo đầy đủ planning hay
  semantic consumption.

## 7. Kết luận nghiên cứu

**Đã có thể nói (chỉ dựa trên dữ liệu tất định):**

- Pipeline tool-enabled chạy ổn định end-to-end: 20/20 tool call được D4 ALLOW và D9 commit,
  20/20 final hợp lệ về cấu trúc.
- Arm no-tool thường không đưa ra kết luận: 13/20 xin thêm evidence.
- Agent gọi tool kể cả khi không cần (8/8 case không cần import), và hiếm khi đọc tiếp
  retrieval khi evidence nằm ở trang sau (1/6 case thấy được evidence liên quan).
- Chi phí của C khoảng 2.5 lần số lần gọi LLM và khoảng 3.4 lần token prompt so với B.

**Còn chờ (SEMANTIC_GRADING_PENDING):** liệu tool-enabled có cải thiện tính đúng mức claim,
truy nguồn, giá trị điều tra (R6), quyết định gọi tool (R3), mức liên quan (R4) và uncertainty
(R7) so với A và B, mà không làm tăng claim không có căn cứ.
