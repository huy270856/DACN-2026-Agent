# SoT update notes — 2026-10-23

Authoritative addendum to legacy SoT docs; preserve original diagrams and historical node names.

1. B/C v1.2 verified by team on Windows (reported by lead); D.0 REA-informed v1 design freeze candidate and contract tests available; Node D runtime D1–D9 not yet implemented.
2. The original SoT calls `Node D = Agent Planner`, `Node E = Executor`; the D.0 implementation nomenclature calls `Node D = Trusted Tool Orchestrator`, modules D1–D9. Do not equate these. Keep legacy A–Z names for capability map; use `agent/`, `orchestrator/`, `analyzers/` in code.
3. New approved workflow: known with authoritative fresh reputation → assessment; unknown file → static first; dynamic when insufficient/conflict/policy, only isolated Windows VM. Process/PID cases can prioritize read-only process metadata and backing-file static without executing the sample on host.
4. Python orchestrator; analyzer adapter may be written in Rust/C++/Go/Node if canonical schema is satisfied.
5. Human authenticated approval with audit for containment; Agent never holds keys or executes high-impact response.
6. Provider pinned for each ToolRun; no silent fallback; UNKNOWN/partial does not imply benign.
7. Baselines: fixed pipeline, rule workflow, AI Agent; metrics and ground truth to be documented before evaluation.
8. D.3 blockers: atomic expected_revision check inside Node C case lock, real D8 trust/approval, lossless audit ledger, VM isolation/cleanup validation.
9. Module ownership: member 1 D1/D4/D8 + Agent; member 2 D5/D6 + Static ML; member 3 D3/D7 + telemetry; member 4 D2/D9 + CLI/GUI. Ticket details in `docs/tickets/`.
10. D.0 schemas and fixtures are the interface SoT for D1–D9; changes require lead-reviewed ADR and contract test update.
