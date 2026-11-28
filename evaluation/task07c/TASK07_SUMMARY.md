# TASK 07 — Tổng kết (07A, 07B, 07C)

Mọi kết quả là `DEV_DIAGNOSTIC` trên PE benign, chạy Qwen thật cục bộ (`qwen3.5:4b`). Không có confirmatory, không
có semantic grading hay human grading (NOT_RUN / PENDING). Chưa push.

## 1. Đi qua từng bước

| Bước | Thay đổi | Kết quả chính | Trạng thái |
|---|---|---|---|
| 07A | Ablation prompt: analysis-first, thinking | Analysis-first giúp model đọc thêm import; V3 cites 7/8 | DONE |
| 07B | `investigation-v4.0`: handle E#/I#, tool `static.pe_imports_table`, `QUERY_IMPORTS` | M1b 7/8 (V4) so với 0/8 (BASE); nhưng M4 unscoped 0.55–0.60 (A4) | DONE, row 1 không đạt |
| 07C v4.1 | Coverage ledger + `absence_claims` | Model vẫn viết absence bằng free text (smoke) | bỏ |
| 07C v4.2 | Final có cấu trúc + filter P1 | M4 raw 0.05/0.10, nhưng M1b 5/8, 4/8 (findings rỗng, A5) | không đạt |
| 07C-R | Lọc phủ định offline trên trace v4.0 | M1b 7/8, nhưng 85% run có câu trả lời; báo cáo RA rỗng | không đạt |
| 07C v4.3 | Final hai bước F1/F2 + `unresolved` enum | M1b 7/8, 6/8; câu trả lời 20/20; latency 1.65×/1.42× | không đạt (latency s42) |

## 2. Kiến trúc cuối được chọn

- **Truy xuất:** giữ `investigation-v4.0`, gồm tool `static.pe_imports_table` và `QUERY_IMPORTS` có chỉ mục DLL.
  Đây là cải tiến rõ ràng nhất của TASK 07: 0/8 → 7/8. Vai trò D1–D9, D4 default-deny và D9 commit không đổi.
- **Grounding cho absence:** coverage ledger tất định, `absence_claims` bám scope Qk và trusted renderer là
  những thành phần đã có, có test và cài theo opt-in (`contract_version`).
  - Chưa có contract final nào đạt đủ tiêu chí đăng ký trước.
  - **v4.3 là ứng viên tốt nhất về chất lượng**. Khi dùng nó phải chấp nhận latency khoảng 1.4–1.65× hoặc tối ưu
    sau.
  - Việc chọn contract mặc định cho CLI `python -m dacn` để Owner quyết; TASK 07 không thay đổi mặc định.
- **Nguyên tắc rút ra:** chuyển phần tất định (coverage, scope, render, loại câu phủ định) sang trusted code;
  mỗi lần gọi model chỉ giao **một** ràng buộc.

## 3. Negative result (ghi rõ)

- Model 4B không ngừng viết câu phủ định hoặc absence trong free text, kể cả khi prompt cấm và đã repair. Trusted
  filter che được ở báo cáo, nhưng **đạt nhờ filter ≠ model đã học được**.
- Gộp hai ràng buộc vào một lần gọi làm model đánh đổi: hoặc bỏ trống findings, hoặc nhét câu phủ định vào ô bắt
  buộc (A5).
- Lọc phủ định sau sự kiện, không có contract, xóa đúng phần câu trả lời ở các câu hỏi mà đáp án là vắng mặt
  (07C-R).
- Tách hai bước sửa được chất lượng nhưng tăng latency vượt ngân sách.
- 07B ghi nhận agent 4B bắt được 0/50 lỗi của detector (05C). TASK 07 không thay đổi kết luận này.

## 4. Giới hạn

- Một cohort (`cases_v2`) dùng lặp lại qua các vòng, nên các vòng sau đều là CONSUMED.
- n = 8 câu RP mỗi seed; 2 seed; chỉ PE benign.
- Track `FEATURE_RECORD_REPLAY` và raw malicious nằm ngoài phạm vi; raw malicious vẫn BLOCKED theo CLAUDE.md.
- Metric là rule screen tất định (M4 là `RULE_SCREEN_CANDIDATE`), không phải semantic judge.
- Muốn khái quát hóa cần holdout mới chưa dùng, cùng semantic grading hoặc human grading.

## 5. Đề xuất (chưa làm, để Owner quyết)

- Nếu chọn v4.3: tối ưu latency, ví dụ giới hạn `num_predict` của F2, bỏ repair F2 khi chỉ có claim nhỏ bị
  reject; rồi đo trên holdout mới.
- Thêm filter cho `unresolved.topic` hoặc buộc topic theo template.
- Chạy semantic grading hoặc human grading cho mẫu báo cáo render.

## 6. Completion của TASK 07

- **Engineering: PASS.** Mọi bước có code, test, freeze, review và artifact write-once.
- **Research: PARTIAL.**
  - Cải tiến truy xuất (07B) đứng vững trên DEV.
  - Grounding cho absence mới đạt ở mức sản phẩm nhờ trusted code; chưa có contract nào đạt đủ tiêu chí.
