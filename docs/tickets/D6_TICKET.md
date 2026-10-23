## D6-01 — Execution Control | Owner: 2

**Mục tiêu:** hiện thực Execution Control theo D.0, có thể kiểm thử độc lập bằng fixtures.

**Tài liệu bắt buộc:** `docs/d0/01_ARCHITECTURE_AND_ADRS.md`, `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md`, `docs/d0/05_TEAM_HANDOFF.md`, `docs/d0/06_SECURITY_AND_TEST_PLAN.md`; D9 thêm `docs/d0/03_BC_V12_BRIDGE.md`.

**Dependency:** D5 interface. Dependency chưa xong phải mock, không được sửa code người khác để lách.

**Input:** run handle, timeout/budget, cancellation request.

**Output:** ExecutionReceipt with outcome/cleanup/resources, artifact references.

**Files ownership (đề xuất):** `orchestrator/execution_control.py`; tests `tests/test_d6_execution_control.py`.

**Acceptance tests:** timeout kills owned process tree; cancellation cleanup; bounded stdout/artifact; partial/failed preserved; VM reset gate.

**Out of scope:** Không tự thay đổi `d0/schemas/`, không tự cấp approval, không chạy malware trên host. Các hành vi ngoài phạm vi phải tạo ticket mới.

**PR evidence:** test log + fixture I/O + schema version + security notes + reviewer sign-off.
