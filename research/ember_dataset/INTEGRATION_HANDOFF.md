# Huy — thử nối EMBER v2 thật vào D1–D9

Ngày thử: 10/11/2026 (Asia/Saigon). Nhánh local `feat/ember-lightgbm-integration` tạo từ `origin/main` @ `6c148ece`, rồi cherry-pick hai commit dataset/train đã kiểm chứng. Không sửa D1–D9 hay JSON Schema; chưa push/merge.

## Đường chạy đã kiểm chứng

`Node B file intake → Node C CaseState → D1/D2/D3/D4 → D5/D6 staged read-only PE → ember_v2_provider.py (official extractor v2) → D7 ember-output-v1 validation → D8 TEST key → D9 commit → Node C feature evidence → score_case_evidence.py → LightGBM sidecar JSON`.

`ember_v2_provider.py` thay vector zero giả lập bằng **2.381 giá trị float32 hữu hạn trích xuất từ PE thật**. D5 pin executable Python nghiên cứu và script adapter, kiểm TargetRef/SHA-256 từ file nguồn, stage rồi khóa file. D7 kiểm schema, 2.381 số hữu hạn và SHA-256 so với target đã revalidate. D9 ghi observation `static.ember_features` và giữ liên kết `tool_run_id`/`evidence_id`. Sidecar đọc đúng evidence đã commit, kiểm lại target hash, phiên bản feature, model hash rồi chấm điểm. Sidecar không ghi `ToolResult` dự đoán, không đổi `assessment` trong CaseState.

| Target | D1–D9 | Evidence | Score LightGBM | Ngưỡng | Nhãn model |
|---|---|---|---:|---:|---:|
| `C:\Windows\System32\notepad.exe` | `COMMITTED/SUCCESS`, revision 3 | `EV-80162052e01a443ba8c2fca7912199b2` | 0,0071204 | 0,8521730 | 0 |
| `C:\Windows\System32\kernel32.dll` | `COMMITTED/SUCCESS`, revision 3 | `EV-b258442c23144a1d94e0702222dff453` | 0,0003003 | 0,8521730 | 0 |
| Repo `test.txt` (văn bản) | `COMMITTED/FAILED`, `provider_failed` | Không có feature evidence | Không chạy scorer | — | — |

Hai file Windows có Authenticode `Valid`, signer Microsoft Windows. Hash target trong payload, CaseState và phép `Get-FileHash` độc lập khớp nhau. Score từ CaseState bằng **chính xác** score của `infer_pe.py` độc lập trên từng file. Với `test.txt`, stderr ghi `ValueError: Staged target lacks PE DOS magic`; case có 0 feature evidence từ run lỗi và `assessment=null`. Sidecar từ chối chấm run lỗi (`Expected one successful committed tool run`). Case Notepad cũng giữ `assessment=null` sau khi chấm score.

Bằng chứng nhỏ: [Notepad chain](results/integration_2026_11_10/notepad-chain.json), [Notepad score](results/integration_2026_11_10/notepad-score.json), [kernel32 chain](results/integration_2026_11_10/kernel32-chain.json), [kernel32 score](results/integration_2026_11_10/kernel32-score.json), [text failure](results/integration_2026_11_10/text-chain.json) và [kiểm tra liên kết](results/integration_2026_11_10/checks.json). Toàn bộ context, case, receipt, raw stdout/stderr, audit ledger và sidecar JSON của các lượt chạy nằm tại `D:\datasets\ember2018-integration-runs\{notepad,kernel32,text}-2026-11-10-v1`. Model ở `D:\datasets\ember2018-model-runs\2026-11-10-v2`, SHA-256 `b5f5fd69e06c59d44407c1a87c3af4403f2b274ee308127852c99f18e29abf4f`.

## Lệnh chạy lại

Chạy từ root worktree trên Windows. Mỗi `--home` phải là **đường dẫn mới**, không chọn thư mục kết quả mới nhất. Đọc `case_state_path` và `run_id` từ đúng `integration_report.json` trả về:

```powershell
$appPy = 'C:\Users\Admin\Đồ án chuyên ngành\Bản trên git\.venv\Scripts\python.exe'
$researchPy = 'D:\datasets\envs\ember-v2\Scripts\python.exe'
& $appPy research/ember_dataset/integration_probe.py --file C:\Windows\System32\notepad.exe --home D:\datasets\ember2018-integration-runs\NEW-RUN --research-python $researchPy
$probe = Get-Content -LiteralPath 'D:\datasets\ember2018-integration-runs\NEW-RUN\integration_report.json' -Raw | ConvertFrom-Json
& $researchPy research/ember_dataset/score_case_evidence.py --case $probe.case_state_path --run-id $probe.run_id --model-dir D:\datasets\ember2018-model-runs\2026-11-10-v2
```

Regression sau tích hợp: D1 trusted full-chain **6 pass**, D7 EMBER normalization **23 pass**, integration chain **9 pass**, research dataset/train **20 pass**. Các lượt real PE ở trên là kiểm thử ngoài suite giả lập; không thực thi PE, không tải malware.

## Chưa phải tích hợp sản phẩm hoàn chỉnh

- Contract `ember-output-v1` hiện là **feature extraction only** và cấm gắn prediction/verdict vào payload. LightGBM chỉ chấm trong sidecar nghiên cứu; `dacn smoke` và Agent backend vẫn đăng ký adapter MOCK. Muốn Agent/CaseState dùng dự đoán thật phải được nhóm chốt ToolSpec, output schema, model/version/threshold, nguồn gốc score và quy tắc chuyển score thành evidence/assessment. Chưa tự sửa contract.
- Lượt thử dùng `InMemoryKeyProvider` là TEST key; không chứng minh key custody hoặc cách ly production. D5 chỉ pin interpreter và script adapter; các thư viện import như `ember`, LIEF, NumPy chưa được D5 pin toàn bộ theo dependency closure. Cần xử lý trước khi coi provider là trusted deployment.
- `score_case_evidence.py` kiểm cấu trúc/hash/nguồn của evidence nhưng đọc CaseState trong local workspace, không tự xác thực chữ ký/ACL của file CaseState. Đây là sidecar nghiên cứu, không phải cổng quyết định an toàn.
- LIEF 0.10.1 khác 0.9.0 gốc; payload giữ cảnh báo. Hai PE lành tính không đo accuracy hay robustness ngoài phân phối EMBER2018. Model score không phải xác suất đã calibration; nhãn model không chứng minh file an toàn.
