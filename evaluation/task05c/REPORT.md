# TASK 05C — Báo cáo: Đánh giá có kiểm soát Static-only vs Static + Qwen Agent

**Kết luận: PARTIAL.** Toàn bộ pipeline tự động đã hoàn thành và chạy Qwen thật trên
120 mẫu có nhãn; nhưng các tiêu chí **semantic** của rubric (A2/B1/B2/C1/D1) cần
**người chấm độc lập** (không dùng LLM, không tự chấm) — đã xuất gói chấm blind và để
`CHƯA CHẤM`. Đây đúng theo mục 12 đề bài (automated xong, chưa có human annotation → PARTIAL).

Mọi số liệu sinh từ chính lượt chạy (Windows 11, Python 3.12.10, Ollama qwen3.5:4b),
2026-11-14, track **FEATURE_RECORD_REPLAY**.

---

## 0. Trạng thái & bảo toàn

- Branch khi bắt đầu: `feat/task05b-agent-integration`, HEAD `8a712a2`, worktree sạch.
- Đã đọc `research/independent_static_ml/REPORT.md`, `docs/task05b/REPORT.md`, agent
  schema/context/report, CLI. Model manifest verify: SHA-256 `5db192ec…c509609`, 2381 features.
- TASK 05C làm trên branch riêng `feat/task05c-evaluation`. **Không** retrain, **không**
  đổi model/threshold, **không** sửa D4/D8, **không** thêm node, **không** thực thi malware,
  **không** push/merge. Chỉ thêm package `evaluation/task05c/` (additive).

## 1. Thiết kế hai nhánh / hai track

- **Nhánh A — Static-only**: cùng model LightGBM 05A. Giải thích theo **template cố định**
  + khuyến nghị theo **quy tắc cố định** (đóng băng, versioned bằng hash), chỉ dùng evidence
  có thật. Không LLM, không ground truth.
- **Nhánh B — Static + Agent**: **cùng** score/threshold/static label + **cùng** evidence
  projection. Qwen3.5-4B (tái dùng `agent.context/planner/schema` thật) tạo evidence
  alignment + review + explanation + recommendation. **Không** sửa static label.
- **Track**: `FEATURE_RECORD_REPLAY` (chạy model trên feature records, KHÔNG phải raw-PE E2E).
  `RAW_PE_E2E` malicious = **BLOCKED** (không tải/chạy malware); benign raw-PE đã chứng minh ở 05B.
- **Chống leakage**: ground truth chỉ ở manifest (evaluator-only); có guard `_assert_no_ground_truth`
  kiểm context render không chứa `true_label/ground_truth`; projection không có nhãn; không đưa
  tên file/đường dẫn lộ nhãn; không đưa 2381 floats cho Qwen.

## 2. Tập đánh giá (manifest khóa, tái lập)

- Nguồn: official EMBER2018 v2 **test** (200.000 mẫu) đã audit ở 05A; không tuning theo test.
- Chấm toàn bộ bằng model đóng băng → phân tầng theo (nhãn, dự đoán) tại threshold 0.8322.
- Lấy mẫu có **seed=20261114**, phân tầng: **TP 25 · TN 25 · FP 25 · FN 25 · NEAR 20 = 120 mẫu**
  (NEAR = |score−threshold|<0.10). Dedup SHA-256 = 0.
- Pool thực tế: TP 91.710 · TN 99.002 · FP 998 · FN 8.290 · NEAR 11.268.
- `audit_manifest.json` có `manifest_sha256 = 2732a044…686a`. Tập audit cân đối theo strata
  (để soi ca khó) nên **KHÔNG** đại diện tỷ lệ lỗi tự nhiên — đã ghi rõ, không dùng để suy FP/FN rate thực.

## 3. Cấu hình Qwen (đóng băng)

`model=qwen3.5:4b`, digest `d8b0f5e9760c…e38c04`, `temperature=0.1`, `num_predict=1536`,
`think=OFF`, `inference_timeout_s=180`. prompt_id `agent-context-v1` (hash trong results),
baseline + rubric versioned bằng hash. Resume/idempotency: mỗi mẫu lưu riêng, chạy lại bỏ qua
mẫu đã OK. FAIL/TIMEOUT được ghi; incomplete **không** coi là PASS.

## 4. Detection metrics (GIỐNG NHAU hai nhánh)

Vì cả hai nhánh dùng chung model/score/threshold, detection trên full test là **đồng nhất**:

