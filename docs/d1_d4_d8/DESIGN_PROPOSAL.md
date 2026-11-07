# ĐỀ XUẤT THIẾT KẾ — D1 Orchestrator Core / D4 Policy Engine / D8 Trust & Approval

Branch: `feat/d1-d4-d8-core-policy-trust` (từ `main` @ `fe1160b`).
Trạng thái: **ĐỀ XUẤT — chờ trưởng nhóm duyệt trước khi implement.**

Nguyên tắc nền: D1 **điều phối** các module thật D2/D3/D5/D6/D7/D9, KHÔNG viết lại chúng.
Deny-by-default, fail-closed, không tin đầu vào từ Agent/ToolCall/provider output.
Bám sát `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md` (lifecycle), `06_SECURITY_AND_TEST_PLAN.md`
(threat→control→test) và ADR-001..007.

---

## 1. Interface đã audit (dùng lại nguyên trạng, không sửa)

| Module | Entry point dùng cho D1 |
|---|---|
| D2 | `ToolRegistry.get_tool / resolve_provider / is_provider_available / validate_target_support` |
| D3 | `input_validator.validate_tool_call(call, spec, case, input_schemas=None, provider_available=True)` |
| D2→D5 | `provider_install.ProviderInstallation.pinned_adapter_for(spec)` (Phase B) |
| D5/D6 | `executor.ToolExecutor(root).execute(call, spec, policy, case_snapshot, adapter, cancel=) -> ExecutionOutput` |
| D5→D7 | `execution_adapter.ember_result_from_execution(output, call, spec, artifact_root=)` (Phase B) |
| D7 | `result_validator.validate_tool_result / normalize_ember_result` |
| D9 | `case_bridge.CaseBridge.commit_tool_result(..., trusted_key=, expected_revision=) / record_denied_action / reconcile_ledger` |
| Node C | `case_manager.apply_update(..., authorization, trusted_keys, expected_revision)`, `sign_for_trusted_boundary(case_id, op, payload, key)`, `_verify_proof` (nonce replay, cửa sổ 300s, role tool/approval), op `response` (cần `human_approved`+`approver`) |

Phát hiện khóa chốt: **ký HMAC + chống replay (nonce) đã có sẵn trong Node C**. D8 sẽ *sở hữu khóa* và *xác thực analyst*, rồi gọi `sign_for_trusted_boundary` — không phát minh lại crypto.

---

## 2. D4 — Policy Engine (`orchestrator/policy_engine.py`)

Thuần, tất định, không IO/không execution. **Deny-by-default**, mọi quyết định có `reason_code` rõ.

```python
class PolicyConfig:        # chỉ từ config tin cậy của operator, KHÔNG từ Agent/ToolCall
    tool_allowlist         # {(tool_id, tool_version, provider_id)} được phép
    capability_risk        # capability -> LOW/MEDIUM/HIGH
    approval_required_caps # capability cần REQUIRE_APPROVAL (vd dynamic)
    budget_caps            # trần timeout/output/artifact/concurrency
    policy_version: str

class PolicyEngine:
    def evaluate(self, call, spec, case_snapshot) -> dict  # trả policy_decision (schema-valid)
```

Luật đánh giá (theo thứ tự, fail-closed):
1. Input không schema-valid / thiếu ràng buộc → **DENY** `schema_invalid`.
2. `(tool_id, tool_version, provider_id)` không trong allowlist → **DENY** `tool_not_allowlisted` (ADR-005).
3. `effects.executes_foreign_code | mutates_target | writes_filesystem = true` → cần VM. VM chưa có trong scope → **DENY** `vm_required_unavailable` (ADR-003: không chạy foreign code trên host).
4. `effects.requires_human_approval = true` (vd dynamic/response-adjacent) → **REQUIRE_APPROVAL** `analyst_approval_required`.
5. FILE read-only nhưng `target_ref.identity_strength == UNAVAILABLE` hoặc thiếu `verified_digest` → **DENY** `target_identity_insufficient` (doc 02: success cần verified binding).
6. `call.budget` vượt `budget_caps` (trần cứng) → **DENY** `budget_exceeds_policy`; nếu trong trần, đặt `effective_limits = min(spec.limits, budget_caps, call.budget)`.
7. Tool read-only static thỏa mọi điều kiện → **ALLOW** + `effective_limits`.

Chống self-approval (yêu cầu bắt buộc): quyết định **chỉ** sinh từ `PolicyConfig` + sự kiện quan sát; mọi cờ "đã duyệt"/budget/allowlist do ToolCall mang theo bị **bỏ qua**. Agent không thể chế ToolCall để bypass D4 vì D4 không đọc quyền từ call — chỉ đọc *yêu cầu* và đối chiếu config.
Bất kỳ exception/bất định → **DENY** `internal_error` (fail-closed).

