# TASK 07C rev 3 — investigation-v4.3 (final hai bước): kết quả

| Hạng mục | Giá trị |
|---|---|
| Loại | `DEV_DIAGNOSTIC_CONSUMED_COHORT` (cohort `cases_v2` của 07B đã dùng). Không phải confirmatory. Metric tất định `task07b-metrics-v4`; không có semantic grading |
| Track | `RAW_PE_E2E`, `LOCAL_QWEN` (`qwen3.5:4b`, digest `d8b0f5e9…`, Ollama 0.40.16 headless) |
| Freeze | `ec2e85de155a0929d8939eb0516cb836a9af4a80` (thay cho `5169eec` trước khi chạy, vì mở rộng phạm vi M4 sang `unresolved.topic`) |
| Run | Owner chạy 09:38:55–10:06:19, có 1 lần dừng hạ tầng (§4). 40/40 run có final (11 FINISHED, 29 FINISHED_FLAGGED) |
| Artifact | `results/frozen_v43/V4_3_s{42,7}/`, `results/frozen_v43/metrics_v4.json`, `run_stdout.txt` |
| Engineering completion | **PASS** |
| Research completion | **PARTIAL**. 3/4 tiêu chí đạt ở cả hai seed; latency **không đạt ở s42** (1.65 > 1.5), nên theo PROTOCOL_V43 v4.3 **không đạt** |

## 1. Tóm tắt

- Tách final thành hai lần gọi, mỗi lần một ràng buộc, đã sửa đúng lỗi của v4.2 (A5):
  - M1b render lên **7/8 và 6/8**, so với 5/8 và 4/8 của v4.2; V4 07B là 7/8 và 7/8.
  - **20/20** run ở cả hai seed có câu trả lời render, so với 85% của 07C-R. Các case RA và NOT_STATIC được trả
    lời bằng absence claim đã kiểm và `unresolved` theo enum.
- Cái giá là thời gian: thêm một lần gọi model và nhiều repair hơn. Median latency 40.73 s và 39.21 s, tức
  **1.65× và 1.42×** V4.
  - **Seed 42 vượt ngưỡng 1.5**, nên theo tiêu chí đăng ký trước, v4.3 **không đạt**.
  - Không nới ngưỡng sau khi đã thấy kết quả.
- **Đạt tiêu chí sản phẩm nhờ trusted filter ≠ model đã học được.**
  - F1 vẫn viết câu phủ định ở 16/20 (s42) và 15/20 (s7) run, nên phải repair.
  - Sau repair vẫn còn 20 và 14 câu bị loại.
  - M4_raw là 0.20 và 0.10.

## 2a. Tiêu chí sản phẩm (PROTOCOL_V43; phải đạt cả hai seed)

| Tiêu chí | Ngưỡng | s42 | s7 | Kết luận |
|---|---|---|---|---|
| M1b render | ≥ 6/8 | 7/8 | 6/8 | đạt |
| `rendered_answer_rate` | ≥ 18/20 | 20/20 | 20/20 | đạt |
| M10 | ≥ 19/20 | 20/20 | 20/20 | đạt |
| Median latency V4_3 / V4 (07B) | ≤ 1.5 | 40.73 / 24.62 = **1.65** | 39.21 / 27.56 = 1.42 | **không đạt (s42)** |

**M4 render:** 2/20 (0.10) ở s42 và 0/20 ở s7. Phần findings thỏa do cấu trúc; phần `unresolved.topic` thì
**không**. Hai topic bị bắt ở s42 là "Complete absence of registry API imports" (0016) và "Confirmation of
absence of StopServiceW and other config APIs" (0015). Topic là free text của model và không có filter.

## 2b. Hành vi model (DIAGNOSTIC, không ngưỡng) và so sánh

