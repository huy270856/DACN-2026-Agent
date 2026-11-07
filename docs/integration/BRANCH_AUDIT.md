# BRANCH_AUDIT — Phase A/B

Branch tích hợp: `integration/d0-modules-2026-11` (tạo từ `origin/main` @ `5f6f2a9`).
Ngày: 2026-11-07. Snapshot SHA đã fetch lại và **khớp chính xác** bảng snapshot 07/11.

## 1. Trạng thái từng branch

| Branch | HEAD | Ahead/Behind vs main | Phân loại | Quyết định |
|---|---|---|---|---|
| `D2_D9` | `0a3b4e7` | 1 / 0 | Có code mới | **MERGED** |
| `feat/d3-d7-validation` | `e71ef34` | 1 / 0 | Có code mới | **MERGED** |
| `feat/d5-d6-static-adapters` | `5c5db2d` | 1 / 0 | Có code mới | **MERGED** |
| `feat/ember-dataset-preparation` | `5e192ff` | 2 / 0 | Có code mới (biệt lập) | **MERGED** |
| `feat/tuan-re-benchmark` | `cf66d86` | 3 / 0 | Có code mới (biệt lập) | **MERGED** |
| `dev/node-bc-v1.1` | `ea97f2b` | 0 / 6 | Ancestor của main | **SKIP** |
| `docs/d0-team-handoff` | `c9d8079` | 0 / 3 | Đã merge (PR #4) | **SKIP** |
| `feat/d0-rea-contracts` | `62ca18d` | 0 / 4 | Ancestor của main | **SKIP** |
| `feat/node-bc-v1.2` | `9359b01` | 1 / 5 | Diverged, superseded | **SKIP** |

### Vì sao SKIP `feat/node-bc-v1.2`
Merge-base = `131ae2c` (đã là ancestor của main). So với merge-base, commit độc nhất `9359b01` **chỉ thêm `tests/__init__.py` rỗng**; toàn bộ nội dung v1.2 đã nằm trong main. So với main, branch này **thiếu 2.368 dòng** (D.0 contracts/schemas/docs/tickets thêm vào main sau đó). Không có nội dung độc nhất cần thiết → không merge để tránh kéo lùi main.

## 2. File độc nhất theo branch đã merge

- **D2_D9**: `orchestrator/registry.py` (303), `orchestrator/case_bridge.py` (427), `orchestrator/__init__.py`, `tests/test_d2_registry.py`, `tests/test_d9_case_bridge.py`, `tests/test_ember_contracts.py`, + bộ EMBER contract, `d0/validate.py` (+4), `.gitignore` (M).
- **feat/d3-d7-validation**: `orchestrator/input_validator.py` (109), `orchestrator/result_validator.py` (239), `orchestrator/README.md`, `tests/test_d3_input_validator.py`, `tests/test_d7_result_validator.py`, `tests/test_d7_ember_normalization.py`, `tests/__init__.py`, + bộ EMBER contract (trùng D2_D9).
- **feat/d5-d6-static-adapters**: `orchestrator/executor.py` (311), `orchestrator/execution_control.py` (291), `docs/D5_D6_IMPLEMENTATION.md`, `tests/d5_support.py`, `tests/fixtures/d5_safe_adapter.py`, `tests/test_d5_executor.py`, `tests/test_d6_execution_control.py`.
- **feat/ember-dataset-preparation**: `research/ember_dataset/{README.md,prepare.py,test_prepare.py,results/*}` (biệt lập, không đụng D1–D9).
- **feat/tuan-re-benchmark**: `benchmarks/re/*` (scripts, src `.c`, JSON evidence; biệt lập). **Không** commit binary `.exe` (build/ gitignore); **không** dùng Git LFS filter.

## 3. Overlap & trùng blob (Phase A đã xác minh)

`D2_D9` và `feat/d3-d7-validation` cùng thêm 8 file. Blob SHA:

| File | Kết quả |
|---|---|
| `README_EMBER_PATCH.md` | IDENTICAL |
| `d0/fixtures/ember-input-v1.json` | IDENTICAL |
| `d0/fixtures/ember-output-v1.json` | IDENTICAL |
| `d0/schemas/ember-input-v1.schema.json` | IDENTICAL |
| `d0/schemas/ember-output-v1.schema.json` | IDENTICAL |
| `d0/validate.py` | IDENTICAL (+4 dòng `math.isfinite` cho ember-output) |
| `tests/test_ember_contracts.py` | IDENTICAL |
| `orchestrator/__init__.py` | **KHÁC** (3 branch khác nhau) |

→ 7/8 tự hợp sạch; chỉ `orchestrator/__init__.py` cần hợp nhất tay (xem MERGE_PLAN).

## 4. Conflict ẩn (git không báo textual) đã phát hiện ở Phase B

- `tests/__init__.py` (d3-d7 thêm) biến `tests` thành package → phá sibling import `from d5_support import` của test D5/D6. Đã xử lý bằng cách bỏ file rỗng (xem MERGE_PLAN §Conflict).

## 5. PR

PR #1/#2/#4 merged; PR #3 closed-không-merged; PR #5 (RE benchmark) còn open → nội dung đã đưa vào integration branch qua merge `feat/tuan-re-benchmark`.