---

## 3. D8 — Trust & Approval (`orchestrator/trust.py`)

Hai trách nhiệm, tách **MOCK** khỏi **TRUSTED** rõ ràng.

### 3a. Attestation signer (ký ToolResult commit)
```python
class KeyProvider(Protocol):        # custody khóa
    def tool_key(self) -> bytes     # >=32 byte, KHÔNG lộ ra Agent/tool/D1-public
class TrustedSigner:                # production-path
    def __init__(self, key_provider: KeyProvider)
    def sign_tool_result(self, case_id, payload) -> dict   # -> case_manager.sign_for_trusted_boundary('tool-result')
    def trusted_keys(self) -> dict  # {'tool': key} để D9/Node C verify
class MockSigner(TrustedSigner):    # CHỈ cho test khói; nhãn MOCK, khóa sinh tại chỗ
```
Custody khóa trên Windows (đề xuất, có giới hạn): `DpapiKeyProvider` dùng DPAPI (CryptProtectData, phạm vi user) lưu khóa ở file ACL-restricted; nạp bởi service tin cậy, không truyền cho adapter (D6 `clean_environment` đã loại env secret). **Giới hạn ghi rõ**: không có HSM/TPM-sealing trong scope → không tuyên bố "production-grade"; mức bảo vệ = DPAPI-user + ACL. Nếu DPAPI không khả dụng, fail-closed và yêu cầu cấu hình khóa tường minh.

### 3b. Approval service (response actions — ADR-004)
Dành cho hành động QUARANTINE_FILE/TERMINATE_PROCESS/ISOLATE_HOST/RESTORE_FILE (op `response` của Node C), **không** phải tool call.
```python
class AnalystAuthenticator(Protocol):
    def authenticate(self) -> str          # trả local OS account; TRUSTED impl dùng OS, test dùng double
class ApprovalService:
    def create_request(self, case_snapshot, action) -> dict         # approval_request PENDING (bind revision/target/effects/risk/expires_at)
    def record_decision(self, request, decision, authenticator) -> dict  # approval_event (APPROVED/REJECTED)
    def authorize_response(self, case_id, response_payload, event) -> dict # -> sign_for_trusted_boundary('response'), approver == authenticated_subject
```
Ràng buộc bắt buộc:
- `approval_event` gắn `action_digest_sha256`, `case_revision`, `expires_at`, `authenticated_subject`, nonce dùng-một-lần.
- **Không** nhận `human_approved`/approver/khóa/token do Agent cấp (ADR-004). `approver` = chủ thể D8 tự xác thực.
- Replay (nonce đã dùng) → reject; quá hạn (`expires_at` hoặc cửa sổ 300s của `_verify_proof`) → `APPROVAL_EXPIRED`; xác thực thất bại → `AUTHENTICATION_FAILED`.
- Response execution **re-check** revision + target trước khi tác động (ADR-004) — D1 thực thi.

---

## 4. D1 — Orchestrator Core (`orchestrator/core.py` + `orchestrator/workflow.py`)

Compose module thật theo lifecycle doc 02. **Không** reimplement D2–D9.

```python
class Orchestrator:
    def __init__(self, registry, policy, signer, installation, executor_factory,
                 bridge, run_ledger_path, approval_service=None, result_adapters=None)
    def run_tool_call(self, call, case_path, *, cancel=None) -> RunRecord
```

State machine (per `02_CONTRACTS_AND_LIFECYCLE.md`):
```
PROPOSED → VALIDATED → POLICY_EVALUATED
   │DENY → record_denied_action (D9) → REJECTED
   │REQUIRE_APPROVAL → WAITING_APPROVAL → [D8 approval, recheck] → ALLOW/REJECTED
   │ALLOW
   ▼
ADMITTED → TARGET_REVALIDATED → RUNNING
   → VALIDATE (D7) → SIGN (D8) → COMMIT (D9, expected_revision) → Node C
```
Thành phần:
- **Idempotency**: durable run-ledger JSONL (của D1). `call_id` + canonical-payload-digest: cùng payload đã terminal → trả kết quả cũ (không chạy lại); khác payload → `IDEMPOTENCY_CONFLICT`. Không blind-retry tool có foreign-code/mutate (ADR/doc 02).
- **Concurrency**: serialize theo case qua `case_manager.locked_case` tại admission/commit; run dài KHÔNG giữ lock — commit dùng `expected_revision` (compare-and-swap của Phase B). Stale → **replan** (đọc lại snapshot, re-evaluate), không ghi đè case mới hơn.
- **Cancellation/timeout**: truyền `threading.Event` xuống D5/D6; map TIMEOUT/CANCELLED đúng; cleanup incomplete → quarantine (đã có ở D5).
- **Fail-closed**: mọi lỗi/bất định → REJECTED/FAILED, không execute.
- **Durable audit**: mỗi lần chạy ghi RunRecord (run_id, call_id, decision_id, outcome, revision, timestamps).

