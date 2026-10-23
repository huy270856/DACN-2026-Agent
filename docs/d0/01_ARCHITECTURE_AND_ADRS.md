# D.0 Architecture & ADRs — 2026-10-23

## Sources and precedence

1. **User-approved seven D.0 choices (2026-10-23)** are the current authoritative architecture decisions.
2. **Actual Node B/C v1.2 source**: `bc_contracts.py`, `case_state.py`, `case_manager.py` provided in the working environment.
3. **Project SoT V3**: `source_of_truth_revised_v3_flowstyle.docx`, especially sections 1–10; it is background context. Its section 4's unrestricted route-selection explanation is **superseded** by approved workflow choice 1A.
4. **REA public reference**: https://github.com/morluto/rea ; https://github.com/morluto/rea/blob/main/docs/mcp-contracts.md ; https://github.com/morluto/rea/blob/main/docs/tool-design.md . Design principles only, not a claim of direct code reuse.

## System architecture

```text
Windows CLI / future GUI / human analyst
                 |
             Intake / B (minimum context) ---> C (CaseState v1 + Evidence v2)
                 |                                 ^
                 v                                 |
      Workflow Engine (deterministic gates)        |
         |                 |                       |
   Reputation route   Agent (local model)          |
         |          [follow-up, conflict,          |
         |           escalate, stop, recommend]    |
         +-----------------+                       |
                           | ToolCall / action proposal
                           v
                  D — Trusted Tool Orchestrator
        D2 Registry -> D3 Validation -> D4 Policy / D8 Trust
                           |
                    D1 Core + D5 Executor + D6 Control
                           |
       static / EMBER-LightGBM / sandbox VM / process-DLL tools
                           |
                 D7 Result Validation -> D8 Signing
                           |
                       D9 Case Bridge ------------+
                           |
                  Final Assessment -> response proposal
                           |
                  Human approval + policy -> response executor
                           |
                   verify -> report -> close
```

D is a **trusted enforcement boundary**; neither the Agent nor tool outputs are trusted authorization sources. D.0 defines it but does not implement it.

## ADR-001 — Workflow-led Agent (accepted)

- Reputation state from local, provenance-backed sources: `KNOWN_MALICIOUS`, `KNOWN_BENIGN`, `UNKNOWN`, `UNAVAILABLE`, `CONFLICT`.
- Known (both malicious and benign) may proceed to assessment **only if** evidence freshness, target binding and source trust are sufficient. Known benign is not an absolute bypass; suspicious conflicting observations force review.
- Unknown/unavailable/conflicting reputation -> **static first** (file context, PE/EMBER/LightGBM where supported). `UNKNOWN` is not benign.
- Dynamic is conditional on inconclusive static, conflicting evidence, policy/analyst requirement, and sandbox availability. If sandbox unavailable, mark unknown and escalate/use recorded fixtures for demonstration; do not run the sample on host.
- The Agent can choose approved follow-up tools, reconcile questions, request more evidence, propose stop/escalate and recommend response **within workflow/policy gates**. It cannot override static-first or VM isolation.
- A PROCESS target without safe file backing may use read-only telemetry first; record static as `UNAVAILABLE` rather than pretending a file exists. Any exception route is explicitly documented and policy-gated.

## ADR-002 — Python orchestrator, polyglot analyzer adapters (accepted)

- Python package monolith and CLI first; GUI/API later. All contracts JSON-compatible, no Python object pickles across boundaries.
- External analyzers in Rust/C++/Go/Node/etc are allowed through D5 adapters with pinned binary identity, exact argv, no shell, isolated working directory, bounded stdout/stderr, timeout and cleanup.
- External tools cannot access signing keys or approval service. Avoid accepting executable paths or arbitrary commands from the Agent.
- Native FFI is optional but higher risk and requires explicit review; default external process/IPC.

## ADR-003 — VM-only malware execution (accepted)

- Dynamic analysis of untrusted binaries only inside an isolated Windows VM with controlled staging, snapshots/restore and verified isolation configuration. No real malware execution on development host.
- Record guest identity, sample hash, snapshot ID, instrumentation version, run ID, network isolation mode, teardown/restore status and limitations.
- Recorded telemetry fixtures are acceptable while VM not ready, labeled `REPLAYED`/`SIMULATED` and never passed off as live observations.
- VM cleanup failure blocks reuse; don't silently mark an incomplete run complete.

## ADR-004 — Local human approval (accepted)

- CLI/service authenticated as an actual local analyst identity; decision binds case revision, action digest, target identity, expiration, risk, and requested effects.
- Approval request and approval event are different artifacts. No `human_approved: true` field from the Agent.
- Response execution must **re-check** current case revision and target before effects, and separately record verification.
- Local login authentication design and secret storage are future D8 work, not present in this package.

## ADR-005 — Immutable provider binding (accepted)

- A ToolSpec binds one concrete provider ID/version per ToolRun. Failure -> typed error; never silently substitute a provider.
- A new provider attempt requires a **new ToolCall + PolicyDecision + run ID**, preserving the old failure.
- Discovery and availability are distinct from authorization.

## ADR-006 — Three research baselines (accepted)

- A: fixed pipeline, B: rule workflow, C: workflow-guided local AI Agent.
- Compare on same held-out sample set, same evidence budget, same safety gates, same target population. Measure accuracy, false positives/negatives, coverage, analysis time, number of tool calls, escalation/approval rate, cost and invalid tool proposals.
- Avoid claiming Agent superior before empirical results. Prevent train/test leakage by splitting by sample family/time where feasible.

## ADR-007 — Security & ownership

- D2/3/4/5/6/7/8/9 are modules, D1 composes them. Tool author != tool authorizer.
- Node C remains source of case truth. Workflow owns route policy; D owns enforcement; Agent owns bounded recommendations; human owns approval; tools own observations only.
- `D.0` is design/contracts; `D.1–D.4` are implementation/integration milestones, not a runtime component.
