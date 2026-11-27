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

## 2026-11-27 — S6 sự cố: Ollama ngừng phục vụ giữa V0 s42

- `prepare V0 s42` OK (2026-11-26 17:08). `run V0 s42` bắt đầu 17:08:58.
- sample_0001–0012: hoàn tất bình thường (11 FINISHED_FLAGGED, 1 FINISHED).
- sample_0013: lượt 3 lỗi `Ollama inference failed: ConnectionResetError [WinError 10054]`
  (sau TOOL_CALL đã commit rev 5 và FINISH-select) → `INVESTIGATION_INCOMPLETE`.
- sample_0014, 0015, 0016: lượt 1 lỗi `URLError [WinError 10061]` (connection refused) →
  `INVESTIGATION_INCOMPLETE`, không có tool call.
- Sau đó tiến trình script và session Claude Code kết thúc; sample_0017–0020 **chưa có trace**.
  V0 s7, V2, V3, V1 chưa bắt đầu.
- Ngày 2026-11-27: `http://127.0.0.1:11434` không phản hồi. Không tự khởi động lại Ollama
  (PLAN §6), chờ owner.
- Xử lý theo PROTOCOL §6 (đã freeze): 4 run lỗi do Ollama **được giữ nguyên, tính vào mẫu số, không
  chạy lại**. Đây là lỗi hạ tầng, không phải hành vi model; báo cáo sẽ tách riêng số run bị lỗi
  hạ tầng. Các case chưa có trace (0017–0020) được tiếp tục bằng `run` trên cùng thư mục
  (protocol cho phép), sau khi `validate_freeze` xác nhận Qwen digest/version không đổi.

## 2026-11-27 — S6: resume V0 s42, V0 s7 xong, sự cố Ollama lần 2 giữa V2 s42

- 04:32 Ollama phản hồi lại (ứng dụng desktop đã tự khởi động lại; owner cho phép bật Ollama).
  Digest `d8b0f5e9…` và version 0.40.16 khớp freeze. Không cần thao tác khởi động.
- `run V0 s42` tiếp tục cho case chưa có trace: 0017–0020 đều `FINISHED_FLAGGED`, isolation PASS.
  V0 s42 đủ 20 trace, trong đó **4 run lỗi hạ tầng** (0013–0016) giữ nguyên trong mẫu số.
- V0 s7: 20/20 trace, 17 `FINISHED_FLAGGED`, 3 `FINISHED`, không lỗi hạ tầng.
- V2 s42: 0001–0017 chạy; **3 run lỗi hạ tầng**:
  - 0018: lượt 3 (final) `HTTP Error 500` (server log: 500 ở 04:51:39 rồi runner nạp lại model);
  - 0019: `RemoteDisconnected`;
  - 0020: `WinError 10061` connection refused.
- Nguyên nhân quan sát được (`%LOCALAPPDATA%\Ollama\app.log`): 04:51:58 `shutting down desktop
  server` / `shutting down ollama server`. Updater của ứng dụng desktop đã tải sẵn v0.40.18
  (`update already downloaded`). Trong `server.log` còn có request lạ không thuộc harness
  (04:50:36–42 `HEAD /`, `GET /api/ps`, `POST /api/show`, `POST /api/generate`) ngay trước một
  lần nạp lại model. Nguyên nhân gốc chưa xác minh chắc chắn; khả năng cao là ứng dụng desktop
  (UI/updater). Sự cố V0 s42 ngày 2026-11-26 có cùng kiểu (reset rồi refused).
- Chuỗi script bị dừng thủ công ngay khi thấy connection refused để không tiêu run vào lỗi kết nối.
  Tiến trình `prepare V2 s7` mồ côi chạy xong: `results/V2_s7/freeze.json` ghi
  `ollama.status=UNAVAILABLE`, nên `run` bị chặn `BLOCKED_OLLAMA_UNAVAILABLE`. **Không có case nào
  của V2_s7 được chạy.** Thư mục này giữ nguyên (write-once), đánh dấu `NOT_RUN_BLOCKED`, và V2
  seed 7 được prepare/run ở thư mục mới `results/V2_s7_r2/`. Đây không phải rerun ca lỗi.