| Chỉ số | BASE 07B s42/s7 | V4 07B s42/s7 | V4_2 07C s42/s7 | **V4_3 s42/s7** |
|---|---|---|---|---|
| M1b (render với v4.2/v4.3) | 0/8, 0/8 | 7/8, 7/8 | 5/8, 4/8 | **7/8, 6/8** |
| M8 query hit | — | 7/8, 7/8 | 6/8, 7/8 | 7/8, 7/8 |
| M4 raw unscoped (định dạng khác nhau, so sánh có giới hạn) | 0.05, 0.20 | 0.60, 0.55 | 0.05, 0.10 | 0.20, 0.10 |
| M4 render unscoped | — | — | 0, 0 | 0.10, 0 |
| Run có câu trả lời render | — | (07C-R: 85%, 85%) | — | **20/20, 20/20** |
| M2_correct_no_tool | 0/8, 0/8 | 4/8, 4/8 | 4/8, 4/8 | 3/8, 3/8 |
| M9 | — | 7/8, 7/8 | 7/8, 6/8 | 5/8, 7/8 |
| M10 | 20/20 | 20/20 | 20/20 | 20/20 |
| Median latency (s) | — | 24.62, 27.56 | 26.71, 30.35 | 40.73, 39.21 |

V4_3: số repair theo `step_repairs` là F1 16 và 15 run, F2 13 và 7 run. Câu F1 bị loại sau repair: 20
(14 run) và 14 (11 run). absence_claims accepted/rejected: 21/15 và 28/11. Truncation, overflow, lỗi trong run
và isolation fail đều bằng 0.

Nhiễu giữa hai seed: M1b 1, M9 2, M4 rate 0.10. Không chênh lệch nào giữa hai seed vượt nhiễu.

## 2c. Vì sao FLAGGED cao (29/40)

FLAGGED là cờ của verifier, **không phải lỗi**: báo cáo vẫn render, phần bị flag được loại hoặc ghi chú.
Phân rã theo cờ (một run có thể mang nhiều cờ):

| Cờ | s42 | s7 | Ý nghĩa |
|---|---|---|---|
| `free_text_absence_rejected` | 14 | 11 | F1 còn câu phủ định sau repair → bị loại (P1) |
| `absence_claims_rejected` | 7 | 4 | Claim F2 vẫn bị reject sau repair (scope không đúng hoặc chưa exhausted) |
| `absence_beyond_coverage_suspected` | 3 | 4 | Verifier nghi absence vượt phạm vi đã phủ |
| `absence_claim_without_imports_source_suspected` | 3 | 0 | Claim không có nguồn là import |
| `finding_flags_present` | 3 | 0 | Finding có cờ của verifier v4 |

Cờ chủ đạo là `free_text_absence_rejected`: model 4B vẫn viết phủ định trong F1 dù prompt cấm. Tỷ lệ FLAGGED
cao hơn V4_2 (15/40) vì v4.3 kiểm hai bước và ghi lại cả câu đã bị loại.

## 2d. `unresolved.topic` do model viết

Nguyên văn, kèm reason (NOT_ST = NOT_STATIC_DETERMINABLE, NOT_CO = NOT_COVERED, INSUFF = INSUFFICIENT_EVIDENCE).

**s42** (34 topic):

- 0001 INSUFF "Network communication capability"
- 0002 INSUFF "Network communication capability"; NOT_CO "Presence of network APIs in unseen import entries"
- 0003 NOT_ST "Runtime registry read capability"; NOT_CO "Full import table coverage for registry APIs"
- 0004 INSUFF "Presence of CreateFile import" / "…WriteFile…" / "…MoveFile…" / "…CopyFile import"
- 0005 INSUFF "Network communication capability"
- 0006 NOT_ST "Runtime execution of process control APIs"; INSUFF "Full import table coverage for memory access APIs"
- 0008 INSUFF "Read file capability", "Write file capability"; NOT_CO "Move file capability", "Delete file capability"
- 0009 INSUFF "Accessing another process's memory"
- 0010 INSUFF "Delay-loaded API presence"
- 0012 INSUFF "File system read/write/delete/move capabilities"
- 0014 NOT_CO "Presence of network socket APIs (e.g., WS2_32.dll imports)"; INSUFF "Network communication capability"
- 0015 INSUFF "Complete list of service control APIs imported"; NOT_CO "Confirmation of absence of StopServiceW and
  other config APIs"
- 0016 NOT_CO "Complete absence of registry API imports"; INSUFF "Registry modification capability"
- 0017 INSUFF "Which specific APIs are imported?"; NOT_ST "What is the runtime behavior of the image?"
- 0018 INSUFF "Runtime network communication capability"; NOT_CO "Presence of Winsock/socket APIs in unviewed
  import entries"
- 0019 NOT_CO "IPHLPAPI.DLL contents", "api-ms-win-core-url-l1-1-0.dll contents"; INSUFF "HTTP capabilities",
  "ICMP capabilities"
