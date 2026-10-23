## D3-01 — Input Validator | Owner: 3

**Mục tiêu:** hiện thực Input Validator theo D.0, có thể kiểm thử độc lập bằng fixtures.

**Tài liệu bắt buộc:** `docs/d0/01_ARCHITECTURE_AND_ADRS.md`, `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md`, `docs/d0/05_TEAM_HANDOFF.md`, `docs/d0/06_SECURITY_AND_TEST_PLAN.md`; D9 thêm `docs/d0/03_BC_V12_BRIDGE.md`.

**Dependency:** D.0; D2 contract (mockable). Dependency chưa xong phải mock, không được sửa code người khác để lách.

**Input:** ToolCall, ToolSpec, TargetRef, CaseState snapshot.

**Output:** validated call or typed validation error.

**Files ownership (đề xuất):** `orchestrator/input_validator.py`; tests `tests/test_d3_input_validator.py`.

**Acceptance tests:** reject wrong case, unsupported target, stale revision snapshot, bad budget/schema, unknown args; not authorization.

**Out of scope:** Không tự thay đổi `d0/schemas/`, không tự cấp approval, không chạy malware trên host. Các hành vi ngoài phạm vi phải tạo ticket mới.

**PR evidence:** test log + fixture I/O + schema version + security notes + reviewer sign-off.
