# DACN Unified Application — Test Report

- Platform: **Windows 11** (Windows-11-10.0.26300). Python **3.12.10**.
- Branch: `feat/unified-application-entrypoint`.
- Lệnh: chạy từ repo root.

## Tổng hợp — **346 PASS / 2 SKIP / 0 FAIL**

| Suite | Lệnh | Kết quả |
|---|---|---|
| `tests/` (D1–D9 + orchestrator + integration) | `python -m unittest discover -s tests -p "test_*.py"` | 210 PASS |
| root (Node B/C + D1/D4/D8 root + **dacn**) | `python -m unittest discover -s . -p "test_*.py"` | 129 PASS, 2 SKIP |
| `research/ember_dataset` | `python -m unittest discover -s research/ember_dataset -p "test_*.py"` | 7 PASS |

2 SKIP = test đặc quyền symlink / exclusive-lock (môi trường), không che lỗi.

## `test_dacn.py` — 20 test (mới)

| Nhóm | Test | Bao phủ yêu cầu |
|---|---|---|
| intake | `test_intake_file_pe_creates_case` | File intake thành công, format PE, SHA-256=đúng digest (read-only) |
| intake | `test_intake_pid_creates_process_case` | PID intake |
| intake | `test_intake_non_pe_is_unknown` | non-PE → UNKNOWN |
| intake | `test_intake_malformed_pe` | PE malformed |
| intake | `test_intake_missing_file_does_not_crash` | File không tồn tại (collection FAILED, không crash) |
| intake | `test_intake_file_changed_during_collection` | File đổi lúc đọc → SHA-256 withheld, format UNAVAILABLE |
| intake | `test_duplicate_intake_creates_distinct_cases` | Duplicate intake → case khác nhau |
| intake | `test_append_same_target_updates_case` | Node C revision handling (append cùng target) |
| intake | `test_target_mismatch_rejected` | Target mismatch bị từ chối |
| inspect | `test_inspect_reloads_persisted_state` | CaseState persistence/reload, evidence/format/SHA-256/TargetRef, provenance |
| inspect | `test_inspect_invalid_case_id` | Invalid case id |
| inspect | `test_inspect_case_not_found` | Case không tồn tại |
| config | `test_config_isolated_roots` | Storage path validation |
| CLI | `test_cli_intake_and_inspect` | CLI intake thành công |
| CLI | `test_cli_pid_must_be_positive` | Argument validation |
| CLI | `test_cli_backing_file_requires_pid` | Argument validation |
| CLI | `test_cli_inspect_requires_case_id` | Argument validation |
| CLI | `test_cli_missing_file_returns_nonzero` | Exit code |
| smoke (Win) | `test_smoke_runs_full_d1_d9_chain` | Smoke D1–D9 thật, D7 validated + D9 committed |
| smoke (Win) | `test_deny_policy_does_not_execute_tool` | DENY không chạy tool |

## CLI thực tế đã chạy (Windows PowerShell tương đương)

```
python -m dacn --home <H> intake --file <H>\hello.exe
  -> case_id=CASE-..., collection_status=SUCCESS, format=PE, identity_strength=STRONG,
     sha256=ee0964f1...  (bằng đúng SHA-256 của file)
python -m dacn --home <H> inspect --case-id CASE-...
  -> lifecycle=READY_FOR_INVESTIGATION, format=PE, evidence=7, unknowns=1
python -m dacn --home <H> smoke
  -> supported=True, phase=COMMITTED, outcome=SUCCESS, d7_validated_and_d9_committed=True
```

## Luồng B → C → D đã kiểm thử
- **Node B → Node C**: file/PID intake thật → CaseState bền trên disk, evidence +
  provenance đúng, SHA-256 & TargetRef kiểm tra lại được qua `inspect`.
- **Node D**: smoke lắp D1–D9 thật, chạy benign mock analyzer → **D7 kiểm tra +
  D9 commit vào Node C** (có evidence `static.ember_features`); DENY → không execute.

## Giới hạn (không tuyên bố hoàn thành)
- Mock analyzer lành tính; **không** chứng minh EMBER/LightGBM/Ghidra/REA thật.
- `smoke`/Node D chỉ Windows; nền tảng khác báo unsupported rõ ràng.
- D8 dùng TEST key (`InMemoryKeyProvider`); không phải production key store.
- Không chạy target executable trong bất kỳ test nào.
