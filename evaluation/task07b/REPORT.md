# TASK 07B — Investigation v4 lát cắt 1: kết quả và phân tích

| Hạng mục | Giá trị |
|---|---|
| Loại đánh giá | `DEV_EVALUATION_FRESH_COHORT`. **Không** phải confirmatory của dự án (n = 20, chỉ PE benign). `confirmatory: NOT_RUN` |
| Track | `RAW_PE_E2E` (20 PE hệ thống có chữ ký Microsoft, staged copy; không thực thi PE) |
| Planner | `LOCAL_QWEN`: `qwen3.5:4b`, digest `d8b0f5e9…`, Ollama 0.40.16 headless (loopback) |
| Loại bằng chứng | **Metric tất định** (`task07b-metrics-v1`) từ trace và manifest evaluator-only. **Không** phải semantic grading, không Judge, không human grading. Phần M4 rà tay là *developer review* (provisional) |
| Protocol | `PROTOCOL.md`, freeze ở commit `dafc62aee5d0404878c77bc173ad5d34d29c34e5` **trước** mọi inference trên cohort mới; review độc lập PASS |
| Run | S8 do Owner chạy ngoài session (`run_s8.ps1`), 2026-11-27 11:17:36–12:05:26 (~48 phút), đủ **120/120** run |
| Artifact | `results/frozen/{BASE,V4_NOQ,V4}_s{42,7}/`, `results/frozen/metrics_v1.json`, `results/frozen/M4_developer_review_v1.json`, `EVALUATION_LOG.md` |
| Engineering completion | **PASS** (§8) |
| Research completion | **PARTIAL**: retrieval có chỉ mục có hiệu ứng rõ; dòng 1 của bảng quyết định **không đạt** vì absence claim không phạm vi tăng (§6) |

---

## 1. Tóm tắt

- **Tìm và trích dẫn evidence (M1b):** V4 đạt **7/8** ở cả hai seed, V4_NOQ 3/8, BASE (v3.4) **0/8**.
  - Tầng entry liên quan < 48 (trong tầm của v3.4): V4 3/3, BASE 0/3 ở cả hai seed. V4 **không** kém
    v3.4 ở trường hợp mà evidence nằm trong tầm của cả hai.
  - Tầng ≥ 48: V4 4/5, V4_NOQ 0–1/5, BASE 0/5.
- **Retrieval có chỉ mục có đóng góp riêng:** V4 vượt V4_NOQ ở M1b ở cả hai seed (7 so với 3, nhiễu
  = 0). Query trúng entry liên quan (M8) ở 7/8 case, thường ngay ở query đầu tiên hoặc thứ hai.
- **Tín hiệu xấu: absence claim không phạm vi tăng.** M4-UNSCOPED (rule screen, tính theo rate) của V4 là
  0.60 và 0.55, so với BASE 0.05 và 0.20. Mức tăng vượt nhiễu ở cả hai seed.
  - Developer review cùng chiều: V4 có 2/8 và 3/8 case RELEVANT_PRESENT chứa câu khẳng định "không có"
    sai so với bảng đầy đủ. BASE có 0/8, nhưng chỉ vì BASE không thấy gì và luôn viết câu có phạm vi.
  - Vì vậy dòng 1 ("lát cắt 1 có tác dụng") **không đạt**.
- **Quyết định gọi tool:** ở INITIAL_EVIDENCE_SUFFICIENT, V4 và V4_NOQ **không** gọi analyzer
  (4/4), còn BASE luôn gọi (0/4 đúng). Ở NOT_STATIC, cả 3 arm đều gọi analyzer 4/4. Cải thiện này đến
  từ contract và workflow v4 (V4 bằng V4_NOQ), không đến từ query.
- **Toàn vẹn và chi phí:** 0 truncation, 0 tràn context, 0 lỗi hạ tầng, 0 isolation fail.
  - Có 1 run không có final: BASE s42 / sample_0005, `VALIDATION_REPAIR_EXHAUSTED` (model trích một
    evidence ID không hiển thị ở lượt TOOL_CALL).
  - Median latency của V4 so với BASE là 1.15× và 1.32×.
  - Prompt lớn nhất của V4 là 3 815 token, so với 6 002 của BASE.

## 2. Thiết kế đã chạy

