# TASK 06A — Evidence-Driven Agent Investigation v2 — BÁO CÁO

> Trạng thái: **ENGINEERING PASS (một phần) / RESEARCH PARTIAL**. Lõi deterministic v2
> (schema + grounding + consistency + assessor) đã hoàn thành, có test (23/23 PASS) và đã
> được **xác minh LIVE** với Qwen thật. Phần ablation DEV đầy đủ (v1 vs v2 trên tập DEV) **CHƯA
> chạy xong** trong lượt này (hết hạn mức usage) — xem mục 8 "Việc còn lại".

## 1. Branch / commit / repo
- Branch mới: `feat/task06a-evidence-driven-agent-v2`, tạo từ `origin/main = edd0a25`.
- `origin/main (edd0a25)` và HEAD 05D cũ `ba22e78` có **tree giống hệt** (edd0a25 là squash-merge PR #12); working tree sạch.
- Không reset/clean/force-push; không merge main; không sửa README top-level.
- Model 05A (`model_lightgbm.txt`), Ollama `qwen3.5:4b`, và EMBER2018 v2 (`D:\datasets\...`) đều **có thật** và khả dụng.

## 2. Files đã đọc (audit source thật)
- Agent v1: `agent/{schema,context,planner,controller,loop,report,config}.py`.
- Ứng dụng: `dacn/investigation.py`, đường chạy agent trong `dacn/application.py`.
- Orchestrator: `orchestrator/workflow.py` (D1 routing), `orchestrator/registry.py` (register/list tools).
- 05C: `agent_replay.py`, `evidence_projection.py`, `metrics.py`, `examples.py`, `repair/agreement_bias.py` + `results/agreement_bias.json`, 1 sample thật.
- 05D: `claude_judge.py`, `results/GRADING_METHOD_AUDIT.md`.

## 3. Trả lời 8 câu hỏi audit (có dẫn chứng)

1. **Agent coi static prediction là nhãn bắt buộc đồng thuận hay chỉ là observation?**
   → Bắt buộc. `agent/context.py:97-108`: prompt nói *"That label is AUTHORITATIVE and you must NOT
   override it"* và liệt kê **CONSISTENT trước** với gán nghĩa khẳng định ("the observable PE evidence
   agrees with the static label"). Đây là anchoring có cấu trúc.
2. **Có được trả CONFLICT khi có mâu thuẫn cụ thể không?** → Schema *cho phép* (`schema.py:48-49`),
   nhưng prompt không yêu cầu liệt kê bằng chứng phản chứng nên thực tế không bao giờ chọn:
   **120/120 CONSISTENT** (`agreement_bias.json`).
3. **Schema có phân biệt evidence_supporting / contradicting / unknown không?** → **KHÔNG**. v1 chỉ có
   `alignment` (1 enum) + `explanation` tự do. Không có trường ràng buộc bằng chứng hai chiều.
4. **CONSISTENT có bị dùng sai (chỉ là thiếu phản chứng)?** → Có. Ví dụ FN thật
   (`samples/01358…json`): model dự đoán *benign* (ca này thực tế malicious bị bỏ sót), agent vẫn ghi
   CONSISTENT "evidence consistent with the benign prediction" ⇒ anchor vào nhãn, **không bắt lỗi detector**.
5. **Vì sao `review_required` và `recommendation` có thể trái nhau?** → Hai trường tự do do LLM điền,
   **không có cross-check**. `investigation.py:218` tin thẳng `review_required` của model; `agent_suggested_recommendation`
   (05D) có ca **MONITOR trên mẫu malicious-predicted** — không trường nào kiểm nhất quán.
6. **LLM có thấy evidence bị cắt?** → Có. `context.py:36-39` cắt mỗi value còn `max_value_chars=800`;
   `context.py:86-96` **drop cả observation** khi vượt `max_context_chars=12000`, chỉ gắn cờ `context_truncated`.
   Nhưng `evidence_refs` được validate so với state (controller), **không** so với phần model thực sự nhìn thấy.
7. **Tool loop production khác one-shot replay thế nào?** → 05C (`agent_replay.run_agent_once`) là **one-shot**
   với `available_tools=[]`. Production (`application.py:344-362`) chỉ đăng ký **1 tool** `static.pe_malware_predict`,
   và nó đã được workflow chạy *trước* khi agent chạy ⇒ agent **không có tool mới** để gọi.
8. **Có bằng chứng agent tự chọn tool điều tra bổ sung trên real PE không?** → **KHÔNG**. Không có analyzer
   tĩnh bổ sung nào được đăng ký ngoài 1 detector đã chạy sẵn. "Loop" production thực chất = đọc prediction → FINISH.
   ⇒ Multi-step autonomous investigation **chưa chứng minh được** (blocker, xem mục 9 → 06B).

## 4. Lỗi thật của Agent v1 (root cause)
- **RC-1 Agreement bias do prompt**: prompt mồi CONSISTENT + tuyên bố nhãn "authoritative" ⇒ 120/120 CONSISTENT;
  probe disconfirmation-first lại lật 16/16 CONFLICT ⇒ **output bị prompt chi phối**, không phải lập luận vững.
- **RC-2 Thiếu cấu trúc bằng chứng**: không tách supporting/contradicting/unknown ⇒ "thiếu phản chứng" bị
  coi là "đồng thuận".
- **RC-3 Không có guardrail nhất quán quyết định**: MONITOR trên malicious, review/recommendation trái nhau,
  near-threshold thả trôi — không lớp nào chặn.
- **RC-4 Grounding yếu**: bịa import (MFC/CRM/ExitProcess/MoveFileA), "high entropy" khi 0 section entropy≥7
  (xác nhận trong `GRADING_METHOD_AUDIT.md`).

## 5. Thay đổi đã triển khai (additive, versioned — KHÔNG đụng `agent/*` production)
Tất cả nằm trong `evaluation/task06a/` (v1 production **đóng băng nguyên trạng**):
- `schema_v2.py` — schema v2 có cấu trúc: `supporting_evidence_ids` / `contradicting_evidence_ids` /
  `uncertainty_notes` + `confidence_in_assessment` (định tính, **không** phải raw score). Alignment phải được
  "earn" bằng citation hai chiều.
- `assessor_v2.py` — **giao thức đánh giá trung lập**: prompt đối xứng (không mồi CONSISTENT, cũng không ép
  CONFLICT); "thiếu phản chứng ⇒ INSUFFICIENT_EVIDENCE, KHÔNG phải CONSISTENT"; cấm nêu import/entropy/hành vi
  không có trong evidence. Tái dùng `OllamaPlanner`, **cùng evidence projection** như v1 (so sánh công bằng).
  Có guard chống rò ground truth + fence untrusted content.
- `grounding.py` — verifier **deterministic**: bắt evidence_id bịa, API/thư viện bịa (lexicon + MFC/CRM…),
  "high-entropy/packed" khi 0 section entropy≥7 (có xử lý phủ định), và claim **hành vi runtime** (bất khả thi
  với static). Áp dụng **cho cả v1 và v2** ⇒ cùng thước đo.
- `consistency.py` — guardrail **deterministic** + **fail-safe recommendation**: bắt `under_cautious_monitor_on_malicious`,
  `conflict_without_review`, `monitor_on_near_threshold`, `alignment_consistent_not_justified_by_structure`,
  recommendation thiếu/không hợp lệ… và **không bao giờ âm thầm về MONITOR** (malicious→CONSIDER_QUARANTINE,
  CONFLICT/near-threshold→MANUAL_REVIEW). Score được xử lý ở **không gian raw**, ghi rõ chưa calibrate.
- `tests/test_task06a.py` — 23 test, **23/23 PASS**.

## 6. v2 khác v1 ở hành vi điều tra
- Agent phải **trích dẫn bằng chứng cho phía mình chọn** (supporting/contradicting) thay vì phát CONSISTENT mặc định.
- "Không đủ dữ liệu" có đường ra tường minh (INSUFFICIENT_EVIDENCE) thay vì bị gộp thành CONSISTENT.
- Quyết định xử lý cuối **do lớp deterministic chốt** (fail-safe), phần *lập luận bằng chứng* vẫn là chức năng của Agent.

## 7. Bằng chứng LIVE (1 record EMBER, Qwen thật)
Chạy `assess_once_v2` với `OllamaPlanner` trên 1 train record (true_label chỉ cho evaluator):
- `run_status=OK`, latency **6.99s**; predicted **malicious** (score 0.9993).
- v2 model vẫn mắc lỗi: `alignment=CONSISTENT, review_required=False, recommendation=MONITOR`, và **bịa 1 evidence_id**.
- **Lớp verifier bắt được ngay**: `grounding.grounded=False` (invalid_evidence_ids=[`EV-ad85…`]);
  `consistency.consistent=False` (flags: `under_cautious_monitor_on_malicious`, `malicious_without_review`);
  **fail-safe ghi đè** `safe_recommendation=CONSIDER_QUARANTINE`.

**Nhận định quan trọng (trung thực):** prompt v2 *một mình* **chưa** đủ sửa agreement bias/MONITOR-on-malicious —
giá trị thực tế nằm ở **lớp verification deterministic** chặn/sửa lỗi của LLM. Đây là bằng chứng ủng hộ
"deterministic guardrails + agent reasoning" hơn là "prompt tốt hơn". (Một điểm quan sát, **chưa** phải kết luận
thống kê — cần ablation đầy đủ ở mục 8.)

## 8. Việc còn lại (chưa làm xong trong lượt này — hết hạn mức usage)
- **DEV set** từ TRAIN split (disjoint SHA với 120 audit + test + 05D pilot; provenance + overlap check) — *chưa dựng*.
- **Ablation đầy đủ v1 (frozen) vs v2** trên DEV: schema-valid, citation coverage, **grounding errors**,
  unsupported specifics, alignment distribution, **recommendation consistency**, review load, invalid-action,
  latency, tokens — *chưa chạy*.
- **Confirmatory error-probe** (v2 trên slice test FP/FN ngoài 120+16, metric pre-registered) — *chưa chạy*.
- Lưu ý dữ liệu: model 05A **memorize TRAIN** ⇒ FP/FN trên DEV-train rất thưa; câu hỏi "bắt lỗi detector" cần
  slice **held-out** (để 06B), không tune trên locked 120.

## 9. Giới hạn còn lại & 10. Kết luận
- **An toàn/trust boundary**: giữ nguyên read-only static-first; không đụng D4/D8, không execute PE,
  không auto-quarantine; v2 chỉ *đề xuất*, `execution_status=NOT_EXECUTED`.
- **Multi-step (mục E)**: **BLOCKER** — production chỉ có 1 tool detector chạy sẵn, không analyzer bổ sung ⇒
  không thể chứng minh multi-step thật ở 06A. Đề xuất **06B**: đăng ký ≥1 analyzer **tĩnh read-only** bổ sung
  (ví dụ: trích import/section/strings sâu hơn qua D1–D9) để agent có tool thật để chọn, rồi đo
  CaseState cập nhật giữa các vòng + FINISH/REQUEST_MORE_EVIDENCE hợp lý.
- **Không** đổi/làm đẹp benchmark cũ; **không** sửa output Qwen/baseline; model & threshold không đổi.
- **TASK 06A: ENGINEERING PASS (lõi v2 + verifier + tests + live-verified) / RESEARCH PARTIAL** (ablation đầy đủ chưa chạy).
- Sẵn sàng mở **06B** sau khi hoàn tất ablation DEV + confirmatory của 06A.
