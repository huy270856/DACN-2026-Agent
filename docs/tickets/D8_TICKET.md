## D8-01 — Trust & Approval | Owner: 1

**Mục tiêu:** hiện thực Trust & Approval theo D.0, có thể kiểm thử độc lập bằng fixtures.

**Tài liệu bắt buộc:** `docs/d0/01_ARCHITECTURE_AND_ADRS.md`, `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md`, `docs/d0/05_TEAM_HANDOFF.md`, `docs/d0/06_SECURITY_AND_TEST_PLAN.md`; D9 thêm `docs/d0/03_BC_V12_BRIDGE.md`.

**Dependency:** D.0; Node C v1.2. Dependency chưa xong phải mock, không được sửa code người khác để lách.

**Input:** trusted run facts, authenticated analyst identity, ApprovalRequest.

**Output:** signed attestation, ApprovalEvent, audit/replay protection.

**Files ownership (đề xuất):** `orchestrator/trust.py`; tests `tests/test_d8_trust.py`.

**Acceptance tests:** key inaccessible to Agent/tool; deny forged/expired/replayed approvals; bind case revision/action digest; mock signer explicitly test-only.

**Out of scope:** Không tự thay đổi `d0/schemas/`, không tự cấp approval, không chạy malware trên host. Các hành vi ngoài phạm vi phải tạo ticket mới.

**PR evidence:** test log + fixture I/O + schema version + security notes + reviewer sign-off.