| Arm | Engine | Retrieval | Seed | Run | Final |
|---|---|---|---|---|---|
| BASE | v3.4 (= 07A V0) | `pe_imports_detail` 64 entry, ≤ 2 READ offset | 42 / 7 | 20 / 20 | 19 / 20 |
| V4_NOQ | `investigation-v4.0` | `pe_imports_table` đầy đủ, READ_TABLE theo offset (≤ 6) | 42 / 7 | 20 / 20 | 20 / 20 |
| V4 | `investigation-v4.0` | `pe_imports_table`, LIST_IMPORT_INDEX + QUERY_IMPORTS{DLL, SYMBOL_PREFIX} (≤ 6) | 42 / 7 | 20 / 20 | 20 / 20 |

- Cohort `cases_v2` (digest `f984cc7f…`):
  - 8 RELEVANT_PRESENT: 5 case ≥ 48 và 3 case < 48;
  - 4 RELEVANT_ABSENT;
  - 4 NOT_STATIC_ANSWERABLE;
  - 4 INITIAL_EVIDENCE_SUFFICIENT.
- Cấu hình đầy đủ xem `PROTOCOL.md` §2. Mọi run kiểm HEAD = commit freeze, tracked tree sạch,
  Ollama 0.40.16 và đúng digest (log `run_stdout.txt`).

## 3. Kết quả M1–M10 (`results/frozen/metrics_v1.json`)

Mẫu số đầy đủ. Run không có final được tính là không đạt cho M1b/M8/M9/M10.

| Metric | Mẫu số | BASE s42 | BASE s7 | V4_NOQ s42 | V4_NOQ s7 | V4 s42 | V4 s7 |
|---|---|---|---|---|---|---|---|
| M1 relevant_seen | RP | 0/8 | 0/8 | 3/8 | 3/8 | **7/8** | **7/8** |
| M1 tầng ≥ 48 | RP ≥ 48 | 0/5 | 0/5 | 0/5 | 1/5 | 4/5 | 4/5 |
| M1 tầng < 48 | RP < 48 | 0/3 | 0/3 | 3/3 | 2/3 | 3/3 | 3/3 |
| **M1b relevant_cited** | RP | 0/8 | 0/8 | 3/8 | 3/8 | **7/8** | **7/8** |
| M1b tầng ≥ 48 | RP ≥ 48 | 0/5 | 0/5 | 0/5 | 1/5 | 4/5 | 4/5 |
| M1b tầng < 48 | RP < 48 | 0/3 | 0/3 | 3/3 | 2/3 | 3/3 | 3/3 |
| M8 query_hit | RP | — | — | — | — | 7/8 | 7/8 |
| M8_read_hit_reference (tham khảo) | RP | — | — | 3/8 | 3/8 | — | — |
| **M2_correct_no_tool** | IS + NS | 0/8 | 0/8 | 4/8 | 4/8 | 4/8 | 4/8 |
| M2_correct_no_tool (chỉ IS) | IS | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| M2_unnecessary_tool (mô tả) | IS + NS | 8/8 | 8/8 | 4/8 | 4/8 | 4/8 | 4/8 |
| M2_broken_runs | IS + NS | 1 | 0 | 0 | 0 | 0 | 0 |
| **M4-UNSCOPED (rate)** | có final | 1/19 (0.05) | 4/20 (0.20) | 7/20 (0.35) | 8/20 (0.40) | **12/20 (0.60)** | **11/20 (0.55)** |
| M4-SCOPED (rate) | có final | 12/19 (0.63) | 14/20 (0.70) | 14/20 (0.70) | 12/20 (0.60) | 7/20 (0.35) | 11/20 (0.55) |
| M5 structural self-corroboration | có final | 17/19 | 18/20 | 0/20* | 0/20* | 0/20* | 0/20* |
| M9 answer_status_fit | NS + IS | — | — | 6/8 | 8/8 | 7/8 | 7/8 |
| M10 final hợp lệ | 20 | 19/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |

\* M5 bằng 0 **do cấu trúc**: detector không có handle trong `investigation-v4.0`. Đây **không** phải
cải thiện hành vi.

**M6 và M7**

