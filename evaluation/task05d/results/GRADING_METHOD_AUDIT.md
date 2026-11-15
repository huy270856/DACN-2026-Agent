# TASK 05D-J — Audit tính trung thực của phương pháp chấm

Trả lời trực tiếp 4 câu hỏi của chủ dự án, nêu lỗi đã sửa và kết quả lượt LLM thật.

## Phát hiện (trung thực)

1. **40 phiếu được tính bằng QUY TẮC Python (keyword/regex), KHÔNG phải LLM suy luận
   từng phiếu.** Hàm `judge_form()` chấm bằng khớp chuỗi (vd B1: có "uncalibrated"/
   "không phải xác suất" ⇒ 2).
2. **`judge_model=claude-opus-4-8` (bản cũ) là metadata GÂY HIỂU NHẦM.** Không có
   inference nào của Claude sinh ra các điểm đó — tôi chỉ *viết luật*. Đã sửa.
3. **Reasoning cũ là chuỗi template theo luật đã khớp**, không phải lập luận ngữ nghĩa
   riêng từng phiếu.
4. **Static-only = 2.0 tuyệt đối là do checker THIÊN VỊ template cố định:** báo cáo
   static-only là template viết sẵn chứa đúng các cụm từ mà luật thưởng điểm; checker đo
   **bề mặt câu chữ**, không đo chất lượng ngữ nghĩa.

## Đã sửa

- Đổi tên `ai_judge.py` → **`rule_checker.py`**; metadata: `judge_model="none
  (deterministic rule-based checker; NO LLM inference)"`, `is_llm_as_judge=false`,
  `evaluation_type=RULE_BASED_HEURISTIC_PROVISIONAL`. **Giữ nguyên số cũ** làm baseline
  rule-based (`results/rule_based_checker/`): Static-only **2.0** vs Static+Agent **1.58**.
- **KHÔNG** bịa một lượt gọi Claude; chỉ nêu rõ bản cũ là rule-based.

## Lượt LLM thật (Claude) — `claude_judge.py` → `results/claude_llm_judge/`

Claude (claude-opus-4-8) **đọc trực tiếp từng phiếu trong 40** và chấm 0/1/2 kèm lý do,
**blind** với branch mapping/ground truth. `evaluation_type=AI_LLM_JUDGE_PROVISIONAL`,
`is_llm_as_judge=true`, `reproducible=false`, `human_verified=false`.

| Tiêu chí | Rule-based (cũ) SO / SA | **LLM Claude** SO / SA |
|---|--:|--:|
| A2 claims supported | 2.0 / 1.0 | 2.0 / **1.8** |
| B1 score vs truth | 2.0 / 1.15 | 2.0 / **2.0** |
| B2 no feature-importance | 2.0 / 2.0 | 2.0 / 2.0 |
| C1 uncertainty | 2.0 / 2.0 | 2.0 / 2.0 |
| D1 recommendation | 2.0 / 1.75 | 2.0 / **1.65** |
| **overall** | **2.0 / 1.58** | **2.0 / 1.89** |

(SO=Static-only, SA=Static+Agent)

**Vì sao LLM công bằng hơn với Agent:** rule-checker chỉ soi câu chữ trong *explanation*
nên chấm thấp oan Agent ở B1 (bỏ qua việc Agent nêu "uncalibrated" trong *limitations*) và
A2 (phạt nặng việc trích dẫn evidence prediction mà annotation sheet bỏ sót). LLM đọc hiểu
nên trả lại điểm xứng đáng ở B1/C1, đồng thời **vẫn trừ điểm thật**:
- **A2=1** ở các phiếu Agent bịa chi tiết không có trong evidence: "CRM imports", "MFC
  imports", "ExitProcess/MoveFileA", hoặc nói "high entropy" khi mẫu có 0 section entropy≥7.
- **D1=1** ở các phiếu Agent khuyến nghị **MONITOR cho ca dự đoán malicious** (0.95–0.9997)
  hoặc ca **near-threshold** — under-cautious.

**Meta-caveat:** 5 tiêu chí rubric có thể thỏa bằng boilerplate ⇒ template đạt trần điểm
không phải vì sâu sắc. Một tiêu chí "độ cụ thể/insight" (không có trong rubric hiện tại) có
thể đảo lợi thế về phía Agent tự do.

## Kết luận

- Cả hai lượt (**rule-based** và **LLM Claude**) đều **PROVISIONAL**, **không** phải human
  grading — human grading TASK 05D vẫn **PENDING**.
- Cả hai đồng hướng: Static-only (template) ≥ Static+Agent trên rubric này; **không** tuyên
  bố nhánh nào thắng.
- **Không** sửa outputs Qwen hay baseline để nâng điểm; model LightGBM/threshold không đổi.
- Audit trail: `results/rule_based_checker/` và `results/claude_llm_judge/`
  (scores + reasoning + summary + provenance). Người chấm có thể dùng `ui/grading.html` +
  `grading_import.py` để chấm độc lập và so với cả hai bản provisional.
