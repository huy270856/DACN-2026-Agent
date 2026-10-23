## D9-01 — Case Bridge | Owner: 4

**Mục tiêu:** hiện thực Case Bridge theo D.0, có thể kiểm thử độc lập bằng fixtures.

**Tài liệu bắt buộc:** `docs/d0/01_ARCHITECTURE_AND_ADRS.md`, `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md`, `docs/d0/05_TEAM_HANDOFF.md`, `docs/d0/06_SECURITY_AND_TEST_PLAN.md`; D9 thêm `docs/d0/03_BC_V12_BRIDGE.md`.

**Dependency:** D.0; Node C v1.2; D7/D8 mocks. Dependency chưa xong phải mock, không được sửa code người khác để lách.

**Input:** validated signed ToolResult, receipt, CaseState.

**Output:** case revision + evidence IDs + append-only audit references.

**Files ownership (đề xuất):** `orchestrator/case_bridge.py`; tests `tests/test_d9_case_bridge.py`.

**Acceptance tests:** static.ember_features -> static_ember_features; no lossy silent mapping; no DENIED as tool success; atomic expected_revision in lock before D.3 merge; old state opens.

**Out of scope:** Không tự thay đổi `d0/schemas/`, không tự cấp approval, không chạy malware trên host. Các hành vi ngoài phạm vi phải tạo ticket mới.

**PR evidence:** test log + fixture I/O + schema version + security notes + reviewer sign-off.