| | BASE s42 | BASE s7 | V4_NOQ s42 | V4_NOQ s7 | V4 s42 | V4 s7 |
|---|---|---|---|---|---|---|
| Lần gọi LLM | 63 | 64 | 111 | 119 | 121 | 129 |
| Latency median (s) | 21.39 | 20.89 | 21.01 | 24.58 | 24.62 | 27.56 |
| Median ratio so với BASE | — | — | 0.98 | 1.18 | **1.15** | **1.32** |
| Prompt token / output token | 275 819 / 30 498 | 278 990 / 31 868 | 249 498 / 29 312 | 271 460 / 31 626 | 224 516 / 35 337 | 249 850 / 37 743 |
| Prompt lớn nhất (token) | 6 002 | 5 410 | 5 146 | 5 146 | 3 177 | 3 815 |
| Truncation / overflow / hạ tầng / missing / isolation fail | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| Run có validation error | 1 | 0 | 0 | 0 | 0 | 0 |

**Theo lớp.** Ở RELEVANT_ABSENT, cả 3 arm đều gọi analyzer 4/4 (hợp lý, vì cần xem bảng mới trả lời
được). Ở NOT_STATIC, cả 3 arm gọi analyzer 4/4. Ở INITIAL_SUFFICIENT, BASE gọi 4/4, V4 và V4_NOQ gọi
0/4.

**Chi tiết hành vi đáng chú ý:**

- BASE ở tầng < 48: với 0003 và 0006 (entry liên quan ở index 38 và 32), BASE **không đọc trang nào**
  rồi FINISH. Với 0008 (index 46), BASE chỉ đọc @16 rồi FINISH. Đây là lặp lại knowing–doing gap của 07A.
- V4 bỏ sót 1 case mỗi seed: s42 / 0004 (osk, FILE, `DeleteFileW` ở index 65) và s7 / 0009
  (smartscreen, PROCESS, `OpenProcess` ở index 250).
- Query trúng đầu tiên ở query thứ 1–4 (s42: 1, 3, 1, 2, 1, 4, 1; s7: 1, 4, 2, 1, 1, 1, 1).
- V4_NOQ đọc theo offset tuần tự: thấy được tầng < 48 (5/6 qua 2 seed), gần như không tới tầng ≥ 48
  (1/10).

## 4. Nhiễu (PROTOCOL §4)

Nhiễu = |Δ| giữa seed 42 và seed 7 trong cùng một arm.

| Metric | BASE | V4_NOQ | V4 |
|---|---|---|---|
| M1 / M1b | 0 / 0 | 0 / 0 | 0 / 0 |
| M1b ≥ 48 / < 48 | 0 / 0 | 1 / 1 | 0 / 0 |
| M8 (V4) / M8_read_ref (NOQ) | — | 0 | 0 |
| M2_correct_no_tool | 0 | 0 | 0 |
| M9 | — | 2 | 0 |
| M10 | 1 | 0 | 0 |
| M4-UNSCOPED rate | 0.147 | 0.05 | 0.05 |
| M4-SCOPED rate | 0.068 | 0.10 | 0.20 |

## 5. M4: rule screen và developer review

Nguồn: `results/frozen/M4_developer_review_v1.json` (174 câu ứng viên, nguyên văn, có nhãn và lý do).

- **PROVISIONAL.** Claude Code tự rà. Đây không phải semantic grading hay human adjudication, và cần
  Owner xem.
- Áp như nhau cho 3 arm. Rule screen gốc và `metrics.py` **không** đổi.
- Dữ kiện dùng để gán nhãn:
  - bảng đầy đủ của các case RELEVANT_ABSENT và NOT_STATIC **không** có entry thuộc họ được hỏi;
  - một số API cụ thể đã được kiểm trên bảng đầy đủ, ví dụ osk không có CreateFile/ReadFile/WriteFile
    nhưng có `DeleteFileW`; verifier.exe có `StartServiceW` và `ControlService`; smartscreen có
    `OpenProcess`; fveprompt có `ShellExecuteW`.

| Nhóm | FALSE_ABSENCE (case / RP có final) | RUNTIME_OVERCLAIM (case / có final) | TRUE_ABSENCE câu (RA/NS) | Câu giới hạn |
|---|---|---|---|---|
| BASE s42 | 0/8 | 0/19 | 9 | 2 |
| BASE s7 | 0/8 | 0/20 | 9 | 4 |
| V4_NOQ s42 | 2/8 (0006, 0009) | 1/20 | 14 | 8 |
| V4_NOQ s7 | 1/8 (0006) | 1/20 | 13 | 5 |
| V4 s42 | 2/8 (0004, 0015) | 1/20 | 14 | 7 |
| V4 s7 | 3/8 (0006, 0009, 0015) | 1/20 | 19 | 8 |

