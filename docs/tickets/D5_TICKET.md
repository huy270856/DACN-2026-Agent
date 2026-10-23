## D5-01 — Tool Executor | Owner: 2

**Mục tiêu:** hiện thực Tool Executor theo D.0, có thể kiểm thử độc lập bằng fixtures.

**Tài liệu bắt buộc:** `docs/d0/01_ARCHITECTURE_AND_ADRS.md`, `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md`, `docs/d0/05_TEAM_HANDOFF.md`, `docs/d0/06_SECURITY_AND_TEST_PLAN.md`; D9 thêm `docs/d0/03_BC_V12_BRIDGE.md`.

**Dependency:** D.0; D3/D4 mocked. Dependency chưa xong phải mock, không được sửa code người khác để lách.

**Input:** admitted call, pinned adapter, verified target, effective limits.

**Output:** raw tool output and execution metadata for D6/D7.

**Files ownership (đề xuất):** `orchestrator/executor.py`; tests `tests/test_d5_executor.py`.

**Acceptance tests:** no shell injection; pinned provider; TOCTOU check via handle/staged bytes; mock adapter; never run sample on host.

**Out of scope:** Không tự thay đổi `d0/schemas/`, không tự cấp approval, không chạy malware trên host. Các hành vi ngoài phạm vi phải tạo ticket mới.

**PR evidence:** test log + fixture I/O + schema version + security notes + reviewer sign-off.