- Từ 2026-11-27 ~05:0x, Ollama được chạy **headless** bằng `ollama.exe serve` (cùng binary 0.40.16,
  `OLLAMA_HOST=127.0.0.1:11434`), không qua ứng dụng desktop, để tránh updater tự cài 0.40.18.
  Model và digest không đổi; `num_ctx`/sampling do request quy định. Chênh lệch có thể có giữa
  server do app khởi chạy và server headless (biến môi trường của app) chưa được kiểm; V0 s42/s7
  và V2 s42 chạy dưới app, phần còn lại chạy headless. Ghi lại như một confound hạ tầng.
- Khuyến nghị owner: tắt auto-update của ứng dụng Ollama trong thời gian chạy thí nghiệm.

## 2026-11-27 — Đính chính mục trước

- Mốc bật Ollama headless ghi "~05:0x" là sai. Đúng là khoảng **04:53** (V2 s7_r2 `PREPARE`
  04:53:51, `RUN` 04:54:38 đã chạy dưới server headless).
- Diễn biến sau đó: V2 s7_r2 xong 05:06 (20 trace: 16 `FINISHED_FLAGGED`, 3
  `MODEL_REQUESTED_MORE_EVIDENCE`, 1 `RETRIEVAL_NO_INFORMATION_GAIN`; 0 lỗi hạ tầng). V3 s42 xong
  05:10 (8 trace). V1 s42 bắt đầu 05:11; trace cuối `sample_0007_C.json` lúc 05:37.

## 2026-11-27 — S6 kết thúc: V1 dừng

Ghi nguyên văn quyết định của owner (tin nhắn trong session Claude Code, 2026-11-27):

> BỐI CẢNH
> - V1 s42 dừng sau sample_0007 (file cuối 05:37). Session trước kết thúc kéo theo runner và `ollama serve` headless (tiến trình con của session).
> - Case 0008: CaseState trong home C đã lên rev 5 (tool đã commit) nhưng không có `sample_0008_C.json`. Resume sẽ bị guard STATE_CHANGED_WITHOUT_SAVED_TRACE_NO_RETRY chặn (ablation.py:132) và dừng cả vòng lặp. Guard này đúng.
> - Trong 7 trace của V1 s42, có 3 case (0001, 0002, 0007) bị truncation ngay lượt 1: thinking khoảng 42–44k ký tự, eval_count=12288, done_reason=length, content rỗng.
>
> QUYẾT ĐỊNH CỦA OWNER
> 1. KHÔNG resume V1 s42, KHÔNG chạy V1 s7, KHÔNG sửa harness hay metrics đã freeze, KHÔNG rerun case nào.
>    - V1 s42 = PARTIAL: 7 trace + 1 INFRA_INTERRUPTED (0008) + 12 NOT_RUN (0009–0020).
>    - V1 s7 = NOT_RUN.
>    - Lý do: (a) quy tắc toàn vẹn ghi trước trong PROTOCOL §7 (truncation > 2 ca → variant không diễn giải được) đã kích hoạt; (b) muốn resume thì phải sửa harness sau freeze, không đáng.
>    - Đây là deviation có owner duyệt, dựa trên metric toàn vẹn chứ không dựa trên kết quả nghiên cứu.
>    - V1b vẫn NOT_RUN như đã quyết định trước đó.
> 2. Ghi limitation về provenance: với các lượt trả content rỗng, agent/planner.py:154 raise PlannerError trước khi gắn meta, nên raw thinking bị mất, chỉ còn thinking_chars. Không sửa trong 07A (sẽ gây SOURCE_DRIFT). Đưa vào danh sách việc cần làm của TASK 07B.
> 3. Ghi confound hạ tầng đã biết: V0 s42/s7 và V2 s42 chạy dưới Ollama của ứng dụng desktop; V2 s7_r2, V3 và V1 chạy dưới Ollama headless. Ghi cả sự cố tiến trình chết theo session.
> 4. Ghi minh bạch: đã xem kết quả sơ bộ V0/V2/V3 trong scratchpad trong lúc V1 chạy. Không có cấu hình, ngưỡng hay regex nào bị đổi sau khi xem.

