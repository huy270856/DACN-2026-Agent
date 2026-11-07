# CONTRACT_COMPATIBILITY — integration/d0-modules-2026-11

Dựa trên implementation Python thật (không chỉ README). Trạng thái SAU khi thêm
adapter tích hợp (`orchestrator/provider_install.py`, `orchestrator/execution_adapter.py`)
và fix D9.

## Ma trận Producer → Consumer

| Producer → Consumer | Dữ liệu | Tương thích | Adapter / ghi chú |
|---|---|---|---|
| Node B → Node C | Context/TargetRef (`bc_contracts.target_ref_from_context`) | ✅ | Có sẵn trong main |
| Node C → D3 | Case snapshot `{case_id, revision:int, target_ref}` | ✅ | D1 phải cấp snapshot; đã dùng trong integration test |
| D2 → D3 | ToolSpec + `provider_available:bool` | ✅ | D1 bơm `registry.get_tool()` + `is_provider_available()` vào `validate_tool_call` |
| D2 → D5 | ToolSpec provider → `PinnedAdapter` | ✅ (ĐÃ VÁ) | **`provider_install.ProviderInstallation.pinned_adapter_for(spec)`** dựng PinnedAdapter từ config tin cậy (command+SHA-256 pins). KHÔNG lấy từ ToolCall/Agent |
| D3 → D4 | Validated ToolCall | ⚠️ MOCK | **D4 CHƯA CÓ**. Integration dùng `MOCK_admission_policy()` gắn nhãn MOCK |
| D4/D8 → D5 | `policy_decision` (ALLOW) + PinnedAdapter | ⚠️ MOCK policy | D5 thực thi đúng khi policy ALLOW bound-to-call; policy hiện là MOCK |
| D5/D6 → D7 | `ExecutionOutput(receipt, raw_artifacts, error, …)` | ✅ (ĐÃ VÁ) | `receipt` khớp schema `execution_receipt`. **`execution_adapter.ember_result_from_execution()`** đọc stdout.bin (verify SHA-256) → parse payload → `normalize_ember_result`; map error UPPER→lowercase wire |
| D7/D8 → D9 | ToolResult + `receipt_sha256` | ✅ / ⚠️ | D9 verify `digest(receipt)==receipt_sha256` (hash binding). Chữ ký HMAC qua `trusted_key` — **D8 chưa có**, dùng `MOCK_TRUSTED_KEY` |
| D9 → Node C | `apply_update('tool-result', payload, authorization, trusted_keys)` | ✅ | Khớp `_append_tool`; PARTIAL→DEGRADED, TIMEOUT/CANCELLED→FAILED, DENIED bị chặn |
| Node C → D1 | CaseState | ⚠️ | **D1 CHƯA CÓ** (orchestrator core) |

## Chi tiết các cạnh đã vá (Phase B)

### D2 → D5 (provider installation binding)
- File: `orchestrator/provider_install.py`.
- `PinnedAdapter(command, pins)` được dựng **chỉ** từ config operator (`install()`/`from_config()`): command tuyệt đối `.exe`, mọi file mang mã phải pin SHA-256, `command[0]` phải được pin. `pinned_adapter_for(spec)` chỉ *tra cứu* theo provider identity của ToolSpec (ADR-005, không silent fallback). Không nhận đầu vào từ ToolCall/Agent/payload.
- Ranh giới: đây là lớp cài đặt do backend/D1 sở hữu, không phải logic của D2 hay D5.

### D5 → D7 (execution output → ToolResult)
- File: `orchestrator/execution_adapter.py`.
- `make_artifact_reader(root)`: resolve `relative_path` dưới artifact root, chặn path escape, verify size + SHA-256 trước khi trả bytes.
- `ember_result_from_execution(output, call, spec, artifact_root=…)`: SUCCESS/PARTIAL → đọc `stdout.bin` (integrity-check) → `json.loads` (payload untrusted) → `normalize_ember_result`. FAILED/TIMEOUT/CANCELLED → payload=None, mang error đã map.
- `wire_error()`: executor phát code UPPER_SNAKE (`PROVIDER_FAILED`, `TIMEOUT`…); schema `tool_result.error.code` yêu cầu `^[a-z]…`. Lower-case hóa (lossless, cùng token). `status` = `receipt.outcome` (cùng enum 6 giá trị) nên khớp trực tiếp.
- Payload luôn giữ `trust_level=UNTRUSTED_CONTENT`; không chế verdict/probability.
- **Giới hạn**: chỉ EMBER (`static.ember_features`) có normalizer D7 cụ thể. Tool khác cần normalizer riêng theo cùng khuôn; **không** tạo generic builder giả.

## Ranh giới bảo mật (security boundaries)
- **Pins & command**: chỉ từ trusted config, không từ ToolCall/Agent/provider output.
- **Provider output = untrusted data**: đọc, verify hash, parse; không bao giờ coi là lệnh (prompt-injection giữ nguyên là dữ liệu — có test ở `test_d0_contracts`).
- **HMAC ≠ attestation an toàn tuyệt đối**: `digest(receipt)` là binding bằng SHA-256; HMAC `sign_for_trusted_boundary` chỉ an toàn khi khóa được bảo vệ — đó là nhiệm vụ D8 (CHƯA CÓ). Trong test là MOCK.
- **Không chạy file nghi vấn trên host**: D5 chặn `executes_foreign_code/mutates_target/writes_filesystem/requires_human_approval`; chỉ đọc read-only FILE đã verify digest; PROCESS target chưa hỗ trợ.
- **Revision/atomicity**: `apply_update(expected_revision=…)` kiểm tra dưới lock; D9 2 pha ledger + reconcile (xem INTEGRATION_STATUS §D9).

## Tests chứng minh từng cạnh
Xem `tests/test_integration_chain.py` và TEST_REPORT.md.
