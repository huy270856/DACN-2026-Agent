# MERGE_PLAN — integration/d0-modules-2026-11

Baseline: `origin/main` @ `5f6f2a9`. Không sửa/reset/force-push/merge trực tiếp main.
Mọi merge dùng `--no-ff` để giữ provenance và ranh giới đóng góp của từng thành viên.

## Thứ tự merge đã thực hiện

| # | Branch | Merge commit | Kết quả |
|---|---|---|---|
| 1 | `D2_D9` | `fc9d5b1` | Sạch (nền `orchestrator/` + EMBER contracts) |
| 2 | `feat/d3-d7-validation` | `850f547` | Sạch về text; `__init__.py` cần hợp nhất (commit `158be96`) |
| 3 | `feat/d5-d6-static-adapters` | `1427928` | Conflict `__init__.py` (add/add) → giữ union; sau đó bỏ `tests/__init__.py` (`a0fdbce`) |
| 4 | `feat/ember-dataset-preparation` | `7943536` | Sạch (biệt lập) |
| 5 | `feat/tuan-re-benchmark` | `b7d150c` | Sạch (biệt lập) |

Commit tích hợp bổ sung: `e0a2804` (adapters + fix D9), `8ec6cfe` (integration tests + mock adapter).

## Lệnh tái lập

```bash
git checkout -b integration/d0-modules-2026-11 origin/main
git merge --no-ff origin/D2_D9
git merge --no-ff origin/feat/d3-d7-validation      # + hợp nhất orchestrator/__init__.py
git merge --no-ff origin/feat/d5-d6-static-adapters # resolve __init__.py (--ours = union); rm tests/__init__.py
git merge --no-ff origin/feat/ember-dataset-preparation
git merge --no-ff origin/feat/tuan-re-benchmark
```

## Chiến lược giải quyết conflict

### `orchestrator/__init__.py` (3 phiên bản)
- D2_D9 export registry+case_bridge; d3-d7 rỗng; d5-d6 chỉ docstring.
- **Giải pháp**: `__init__.py` union **tường minh** export D2/D3/D7/D9 (các module thuần `jsonschema`, không phụ thuộc nền tảng). **KHÔNG** import D5/D6 ở cấp package vì chúng Windows-only (`from ctypes import wintypes` top-level) — để import qua submodule `orchestrator.executor` / `orchestrator.execution_control`. Đã kiểm tra: không có circular import (không module nào import gói `orchestrator`).

### Bộ EMBER contract + `d0/validate.py`
- 7 file blob IDENTICAL giữa hai branch → merge tự hợp, giữ 1 bản. Canonical contract `ember-output-v1`: `feature_version=2`, `feature_count=2381`, đúng 2381 số hữu hạn (`math.isfinite`). Giữ nguyên, không sửa (freeze).

### `tests/__init__.py` (conflict ẩn)
- d3-d7 thêm file rỗng này; kết hợp d5-d6 (sibling import `from d5_support import`) làm hỏng discovery. **Giải pháp**: bỏ file rỗng (không chứa logic, không test nào import `tests` như package). Lệnh chạy chuẩn: `python -m unittest discover -s tests -p "test_*.py"` từ repo root.

## Nguyên tắc
- Không squash/cherry-pick làm mất ownership. Không xóa code/logic thành viên. Không force-push. Không tự xóa branch sau merge.
- Sau mỗi merge chạy test module liên quan (xem TEST_REPORT).

## Rollback
- Branch `integration/d0-modules-2026-11` tách biệt; `main` không bị đụng.
- Hoàn tác 1 merge: `git revert -m 1 <merge_sha>` (giữ lịch sử), hoặc `git reset --hard <sha_trước_merge>` **chỉ trên branch integration** nếu chưa push.
- Head trước từng merge đã ghi trong log phiên (ví dụ trước merge 1 = `5f6f2a9`).
- Vì chưa push và chưa tạo PR, có thể xóa branch integration để quay lại trạng thái sạch mà không ảnh hưởng ai.
