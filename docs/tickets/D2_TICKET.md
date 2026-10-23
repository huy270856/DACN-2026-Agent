## D2-01 — Tool Registry | Owner: 4

**Mục tiêu:** hiện thực Tool Registry theo D.0, có thể kiểm thử độc lập bằng fixtures.

**Tài liệu bắt buộc:** `docs/d0/01_ARCHITECTURE_AND_ADRS.md`, `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md`, `docs/d0/05_TEAM_HANDOFF.md`, `docs/d0/06_SECURITY_AND_TEST_PLAN.md`; D9 thêm `docs/d0/03_BC_V12_BRIDGE.md`.

**Dependency:** D.0. Dependency chưa xong phải mock, không được sửa code người khác để lách.

**Input:** ToolSpec, provider availability.

**Output:** versioned registry lookup, enabled/capability/provider binding.

**Files ownership (đề xuất):** `orchestrator/registry.py`; tests `tests/test_d2_registry.py`.

**Acceptance tests:** reject invalid/duplicate; disabled tool unavailable; pin provider/version; no silent fallback.

**Out of scope:** Không tự thay đổi `d0/schemas/`, không tự cấp approval, không chạy malware trên host. Các hành vi ngoài phạm vi phải tạo ticket mới.

**PR evidence:** test log + fixture I/O + schema version + security notes + reviewer sign-off.