Ghi chú của người thực hiện (Claude Code):

- Bảng quyết định nằm ở **PROTOCOL §5** (owner gọi là "§7" theo số mục trong PLAN; cùng một bảng,
  dòng "Variant có M7 overflow hoặc truncation > 2 run").
- Xác nhận mục 4: kết quả sơ bộ được tính bằng `metrics.collect` (chỉ đọc) và ghi vào
  scratchpad lúc khoảng 05:1x–05:3x. Sau thời điểm đó **không** có file nào trong `variants.py`,
  `ablation.py`, `metrics.py`, `PROTOCOL.md` bị sửa (`git diff c58d351 -- evaluation/task07a/*.py
  evaluation/task07a/PROTOCOL.md` rỗng).
- Sự cố tiến trình chết theo session: cả chuỗi `live07a_resume2.sh` lẫn `ollama.exe serve` được
  khởi chạy làm tiến trình con của session Claude Code; khi session kết thúc, cả hai bị dừng. Đây
  là lần thứ hai một run bị ngắt theo kiểu này (lần đầu V0 s42 ngày 2026-11-26).

## 2026-11-27 — Đính chính bối cảnh V1 s42 (kiểm từ trace)

- 0001 và 0002: truncation ở **lượt 1** (PlannerError `empty content`, thinking_chars 42 912 /
  44 044, `done_reason=length`, `eval_count=12288`).
- 0007: truncation ở **lượt 4** (lượt viết final), **không** phải lượt 1. Ba lượt trước hợp lệ
  (thinking 24 162 / 13 968 / 18 582 ký tự, `done_reason=stop`); lượt 4 PlannerError
  thinking_chars 42 582, `done_reason=length`.
- Tổng: 3/7 trace V1 s42 kết thúc do thinking dùng hết `num_predict=12288` (2 ở lượt 1, 1 ở lượt
  final). Các lượt lỗi không có `meta` (PlannerError raise trước khi gắn meta); thinking_chars chỉ
  còn trong chuỗi lỗi, raw thinking bị mất (limitation provenance, owner mục 2).
- 0008: CaseState home C đang ở rev 5 (initial rev 3), không có `sample_0008_C.json` → đúng như
  owner mô tả (INFRA_INTERRUPTED).

## 2026-11-27 — Việc A: kiểm tra V3 s42 / sample_0013

- So context lượt 1 của `V3_s42/sample_0013_C.json` với V0_s42, V0_s7, V2_s42, V2_s7_r2: sau khi
  chuẩn hóa ID theo run (CASE/EV/RUN/COL), timestamp, thư mục runtime băm, và `snapshot`
  (device/inode/mtime của bản staged), hai bản **giống hệt nhau**. Phần khác duy nhất là metadata
  snapshot của bản copy staged (mỗi `prepare` staging một bản mới). `system` giống hệt;
  `requested_decoding_schema` giống hệt (sau chuẩn hóa ID).
- Oracle **không tác động**: `EVALUATOR_ONLY/sample_0013_C_oracle.json` có `per_turn: []` vì imports
  chưa được commit ở lượt 1 và run kết thúc tại lượt 1.
- Lỗi: lượt 1 `TOOL_CALL`, `validation_error = EVIDENCE_NOT_VISIBLE`. Model trích
  `EV-cf435bc78a7d44d6b477d3f55607d3d` (31 hex), trong khi ID hiển thị là
  `EV-cf435bc78a7d44d6b477d3f556607d3d` (32 hex): **chép sai ID** (rơi một ký tự). v3.4 không cho
  repair TOOL_CALL → `VALIDATION_REPAIR_EXHAUSTED`.
