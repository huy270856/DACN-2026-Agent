# Team handoff: D1–D9 modules and independent work

Team skill ordering supplied by project lead: Member 1 (lead, hardest), Member 2 (next), Members 3/4 (similar, less complex). Workload is intentionally **not equal**; each person must have verifiable deliverables.

## Ownership matrix

| Module | Owner | Inputs | Outputs | Acceptance (minimum) |
|---|---|---|---|---|
| D1 Orchestrator Core | 1 | ToolCall, policy, registry, receipts | durable run lifecycle and dispatch | mock end-to-end; idempotency; no execution after deny |
| D2 Tool Registry | 4 | ToolSpec | capability discovery, availability, binding | versioned registration; disable; duplicate ID rejection; no silent fallback |
| D3 Input Validator | 3 | ToolCall, TargetRef, schema | validated candidate / typed reject | malformed, unsupported, wrong case/target, budget rejection |
| D4 Policy Engine | 1 | ToolSpec effects, case, workflow, analyst grants | PolicyDecision | VM-only foreign-code; no auto-approval; fail closed |
| D5 Tool Executor | 2 | admitted call, verified target, provider adapter | run + raw artifacts | no shell; pinned provider; safe mock; target revalidation |
| D6 Execution Control | 2 | limits, process/VM owner | timeout/cancel/cleanup receipt | bounded output, process-tree cleanup, partial observations |
| D7 Result Validator | 3 | receipt, raw tool output | normalized ToolResult | schema/coverage/trust, oversized artifact rejection |
| D8 Trust & Approval | 1 | signed run facts, analyst identity | signed attestations, approval events | isolated key; replay/expiry/revision; spoof rejection |
| D9 Case Bridge | 4 | validated signed result, Node C | case update + audit refs | legacy mapping, atomic revision, no data loss |

**Security review gates:** Lead reviews D4/D8 and any D5 foreign-code or filesystem mutation capability; Member 2 reviews D5/D6 adapter isolation; Member 3 reviews D7 untrusted-content handling; Member 4 reviews D9 case revision/audit.

## After D.0: parallel delivery plan

**Sprint D.1 (all four work simultaneously):**

- 1: D4 policy rules and D8 trust interface with mock signer (never a production secret); D1 state-machine skeleton.
- 2: EMBER/LightGBM offline static analyzer adapter, plus D5 subprocess mock adapter; model evaluation plan.
- 3: D3 validation and D7 result normalization with adversarial fixtures; optional read-only process/DLL telemetry.
- 4: D2 registry and D9 compatibility adapter, explicit `static.ember_features -> static_ember_features` mapping; simple CLI case inspector.

**Sprint D.2:** 1 integrates D1 with mock components; 2 implements D6 cancellation and safe VM interface (recorded telemetry until VM ready); 3 develops Windows read-only telemetry/recorded sandbox normalization; 4 finishes D9 ledger and case CLI.

**Sprint D.3:** secure signer + authenticated local analyst approval; implement transactional case revision admission, real result receipts, artifact store, end-to-end static analysis. VM analysis remains optional until isolation gate is satisfied.

**Sprint D.4:** adversarial and Windows E2E tests, recovery from crash/cancellation, three-baseline evaluation, GUI/report integration.

## Per-module Definition of Done

- Own folder/file with typed interface and documentation; does not alter other modules' contracts without ADR.
- Unit tests for success, malformed input, timeout/unavailable where applicable, and security negative tests.
- Contract fixtures validate against `d0/schemas` and semantic checks.
- No unexpected side effects; no host execution of untrusted binaries.
- CI and Windows tests green; PR reviewed by owner + lead, screenshots/logs of real platform tests where relevant.
- Explicit error code, audit IDs, version and source provenance; no fabricated success.

## Suggested branches / PRs

- `feat/d1-d4-d8-core-policy-trust` (Member 1)
- `feat/d5-d6-static-adapters` (Member 2)
- `feat/d3-d7-validation` (Member 3)
- `feat/d2-d9-registry-bridge` (Member 4)

Keep `d0/schemas` protected by code review; do not make independent incompatible edits. Each PR references its module ID and D.0 contract version.

## Ticket template

```text
ID: D2-01
Owner: Member 4
Input: d0/schemas/tool_spec.schema.json
Output: orchestrator/registry.py + tests
Out of scope: execution, approval, signing
Dependencies: D.0 only
Acceptance: register/query/disable, reject invalid/duplicate, preserve immutable provider binding
Evidence: unit tests, mock CLI transcript, code review
```
