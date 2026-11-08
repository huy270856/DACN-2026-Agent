# TASK 04B recovery and review

Branch: `feat/agent-mvp-qwen`; HEAD: `341e102beec3ed28554a315067f21de614667fd4`.
No reset, discard, branch replacement, commit, push, merge or dependency upgrade performed.
Existing branch retained to preserve interrupted work; latest remote main was not fetched or asserted.

## Recovery audit (before edits)
Claude supplied untracked `agent/{__init__,config,context,controller,loop,planner,report,schema}.py`,
`tests/test_agent.py`, and tracked modifications to `dacn/application.py`, `dacn/cli.py`.
Baseline: 16 passing tests, 1 skipped live test, 1 mock E2E error from sandbox AppData ancestry access.
No historical test execution evidence was available. Live assertion originally allowed ERROR as success.

## Continuation by Codex
Retained components and CLI. Modified config, context, controller, loop, planner, report, schema,
application and test_agent. Added tests/benchmark_agent.py and these review artifacts.
Loopback URL parsing rejects lookalike hosts; model pinned to qwen3:1.7b; budgets validated.
D3 validates arguments and target binding before dispatch; WorkflowEngine gates static/dynamic routing.
Only static nonmutating follow-ups enabled. No direct analyzer/shell execution by Agent.
D4/D8 remain unchanged. Context now supplies trusted argument schemas and remains valid bounded JSON.
Deadline checked after inference; HTTP timeout bounded by remaining time; no proxy for Ollama.
Report cites explicit proposal references instead of attributing all evidence to model.
Controller rejects substantive verdicts without a trusted assessment policy; this MVP deliberately
returns UNKNOWN/INSUFFICIENT_EVIDENCE. Reputation currently conservatively UNAVAILABLE;
known reputation fast path is not integrated. No evidence fabrication.

## Runtime and results
Ollama 0.40.15; qwen3:1.7b ID 8f68893c685c, 1.4 GB, loopback :11434.
Temperature 0.1, num_ctx 8192, num_predict 1536, normal inference timeout 180s.
Default thinking remains off; strict live test explicitly uses thinking on.
RAM/GPU CIM inspection denied by environment; not measured.

- Agent unit: 20 PASS. Real D1-D9 MOCK_LLM E2E: 1 PASS. Live omitted: 1 SKIP in normal suite.
- Regression tests/ suite: 232 tests, OK (1 live SKIP).
- Root B/C/application regression: 129 tests, OK (2 SKIP: Windows symlink privileges and large-file opt-in).
- Strict live E2E: FAIL. Last run used real Qwen, committed static evidence through D9,
  reloaded revision 3, then requested human dynamic review instead of FINISH.
- Live benchmark: thinking off ERROR, 4 JSON-valid proposals, 3 controller rejects, 1 tool call;
  thinking on FINISHED, 2 valid proposals, no rejects, 1 tool call, INSUFFICIENT_EVIDENCE.
  Accepted inference latencies: off 2.21s; on 3.01s and 4.65s. Rejected proposal latencies
  were not retained, so this is not total benchmark latency. Only one case per mode.

benchmark.json includes actual proposal evidence IDs, tool run ID and revision; live_trace.json
captures the subsequent strict run. Temporary sample/case directories were cleaned by test fixtures;
these JSON traces are retained, not persistent Node C case archives.
Raw test outputs remain locally under ignored demo_results/task04b/.

## Limits / outstanding acceptance criteria
TASK 04B is not fully accepted: strict live FINISH is unreliable. Do not infer model quality from JSON validity.
Prompt injection isolation uses data framing and deterministic gates, not a proof of semantic immunity.
Context character and per-request token caps plus finite iterations bound usage; actual cumulative token
accounting and reserved per-tool remaining wall-clock time are not implemented. A synchronous D1 call
can extend past the agent wall-clock boundary by its trusted tool timeout.
Field validation is partly permissive (optional common lists, extra nested fields); unknowns_targeted
is not yet checked against residual unknowns. Retry budget exists; no inference transport retry.
No REA/Ghidra, LightGBM inference, VM dynamic, response actions, or Windows security changes.
No D4/D6 containment, EMBER, sandbox or adapter modifications.

Review before accepting, committing or publishing. No push or merge performed.