- Phần lớn câu UNSCOPED của V4 nằm ở RELEVANT_ABSENT/NOT_STATIC. Ở đó câu "không có X" **đúng** so với
  bảng đầy đủ (TRUE_ABSENCE). Một phần lớn mức tăng của M4-UNSCOPED vì vậy là do V4 **đã xem** bảng và
  nói thẳng, còn BASE chỉ nói "không thấy trong 16 entry đầu".
- Tuy vậy, lỗi thật vẫn có và cùng chiều. V4 viết câu khẳng định vắng mặt **ở mức cả họ hoặc
  capability**, sai so với bảng đầy đủ: "lacks explicit imports for ... opening processes" khi có
  `OpenProcess`; "no direct file-system access APIs" khi có `DeleteFileW`; "does not show ... starting,
  stopping services" khi có `StartServiceW` và `ControlService`; "no capability to create processes"
  khi có `ShellExecuteW`. Nhiều câu là suy rộng từ một query hẹp (ví dụ query `CreateProcess` 0 match
  thành "không có process control").
- Verifier v4 đã flag `absence_beyond_coverage_suspected` ở 13–14/20 run mỗi arm v4 (chỉ số mô tả,
  không vào quyết định).

## 6. Áp bảng quyết định (PROTOCOL §5, đã freeze)

| Dòng | Điều kiện | Quan sát (s42 / s7; nhiễu) | Kết luận |
|---|---|---|---|
| 1. Lát cắt 1 có tác dụng | V4 > BASE ở M1b **và** M8; M4-UNSCOPED rate không tăng; M10 ≥ BASE; median ratio ≤ 3 cả hai seed | M1b 7 so với 0, 7 so với 0 (nhiễu 0) ✓. M8 7/8 so với read-hit V4_NOQ 3/8 và BASE 0 ✓. **M4-UNSCOPED 0.60 so với 0.05, 0.55 so với 0.20; Δ 0.55 và 0.35 > max nhiễu 0.147 → tăng ✗**. M10 20 ≥ 19, 20 ≥ 20 ✓. Ratio 1.15 / 1.32 ✓ | **Không đạt** (vì M4-UNSCOPED) |
| 2. V4 kém BASE ở M1b tầng < 48 | — | 3/3 so với 0/3 ở cả hai seed | Không áp dụng (V4 **không** kém) |
| 3. V4 > V4_NOQ ở M1b | cả hai seed, vượt nhiễu | 7 so với 3, 7 so với 3; nhiễu max(0, 0) = 0 | **Đạt**: retrieval có chỉ mục đóng góp riêng |
| 4. V4 ≈ V4_NOQ, cả hai > BASE | — | V4 > V4_NOQ | Không áp dụng |
| 5. M8 cao nhưng M1b thấp | — | M8 7/8, M1b 7/8 | Không áp dụng |
| 6. M8 thấp | — | 7/8 | Không áp dụng |
| 7. M2 hoặc M9 không cải thiện | áp quy tắc nhiễu | M2_correct_no_tool: V4 4 so với BASE 0 ở cả hai seed (nhiễu 0) → **cải thiện so với BASE**; V4 4 so với V4_NOQ 4 → không đổi; M9 V4 7/7 so với V4_NOQ 6/8 (nhiễu 2) → không phân biệt được. Ở NOT_STATIC mọi arm gọi tool 4/4 | **Áp dụng một phần**: cải thiện đến từ contract/workflow, không từ query; NOT_STATIC vẫn gọi tool theo phản xạ |
| 8. Truncation > 2 hoặc tràn context | — | 0 ở mọi arm | Không áp dụng |

**Kết luận và hướng tiếp theo** (theo bảng, Owner quyết định):

1. **Giữ query service** (dòng 3) và mở rộng sang facet khác ở 07C.
2. **Không** tuyên bố "lát cắt 1 có tác dụng" (dòng 1 không đạt). Nút thắt mới, đo được, là
   **absence claim vượt coverage**: model đã có bảng đầy đủ và index nhưng vẫn khái quát từ query hẹp
   thành "không có cả họ".
