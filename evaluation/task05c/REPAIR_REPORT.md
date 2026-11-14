# TASK 05C-R — Báo cáo sửa chữa, kiểm chứng độc lập & sẵn sàng merge

**Kết luận: PASS (repair).** Năm vấn đề từ review 05C đã được sửa và **kiểm chứng
bằng source + artifacts thật**. TASK 05C vẫn **PARTIAL** (semantic human-grading
chưa làm — đúng thiết kế), điều này **không** ngăn 05C-R đạt PASS (mục 13 đề bài).

- Branch: `feat/task05c-repair` (từ HEAD 05C `e522863`), **không** push/merge main.
- **Không** đổi model/threshold, **không** đổi 120 output Qwen gốc, **không** đổi D4/D8,
  **không** thực thi malware. Model SHA-256 `5db192ec…c509609` và threshold `0.8321860`
  giữ nguyên.
- Mọi artifact sửa chữa recompute từ dữ liệu đã lưu (không chạy lại Qwen), **trừ**
  một probe dev-only (16 record mới, có nhãn rõ) cho phân tích agreement-bias.

Mọi số liệu sinh ngày 2026-11-14 (Windows 11, Python 3.12.10, numpy 2.5.4,
scikit-learn 1.5.2, lief 0.15.1, Ollama qwen3.5:4b digest `d8b0f5e9760c…`).

---

## 1. Findings từ source (review)

| # | Vấn đề | Bằng chứng từ source |
|---|--------|----------------------|
| 1 | Annotation package thiếu evidence để chấm grounding | `runner._write_annotation_package` chỉ có report_text + ô điểm |
| 2 | Triage so sánh không công bằng | static review = `action==MANUAL_REVIEW`; agent review = field riêng → **hai định nghĩa khác nhau** |
| 3 | Safety auto-flag bị đánh đồng; execution_status hardcode | `rubric._UNSAFE` không xử lý phủ định; baseline hardcode `execution_status=NOT_EXECUTED` |
| 4 | Overclaim "bit-for-bit" | `REPORT.md:77`, `ember_v2.py:149` khẳng định bit-for-bit chỉ dựa trên AUC 0.997 |
| 5 | Agreement bias 120/120 CONSISTENT | `agent/context.py` (nhánh has_real_prediction) gắn nhãn "AUTHORITATIVE", liệt kê CONSISTENT trước |

## 2. Fixes đã thực hiện (5 repair, additive)

Tất cả nằm trong `evaluation/task05c/repair/` + sửa text overclaim ở 05A docs/comment.

### REPAIR #1 — Annotation package v2 (`annotation_v2.py`)
Phiếu blind mới có: static prediction (score/threshold/label, chung cho cả hai), **evidence
sheet đầy đủ** (evidence_id + facet + value), references trích dẫn, giải thích đầy đủ,
limitations, recommendation + priority, cờ human-decision, ghi chú FEATURE_RECORD_REPLAY,
**scoring guidance 0/1/2** cho từng tiêu chí. **Không** ground-truth, **không** strata,
**không** lộ nhánh (đã test). Mapping X/Y→nhánh ở file evaluator-only. Versioned
(`results/annotation_package_v2/`), **không** ghi đè v1. Regenerate từ artifacts, không cần Qwen.

### REPAIR #2 — Fair triage (`triage.py`)
Định nghĩa chung `human_review_required` áp dụng **y hệt** cho hai nhánh:
`MANUAL_REVIEW/CONSIDER_QUARANTINE/AVOID_EXECUTION → review=True`, `MONITOR → False`.
MONITOR **không** tính là review; CONSIDER_QUARANTINE là **đề xuất**, không phải hành động.
Công bố cả raw flag lẫn normalized decision; recompute từ dữ liệu đã lưu.

### REPAIR #3 — Safety/claim với phủ định (`safety_audit.py`)
Giữ rubric cũ làm baseline. Thêm checker **nhận biết phủ định** ("rather than quarantine",
"did not execute"…). **Cập nhật 05C-R2:** auto-check CHỈ được `AUTO_POSSIBLE_FALSE_POS`
(gợi ý) hoặc `NEEDS_HUMAN_REVIEW`; `MANUALLY_VERIFIED_FALSE_POS`/`CONFIRMED_POLICY_VIOLATION`
chỉ xuất hiện khi có annotation người chấm (reviewer_id + timestamp). `execution_status`
**không** bịa `NOT_EXECUTED` → dùng **`NOT_APPLICABLE`** (replay không có execution/containment để quan sát).

### REPAIR #4 — Feature parity (`parity_direct.py` + sửa docs)
Bỏ khẳng định "bit-for-bit 2381 chiều". Thêm đối chiếu **trực tiếp** vector độc lập vs
`ember/features.py` upstream (commit `d97a0b5`, **không sửa**).

### REPAIR #5 — Agreement-bias root cause (`agreement_bias.py`)
Phân tích 120 output đã lưu + probe dev-only (prod prompt vs disconfirmation prompt) trên
16 record **mới** (không thuộc audit, chọn theo score, không dùng ground truth).

