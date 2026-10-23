# 9 IMPLEMENTATION TICKETS — D1–D9

**Đọc `docs/team/TEAM_START_HERE.md` trước.** Đây là bản giao việc kỹ thuật có thể đưa lên GitHub Issues. Không phải chứng nhận module đã code xong.

- [D1-01 — Orchestrator Core](D1_TICKET.md) — Owner 1; input: ToolCall, registry lookup, validator result, PolicyDecision, trusted admission; output: run state machine, run_id, execution receipt, D9 commit or typed failure.
- [D2-01 — Tool Registry](D2_TICKET.md) — Owner 4; input: ToolSpec, provider availability; output: versioned registry lookup, enabled/capability/provider binding.
- [D3-01 — Input Validator](D3_TICKET.md) — Owner 3; input: ToolCall, ToolSpec, TargetRef, CaseState snapshot; output: validated call or typed validation error.
- [D4-01 — Policy Engine](D4_TICKET.md) — Owner 1; input: validated ToolCall, ToolSpec effects, workflow state, budget, authenticated grants; output: PolicyDecision allow/deny/approval_required + effective limits.
- [D5-01 — Tool Executor](D5_TICKET.md) — Owner 2; input: admitted call, pinned adapter, verified target, effective limits; output: raw tool output and execution metadata for D6/D7.
- [D6-01 — Execution Control](D6_TICKET.md) — Owner 2; input: run handle, timeout/budget, cancellation request; output: ExecutionReceipt with outcome/cleanup/resources, artifact references.
- [D7-01 — Result Validator](D7_TICKET.md) — Owner 3; input: raw output, ExecutionReceipt, ToolSpec output schema; output: validated ToolResult with observations/coverage/artifact digests.
- [D8-01 — Trust & Approval](D8_TICKET.md) — Owner 1; input: trusted run facts, authenticated analyst identity, ApprovalRequest; output: signed attestation, ApprovalEvent, audit/replay protection.
- [D9-01 — Case Bridge](D9_TICKET.md) — Owner 4; input: validated signed ToolResult, receipt, CaseState; output: case revision + evidence IDs + append-only audit references.