3. Dòng 7: thêm **investigation state** hoặc một bước kế hoạch rõ ràng ở 07C để giảm việc gọi tool ở
   NOT_STATIC.

Đề xuất ngoài bảng (để Owner cân nhắc, không tự mở rộng phạm vi): vì verifier đã phát hiện absence
vượt coverage ở 13–14/20 run, 07C có thể đưa phản hồi coverage tất định vào lượt final ("query X phủ
họ nào; DLL Y đã xem n/m") hoặc yêu cầu absence claim phải trích query hoặc DLL đã phủ. Việc này cần
đo lại, không tự thêm vào 07B.

## 7. Sự cố, deviation và limitation

**Sự cố S8:** không có. Không lỗi hạ tầng, không dừng giữa chừng, không truncation. Log
`results/frozen/run_stdout.txt` được PowerShell ghi bằng UTF-16 LE (hành vi của `Tee-Object` trong
PS 5.1). Nội dung đầy đủ, nhưng công cụ đọc phải decode UTF-16.

**Deviation sau freeze:**

1. `m4_developer_review.py` và `M4_developer_review_v1.json` là review rà tay theo PROTOCOL §3
   ("developer review, ghi riêng"). File này **không** thay đổi metric. `metrics.py` giữ nguyên
   `task07b-metrics-v1` (đã kiểm: không có diff so với `dafc62a`).

**Limitation:**

- n nhỏ: 8 RP, trong đó 3 case < 48 và 5 case ≥ 48. Chỉ có PE benign hệ thống. Các con số là mô tả,
  không phải kiểm định thống kê, và không khái quát hóa được.
- Phân lớp và `relevant_entries` dựa trên lexicon v2 (khớp tên chính xác). Lexicon coi `ShellExecute`
  là PROCESS và `TerminateProcess` là process control.
- M1/M1b đo việc thấy và trích entry liên quan, **không** đo câu trả lời có đúng về ngữ nghĩa hay không.
  Semantic grading: NOT_RUN.
- M4 là rule screen. Developer review là của chính Claude Code, chỉ là provisional.
- V4 so với BASE là so sánh **gói tổng**: contract, workflow, analyzer, num_ctx, num_predict và số lượt
  đều khác.
- Bảng ordinal resolve phụ thuộc build Windows của host (26300.9974).
- `relevant_entries` của cohort mới chưa được người kiểm.

## 8. Completion

### Engineering completion: **PASS**

- Analyzer `static.pe_imports_table`, query service, projector, contract `investigation-v4.0`,
  verifier, ánh xạ recommendation D2 và workflow v4 đều có test (unit, integration qua D1–D9 thật,
  MOCK_LLM).
- G3 PASS.
- Protocol commit trước run (`dafc62a`), review độc lập PASS.
- Mọi artifact ghi write-once. Đủ 120/120 run.
- Guard freeze hoạt động: HEAD, tree, digest và version đều được kiểm.
- Full regression: xem §9.

### Research completion: **PARTIAL**

| Yêu cầu (PLAN §7) | Trạng thái |
|---|---|
| Đủ 120 run | **PASS** (120/120; 1 run không có final, tính vào mẫu số) |
| Bảng M1–M10 theo arm, seed và lớp | **PASS** (§3) |
| Phân tích nhiễu | **PASS** (§4) |
| Áp bảng §4.5 và chọn hướng 07C | **PASS** (§6): giữ query service; dòng 1 không đạt vì absence claim; 07C ưu tiên state/kế hoạch và grounding của absence claim |
| Kết luận "lát cắt 1 có tác dụng" | **NOT MET** (M4-UNSCOPED tăng vượt nhiễu) |
| Semantic grading / human review | **NOT_RUN** / M4 developer review **PENDING** Owner xem |

## 9. Regression

Full regression (`python -m pytest -q`, Python 3.12.10 hệ thống, không có `.venv`), chạy ngay trước
commit kết quả:

| Thời điểm | Passed | Failed | Skipped |
|---|---|---|---|
| Trước 07B (sau 07A) | 743 | 0 | 4 |
| Pre-run freeze (`dafc62a`) | 856 | 0 | 4 |
| S9 (commit này) | **856** | **0** | **4** |

Cả ba lần đều có thêm 81–83 subtest pass. 4 test skipped không được tính là pass.
