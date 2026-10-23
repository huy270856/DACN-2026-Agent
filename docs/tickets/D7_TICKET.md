## D7-01 — Result Validator | Owner: 3

**Mục tiêu:** hiện thực Result Validator theo D.0, có thể kiểm thử độc lập bằng fixtures.

**Tài liệu bắt buộc:** `docs/d0/01_ARCHITECTURE_AND_ADRS.md`, `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md`, `docs/d0/05_TEAM_HANDOFF.md`, `docs/d0/06_SECURITY_AND_TEST_PLAN.md`; D9 thêm `docs/d0/03_BC_V12_BRIDGE.md`.

**Dependency:** D.0; D6 receipt fixture. Dependency chưa xong phải mock, không được sửa code người khác để lách.

**Input:** raw output, ExecutionReceipt, ToolSpec output schema.

**Output:** validated ToolResult with observations/coverage/artifact digests.

**Files ownership (đề xuất):** `orchestrator/result_validator.py`; tests `tests/test_d7_result_validator.py`.

**Acceptance tests:** schema invalid rejected; missing not false; content_origin untrusted; provider/run IDs consistent; oversized outputs externalized.

**Out of scope:** Không tự thay đổi `d0/schemas/`, không tự cấp approval, không chạy malware trên host. Các hành vi ngoài phạm vi phải tạo ticket mới.

**PR evidence:** test log + fixture I/O + schema version + security notes + reviewer sign-off.
