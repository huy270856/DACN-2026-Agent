# TEST_REPORT — integration/d0-modules-2026-11

## Môi trường
- Platform: **Windows 11** (Windows-11-10.0.26300-SP0).
- Python: **3.12.10**.
- Dependencies có mặt: `jsonschema`, `referencing`, `numpy`, `psutil`.
- Dependencies **vắng mặt**: `ember`, `lief`, `lightgbm` → không chạy được EMBER matrix thật/LightGBM (xem §EMBER).
- Ngày chạy: 2026-11-07. Commit: `integration/d0-modules-2026-11` @ `8ec6cfe` (trước khi thêm docs).

## Lệnh đã chạy (thực tế)
```bash
python -m unittest discover -s tests -p "test_*.py"            # Suite 1
python -m unittest discover -s . -p "test_*.py"                # Suite 2 (Node B/C root)
python -m unittest discover -s research/ember_dataset -p "test_*.py"  # Suite 3
```
Lưu ý: chạy từ repo root (cwd đưa repo root lên `sys.path`; discover thêm `tests/` lên path cho sibling import của D5/D6). KHÔNG dùng `-t .` (sẽ đòi `tests` là package).

## Kết quả tổng hợp

| Suite | Ran | Pass | Fail | Skip |
|---|---|---|---|---|
| 1 — `tests/` (D2/D3/D5/D6/D7/D9 + contracts + integration) | 162 | 162 | 0 | 0 |
| 2 — root (Node B/C regression) | 96 | 96 | 0 | 2 |
| 3 — `research/ember_dataset` (synthetic) | 7 | 7 | 0 | 0 |
| **Tổng** | **265** | **265** | **0** | **2** |

### Chi tiết theo module (tests/)
| Module | Tests | Ghi chú |
|---|---|---|
| `test_d0_contracts` | 25 | Contract/schema + prompt-injection-as-data |
| `test_ember_contracts` | 4 | feature_version/count/hash/vector-length |
| `test_d2_registry` | ~20 | Versioned reg, no silent fallback, capability |
| `test_d3_input_validator` | ~24 | Validate-not-authorize, stale revision, target changed |
| `test_d7_result_validator` + `test_d7_ember_normalization` | ~47 | Receipt/result binding, artifact budget, EMBER normalize |
| `test_d5_executor` | 19 | **Windows thật**: locked handle, staging, reparse, pin |
| `test_d6_execution_control` | 14 | **Windows thật**: Job Object, timeout, cancel, artifact tamper |
| `test_d9_case_bridge` | 9 | Mapping, DENIED-chặn, stale revision, 2-phase ledger |
| `test_integration_chain` | 9 | Chuỗi đầy đủ (xem dưới) |

### Skip (2) — Suite 2
- `test_context_collector`: 1 skip (gated nền tảng/đặc quyền).
- `test_windows_advanced`: 1 skip (yêu cầu quyền tạo symlink/đặc quyền đặc biệt).
- Không skip nào che giấu lỗi; đây là test có điều kiện môi trường.

### Ghi chú output negative-test
Suite 2 in ra stderr các dòng như `Node C error: Protected operation…` và `--hash-timeout must be a finite positive number` — là **đầu ra mong đợi** của các test đường lỗi (CLI bị chặn / argparse exit). Suite vẫn báo `OK`.

## Integration chain (tests/test_integration_chain.py) — 9/9 PASS trên Windows
Chuỗi: **D2 → D3 → [MOCK D4/D8 admission] → D5/D6 (subprocess thật) → (D5→D7 adapter) → D7 → D9 → Node C**.

| Test | Kịch bản yêu cầu | Kết quả |
|---|---|---|
| `test_full_success_chain_D2_D3_D5_D7_D9_NodeC` | Luồng đầy đủ chạy thật | PASS |
| `test_provider_mismatch_rejected_at_D3` | Provider mismatch | PASS (code `PROVIDER_MISMATCH`) |
| `test_stale_revision_rejected_at_D3` | Stale revision (D3) | PASS (`CASE_REVISION_STALE`) |
| `test_target_changed_after_collection_rejected_at_D5` | Target đổi sau thu thập | PASS (`TARGET_CHANGED`) |
| `test_policy_denied_never_executes_and_not_recorded_as_success` | DENIED không chạy / không là SUCCESS | PASS (`POLICY_DENIED`) |
| `test_artifact_tampering_detected_by_D5_to_D7_adapter` | Artifact tampering | PASS (`ARTIFACT_INTEGRITY_FAILED`) |
| `test_replay_duplicate_run_rejected_by_node_c` | Replay / duplicate run | PASS (`Duplicate tool_run_id`) |
| `test_concurrent_writer_detected_by_D9_optimistic_lock` | Concurrent writer | PASS (`StaleRevisionError` dưới lock) |
| `test_audit_ledger_crash_recovery_reconcile` | Ledger failure/recovery | PASS (reconcile PENDING→RECONCILED_COMMITTED) |

Timeout/cancel/oversized-output đã được bao phủ ở `test_d6_execution_control` (chạy thật trên Windows).

## Nhãn MOCK rõ ràng
- `MOCK_admission_policy()` và `MOCK_TRUSTED_KEY` đại diện cho D4/D8 (CHƯA CÓ) — KHÔNG phải policy engine/signer thật.
- `tests/fixtures/ember_mock_adapter.py` phát vector 0.0 placeholder — KHÔNG phải EMBER thật, KHÔNG LightGBM, không thực thi target.

## EMBER / LightGBM — KHÔNG có bằng chứng chạy thật
- `research/ember_dataset/test_prepare.py`: 7 test trên **dữ liệu synthetic**.
- `prepare.py matrix()` gọi `ember.PEFeatureExtractor(feature_version=2)` **chưa chạy** (thiếu `ember`/`lief` và dataset). `REQUIREMENTS_STATUS.md` ghi download BLOCKED (proxy 403).
- Không có checkpoint/manifest/kết quả train. **Không tuyên bố** EMBER thật hay LightGBM đã chạy.

## Không chạy PE nghi vấn
Chỉ dùng file synthetic lành tính + mock adapter. Không file PE nào được thực thi trên host.
