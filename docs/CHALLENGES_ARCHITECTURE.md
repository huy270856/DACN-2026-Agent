# Khó khăn kiến trúc lớn — DACN-2026-Agent

Chỉ ghi khó khăn **lớn** buộc phải đổi thiết kế, contract, luồng hoặc phân vai. Không ghi bug nhỏ, lỗi cú pháp hay nit review.
Mỗi mục: Task · Vấn đề · Bằng chứng · Quyết định/hướng xử lý · Trạng thái (OPEN / RESOLVED / PARTIAL).

---

## A1. SLM 4B ôm quá nhiều vai trò
- **Task:** 05C → 07B
- **Vấn đề:** Qwen3.5:4B vừa phải lập kế hoạch, chọn tool, phân trang import, tự kiểm nhãn detector và viết báo cáo trong một funnel cố định. Kết quả là model hoạt động kém: 05C bắt được 0/50 lỗi detector, và bảng điểm của chính model cho thấy năng lực planning thấp (DeepPlanning 17.6).
- **Bằng chứng:** `research/agent_architecture_review/REPORT.md`, `evaluation/task07a/REPORT.md`.
- **Quyết định:** chuyển các phần tất định sang trusted Python, gồm coverage, recommendation qua D2 mapping và ordinal resolve. Model chỉ còn ba việc: phân tích, chọn query, viết câu trả lời (contract `investigation-v4.0`).
- **Trạng thái:** PARTIAL. Ở 07B, M1b tăng từ 0/8 lên 7/8.

## A2. Contract xác minh nhãn gây tự chứng thực
- **Task:** 06A → 07A
- **Vấn đề:** để kết luận CONSISTENT, model bắt buộc phải trích một ID hỗ trợ, trong khi prediction của detector lại nằm trong danh sách có thể trích. Model vì thế bị đẩy về cấu trúc tự chứng thực (M5 khoảng 85–100%).
- **Quyết định:** chuyển sang contract hướng vào câu trả lời; đặt `detector_context` ở dạng không thể trích. Policy v4.0 hoãn sang 07C.
- **Trạng thái:** PARTIAL.

## A3. Phân trang offset mù, không có tín hiệu dẫn đường
- **Task:** 06B-J → 07B
- **Vấn đề:** model đọc import tuần tự theo offset 16/32, không biết entry liên quan nằm ở đâu, nên không với tới entry từ vị trí 48 trở đi.
- **Quyết định:** thêm tool `static.pe_imports_table` có chỉ mục DLL và `QUERY_IMPORTS`.
- **Trạng thái:** RESOLVED cho lát cắt 1. V4 7/8 so với V4_NOQ 3/8.

## A4. Khẳng định vắng mặt bị khái quát quá phạm vi đã xem
- **Task:** 07B
- **Vấn đề:** model chỉ hỏi query hẹp rồi kết luận "không có cả họ API", ví dụ nói không có process opening trong khi có `OpenProcess`. M4-UNSCOPED tăng lên 0.55–0.60.
- **Hướng xử lý:** sang 07C, bắt claim vắng mặt phải trích query/DLL đã phủ, hoặc trả coverage tất định ở lượt final.
- **Trạng thái:** OPEN.
