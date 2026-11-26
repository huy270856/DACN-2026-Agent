# TASK 07A — EVALUATION_LOG

Nhật ký append-only cho TASK 07A (diagnostic ablations, pha P0). Không sửa các mục cũ; sự cố
mới ghi thành mục mới.

## 2026-11-26 — G0: quyết định của owner

Nguồn: tin nhắn của owner trong session Claude Code ngày 2026-11-26 (nguyên văn được tóm lại
dưới đây, không diễn giải thêm).

| # | Quyết định | Trạng thái |
|---|---|---|
| D1 | Dùng lại cohort 20 PE của 06B-J (`candidate_cases_v2_EVALUATOR_ONLY.json`) làm **DEV_DIAGNOSTIC** pool. **Không** dùng lại làm confirmatory | APPROVED |
| D2 | Cho phép oracle V3; **không** đưa ground-truth label, evaluator rationale hoặc expected answer vào model context | APPROVED |
| D3 | Cho phép additive changes trong `agent/config.py` và `agent/planner.py`; default behavior giữ tương thích baseline | APPROVED |
| D4 | Authorization string cho live Qwen run: `DACN_OWNER_TASK07A_DEV_DIAGNOSTIC` | AUTHORIZED |
| D5 | Tạo branch `feat/task07a-agent-diagnostic-ablations`, commit local `REPORT.md` + `PLAN_TASK07A.md` | APPROVED — commit `69efab2` |

Push: **chưa** được phép; không push.

## 2026-11-26 — S1: sai lệch so với PLAN §3.1 (vị trí các knob decoding)

- **Phát hiện:** `evaluation/task06a/tests/test_controls.py::test_frozen_baseline_unchanged` chạy
  `git diff --exit-code edd0a25 -- agent ... ':(exclude)agent/planner.py'`. Tức là mọi file trong
  `agent/` **trừ** `planner.py` đang bị khóa với baseline 06A. Thêm field vào `AgentConfig`
  (`agent/config.py`) sẽ làm test guard này FAIL.
- **Quyết định thực hiện:** D3 *cho phép* (không bắt buộc) sửa `config.py`. Để không phá guard
  frozen-baseline và không sửa test của 06A, toàn bộ knob mới được đặt trong `agent/planner.py`:
  dataclass `DecodingOptions(num_ctx=8192, seed=42, top_p=None, top_k=None,
  presence_penalty=None)` với validate (num_ctx 2048–65536, seed 0..2^31-1, top_p (0,1],
  top_k 1..1000, presence_penalty [-2,2]); `OllamaPlanner(cfg, decoding=None)`.
  `agent/config.py` **không đổi**.
- Mặc định: request body **byte-identical** với `agent/planner.py` tại `e31ee31` (test so sánh
  bằng cách exec source của commit đó với fake HTTP). `meta` chỉ thêm `thinking`,
  `thinking_chars` khi response có field `thinking`.
- Khi `content` rỗng nhưng có `thinking`, `PlannerError` ghi thêm `thinking_chars`,
  `done_reason`, `eval_count` để chẩn đoán G1 (vẫn là lỗi, không fallback).
- Hệ quả cho harness: `workflow_v34.Planner(cfg)` không nhận `DecodingOptions`, nên harness 07A
  dùng `variants.V34Planner(cfg, decoding)` (gọi đúng `decide_with_schema(ctx,
  final_v34.contract(ctx))`). Test xác nhận với V0 s42 request body giống hệt
  `workflow_v34.Planner(runner.CFG)`.
- `runner.AGENT_SOURCES` của 06B-J hash `agent/planner.py`; artifact frozen của 06B-J **không**
  bị ảnh hưởng (không rerun 06B-J). Không có test 06B-J nào so hash nguồn với hằng số cố định
  (test drift dùng monkeypatch).

## 2026-11-26 — S2: sai lệch nhỏ so với PLAN §3.2

- `reference_EVALUATOR_ONLY` trong `candidate_cases_v2_EVALUATOR_ONLY.json` là **dict JSON**, không
  phải chuỗi repr Python như PLAN mô tả. `variants.load_relevant` nhận cả hai dạng (chuỗi thì
  dùng `ast.literal_eval`, không bao giờ `eval`).
- Hai case IN_INITIAL (0005: index 2; 0014: index 1) có entry liên quan đầu tiên nằm ở trang 0, nên
  với V3 oracle **không thêm trang nào** (đã hiển thị sẵn sau tool call). V3 trên hai case này về
  cấu hình tương đương V0 s42.
- Oracle không cập nhật `pages` của workflow. Nếu model READ đúng trang oracle, guard
  `RETRIEVAL_NO_INFORMATION_GAIN` không biết trang đó đã hiển thị, nên lượt đọc đó được tính là
  có information gain. Sai lệch nhỏ, đã biết.
- `ablation.prepare` patch `runner.CFG` trong lúc gọi `runner.prepare` để `freeze.json` ghi đúng
  AgentConfig của variant (initial_contexts chỉ đọc budget context, giống nhau ở mọi variant).
- Ca có exception thoát khỏi `workflow_v34.run` được ghi `status=HARNESS_EXCEPTION`, tính vào
  mẫu số, không chạy lại.
- Thêm variant tùy chọn **V1b** (thinking, temp 0.1, không override sampling, seed 42) như PLAN
  §2.2 gợi ý.
- `.venv` không tồn tại trong repo; toàn bộ test/run dùng Python 3.12.10 hệ thống.

## 2026-11-26 — S1/S2 regression

