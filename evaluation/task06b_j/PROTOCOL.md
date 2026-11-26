# TASK 06B-J — PROTOCOL (viết trước mọi lượt chấm/inference)

Trạng thái: **DRAFT dành cho owner review.** Phần thiết kế DEV calibration (§8) đã được thực
hiện; phần confirmatory (§5–§7, §9) **chưa chạy** vì gate chưa đạt (xem REPORT.md §5).

## 1. Câu hỏi nghiên cứu

Việc Agent tự chọn tool và tự đọc evidence có cải thiện tính đúng, độ cụ thể, mức liên quan,
kế hoạch kiểm chứng và giá trị điều tra hay không, **mà không** làm tăng claim không có căn
cứ hoặc kết luận không an toàn? Kết quả âm hoặc null đều hợp lệ.

H0 cho từng tiêu chí chung: không có khác biệt theo cặp giữa C và A, C và B. Không có giả
thuyết nào về "arm thắng" được đưa cho grader.

## 2. Ba arm

| Arm | Định nghĩa | Hiện thực |
|---|---|---|
| A — STATIC_ONLY | Cùng output LightGBM đã đóng băng và evidence ban đầu; báo cáo template tất định | Builder template của `repair_experiment.prepare` (`STATIC_TEMPLATE_06B_R`), không viết lại sau khi có kết quả |
| B — AGENT_NO_TOOL | Cùng evidence ban đầu và câu hỏi, Qwen thật, **không** có analyzer và không có evidence sau tool | `workflow_v34.run(..., tool_enabled=False)`; budget lặp `min(3, max_iterations)` |
| C — AGENT_TOOL_ENABLED | Như B, cộng analyzer qua Controller và retrieval có giới hạn | `workflow_v34.run(..., tool_enabled=True)`; tối đa 1 tool, 2 lần đọc × 16, 1 repair |

Budget hành động khác nhau giữa B và C là một phần của treatment và được báo cáo, không bị
"cân bằng" để xóa đi lợi thế mà thí nghiệm muốn đo. Latency, token, số lần gọi LLM và tool
được báo theo từng arm.

## 3. Ràng buộc công bằng theo cặp

Với mỗi mẫu: cùng PE, SHA-256, output detector, evidence ban đầu và câu hỏi cố định. Câu hỏi
cố định của 06B: *"Which concrete declared DLL/API imports support or limit network/process
capability hypotheses? What remains unknown?"*

- Mỗi arm chạy trên **bản clone riêng** của CaseState ban đầu, với artifact root riêng (như
  `repair_experiment.prepare`).
- B không bao giờ thấy evidence sau tool của C. A không được chỉnh sau khi có kết quả.
- Thứ tự arm xen kẽ theo chỉ số mẫu (B→C với mẫu chẵn, C→B với mẫu lẻ). Ghi lại cold start
  và tình trạng tải của Ollama.
- Model, config, digest, prompt hash, source hash, tool pin và threshold được ghi trong
  `freeze.json` **trước** inference.

## 4. Chống rò rỉ

- Nhãn ground truth chỉ nằm trong manifest `*_EVALUATOR_ONLY`.
  `_assert_no_ground_truth` tiếp tục được áp dụng cho prompt Agent.
- **Mới, bắt buộc cho confirmatory:** target được stage dưới tên trung tính
  (`T-<index>.exe` trong runtime root đã gitignore) **trước intake**, để `unknowns.path` không
  tiết lộ `System32\<tên tiện ích>`. Việc này chỉ thay đầu vào evaluation, không đổi semantics
  của Agent. Hiện chưa hiện thực, là precondition G6.
- Phía Judge/người chấm: package không chứa tên arm, version, trạng thái, flag của checker,
  nhãn hay mapping (`leakage_scan` bắt buộc PASS). Mapping chỉ được đọc **sau** `analysis.lock`.

## 5. Các khái niệm đánh giá được tách biệt

| Loại | Nguồn trong 06B-J | Không được coi là |
|---|---|---|
| Deterministic checking | `pipeline_metrics.py`, rule screen 06B | semantic judgment |
| LLM-as-Judge | `judge_adapter.py` (chỉ inference mới, có provenance đầy đủ) | ground truth hay human grading |
| Human assessment | Judgment file với `evaluator.kind = HUMAN` | ground truth tuyệt đối |
| Independent reference | Reference sheet (evidence đã commit), provenance của mẫu | nhận định của Agent |

