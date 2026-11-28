# Khó khăn kỹ thuật lớn — DACN-2026-Agent

Chỉ ghi khó khăn kỹ thuật **lớn**: làm hỏng run, mất dữ liệu, chặn tiến độ hoặc tốn nhiều giờ. Không ghi bug nhỏ hay nit.
Mỗi mục: Task · Vấn đề · Nguyên nhân · Cách xử lý · Bài học.

---

## T1. Ollama desktop tự cập nhật làm sập run và gây drift version
- **Task:** 07A, 07B
- **Vấn đề:** app desktop có bản cập nhật 0.40.18 đang chờ, đã làm crash run live hai lần, có nguy cơ QWEN_DRIFT.
- **Cách xử lý:** chạy `ollama serve` headless trong cửa sổ PowerShell riêng của Owner; run live không chạy dưới dạng process con của session Claude. Script run kiểm version 0.40.16 và digest model trước khi chạy.
- **Bài học:** không mở app Ollama desktop trong lúc đang có đợt eval.

## T2. Native thinking của Qwen bị runaway
- **Task:** 07A (V1)
- **Vấn đề:** 3/7 run bị cắt ở `num_predict` 12288, latency tăng khoảng 10 lần.
- **Cách xử lý:** giữ `think=False`. Thay vào đó, đặt trường `analysis` lên trước action trong JSON.
- **Bài học:** model 4B không tự kiểm soát được độ dài suy nghĩ.

## T3. Vòng eval quá dài
- **Task:** 07A, 07B
- **Vấn đề:** thời gian máy chạy S8 chỉ khoảng 48 phút, nhưng cả chuỗi freeze → review (3 vòng) → run → báo cáo kéo dài nhiều giờ.
- **Cách xử lý:** từ 07C, review chỉ chặn ở lỗi core (High/Critical); lỗi nhỏ ghi lại, không chặn.
