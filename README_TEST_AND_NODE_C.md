# Node B timeout test + Node C CaseState Builder

## Install

Copy `case_state.py`, `test_case_state.py`, and `test_node_b_timeout.py` into the **repository root** beside the existing `context_collector.py`. The supplied `context_collector.py` is a reference copy of v1.1.0; do not overwrite a newer local version without comparing.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_node_b_timeout test_case_state
```

`test_node_b_timeout` deterministically simulates elapsed time by mocking `time.monotonic` and verifies timeout never returns a partial SHA-256. This is a **unit test of timeout logic**, not proof of hard Windows I/O cancellation or a real slow disk timeout.

## Build Node C from your actual Collector output

```powershell
.\.venv\Scripts\python.exe case_state.py --context ".\collections\COL-9645ca258a9447db830a67d5ec61899e\context.json" --output cases
```

Outputs `cases/CASE-<uuid>/case_state.json`. Can use any other actual collection JSON path, including PID with nested backing file.

## Node C contract

- Input: one Collector `context-v1` JSON object, with optional `backing_file_context` nested object.
- Output: `casestate-v1` JSON with case_id, target, lifecycle_status, evidence list, residual_unknowns, collection_errors, tool_runs, action_history, assessment.
- Each observed facet gets its own evidence_id; only `SUCCESS` facets have valid `value`.
- Missing/not requested evidence becomes `NOT_COLLECTED` gap, never a benign verdict.
- Nested backing-file context retains collection_id and parent linkage.
- No Agent, external API, verdict, response, Tool Registry discovery, or malware execution.
- `available_tools` intentionally `{}` until the real Tool Registry is connected.
- `source_context_path` is a pointer, not a duplicate raw artifact.

## Important v1 limits / next steps

1. This is an **initial CaseState builder**, not a complete event-sourced CaseManager. Repeated tool executions should append evidence with idempotency rules and audit history; do not recreate the case every time.
2. For production, consider storing evidence values in artifact files and retaining only evidence_id/summary/ref in CaseState. Current small facet values are embedded to make v1 inspectable.
3. `coverage='limited'` means Collector's narrow observation scope; do not equate it with complete scan coverage.
4. File target's SHA-256 is computed by Node B; it is not a malware classification.
5. Do not load untrusted JSON from untrusted directories without size limits and access controls.