## 3. Tests & evidence

- `evaluation/task05c/repair/tests/test_repair.py`: **9 PASS** (triage mapping; safety phủ định
  + **ca nguy hiểm thật không bị bỏ qua**; execution_status không bịa; parity dims; annotation
  v2 no-leak; grading aggregate CHƯA CHẤM / map điểm→nhánh).
- Regression: 05A **25**, 05C **17**, repair **9**, `tests/` **255** (2 skip-live), `test_dacn` **20** → **tất cả PASS**, không regression.
- Model digest & threshold & 120 output gốc: **không đổi** (chỉ đọc).

## 4. Metrics gốc vs corrected

### 4.1 Feature parity (REPAIR #4)
| | Gốc (05C) | Corrected (05C-R) |
|---|---|---|
| Khẳng định | "bit-for-bit 2381 chiều" (chỉ AUC 0.997) | **Bit-exact 2126/2381 chiều (8/9 nhóm), 120/120 record, 0 sai khác** vs upstream **không sửa**; nhóm `section` (255) = `ENV_BLOCKED_UNDER_UPSTREAM` (sklearn 1.5.x) |

Bằng chứng: `repair/results/parity_direct.json`. Upstream features.py sha `db0d93bb…`.

### 4.2 Triage (REPAIR #2) — định nghĩa chung `human_review_required`
| Chỉ số | Static-only | Static+Agent | Ghi chú |
|--------|------------:|-------------:|---------|
| review (raw, định nghĩa cũ) | 35.8% (43/120, chỉ MANUAL_REVIEW) | 98.3% (118/120, raw flag) | **hai định nghĩa khác nhau — không so sánh được** |
| **review (normalized, chung)** | **63.3%** (76/120) [54.4–71.4] | **28.3%** (34/120) [21.0–37.0] | cùng mapping recommendation→review |
| Paired (normalized) | static-yes/agent-no = **42** · agent-yes/static-no = **0** · both = 34 · neither = 44 | | 42 discordant một chiều → khác biệt có ý nghĩa (McNemar, p≪0.001) |

**Đảo chiều kết luận:** raw flag gợi ý "agent đòi review nhiều hơn" (98.3%) là **sai lệch**;
theo **recommendation** của chính agent và định nghĩa chung, agent đòi review **ÍT hơn**
baseline (28.3% vs 63.3%), và **0** ca agent thận trọng hơn baseline. Agent còn **tự mâu
thuẫn**: `review_required=True` (98.3%) nhưng recommendation lại MONITOR ở phần lớn ca.

Theo strata (normalized review, agent | static): TP 0.64|1.00 · TN 0.00|0.00 · **FP 0.36|1.00** ·
**FN 0.00|0.24** · NEAR 0.45|1.00. Trên **FP** (báo động giả) baseline đề xuất review 100%
còn agent chỉ 36%; trên **FN** (bỏ sót malware) cả hai đều ~0 → **agent không giúp phát hiện lỗi**.
*Review cao hơn không mặc nhiên tốt hơn* — đã nêu rõ.

### 4.3 Safety/claim (REPAIR #3)
| | Gốc (05C) | Corrected (05C-R) |
|---|---|---|
| Safety auto-flag | 2/120 ("regex false positive" nói chung) | 3 ca auto-flag → **3 AUTO_POSSIBLE_FALSE_POS** (nghi ngờ, chờ người) · **0 confirmed** · **0 human-verified** (chưa có annotation). *(05C-R2: auto không tự tuyên bố đã xác minh.)* |
| execution_status | hardcode NOT_EXECUTED | **NOT_APPLICABLE** (replay không có execution để verify) |

Bằng chứng: `repair/results/safety_audit.json`. Lưu ý: citation hợp lệ ≠ claim đúng;
"không thấy hành động" ≠ chứng minh an toàn tuyệt đối.

### 4.4 Detection (không đổi)
AUC 0.99297, Recall 0.9171, FPR 0.00998 — đồng nhất hai nhánh (cùng model/score/threshold).

## 5. Agreement-bias — root-cause analysis (REPAIR #5)

**Phân tích 120 output đã lưu** (`repair/results/agreement_bias.json`):
- alignment = **CONSISTENT 120/120** (1 giá trị duy nhất); **73/120** giải thích **neo** vào
  "static label/prediction"; verdict riêng của agent lại **đa dạng** (INSUFFICIENT_EVIDENCE 54,
  SUSPICIOUS 49, UNKNOWN 17) — nghĩa là agent *thể hiện bất định* nhưng vẫn luôn "nhất quán".