`orchestrator/workflow.py` — `WorkflowEngine` tất định (ADR-001, tách khỏi LLM) phát `workflow_decision`:
```
INTAKE→REPUTATION → KNOWN+fresh/consistent→ASSESSMENT ; UNKNOWN/UNAVAILABLE/CONFLICT→STATIC
STATIC→ASSESSMENT (đủ & policy cho phép) | DYNAMIC (cần thêm & VM sẵn sàng) | HUMAN_REVIEW (VM thiếu)
ASSESSMENT→RESPONSE→POLICY→AUTHENTICATED_APPROVAL→EXECUTE→VERIFY→CLOSED
```
Không suy ra benign từ thiếu bằng chứng; `UNKNOWN` ≠ benign; VM thiếu → HUMAN_REVIEW/fixtures `REPLAYED`, không chạy host.

---

## 5. Trust boundary (tóm tắt)

| Thành phần | Tin cậy? | Ghi chú |
|---|---|---|
| Sample bytes, stdout, log, model output, tool description | **UNTRUSTED** | Chỉ dữ liệu, không bao giờ là lệnh |
| PolicyConfig, allowlist, budget caps | TRUSTED (operator) | Không từ Agent/ToolCall |
| Signing key (D8) | TRUSTED, cô lập | DPAPI+ACL; không lộ cho Agent/tool; giới hạn: không HSM |
| Analyst identity | TRUSTED (OS auth) | Agent không cấp được; `human_approved` từ Agent bị từ chối |
| D1 admission/commit | TRUSTED control plane | revision-aware, fail-closed |
| D5 execution | host read-only FILE đã verify | foreign-code/mutate → VM-only (chưa có) → DENY |

---

## 6. Kế hoạch test (benign only, không chạy malware trên host)

E2E thật: **Node B/C → D1 → D2 → D3 → D4 → D8 → D5/D6 → D7 → D9 → Node C** với mock analyzer lành tính (`ember_mock_adapter.py`).

Negative/adversarial (gộp doc 06 + yêu cầu trưởng nhóm):
valid static · invalid request · unknown tool · disabled provider · stale revision ·
target identity changed · DENIED-never-executed · approval required · unauthorized approval ·
expired/replayed approval · provider mismatch · forged receipt · artifact tampering ·
timeout/cancel · concurrent execution · duplicate ToolCall (idempotency) · crash/restart recovery ·
audit consistency · self-approval attempt bị chặn · Agent-forged policy/approval bị bỏ qua.

**Tách MOCK/TRUSTED**: bộ e2e "trusted" dùng **D4 PolicyEngine thật + D8 TrustedSigner + ApprovalService thật** (khóa sinh tại chỗ qua KeyProvider, không hardcode); chỉ `AnalystAuthenticator` và analyzer là test-double lành tính, ghi nhãn rõ. Không còn MOCK D4/D8 trong luồng "trusted".

Tất cả test cũ (265) phải vẫn PASS.

---

## 7. Giới hạn sẽ ghi rõ (không tuyên bố hoàn thành)
- D8 key custody = DPAPI+ACL, **không phải HSM/production-grade**.
- `AnalystAuthenticator` thật phụ thuộc môi trường OS; test dùng double.
- VM dynamic analysis vẫn **chưa có** → tool foreign-code bị DENY (fail-closed), không chạy host.
- LLM planning, EMBER/LightGBM thật, RE integration **ngoài phạm vi** branch này → không tuyên bố AI Agent/malware detector hoàn chỉnh.

---

## 8. Files dự kiến tạo (không sửa code Huy/Tuấn/Đạt)
- `orchestrator/policy_engine.py` (D4) + `tests/test_d4_policy_engine.py`
- `orchestrator/trust.py` (D8) + `tests/test_d8_trust_approval.py`
- `orchestrator/core.py`, `orchestrator/workflow.py` (D1) + `tests/test_d1_orchestrator.py`
- `tests/test_e2e_full_chain.py` (trusted, không mock D4/D8)
- `docs/d1_d4_d8/*` (thiết kế + giới hạn)
- `orchestrator/__init__.py`: thêm export D1/D4/D8 (giữ D5/D6 submodule như cũ)

**Chờ anh duyệt mục 2–6 (đặc biệt: luật D4, custody khóa D8, phạm vi REQUIRE_APPROVAL, có triển khai WorkflowEngine trong branch này không) trước khi tôi implement.**
