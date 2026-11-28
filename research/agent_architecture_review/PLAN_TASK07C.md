# PLAN TASK 07C — Grounding cho khẳng định vắng mặt (v4.1)

Trạng thái: DRAFT, chờ Owner duyệt. Planner, 2026-11-28.
Đầu vào: 07B ee5583b. Review S9 PASS: M1b V4 7/8 so với BASE 0/8; M4-UNSCOPED V4 0.60/0.55 so với BASE 0.05/0.20 (dòng 1 KHÔNG ĐẠT).
Mục tiêu duy nhất: giảm khẳng định vắng mặt vượt phạm vi đã xem, đồng thời giữ được M1b. Không mở rộng sang mục khác (CLAUDE.md §10).

## 1. Nguyên nhân (từ trace 07B)
Model chạy một query hẹp, chẳng hạn DLL kernel32 hoặc prefix `CreateProcess`, rồi viết bằng văn bản tự do "không có cả họ API". Verifier chỉ bắt các cụm từ trong deny-list, nên bỏ lọt cách diễn đạt mới. Model không có thông tin nào về phạm vi mình đã thực sự phủ.

## 2. Thay đổi (chỉ phần core)
1. **Coverage ledger tất định (trusted):** mỗi lần QUERY_IMPORTS hoặc LIST_IMPORT_INDEX được ghi lại thành `Q1..Qn`, gồm DLL/prefix, số entry trả về và trạng thái đã hết trang hay chưa. Model không tự viết ledger.
2. **Contract `investigation-v4.1`**, có version, tương thích ngược với v4.0:
   - Thêm trường `absence_claims[]`. Mỗi phần tử có dạng `{api_or_prefix, scope_ref: "Qk"}`.
   - Verifier chỉ chấp nhận khi `Qk` tồn tại, đã hết trang, và `api_or_prefix` thuộc đúng scope của `Qk`.
   - Ngoài trường này, mọi câu khẳng định vắng mặt trong văn bản tự do đều bị reject. Giữ nguyên whitelist và deny-list hiện có, không nới.
3. **Coverage summary ở lượt ANSWER / FORCED_FINAL:** trusted code chèn một dòng như "Đã phủ: Q1 kernel32 (hết), Q2 prefix Reg* (hết). Chưa phủ: các DLL còn lại." Dòng này là dữ kiện tất định, không phải gợi ý kết luận.
4. Khi bị reject, cho repair 1 lần. Nếu vẫn sai thì claim bị loại và ghi lại trong trace. Không được sửa câu chữ của model (CLAUDE.md §3).

Ngoài phạm vi, chỉ ghi lại: việc NOT_STATIC gọi tool theo phản xạ, policy v4.0 và các nit trình bày.

## 2b. Sửa đổi rev 2 (Owner duyệt 2026-11-28): final có cấu trúc, contract `investigation-v4.2`
**Bằng chứng:** sau S2 smoke ×2, ledger và `absence_claims` hoạt động (5/5 accepted). Nhưng ở 2/2 case, sau repair Qwen vẫn lặp câu absence rộng bằng free-text. Lỗi cùng loại A1: SLM bị giao thêm việc viết văn xuôi.
**Thay đổi:**
- Final chỉ gồm các trường có cấu trúc:
  - `analysis`: giữ lại để model suy luận; không render, không chấm M4;
  - các trường quyết định hiện có của v4;
  - `findings[]` gồm `{statement, refs[≥1 handle]}`, `statement` ngắn và chỉ dành cho khẳng định *có mặt*;
  - `absence_claims[]` như ở v4.1.
- Bỏ toàn bộ free-text narrative trong final.
- Verifier: `statement` có dạng absence thì reject. Dùng lại repair 1 lần (kể cả ở FORCED_FINAL).
- **Trusted renderer**: tạo báo cáo tiếng Việt theo template.
  - `statement` của model được trích nguyên văn và ghi rõ là do model viết.
  - Mỗi `absence_claim` render thành "Không thấy X trong phạm vi Qk (…, đã đọc hết)".
  - Phần "Phạm vi đã xem / chưa xem" render tất định từ ledger.
  - Renderer KHÔNG tạo, KHÔNG sửa claim (CLAUDE.md §3).
- v4.0 và v4.1 giữ nguyên. Arm `V4_2` thay cho `V4_1` trong đợt eval.
**M4:** chấm trên phần do model viết và được render (`statement` cùng các dòng absence). Ghi trong PROTOCOL rằng định dạng khác 07B, nên so sánh với 07B có giới hạn.