- 0013 ở các run khác: không có validation error nào (V0 s42 lỗi hạ tầng ở lượt 3; V0 s7, V2 s7_r2,
  06B-J run_v1 FINISHED_FLAGGED; V2 s42 REQUEST_MORE_EVIDENCE).
- **Kết luận: lỗi do model (sao chép ID 32 hex), không do harness/oracle.** 0013 của V3 nằm trong
  mẫu số với M1 = M1b = 0; không loại, không rerun. Đây là đúng loại lỗi REPORT §2.3 đã nêu (gánh
  nặng chép ID 32 hex).

## 2026-11-27 — S7: metrics và các deviation đi kèm

- **metrics_v1.json** (`task07a-metrics-v1`, frozen, không sửa): chạy bằng CLI đã freeze
  `python -m evaluation.task07a.metrics --results <view> --baseline evaluation/task06b_j/results/confirmatory/run_v1 --out evaluation/task07a/results/metrics_v1.json`.
  `<view>` là thư mục trong scratchpad chứa **directory junction** tới 5 nhóm đầy đủ
  (V0_s42, V0_s7, V2_s42, V2_s7_r2, V3_s42). Lý do: `metrics.collect` bỏ case thiếu trace khỏi
  mẫu số, nên nếu đưa V1_s42 (7/20 trace) hoặc V2_s7 (0 trace) vào sẽ ra mẫu số thu nhỏ sai. Cả 5
  nhóm có `missing_runs = []`; run lỗi hạ tầng có trace nên vẫn nằm trong mẫu số.
  sha256 `1377558dc87520be…`.
- **Deviation (owner cho phép, mục B):** `evaluation/task07a/supplementary_v1.py` (mới, sau freeze,
  không thuộc HARNESS_FILES) → `results/supplementary_v1_metrics.json`
  (sha256 `faf12cf3c51cf634…`). Chỉ phân loại trạng thái
  mọi slot cohort (COMPLETED_FINAL / MODEL_INCOMPLETE / MODEL_OUTPUT_TRUNCATION / INFRA_OLLAMA_ERROR /
  INFRA_INTERRUPTED / NOT_RUN / NOT_RUN_BLOCKED) và tính chi tiết V1 s42 (status, truncation, action
  lượt 1, chi phí, thinking_chars, metric hành vi EXPLORATORY trên 7 trace). Có 3 unit test
  (`tests/test_supplementary.py`).
- **Deviation (owner yêu cầu, mục C):** `results/M4_developer_review_v1.json` (sha256
  `bae61fab5f66a6fe…`), builder
  `evaluation/task07a/m4_developer_review.py`. 119 câu ứng viên M4 được Claude Code gán nhãn thủ công
  theo 7 nhãn cố định, có lý do. **PROVISIONAL developer review**, không phải semantic grading hay
  human adjudication; nhãn `RULE_SCREEN_CANDIDATE` gốc và regex **không** đổi.
- Phát hiện về metric (không sửa hồi tố):
  - M7 `runs_with_done_reason_length` = 0 ở mọi nhóm nhưng **không** bắt được truncation của V1,
    vì lượt bị cắt không có `meta` (PlannerError). Truncation V1 được đếm ở supplementary.
  - M3b chỉ tính khi model chọn FINISH; run kết thúc bằng REQUEST_MORE hoặc lỗi hạ tầng tự động là
    "không stopped_with_gap". Mức giảm M3b của V2 một phần do điều này.
  - SCOPE_RE không có "current view" (câu #34 bị screen gọi UNSCOPED).

## 2026-11-27 — S8: báo cáo và regression

- `REPORT.md` viết xong (tiếng Việt), áp bảng quyết định PROTOCOL §5 đã freeze.
- Full regression: `743 passed, 0 failed, 4 skipped` (+81 subtests).
- Không có live run nào sau 05:37 ngày 2026-11-27. Không khởi động Ollama. Không push, không merge.