Judge có thể độc lập với inference của Qwen, nhưng **không** phải nguồn sự thật độc lập. Kết
quả Judge luôn provisional cho đến khi được đối chiếu với người chấm.

## 6. Thiết kế Judge (khi được cho phép)

- Provider/model được cấu hình tường minh, không có fallback. Mỗi request và raw response được
  ghi nguyên văn (`raw_calls.jsonl`), có prompt SHA-256, timestamp, meta/usage và lỗi.
- Output phải theo schema chặt (`score_validation.py`). Run có item thiếu hoặc lỗi được đánh
  `INCOMPLETE_REJECTED` và không được aggregate. Không tự điền điểm hay lý do.
- Hai lượt blind với seed xáo trộn khác nhau (pass1/pass2) để kiểm tra self-consistency và
  bias vị trí. Self-consistency được ghi là `SELF_CONSISTENCY_NOT_CORRECTNESS`.
- Khi Judge và rule screen bất đồng (ví dụ self-corroboration), giữ cả hai và đánh dấu
  `DISAGREE_NEEDS_HUMAN_ADJUDICATION`.
- Không dùng API trả phí hay endpoint bên ngoài khi chưa có ủy quyền của owner. Không commit
  key. Qwen (cùng họ với Agent) **không** được dùng làm Judge.

## 7. Metrics (mọi ca đều nằm trong mẫu số)

- **Pipeline:** intake, static prediction, đề xuất tool, Controller/D4 allow/deny, D9 commit,
  evidence hiển thị, chọn retrieval, final được chấp nhận về cấu trúc, FINISHED_FLAGGED,
  incomplete/fallback, quyết định không gọi tool.
- **Grounding:** số claim theo verdict, attribution đúng, trích dẫn sai, tự chứng thực bằng
  prediction, assertion API/runtime không căn cứ, hiểu lầm coverage một phần, claim cần
  evidence Agent không thấy. Coverage diagnostic tất định (lexicon
  `task06b-j-relevance-lexicon-v1`) chỉ là heuristic relevance.
- **Utility:** R3–R9.
- **Cost:** latency mean/median, token, số lần gọi LLM, tool, retrieval, tải review, lỗi/fallback.
- Tách riêng: final hợp lệ về cấu trúc ≠ sạch theo rule screen ≠ được Judge xác nhận ≠ được
  người chấm xác nhận.
- Không báo cáo "tăng độ chính xác detector": nhãn LightGBM không đổi trong mọi arm.

## 8. DEV calibration (đã làm, không confirmatory)

Package `results/dev/calibration_package_v1` gồm 19 item từ các trace DEV đóng băng (3 SHA
tracert/findstr/fc):

- A: template.
- B (v3.3, incomplete).
- B (v3.1, có final).
- C (v3.1, tool có sẵn nhưng không gọi).
- C (v3.4 DEBUG).
- 4 probe tự dựng trên tracert v3.4: API bịa, khẳng định hành vi runtime, absence trên coverage
  một phần, score coi như xác suất.

Kỳ vọng và đáp án probe do developer viết, nằm trong `EVALUATOR_ONLY/calibration_key.json`,
gắn nhãn `DEVELOPER_EXPECTATION_NOT_GROUND_TRUTH`. Mục đích là kiểm tra độ nhạy của
rubric/Judge, không phải so sánh arm: contract và lượt intake khác nhau giữa các item.

## 9. Gate trước confirmatory (tất cả phải PASS)

| # | Điều kiện |
|---|---|
| G1 | Provenance mẫu đủ điều kiện được ghi (nguồn, chữ ký, arch, size, SHA) |
| G2 | SHA-disjoint **và** program-disjoint với mọi artifact 05C/05D/06A/06B |
| G3 | Rubric khóa (`rubric_sha256` ghi trong freeze) |
| G4 | Config Agent đóng băng; runner confirmatory 3 arm đã được review |
| G5 | Judge có sẵn và được phép, hoặc người chấm độc lập được xác nhận |
| G6 | Không rò rỉ: neutral staging, leakage scan PASS |
| G7 | Output bất biến (`write_new`, thư mục version mới) |
| G8 | Budget evaluation và ủy quyền rõ ràng của owner |

