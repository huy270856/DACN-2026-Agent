## D1-01 — Orchestrator Core | Owner: 1

**Mục tiêu:** hiện thực Orchestrator Core theo D.0, có thể kiểm thử độc lập bằng fixtures.

**Tài liệu bắt buộc:** `docs/d0/01_ARCHITECTURE_AND_ADRS.md`, `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md`, `docs/d0/05_TEAM_HANDOFF.md`, `docs/d0/06_SECURITY_AND_TEST_PLAN.md`; D9 thêm `docs/d0/03_BC_V12_BRIDGE.md`.

**Dependency:** D.0; D2/D3/D4/D5/D6/D7/D8/D9 mocks. Dependency chưa xong phải mock, không được sửa code người khác để lách.

**Input:** ToolCall, registry lookup, validator result, PolicyDecision, trusted admission.

**Output:** run state machine, run_id, execution receipt, D9 commit or typed failure.

**Files ownership (đề xuất):** `orchestrator/core.py`; tests `tests/test_d1_core.py`.

**Acceptance tests:** no run after DENY; duplicate call_id idempotent; crash recovery records UNKNOWN/FAILED not success; mock full cycle.

**Out of scope:** Không tự thay đổi `d0/schemas/`, không tự cấp approval, không chạy malware trên host. Các hành vi ngoài phạm vi phải tạo ticket mới.

**PR evidence:** test log + fixture I/O + schema version + security notes + reviewer sign-off.