| Metric | Giá trị (cả A và B) |
|--------|------|
| ROC AUC | 0.99297 |
| Average Precision | 0.99370 |
| Precision | 0.98924 |
| Recall/TPR | 0.91710 |
| F1 | 0.95180 |
| FPR | 0.00998 |

Agent **không** thay đổi detection (không ghi đè nhãn). Mọi khác biệt nằm ở phần *điều tra*.

## 5. Investigation metrics (120 mẫu, auto-check; CI 95% Wilson)

| Chỉ số | Static-only | Static+Agent | Chênh lệch | Ý nghĩa |
|--------|------------:|-------------:|-----------:|---------|
| Citation validity (mean) | 1.00 | 1.00 | 0.00 | Agent trích dẫn evidence ID hợp lệ |
| Unsupported-claim rate | 0.0% | **0.83%** (1/120) [0.15–4.57%] | +0.83% | Agent thỉnh thoảng claim ngoài evidence |
| Safety-violation rate (auto) | 0.0% | 1.67% (2/120) [0.46–5.87%] | +1.67% | **Cả 2 là false-positive** (xem §6) |
| Review-required rate | 35.8% (43/120) | **98.3%** (118/120) | +62.5% | Agent gần như luôn đòi review (ít giá trị phân loại) |
| Schema/assessment failure | — | 0.0% | — | Agent luôn ra JSON hợp lệ |
| Run error/timeout | — | 0.0% | — | Không lỗi/timeout |
| Latency mean | — | 4.44 s/mẫu | — | Chi phí |
| Eval tokens mean | — | 376.8 /mẫu | — | Chi phí |
| Explanation semantic (A2,B1,B2,C1,D1) | CHƯA CHẤM | CHƯA CHẤM | — | Cần người chấm (gói blind kèm theo) |

## 6. PHÁT HIỆN CHÍNH (trung thực)

1. **Agent KHÔNG bắt được lỗi của detector.** Evidence alignment = **CONSISTENT cho 100%**
   mẫu ở **mọi** strata: TP 25/25, TN 25/25, **FP 25/25, FN 25/25**, NEAR 20/20. Trên 50 ca
   mà nhãn LightGBM **sai** (25 FP + 25 FN), Qwen vẫn nói “nhất quán” và hợp lý hóa nhãn tĩnh;
   **0 ca CONFLICT**. Ví dụ FP (model sai “malicious”): agent vẫn CONSISTENT và biện minh nhãn.
   ⇒ Trong cấu hình này, Agent **không** cải thiện phát hiện và **không** làm bộ lọc lỗi.
2. **Review-required gần như bão hòa** (98.3%) so với baseline 35.8%. Tỷ lệ review cao **không**
   đồng nghĩa chất lượng (đúng cảnh báo mục 8): agent đòi review gần như mọi ca → ít giá trị triage.
3. **Chi phí**: ~4.44 s và ~377 token/mẫu cho phần đóng góp chủ yếu là văn bản giải thích + cờ review.
4. **An toàn (đã rà tay)**: 2 ca bị auto-check gắn cờ safety đều là **false-positive của regex bảo thủ**
   — agent nói “monitoring/continued monitoring **rather than** quarantine” (khuyến nghị KHÔNG hành động),
   bị bắt vì chứa từ “quarantine”. Rà thủ công: **0 vi phạm an toàn thực**, 0 auto-quarantine/delete,
   0 bypass approval, execution_status luôn NOT_EXECUTED. 1 ca unsupported-claim (nhắc “dynamic
   analysis”) là borderline, để người chấm xác nhận. (Rubric giữ nguyên, **không** tinh chỉnh theo kết quả;
   phán quyết của người đè lên auto-flag — đúng quy trình.)
5. **Mặt tích cực của Agent**: citation 100% hợp lệ, 0 lỗi schema/timeout, luôn nêu limitations
   (uncalibrated score, static-only, replay), và **không bao giờ ghi đè** nhãn tĩnh.

> Diễn giải: với Qwen3.5-4B ở cấu hình này, “Static + Agent” thêm *diễn giải + cờ review + provenance*
> nhưng **không** thêm năng lực phát hiện và không sửa lỗi mô hình, kèm chi phí latency/token và một tỷ lệ
> nhỏ claim cần rà. Đây là kết quả âm tính có giá trị học thuật, không thổi phồng.

## 7. Error analysis theo TP/TN/FP/FN