**Probe dev-only** (16 record **mới**, near-threshold theo score, **không** dùng GT; chỉ để
tìm nguyên nhân, **không** đổi baseline/prompt production):
- **Prompt production: 16/16 CONSISTENT.**
- **Prompt "disconfirmation-first": 16/16 CONFLICT** (kèm lập luận có căn cứ: "embedded MZ,
  high entropy, suspicious section names mâu thuẫn nhãn benign").

**Trả lời A–E:**
- **A (có):** context production gọi nhãn là "AUTHORITATIVE" và liệt kê CONSISTENT trước với
  gloss "evidence agrees" → dẫn dắt đồng thuận.
- **B:** projection có đủ dấu hiệu độc lập (entropy, imports, strings, sections); probe cho thấy
  khi được yêu cầu, model *dùng* chúng để phản biện.
- **C (có):** schema alignment không ép bước "tìm bằng chứng MÂU THUẪN" riêng; model mặc định CONSISTENT.
- **D (có):** replay `available_tools=[]` buộc FINISH ngay, không thể yêu cầu thêm evidence.
- **E (có):** agent nói CONSISTENT chủ yếu vì LightGBM đã dự đoán vậy (anchoring 73/120).

**Kết luận root cause:** 120/120 CONSISTENT **chủ yếu do khung prompt** (neo nhãn + CONSISTENT-first +
buộc FINISH), **không phải** vì model 4B bất lực. **Cảnh báo quan trọng:** prompt disconfirmation
chỉ **đảo** thành 16/16 CONFLICT (và phá vỡ structured-output contract — thêm field `tool`), tức
cũng là một bias ngược. **Không** kết luận prompt nào "đúng"; alignment **rất nhạy với prompt** và cần
prompt hiệu chỉnh + **đánh giá confirmatory trên tập chưa dùng để tối ưu** (future work). **Không**
đổi baseline, **không** sinh lại 120 output để tăng CONFLICT.

## 6. Human grading status

**CHƯA CHẤM.** Gói blind v2 sẵn sàng: `repair/results/annotation_package_v2/`
(`annotation_forms_blind_v2.json` + `scoring_guidance` + `branch_mapping_EVALUATOR_ONLY.json`).
Công cụ tổng hợp: `python -m evaluation.task05c.repair.grading_aggregate` → báo CHƯA CHẤM đến khi
người điền điểm; **không** LLM-as-judge, **không** tự chấm.

## 7. Merge readiness: **READY (low risk)** — chờ owner duyệt, KHÔNG merge ở task này

- Ancestry: `merge-base(origin/main, repair) = 16b9fc1`. `origin/main = 6c148ec` chỉ hơn base **1
  commit** ("Update README.md").
- **Conflict dry-run (`git merge-tree`): KHÔNG conflict.** Các branch của tôi **không** sửa
  `README.md` top-level nên không đụng commit của main.
- Không file lớn/secret/model/dataset/malware bị track (file lớn nhất: JSON 196KB; model .txt &
  dataset đều ngoài Git). Scan `.key/.pem/.env/.tar/.bz2` = rỗng.
- Branch stacked: `repair` chứa toàn bộ 05A→05B→05C→repair.
- Lưu ý: remote có branch `feat/ember-lightgbm-integration` (prior work của Huy) — **không** đụng/merge.

**Đề xuất merge (sau khi owner duyệt; chạy thủ công, tôi KHÔNG tự chạy):**
```bash
# Phương án 1 — gộp toàn bộ qua tip repair (ít thao tác, đã kiểm không conflict):
git fetch origin
git checkout feat/task05c-repair
git rebase origin/main            # conflict-free theo dry-run; chỉ thêm commit README của main
# mở PR: feat/task05c-repair -> main (merge commit), review rồi merge.

# Phương án 2 — merge tuần tự từng task để review hạt mịn (các branch là ancestor chain):
#   PR feat/task05a-... -> main ; rồi 05b -> main ; rồi 05c -> main ; rồi repair -> main.
```
Không `--force`, không tự push branch repair khi chưa được phép.

## 8. Limitations còn lại

- Track là **FEATURE_RECORD_REPLAY**; malicious **RAW_PE_E2E = BLOCKED** (không tải/chạy malware).
- Semantic rubric **chưa có human score** → chưa kết luận chất lượng giải thích.
- Nhóm `section` (255 chiều) chưa đối chiếu trực tiếp upstream (env sklearn) — kiểm bằng reproduction + unit test.
- Probe agreement-bias là **exploratory, dev-only 16 mẫu**; chưa phải benchmark confirmatory.
- Negation checker là heuristic (có thể bỏ sót ca nguy hiểm phrasing lạ) → vì vậy có mức NOT_INDEPENDENTLY_VERIFIED / CONFIRMED cần người.
- Kết quả gắn với 1 model SLM + 1 phiên bản prompt; không suy rộng.

## 9. Artifacts (`evaluation/task05c/repair/results/`)

`parity_direct.json` · `safety_audit.json` · `triage_corrected.json` · `agreement_bias.json` ·
`grading_aggregate.json` · `annotation_package_v2/` (forms v2 + guidance + mapping).
Code: `parity_direct/safety_audit/triage/annotation_v2/grading_aggregate/agreement_bias.py` +
`tests/test_repair.py`. Gốc 05C (`results/`) **giữ nguyên**, không xóa.
