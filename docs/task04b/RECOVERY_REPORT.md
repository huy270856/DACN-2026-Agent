# TASK 04B finalization review ? PARTIAL

Branch feat/agent-mvp-qwen; HEAD 341e102beec3ed28554a315067f21de614667fd4.
No branch replacement, reset, discard, commit, dependency upgrade, push or merge.
Original Claude/Codex changes retained. Prior audit preserved in RECOVERY_REPORT_1_7B.md.

## Files and implementation
Claude originally supplied agent/*.py, tests/test_agent.py, application and CLI changes.
Codex continued those files; finalization changes config/schema/controller/context/loop/planner,
adds tests and replaces the benchmark harness. Reports and setup are under docs/task04b/.
Default qwen3.5:4b with explicit trusted config support for qwen3:1.7b; no silent fallback.
Runtime is Ollama 0.40.15, qwen35 4.2B Q4_K_M. Exact digest/options in runtime.json.
Model was already installed; no pull required. 1.7B absent: same-version comparison SKIP.

Validation now uses Python JSON Schema plus action-specific exclusions and required fields,
actual evidence IDs, residual unknown facets, case/revision, D2 identity and D3 arguments.
WorkflowEngine enforces static-first before assessment; a trusted operator hash snapshot may
permit known-reputation assessment with a matching successful sha256 citation. No automatic
reputation provider or freshness refresh exists; operators must maintain that trusted snapshot.
D4/D8 untouched. DENY blocks retries of the same tool with changed arguments.
Invalid proposals have bounded recovery, revisions reload, duplicate calls are rejected.

Actual prompt/eval usage is logged on successful responses, including proposals later rejected.
Admission control charges at least 8192 + 2*num_predict per request, or higher reported usage.
Socket timeout and tool timeout_ms are capped to remaining wall-clock time. Socket closure is
not proof of immediate Ollama cancellation. D1/D6 cleanup/commit may exceed timeout. No hard
real-time or exact hidden-reasoning-token guarantee is asserted. Missing usage uses reservation.

## Confirmed testing
Agent unit 27 PASS; real Node C/D1-D9 MOCK_LLM E2E 1 PASS; normal live 1 SKIP.
Regression tests/: 239 tests OK (1 live SKIP), run outside sandbox for DPAPI.
Root Node B/C/application: 129 tests OK (2 existing SKIP: symlink privileges, large-file opt-in).
Initial sandbox regression had DPAPI error; unrestricted rerun passed, no D8 change.
Live final static-first version thinking OFF: 2/2 strict E2E PASS. Both call the actual model,
execute only benign MOCK analyzer through D1-D9, D9 commits revision 3, reload, FINISH with
INSUFFICIENT_EVIDENCE and explicit mock limitations. Traces: live_trace_v3_run1/2.json.
No target binary execution. Exact citations and tool run IDs are retained in the traces.
Earlier attempts failed: thinking ON empty output at 1536 cap; OFF before gate fix finished
without tool. Those failures are recorded in local demo_results/task04b logs and v2 benchmark.

## Benchmark interpretation and outstanding criteria
benchmark.json: fixed v3 scenario probes, 6 scenarios x 2 repeats x 2 thinking modes.
These are synthetic labelled scenario variants over a real benign intake snapshot; model and
Controller are real, but probes themselves do not run D1-D9. Full execution is the separate E2E.
Rubric admits action sets, checks schema/controller safety and known-benign assessment correctness.
Deny scenario checks duplicate suppression after an injected prior DENY history; actual D4 DENY
is unit tested via fake run records, not measured as a live real-policy-denial investigation.
v2 benchmark stopped after the static-first gate changed, retained separately, never pooled.

PARTIAL: strict OFF E2E now works, but known-benign decision correctness is not reliable,
thinking ON is not usable at measured latency/output caps, and the benchmark is proposal-level
rather than repeated full E2E for every scenario. Thus no blanket MVP PASS or P0/P1 closure.
No proof of semantic prompt-injection immunity; deterministic execution restrictions remain.
No REA adapter, real EMBER/LightGBM inference, dynamic sandbox, or GUI added.
Node B/C, D4/D8, containment and analyzer adapters unchanged.

See benchmark_summary.json for final counts and AGENT_SETUP.md for commands and API sources.