## 2c. Rev 3 (Owner duyệt "C rồi B, time-box", 2026-11-28): final hai bước, contract `investigation-v4.3`
**Bằng chứng:**
- v4.2 (eval): M1b render còn 5/8 và 4/8, do model bỏ trống findings (A5).
- 07C-R (replay offline v4.0 + lọc phủ định): M1b 7/8, nhưng chỉ 85% run còn câu có mặt. Câu trả lời đúng ở các case RA/NOT_STATIC bị xóa.

**Thiết kế:** mỗi lần gọi model chỉ một ràng buộc.
- **F1, phát hiện có mặt.** Đầu vào: câu hỏi và các entry đã truy xuất (trusted, từ ledger và query). Model trả `analysis` cùng `findings[{statement, refs≥1}]`, có thể rỗng. P1 vẫn loại statement phủ định.
- **F2, trả lời.** Đầu vào: câu hỏi, coverage ledger và findings của F1 (chỉ đọc). Model trả:
  - `analysis`;
  - các trường quyết định v4;
  - `absence_claims[]` (scope Qk, như v4.1);
  - `unresolved[{topic, reason}]`, với `reason` là enum `NOT_STATIC_DETERMINABLE | NOT_COVERED | INSUFFICIENT_EVIDENCE`. Dùng enum để câu giới hạn trung thực không bị lọc nhầm.
- Mỗi bước được repair 1 lần. Renderer tất định render từ F1 và F2, không tạo hay sửa claim. v4.0–v4.2 giữ nguyên. Arm `V4_3`.

**Eval:** V4_3 × 2 seed trên cohort v2, kind `DEV_DIAGNOSTIC_CONSUMED_COHORT`. Tiêu chí, phải đạt ở cả hai seed:
- M1b render ≥ 6/8;
- ≥ 90% run có câu trả lời render (≥ 1 finding, hoặc ≥ 1 absence_claim accepted, hoặc ≥ 1 unresolved);
- M10 ≥ 19/20;
- median latency ≤ 1.5 lần V4.

M4 render thỏa do cấu trúc; M4_raw là diagnostic.

**Time-box:** sau đợt eval này ĐÓNG TASK 07, dù kết quả ra sao. Kết quả ghi vào A4/A5.

## 3. Đánh giá (tối giản để tiết kiệm thời gian)
- **Loại:** DEV_DIAGNOSTIC trên cohort v2 của 07B (đã dùng, ghi rõ là cohort đã tiêu thụ). Chưa phải confirmatory.
- **Arm:** chỉ chạy V4.1 × 2 seed (42, 7), tổng 40 run, ước khoảng 16 phút máy. Baseline là trace frozen của V4 và BASE trong 07B, đã kiểm cùng Ollama 0.40.16 và cùng digest. Không chạy lại 07B.
- **Metric:** dùng lại `metrics.py` (bump version nếu có thay đổi).
  - Chính: M4-UNSCOPED rate.
  - Giữ nguyên: M1b, M8, M10, latency.
  - Mới: absence_claims bị reject / chấp nhận.
- **Tiêu chí, phải đạt ở cả hai seed:**
  - M4-UNSCOPED V4.1 ≤ 0.20 (mức BASE cộng nhiễu);
  - M1b ≥ 6/8;
  - M10 ≥ 19/20;
  - median latency của V4.1 không vượt 1.5 lần V4.
- **Bảng quyết định:**
  - Đạt cả bốn tiêu chí → v4.1 thành nhánh chính của Agent; 07D chạy confirmatory trên một cohort mới nhỏ.
  - M4 giảm nhưng M1b giảm → xem lại prompt hoặc độ dài summary.
  - M4 không giảm → ghi vào CHALLENGES_ARCHITECTURE (A4), cân nhắc bỏ hẳn khẳng định vắng mặt khỏi contract.

## 4. Quy trình và thời gian
| Bước | Việc | Ai |
|---|---|---|
| S1 | Ledger, contract v4.1, verifier, coverage summary, test | dev |
| S2 | DEV smoke 2 case, sửa lỗi core | dev |
| S3 | Freeze protocol, review **1 vòng**, chỉ chặn High/Critical | review |
| S4 | Owner chạy `run_s8`-style 40 run | Owner |
| S5 | Metric, REPORT, cập nhật 2 file CHALLENGES, commit local | dev |
| S6 | Review kết quả (1 vòng) | review |

Commit local `[TASK 07C] …`, KHÔNG push. Push chỉ thực hiện khi xong toàn bộ TASK 07 và có Owner xác nhận.