Quy tắc dừng: chỉ chạy confirmatory **một lần**. Không chạy lại mẫu fail. Không chỉnh prompt
hay rubric sau khi xem kết quả. Lỗi hạ tầng được ghi lại; chạy lại chỉ được phép dưới version
output mới, toàn bộ mẫu, kèm lý do ghi trước.

---

## 10. Bổ sung v1.1 — quyết định của owner (continuation)

Owner đã cho phép: runner 3 arm, neutral staging, Claude-as-Judge qua phiên Claude Code độc
lập, và commit local. Chưa cho phép: paid API, UI chấm R1–R9, confirmatory inference.

### 10.1 Runner (`runner.py`, `task06b-j-runner-v1`)

- Mỗi case: copy file sang `runtime/r<hash>/<alias>/targets/<alias>.exe`. SHA phải khớp trước
  và sau khi copy, và file nguồn được băm lại. Không sửa bytes, không thực thi.
- **Một** lần intake Node B và **một** lần chạy detector, trong home của C. B nhận bản clone
  byte-identical của CaseState trong home và artifact root riêng. A dùng cùng prediction đó.
- B và C dùng cùng `workflow_v34` cùng contract v3.4 và cùng `CFG` với 06B-R2 DEBUG.
  Khác biệt duy nhất: `tool_enabled`, cùng với budget lặp và tool/retrieval ghi trong
  `freeze.arm_differences`. A không gọi LLM.
- Câu hỏi được gắn ở mức harness bằng cách patch hằng `investigation_v3.context.GOAL` trong lúc
  chạy case đó. Source Agent không đổi; hash nằm trong `freeze.source_hashes`. Mọi turn được
  kiểm là mang đúng câu hỏi đã gán.
- `isolation_checks` cho B: không offer tool hoặc retrieval, không có event D1/D4/D5/D7/D9, 0
  tool và 0 read, CaseState và revision không đổi, chỉ thấy evidence ban đầu. Riêng C: mọi ID
  nhìn thấy đều thuộc CaseState của chính C.
- Leakage scan cho context ban đầu và cho **mọi turn** sau khi chạy (evaluator-only).
- Run thật cần freeze có Ollama `AVAILABLE`, digest khớp lúc chạy, và chuỗi `--authorized-by`.
  Output chỉ ghi một lần. Nếu crash, arm chưa ghi chỉ được chạy khi CaseState vẫn nguyên.

### 10.2 Câu hỏi khai báo trước (`questions.py`, `task06b-j-questions-v1`)

Q_NET, Q_FILE, Q_PROC (trả lời được bằng import); Q_RUNTIME_LIMIT (static không trả lời được,
hành vi đúng là nêu giới hạn); Q_NO_TOOL (trả lời được từ evidence ban đầu). Phân bổ xoay vòng
cân bằng trên thứ tự seeded, không dùng output model. Answerability (vị trí các entry liên
quan: trang đầu / cần retrieval / sau cap 64 / không có) được tính phía evaluator từ static
parse, chỉ dùng làm strata. Cả 3 arm của một case dùng cùng câu hỏi.

### 10.3 Judge: `INTERACTIVE_LLM_JUDGE_BLIND_BATCH`

Xem `JUDGE_RUNBOOK.md`. Track A = view `common`, Track B = view `investigation`. Kit được export
**ngoài repo**. Response được giữ nguyên văn kèm SHA. Metadata model/session không biết thì
ghi `UNKNOWN`. Bắt buộc `human_verified=false`, `automated_api_inference=false`. Import thiếu
hoặc sai → `INCOMPLETE_REJECTED`. Lock trước khi mở mapping.

Giới hạn độc lập:

- Judge (Claude) cùng họ model với developer đã viết probe và kỳ vọng.
- Phiên Judge về kỹ thuật vẫn có thể đọc ra ngoài kit nếu được cấp quyền. Owner phải từ chối.
- Judge không phải nguồn sự thật độc lập.

### 10.4 Gate (cập nhật)

Xem REPORT.md §5. Confirmatory chỉ được chạy một lần, sau khi owner duyệt.