- **FP (25)**: baseline khuyến nghị CONSIDER_QUARANTINE/HIGH (vì nhãn malicious); agent CONSISTENT,
  review_required, verdict riêng thường UNKNOWN/INSUFFICIENT_EVIDENCE. Agent **không** gợi ý rằng đây
  có thể là cảnh báo giả.
- **FN (25)**: nhãn benign (model bỏ sót); agent CONSISTENT + đề xuất MONITOR. Agent **không** nâng mức
  nghi ngờ dù thực tế là malware.
- **TP/TN (50)**: agent đồng thuận đúng hướng; giá trị gia tăng là giải thích.
- **NEAR (20)**: baseline tự động chuyển MANUAL_REVIEW; agent cũng CONSISTENT + review.
- Phân phối alignment theo strata nằm trong `eval_results.json` (`agent_alignment_by_stratum`).

## 8. Paired analysis & thống kê

- Paired (cùng mẫu) cho outcome nhị phân: agent tạo thêm 1 unsupported-claim và 2 safety-flag
  (đều false-positive) so với baseline; **discordant pairs quá ít (<10) → KHÔNG** tuyên bố ý nghĩa
  thống kê. Dùng Wilson CI cho proportions. Không có khác biệt detection để kiểm định (đồng nhất theo thiết kế).
- Phân biệt rõ: đây là **case-study + thống kê mô tả** trên tập phân tầng, **không** phải ước lượng tỷ lệ
  lỗi ở phân phối tự nhiên.

## 9. Negative / validation tests (mục 10 đề bài)

`python -m unittest evaluation.task05c.tests.test_05c` → **17 PASS**: ground-truth absent in agent
context; fake evidence IDs; cross-case evidence IDs; unsupported runtime/verified-signature claims;
unsafe-action + injection detection; clean static text passes; score/threshold mismatch detection;
agent timeout → error (không phải benign); mock assessment parse; classify TP/TN/FP/FN; Wilson CI; McNemar.

## 10. CHƯA CHẤM + gói chấm

`results/annotation_package/`: `annotation_forms_blind.json` (mỗi mẫu 2 phiếu X/Y **ẩn nhánh**),
`branch_mapping_EVALUATOR_ONLY.json` (mở sau khi chấm), README hướng dẫn. Các tiêu chí semantic để
`CHƯA CHẤM`, **không** điền ước lượng, **không** LLM-as-judge, **không** tự chấm.

## 11. Đối chiếu acceptance (mục 12)

| # | Tiêu chí | Trạng thái |
|---|----------|-----------|
| 1 | Tập eval có nhãn + manifest tái lập | ✅ 120 mẫu, seed, manifest_sha256 |
| 2 | Không ground-truth leakage vào Agent | ✅ guard + test |
| 3 | Static-only baseline định nghĩa rõ | ✅ frozen, versioned |
| 4 | Static+Agent chạy Qwen thật trên cùng evidence | ✅ 120/120, 0 lỗi |
| 5 | Paired comparison | ✅ bảng + McNemar |
| 6 | Rubric + chấm độc lập | ⏳ auto xong; semantic CHƯA CHẤM (gói blind) |
| 7 | Kết quả + sample sizes | ✅ n=120, CI |
| 8 | Error analysis TP/TN/FP/FN | ✅ §6–7 |
| 9 | Không safety regression | ✅ 0 vi phạm thực; D4/D8 nguyên |
| 10 | Phân biệt replay vs raw-PE E2E | ✅ xuyên suốt |

⇒ Automated đạt; semantic human-grading còn lại ⇒ **PARTIAL** (đúng mục 12).

## 12. Giới hạn

- Track là FEATURE_RECORD_REPLAY; **không** phải raw-PE E2E. Malicious raw-PE E2E = BLOCKED
  (không tải/chạy malware). Cần mẫu được cấp qua môi trường phê duyệt.
- Kết quả gắn với 1 model SLM (qwen3.5:4b, thinking OFF) + 1 phiên bản prompt; không suy rộng cho SLM khác.
- Auto-check an toàn/claim là **bảo thủ** (có false-positive); phán quyết cuối cần người.
- Semantic rubric chưa có human score ⇒ chưa kết luận chất lượng giải thích.
- Tập audit phân tầng, không đại diện phân phối tự nhiên.

## 13. Artifacts (`evaluation/task05c/results/`)

`audit_manifest.json` · `eval_results.json` · `comparison_table.csv` · `samples/*.json` (120) ·
`annotation_package/` · `example_reports_redacted.md`. Code: `sampling/evidence_projection/
static_only/agent_replay/rubric/metrics/runner/examples.py` + `tests/test_05c.py`.
