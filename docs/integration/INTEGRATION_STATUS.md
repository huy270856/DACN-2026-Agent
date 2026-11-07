# INTEGRATION_STATUS — integration/d0-modules-2026-11

Phân loại: **IMPLEMENTED / MOCK ONLY / PARTIAL / MISSING / BLOCKED / NOT VERIFIED**.

## Module coverage

| Module | Owner | Trạng thái | Ghi chú |
|---|---|---|---|
| Node B — Context Collector | — | IMPLEMENTED | Có trong main, regression PASS |
| Node C — CaseState/CaseManager | — | IMPLEMENTED | +`expected_revision` dưới lock (backward-compat) |
| D1 — Orchestrator Core | Trưởng nhóm | **MISSING** | Chưa có file; glue tạm do integration/test đảm nhận |
| D2 — Tool Registry | Đạt | IMPLEMENTED | Versioned, no silent fallback. Lưu ý default version = thứ tự đăng ký (P3) |
| D3 — Input Validator | Tuấn | IMPLEMENTED | Validate-not-authorize; stale revision; target changed |
| D4 — Policy Engine | Trưởng nhóm | **MISSING** | Integration dùng MOCK policy (ALLOW/DENY) gắn nhãn |
| D5 — Tool Executor | Huy | PARTIAL | Read-only FILE subprocess Windows thật; chặn foreign-code/mutation; PROCESS chưa có |
| D6 — Execution Control | Huy | PARTIAL | Job Object, timeout, cancel, cap, cleanup — chạy thật. VMResetGate chỉ là interface |
| D7 — Result Validator | Tuấn | IMPLEMENTED | Envelope + artifact integrity + EMBER normalize; không chế verdict |
| D8 — Trust & Approval | Trưởng nhóm | **MOCK ONLY** | HMAC `sign_for_trusted_boundary` có, key do caller; test dùng MOCK key |
| D9 — Case Bridge | Đạt | IMPLEMENTED (đã vá) | revision dưới lock + 2-phase ledger + reconcile |
| D2→D5 binding | integration | IMPLEMENTED (mới) | `provider_install.py` |
| D5→D7 adapter | integration | IMPLEMENTED (mới, EMBER) | `execution_adapter.py` |
| EMBER v2 extraction | Huy | PARTIAL / BLOCKED | Code thật, chưa chạy (thiếu dataset + `ember`/`lief`) |
| LightGBM inference/train | Huy | **MISSING** | Không có code train/infer/checkpoint |
| Ghidra/REA adapter vào workflow | Tuấn | **MISSING** | Benchmark độc lập; "chưa chạy REA, chưa tích hợp D.0" |
| VM isolated dynamic analysis | — | MOCK ONLY | `VMResetGate` interface state |
| Durable artifact store | — | MISSING | D7 inject reader/writer; chưa có store thật |
| Windows process/DLL telemetry | — | NOT VERIFIED | PROCESS target chưa hỗ trợ ở D5 |
| Full E2E malware investigation | — | MISSING | Thiếu D1/D4/D8 thật |

## Luồng integration đã CHẠY THẬT
D2 → D3 → [MOCK D4/D8] → D5/D6 (subprocess Windows thật) → D5→D7 adapter → D7 → D9 → Node C.
9/9 integration test PASS (TEST_REPORT §Integration chain). Đây là chuỗi thật trên dữ liệu lành tính, KHÔNG phải mô phỏng trên giấy.

## Chỉ hoạt động bằng MOCK
- D4 policy, D8 approval/signing key (`MOCK_admission_policy`, `MOCK_TRUSTED_KEY`).
- EMBER provider = `ember_mock_adapter.py` (vector 0.0). KHÔNG phải EMBER/LightGBM thật.

## Vấn đề P0/P1/P2/P3 còn tồn tại

- **P1 — D1 Orchestrator Core & D4 Policy Engine MISSING**: luồng thật cần glue của D1 và policy của D4. Hiện do integration/test đảm nhận bằng MOCK. Blocker để chạy production.
- **P1 — D8 protected signer MISSING**: khóa HMAC hiện do caller; cần signer bảo vệ + quản lý khóa. Chưa được đảm bảo an toàn.
- **P1 — LightGBM MISSING + EMBER BLOCKED**: chưa có inference/train; EMBER chưa chạy trên dữ liệu thật (dataset BLOCKED, thiếu `ember`/`lief`). Mục tiêu giữ nguyên, chưa hoàn thành.
- **P2 — D9 atomicity**: đã giảm rủi ro (expected_revision dưới lock; 2-phase ledger + reconcile) nhưng ledger và CaseState vẫn là 2 thao tác filesystem riêng — recovery qua `reconcile_ledger`, KHÔNG phải một transaction nguyên tử. Auto-register + tool-result là 2 lần ghi (mỗi lần guarded); fail-safe, không mất dữ liệu.
- **P2 — D5/D6 Windows-only**: test D5/D6 chỉ chạy trên Windows; không chạy trên Linux.
- **P2 — Durable artifact store MISSING**: D7 dùng reader/writer inject; production cần store bảo vệ ACL/symlink/atomic.
- **P3 — D2 default version theo thứ tự đăng ký** (không semver): cần tài liệu hóa hoặc đổi.
- **P3 — PROCESS target** chưa hỗ trợ ở D5.

## Owners & priority (next sprint)
1. **Trưởng nhóm**: D1 core (admission atomic) + D4 policy engine + D8 protected signer. (P1)
2. **Huy**: cài `ember`/`lief`, chạy `prepare.py` trên dataset thật ở máy được phép; thiết kế LightGBM I/O contract + inference adapter. (P1)
3. **Tuấn**: nếu phạm vi cần, thiết kế adapter Ghidra/REA vào D.0 (hiện chỉ benchmark). (P2)
4. **Đạt**: cân nhắc gộp auto-register + tool-result thành một operation Node C để atomic thật; durable artifact store. (P2)

## Sẵn sàng tạo PR vào main?
**CHƯA nên merge vào main như một hệ thống hoàn chỉnh.** Nhánh integration ĐÃ:
- Hợp nhất 5 branch, giữ provenance, 265/265 test PASS (2 skip môi trường), chuỗi D2→…→Node C chạy thật.

Nhưng để bảo vệ đồ án là "hệ thống chạy được & giải thích được", cần nêu rõ D1/D4/D8 là MISSING/MOCK và EMBER/LightGBM chưa chạy thật. Khuyến nghị: tạo PR **có nhãn rõ** là "integration của D2/D3/D5-6/D7/D9 + glue, D1/D4/D8 còn MOCK/MISSING", kèm TEST_REPORT, chỉ merge sau khi trưởng nhóm duyệt và chấp nhận các giới hạn trên.
