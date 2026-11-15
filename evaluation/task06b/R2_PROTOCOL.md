# TASK 06B-R2 — PROTOCOL: evidence-native final contract (v3.4)

## 0. Phạm vi và bất biến

Mục tiêu: sửa **nguyên nhân gốc** khiến Agent nhận evidence mới qua D1–D9 nhưng
không tạo được final hợp lệ, bằng cách thiết kế lại *output contract*, không tuning
prompt để ép FINISH. Không model/threshold mới, không analyzer thứ hai, không sửa
production v1, không chạm D1–D9, Node C, root README, hay bất kỳ frozen artifact
05A–05D / 06A / 06B / 06B-R. Các module v3.3 (`repair_*`) giữ nguyên, đóng băng.

## 1. Chứng cứ chẩn đoán (đọc trước khi sửa)

Nguồn: raw turns `results/repair_dev_v4/{00,01,02}_D.json` (turn 2 = final đầu,
turn 3 = repair), `repair_finalization.py`, `repair_schema.py`, `repair_context.py`,
`REPAIR_REPORT.md`. Mỗi root cause phải trỏ tới raw evidence cụ thể (xem R2_REPORT §5).

## 2. Hợp đồng v3.4 (module mới, không ghi đè)

`investigation_v3/final_v34.py` + `investigation_v3/workflow_v34.py`.

- **Evidence-native claim**: `{kind, text, evidence_ids, import_refs?}`. `import_refs`
  là mảng **bên trong** claim, mỗi phần tử `{evidence_id, entry_index}`.
- **Bỏ** mảng `import_bindings` cấp cao và **bỏ** `claim_index` → không còn join chéo mảng.
- **Bỏ** ràng buộc literal-phải-có-trong-text. Trusted layer *resolve* entry →
  `{library, symbol|#ordinal, phase, value_sha256}` để hiển thị/provenance; đây là
  **source resolution**, không phải tự tạo semantic assertion.
- Giữ nguyên: `evidence_ids` phải visible; OBSERVED phải có nguồn; `import_ref` phải
  là imports-facet nằm trong `evidence_ids` của chính claim và entry phải visible;
  self-corroboration / absence-without-source / entropy-số bị flag; fail-safe
  MANUAL_REVIEW; một repair; Controller/D4/D7/D9; retrieval bounded 2×16.
- Hai stage decoding tách biệt: action-selection vs final-authorship (không đổi so v3.3).

## 3. Kiểm thử deterministic (Phase 4)

`evaluation/task06b/tests/test_v34.py`: structural (bỏ binding array, bỏ claim_index,
malformed/enum, stage separation, Controller ref-limit); resolution (general claim
không literal vẫn accepted + resolved; ref sai facet / ref không thuộc claim / entry
vô hình bị reject; prediction claim không ref); honesty (self-corroboration, numeric,
fabricated API bị flag; OBSERVED thiếu nguồn bị reject); MOCK_LLM integration (repair
bounded, fail-safe, D1–D9 thật rồi final evidence-native). Phân biệt rõ Unit /
MOCK_LLM / Live. MOCK không bao giờ được coi là autonomous behavior.

Lệnh:
```
python -m pytest evaluation/task06b/tests/test_v34.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider        # full regression, no v3.3 drift
```

## 4. Live DEBUG diagnostic (Phase 5) — KHÔNG confirmatory

`evaluation/task06b/r2_debug.py run --out results/r2_debug_v34`.

- **Một lượt duy nhất**, LOCAL_QWEN thật (`qwen3.5:4b`, digest `d8b0f5e9…`), seed 42,
  temp 0.1, think OFF, num_ctx 8192, num_predict 2048. Output exclusive, không overwrite.
- Chạy trên **đúng tracert/findstr/fc** đã dùng v3.1–v3.3 → theo spec §12.1 đây là
  **DEBUG/root-cause**, **NOT_RUN** confirmatory, **không** independent holdout,
  **không** generalization. Không tuning, không re-run-until-pass.
- Lưu: initial_state, full report (turns/raw/meta/events), freeze.json (base commit,
  source hashes, system-prompt hash, model/threshold/ollama digest), summary.json.
- Phân biệt khi báo cáo: **parser/structural accepted** vs **clean grounded (unflagged)**
  vs **flagged (MANUAL_REVIEW)**. FINISHED_FLAGGED ≠ fully grounded.

## 5. Quy tắc dừng

Nếu v3.4 vẫn flagged vì model-semantic (vd self-corroboration), báo đúng, không
tuning prompt để gỡ flag. Semantic relevance = PENDING_INDEPENDENT_REVIEW. Confirmatory
holdout và human grading tách phiên sau; không biến 3 file DEV này thành confirmatory.
