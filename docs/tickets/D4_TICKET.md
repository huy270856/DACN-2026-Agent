## D4-01 — Policy Engine | Owner: 1

**Mục tiêu:** hiện thực Policy Engine theo D.0, có thể kiểm thử độc lập bằng fixtures.

**Tài liệu bắt buộc:** `docs/d0/01_ARCHITECTURE_AND_ADRS.md`, `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md`, `docs/d0/05_TEAM_HANDOFF.md`, `docs/d0/06_SECURITY_AND_TEST_PLAN.md`; D9 thêm `docs/d0/03_BC_V12_BRIDGE.md`.

**Dependency:** D.0; D2/D3 interfaces. Dependency chưa xong phải mock, không được sửa code người khác để lách.

**Input:** validated ToolCall, ToolSpec effects, workflow state, budget, authenticated grants.

**Output:** PolicyDecision allow/deny/approval_required + effective limits.

**Files ownership (đề xuất):** `orchestrator/policy.py`; tests `tests/test_d4_policy.py`.

**Acceptance tests:** deny host malware execution; VM-only foreign-code; fail closed; no Agent self-approval; limits clamped.

**Out of scope:** Không tự thay đổi `d0/schemas/`, không tự cấp approval, không chạy malware trên host. Các hành vi ngoài phạm vi phải tạo ticket mới.

**PR evidence:** test log + fixture I/O + schema version + security notes + reviewer sign-off.