- 0020 NOT_CO "Specific imported APIs"

**s7** (24 topic):

- 0001 NOT_ST "Network communication capability"
- 0002 INSUFF "Runtime network communication capability"; NOT_CO "Presence of unlisted network APIs in import table"
- 0004 INSUFF "Presence of CreateFile, ReadFile, WriteFile, MoveFile, DeleteFile imports"
- 0005 NOT_ST "Runtime network communication capability"
- 0008 NOT_CO "ReadFileW capability", "WriteFileW capability", "DeleteFileW capability"
- 0009 NOT_ST "Runtime capability to create processes", "Runtime capability to terminate processes"
- 0012 INSUFF "File system read/write/move/delete capability" (4 topic riêng)
- 0014 NOT_CO "ICMP capability"; INSUFF "Other network APIs not matching prefix"
- 0015 INSUFF "File capability to create services", "File capability to stop/configure services"; NOT_CO "Presence
  of other service management APIs"
- 0018 NOT_ST "Actual network communication at runtime"; NOT_CO "Indirect network protocols (DNS, etc.)"
- 0019 NOT_CO "HTTP-related APIs", "ICMP-related APIs"; INSUFF "Socket communication capability"

**Nhận xét (DIAGNOSTIC, không phải semantic grading):**

- Phần lớn topic là câu hỏi mở hợp lý.
- Reason không phải lúc nào cũng khớp. Ví dụ 0004 s42 dùng INSUFFICIENT cho các API mà query đã phủ và trả 0
  match; đáng ra phải là absence claim.
- 2 topic s42 thực chất là khẳng định vắng mặt toàn bảng.

## 3. Bảng quyết định (PLAN §2c / PROTOCOL_V43)

| Dòng | Quan sát | Áp dụng? |
|---|---|---|
| Đạt cả bốn tiêu chí → v4.3 là ứng viên cho bước sau | Latency s42 1.65 > 1.5 | Không |
| Không đạt → ghi negative result vào A4/A5; ĐÓNG TASK 07 (time-box) | 3/4 tiêu chí đạt; latency trượt ở một seed | **Có** |

Kết luận ghi lại:

- v4.3 giải quyết được vấn đề chất lượng (M1b và câu trả lời có mặt) nhưng vượt ngân sách latency đã đăng ký.
- Theo time-box, **không tối ưu thêm**.

## 4. Sự cố, deviation, limitation

- **Dừng hạ tầng:** 09:52:34 bắt đầu nhóm s7.
  - `prepare` ghi xong 20 × (`_A`, `_initial_state`, `_initial_trusted_trace`).
  - Rồi `validate_freeze` raise `BLOCKED_OLLAMA_UNAVAILABLE`.
  - Kiểm bằng mtime: **0 trace `_V4_3.json` nào của s7 có trước lần START 09:54:08**.
  - Lần START thứ hai có cùng freeze, version và digest. s42 bị skip vì đã đủ trace; s7 chạy đủ 20 case.
  - Đúng quy tắc dừng của PROTOCOL §6. Không chạy lại có chọn lọc.
- **Deviation:** không có sau freeze `ec2e85d`.
- **Limitation:**
  - Cohort đã dùng, n = 8 RP mỗi seed, chỉ PE benign, DEV_DIAGNOSTIC: không khái quát hóa được.
  - M1b chỉ đo trích entry, không đo ngữ nghĩa. Semantic grading: NOT_RUN.
  - Latency so với V4 lấy từ lần chạy 07B (cùng máy, cùng phiên bản), không phải chạy cặp đôi.
  - So sánh M4 qua các contract có giới hạn.

## 5. Completion

- **Engineering: PASS.**
  - `investigation-v4.3`: F1/F2, mỗi bước repair 1 lần, `render_v43`, arm V4_3, metrics v4.
  - Test unit và MOCK_LLM. Review PASS.
  - Freeze trước run, 40/40 run write-once.
  - Regression 901 passed / 0 failed / 4 skipped (+83 subtests) tại freeze.
- **Research: PARTIAL.**
  - Có cải thiện rõ so với v4.2 về M1b và câu trả lời render, nhưng tiêu chí latency đăng ký trước không đạt ở
    s42.
  - Hành vi model chưa thay đổi: vẫn phủ định trong F1 và gán reason chưa đúng.
