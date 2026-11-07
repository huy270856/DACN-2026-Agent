# D1/D4/D8 — IMPLEMENTATION STATUS & LIMITATIONS

Branch: `feat/d1-d4-d8-core-policy-trust` (từ `main` @ `fe1160b`).
Không sửa/làm mất code của Huy (D5/D6), Tuấn (D3/D7), Đạt (D2/D9) — chỉ thêm file mới
và mở rộng `orchestrator/__init__.py` (exports).

## Module đã triển khai

| Module | File | Trạng thái | API chính |
|---|---|---|---|
| D4 Policy Engine | `orchestrator/policy_engine.py` | **IMPLEMENTED** | `PolicyEngine(PolicyConfig).evaluate(call, spec, snapshot) -> policy_decision` |
| D8 Attestation signer | `orchestrator/trust.py` | **IMPLEMENTED** | `TrustedSigner(KeyProvider).tool_key()/sign_tool_result()` |
| D8 Key custody | `orchestrator/trust.py` | **IMPLEMENTED (có giới hạn)** | `DpapiKeyProvider` (DPAPI+ACL), `InMemoryKeyProvider` |
| D8 Approval service | `orchestrator/trust.py` | **IMPLEMENTED** | `ApprovalService.create_request/record_decision/authorize_response` |
| D1 Orchestrator Core | `orchestrator/core.py` | **IMPLEMENTED** | `Orchestrator.run_tool_call(call, case_path) -> RunRecord` |
| D1 Workflow routing | `orchestrator/workflow.py` | **IMPLEMENTED** | `WorkflowEngine.decide(...) -> workflow_decision` |

D1 **compose** module thật D2/D3/D4/D8/D5/D6/D7/D9 — không reimplement.

## Lifecycle D1 (đúng docs/d0/02)
`PROPOSED → VALIDATED(D2+D3) → POLICY_EVALUATED(D4) → {DENY→note+REJECTED | REQUIRE_APPROVAL→WAITING_APPROVAL | ALLOW} → ADMITTED(D2→D5 binding) → RUNNING(D5/D6) → VALIDATE(D7) → SIGN(D8) → COMMIT(D9 revision-aware) → Node C.`
- **Idempotency**: run-ledger JSONL theo `call_id`+digest(call); replay cùng payload → trả kết quả cũ (không chạy lại); khác payload → `IdempotencyConflict`.
- **Concurrency**: COMMIT dùng `expected_revision` (compare-and-swap dưới lock của D9). Stale → `CASE_REVISION_STALE`, caller replan, không ghi đè.
- **Fail-closed**: mọi lỗi/bất định → REJECTED/FAILED, không execute.
- **Durable audit**: mọi run terminal ghi vào run-ledger; D9 ledger 2 pha riêng.

## Trust boundary (thực thi)
- Sample/stdout/log/model output/tool description = **UNTRUSTED** (không bao giờ là lệnh).
- PolicyConfig/allowlist/budget caps = TRUSTED, chỉ từ operator; **không đọc quyền từ ToolCall** → Agent không self-approve/bypass D4 được.
- Signing key do D8 custody; chỉ trusted control-plane (D1) lấy `tool_key()` để truyền D9; **không lộ cho Agent/tool/adapter** (D6 `clean_environment` loại env secret).
- Analyst identity do D8 xác thực (OS), **không** nhận `human_approved`/approver/token từ Agent (ADR-004).
- Foreign-code/mutate tool → VM-only; VM chưa có → **DENY** (fail-closed, không chạy host).

## Test coverage (Windows 11, Python 3.12.10)
46 test mới, tất cả PASS; toàn repo **311 PASS / 2 skip / 0 fail**.

| Suite | Tests | Bao phủ |
|---|---|---|
| `test_d4_policy_engine` | 12 | ALLOW, DENY (allowlist/VM/target/budget/schema), REQUIRE_APPROVAL, fail-closed, chống self-approve |
| `test_d8_trust_approval` | 11 | signer thật, DPAPI roundtrip, request/event schema, subject từ authenticator, commit response thật, forged digest, rejected, expired, revision-changed |
| `test_d1_orchestrator` | 8 | full ALLOW execute+commit, tool-unknown, policy-deny+NOTE, stale, require-approval, disabled-provider, idempotent replay, idempotency-conflict |
| `test_workflow` | 9 | static-first, UNKNOWN≠benign, known-fresh→assessment, dynamic+VM, VM-unavailable→human, conflict |
| `test_e2e_full_chain` | 6 | **trusted chain không mock D4/D8**, response-approval xác thực, replay proof, restart recovery (idempotency bền), forged receipt, concurrent stale |

Danh sách adversarial yêu cầu đều có: invalid request · unknown tool · disabled provider · stale revision · target changed (D5) · DENIED-never-executed · approval required · unauthorized approval · expired/replayed approval · provider mismatch · forged receipt · artifact tampering (integration) · timeout/cancel (D6) · concurrent · duplicate/idempotency · crash/restart recovery · audit consistency · self-approval chặn.

## MOCK vs TRUSTED (DoD)
- Luồng e2e "trusted" dùng **D4 PolicyEngine thật + D8 TrustedSigner thật (khóa thật từ InMemoryKeyProvider) + ApprovalService thật**. `test_trusted_full_chain_uses_no_mock_d4_d8` assert signer KHÔNG phải mock.
- Test-double còn lại chỉ là: analyzer lành tính (`ember_mock_adapter.py`) và `StaticAuthenticator` (thay cho đăng nhập OS tương tác). `MockSigner` tồn tại nhưng **không** dùng trong luồng trusted.

## GIỚI HẠN (liệt kê rõ, không tuyên bố hoàn thành)
1. **D8 key custody = DPAPI(user)+ACL**, KHÔNG phải HSM/TPM-sealed → không production-grade. Process cùng user có thể unprotect. ACL set best-effort qua `icacls`.
2. **Analyst authentication**: `LocalOsAuthenticator` khẳng định danh tính process-owner, **không** re-verify credential/MFA. Gate production cần đăng nhập tương tác thật trong service tin cậy.
3. **Tool-call REQUIRE_APPROVAL**: D.0 không có schema wire cho approval của *tool call* (approval_request/event chỉ cho response action). D1 fail-closed → `WAITING_APPROVAL`, không execute; cần bước analyst out-of-band.
4. **VM dynamic analysis CHƯA CÓ** → tool foreign-code bị DENY; không chạy malware trên host.
5. **Ngoài phạm vi branch này**: LLM planning, EMBER extraction thật, LightGBM inference, RE integration. **Không** tuyên bố AI Agent hoặc malware detector hoàn chỉnh.
6. D1 core + provider_install + D5/D6 là **Windows-only** (submodule, không export cấp package).
7. D1→D9 truyền raw key để D9 tự ký (API hiện tại của D9 nhận `trusted_key`); D8 vẫn là nơi custody. Nếu muốn D9 không thấy raw key, cần đổi API D9 (ngoài phạm vi, không sửa code Đạt).