- Trước thay đổi (baseline, cùng ngày): `695 passed, 4 skipped, 0 failed` (+81 subtests).
- Sau S1 (planner) + S2 (harness, tests): `740 passed, 4 skipped, 0 failed` (+81 subtests).
  45 test mới: 21 ở `tests/test_task07a_planner.py`, 24 ở `evaluation/task07a/tests/test_07a.py`
  (unit + MOCK_LLM; MOCK_LLM không phải bằng chứng hành vi).

## 2026-11-26 — S3 / G1: smoke V1 (thinking) — FAIL (truncation)

- Lệnh: `python -m evaluation.task07a.ablation smoke --variant V1 --out evaluation/task07a/results/smoke_V1 --authorized-by DACN_OWNER_TASK07A_DEV_DIAGNOSTIC`
- Case: `dev_0001` (tracert.exe, Q_NET; DEV, ngoài cohort). LOCAL_QWEN, Ollama 0.40.16, qwen3.5:4b digest `d8b0f5e9…`.
- Kết quả cơ chế: `think=true` cùng `format` **chạy được**. 3 lượt chọn hành động (TOOL_CALL →
  READ_EVIDENCE → FINISH-select) đều có `thinking` riêng (5 016 / 6 350 / 7 110 ký tự) và
  `content` là JSON hợp lệ theo schema, `done_reason=stop`.
- Lỗi: 2 lượt viết final (lượt 4 và lượt repair 5) bị cắt ở `eval_count=6144 = num_predict`
  (`done_reason=length`), thinking 14 837 / 17 266 ký tự; content JSON dở dang
  (`Unterminated string…`, `Expecting ',' delimiter…`). Run kết thúc `VALIDATION_REPAIR_EXHAUSTED`.
  Không có content rỗng. `prompt+output` lớn nhất 11 499 < 16 384 (`num_ctx` không phải nút thắt).
- Gate G1 (PLAN §6: "không truncation") = **FAIL**. Raw response nằm trong
  `results/smoke_V1/dev_0001_C.json` (`turns[].raw`, `turns[].meta.thinking`).
- Đánh giá: đây là lỗi **budget output** (`num_predict=6144` không đủ cho thinking + final JSON),
  không phải lỗi "thinking cùng format không chạy được". Quyết định tiếp theo cho V1/V1b cần owner
  (xem mục kế tiếp).

## 2026-11-26 — S4 / G2: smoke V2 (analysis-first) — PASS (cơ chế)

- Lệnh: `python -m evaluation.task07a.ablation smoke --variant V2 --out evaluation/task07a/results/smoke_V2 --authorized-by DACN_OWNER_TASK07A_DEV_DIAGNOSTIC`
- `analysis_first=true` (Ollama giữ thứ tự property), `analysis_parse=OK` (634 ký tự),
  `final_v34.parse` chấp nhận phần còn lại, `done_reason=stop`. Gate G2 = **PASS**.
- Ghi chú hành vi (không phải lỗi cơ chế): run smoke dừng ngay lượt 1 với
  `EVIDENCE_NOT_VISIBLE` — model đặt một ID trong `omitted_evidence_ids` vào `evidence_refs` của
  TOOL_CALL; v3.4 không cho repair TOOL_CALL nên `VALIDATION_REPAIR_EXHAUSTED`. Đây là hành vi
  v3.4 đã biết (REPORT §3.5, `omitted_evidence_ids` gây hiểu sai), sẽ được tính vào M7 nếu xảy
  ra trong cohort.

## 2026-11-26 — Owner decision sau G1: nâng budget V1, bỏ V1b

- Câu hỏi đưa owner: V1 = BLOCKED, hay nâng budget rồi smoke lại. Owner chọn **"Nâng budget, bỏ
  V1b"**.
- Thay đổi (trước protocol freeze, chỉ dựa trên smoke DEV ngoài cohort): V1 `num_predict`
  6144 → **12288**, `num_ctx` 16384 → **24576**, `max_tokens` 150000 → **200000** (workflow_v34 trừ
  `max(8192 + 2·num_predict, actual)` mỗi lượt; 5 lượt × 32 768 = 163 840 nên 150 000 sẽ chặn
  lượt 5). Sampling, `inference_timeout_s=240`, `wall_clock_s=900` không đổi.
- **V1b bị loại** khỏi `VARIANTS`. Confound của V1 (đổi cả thinking lẫn sampling temp 0.6 /
  top_p 0.95 / top_k 20 / presence_penalty 0.0) **chưa được tách** và phải ghi trong báo cáo.
- Quy tắc: smoke mới ghi ở `results/smoke_V1_r2/` (giữ nguyên `smoke_V1/` FAIL). Nếu G1 lần 2
  vẫn FAIL thì V1 = **BLOCKED**, không thử thêm.

## 2026-11-26 — S3 / G1 lần 2: smoke V1 (budget mới) — PASS

- Lệnh: `python -m evaluation.task07a.ablation smoke --variant V1 --out evaluation/task07a/results/smoke_V1_r2 --authorized-by DACN_OWNER_TASK07A_DEV_DIAGNOSTIC`
- Cùng case `dev_0001`. 5 lượt (TOOL_CALL, READ, READ, FINISH-select, final), mọi lượt
  `done_reason=stop`, có `thinking` (11 928–16 552 ký tự) và content JSON hợp lệ; không có content
  rỗng, không truncation; `prompt+output` lớn nhất 11 243 (< 0.95 × 24 576). Run
  `FINISHED_FLAGGED`. Gate G1 = **PASS**. VRAM khi model nạp: khoảng 5.5 GB / 8 GB.
