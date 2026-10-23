# DACN — Node C v1: CaseState Builder + CaseManager

**Important separation:** Node B is the **Context Collector**, producing `collections/COL-.../context.json`. Node C is the **CaseState Builder/Manager**, producing/updating `cases/CASE-.../case_state.json`. Node C does not collect from Windows, analyze malware, execute tools, or respond to threats.

## Install on Windows PowerShell

Extract these files into the repository root, alongside `context_collector.py`. Replace the older `case_state.py` and `test_case_state.py`; keep your current `context_collector.py` untouched. **Do not copy both `test_case_state.py` and `test_case_state_updated.py` into the repo.** The `examples/` folder is optional.

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_node_b_timeout test_case_state test_case_manager
```

`test_node_b_timeout` imports your existing `context_collector.py` v1.1.0 and simulates elapsed time to test hash budget handling. It does not claim to interrupt a blocked OS read. This package's other tests do not need `psutil`.

## Workflow (copy/paste)

1. Create a fresh case from a **Node B Context Collection**:

```powershell
.\.venv\Scripts\python.exe case_manager.py init --context ".\collections\COL-9645ca258a9447db830a67d5ec61899e\context.json" --output cases
```

The command prints `case_state_path`. Set `$case` to **the printed actual path**:

```powershell
$case = ".\cases\CASE-PASTE_YOUR_REAL_CASE_ID\case_state.json"
.\.venv\Scripts\python.exe case_manager.py show --case $case
```

2. Register a tool definition **without running it**:

```powershell
.\.venv\Scripts\python.exe case_manager.py register-tool --case $case --input .\examples\register_tool.json
```

3. Append a tool result that was produced by a **real external tool**:

```powershell
.\.venv\Scripts\python.exe case_manager.py tool-result --case $case --input .\examples\tool_result.json
```

`examples/tool_result.json` contains **illustrative synthetic evidence**, not a real malware-analysis result. It is keyed to your example PID 12296 and its start timestamp; it will be rejected for a different process identity. Do not mistake the example for real evidence. To run on another case, replace the target identity and use a new unique `tool_run_id`.

4. Start investigation (lifecycle transition only):

```powershell
.\.venv\Scripts\python.exe case_manager.py action --case $case --input .\examples\start_investigation.json
```

5. Append a **new** Context Collection to the same case (instead of creating another case):

```powershell
.\.venv\Scripts\python.exe context_collector.py --pid $PID --include-backing-file --hash-timeout 5
# Copy the newly printed context_path into this command:
.\.venv\Scripts\python.exe case_manager.py collection --case $case --input ".\collections\COL-NEW\context.json"
```

**Important:** A new collection can be appended only if it matches the original target identity. For process cases, both PID **and process creation timestamp** must match; otherwise the operation is rejected (PID reuse protection). `$PID` must refer to that same process.

## Input contracts

`case_manager.py` supports:

| Command | Input | Behavior |
|---|---|---|
| `init` | Node B `context-v1` JSON | New case with evidence, unknowns, history |
| `collection` | Another Node B `context-v1` JSON | Appends observations to same case; rejects duplicate collection IDs |
| `register-tool` | `{ "name": "static_analyzer", "description": "..." }` | Adds tool *metadata* to `available_tools`; does not execute it |
| `tool-result` | `tool_run_id`, `tool`, `status`, `target_type`, `target`, `observations` | Adds evidence with provenance; rejects duplicate runs and mismatched targets |
| `action` | `event_id`, `action`, `actor`, `reason` | Audit log + guarded lifecycle transition |
| `assessment` | `verdict`, `confidence`, `evidence_ids`, `rationale`, `actor` | Records a provided assessment with evidence references; no model runs here |
| `response` | `status`, `description`, `human_approved:true`, `approver` | Records an explicitly approved response status; **never performs OS action** |
| `show` | Existing case path | Prints summary |

Supported actions: `START_INVESTIGATION`, `REQUEST_MORE_CONTEXT`, `REQUEST_APPROVAL`, `CLOSE_CASE`, `NOTE`. New cases start in `READY_FOR_INVESTIGATION` or `NEEDS_CONTEXT` if collection failed. Existing CaseState files with `INVESTIGATING` remain readable.

## What is and is not tested

- Unit tests cover data mapping, provenance, incomplete hash, nested backing file, deduplication, PID identity, error handling, lifecycle transitions, human approval records, atomic writes, and concurrent lock contention.
- `residual_unknowns` represent **missing observations**, not instructions that the Agent must automatically execute every tool.
- CaseManager does not independently establish the truth of a tool's result or assessment. The orchestrator must validate tool trust, provenance, and evidence before ingestion.
- `.lock` files protect normal concurrent updates. If a process crashes holding a lock, investigate and manually remove the stale lock; it is not automatically broken.
- `case_state.json` is a working mutable snapshot with an audit history, **not** a tamper-evident event store. For production, add durable append-only event logs, signatures, OS ACLs, and external artifact storage.
- CaseState is capped at 8 MiB for updates; store large evidence externally and reference it by `artifact_ref`.
- The hash timeout is **best effort**; blocking OS reads may outlast the timeout.
- There is **no** LightGBM, EMBER, LLM, dynamic sandbox, Tool Registry runtime, or response executor here. Those are separate nodes/modules.

## Files

- `case_state.py`: create initial CaseState from Node B Context Collection.
- `case_manager.py`: update the **same** case as investigations progress.
- `test_case_state.py`: builder tests.
- `test_case_manager.py`: manager tests.
- `test_node_b_timeout.py`: final deterministic Node B timeout tests.
- `examples/*.json`: local demonstration payloads only.
