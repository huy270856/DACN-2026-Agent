# TASK 07C rev 3 — PROTOCOL cho V4_3 (`investigation-v4.3`, final hai bước)

Bổ sung cho `PROTOCOL.md`: giữ nguyên mọi điều khoản, chỉ khác các mục dưới đây. Spec ở `PLAN_TASK07C.md` §2c.

- **Loại:** `DEV_DIAGNOSTIC_CONSUMED_COHORT`. Track `RAW_PE_E2E`, `LOCAL_QWEN` (`qwen3.5:4b`, digest `d8b0f5e9…`,
  Ollama 0.40.16 headless). Không phải confirmatory.
- **Arm:** `V4_3` × seed 42 và 7, trên cohort `cases_v2` (20 case: 8 RP, 12 lớp khác). Output ghi vào
  `results/frozen_v43/` (write-once). Script `run_s4_v43.ps1`, có guard HEAD = freeze, tree sạch, version
  Ollama và digest.
- **Metric:** `task07b-metrics-v4`, chỉ thêm `rendered_answer` / `rendered_answer_rate`. Các metric v3 giữ
  nguyên định nghĩa.
- **Baseline:** trace frozen V4/BASE của 07B (không chạy lại); V4_2 của 07C chỉ để tham khảo.
- **Tiêu chí, phải đạt ở cả hai seed:**
  - M1b render ≥ 6/8.
  - `rendered_answer_rate` ≥ 18/20 (≥ 90%). Một run có câu trả lời khi còn ≥ 1 finding giữ lại, hoặc ≥ 1
    absence_claim accepted, hoặc ≥ 1 unresolved.
  - M10 ≥ 19/20.
  - Median latency V4_3 / V4 (07B) ≤ 1.5.
- **Diagnostic, không ngưỡng:** M4 render (thỏa do cấu trúc), M4_raw, số statement F1 bị loại, số lần repair
  F1/F2, absence accepted/rejected, phân bố reason của unresolved.
- **Quyết định:** đạt cả bốn tiêu chí → ghi v4.3 là ứng viên cho bước sau. Không đạt → ghi negative result vào
  A4/A5. Dù kết quả nào thì cũng **ĐÓNG TASK 07** (time-box), không tối ưu thêm.
- **Dừng:** giống `PROTOCOL.md` §6. Không chạy lại riêng các run lỗi.

**Ghi chú phạm vi (review v4.3):**
- M4 render chỉ phủ findings và absence_claims. `unresolved.topic` được render nguyên văn và không qua
  `statement_absence`.
- Số repair theo từng bước nằm trong `step_repairs`, không cộng vào `repair_attempts`.

**Sửa trước freeze (Planner, Medium):** đè lên ghi chú phạm vi ở trên.
- M4 render phủ findings + unresolved.topic. Phần findings thỏa do cấu trúc; phần topic thì không. M4_raw cũng tính
  cả topic (metrics v4).
- Số repair báo theo `step_repairs`.
