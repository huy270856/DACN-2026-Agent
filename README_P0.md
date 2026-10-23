# Node C P0 Security/Resilience audit

**Scope:** Tests only. Does not overwrite `case_manager.py`, `case_state.py` or Node B `context_collector.py`.

Copy `test_security_resilience.py` into repository root alongside `case_manager.py` and `case_state.py`.

PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_security_resilience
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Expected current Node C v1 results: 9 tests; 5 PASS, 4 `expected failure`. **An expected failure is a known unimplemented security requirement, not a passed security test.** A summary ending `OK (expected failures=4)` is not P0 sign-off. `unexpected success` means the behavior changed and the test should be reviewed and unmarked.

## Passing checks

- P0-01 Reject malformed tool observations without modifying case.
- P0-02 Reject wrong PID creation time without modifying case.
- P0-03 Eight actual OS subprocesses update same CaseState without lost updates.
- P0-04 Inject process exit immediately before `os.replace` and verify original JSON and revision remain intact. **Stale lock remains:** this test does not validate automatic lock recovery.
- P0-05 Preserve both conflicting values and their tool_run provenance.

## Known gaps (expected failures)

- P0-06 No explicit `evidence_conflicts` for contradictory successful values. Beware time-varying facets: conflicts must be evaluated with time semantics, not every changed value is suspicious.
- P0-07 Assessment can cite older successful evidence despite newer contradictory evidence.
- P0-08 Registered tool name does not authenticate result producer; caller can submit arbitrary `tool` JSON. **Real fix belongs at trusted Tool Orchestrator boundary**, not a `trusted: true` JSON flag.
- P0-09 `human_approved: true` and `approver` are caller-controlled strings; not an authenticated approval. Node C only records response; no OS response is executed.

## Interpretation

- The test harness runs no malware and makes no external requests.
- It deliberately kills only its own Python child process in the crash test.
- Each test uses its own temporary CaseState; it does not modify the user's existing `cases/` directory.
- On Windows, subprocess startup may be slower than on Linux. If concurrency test fails, share its output before changing locking behavior.
- `case_state.json` is a mutable snapshot, not a tamper-evident log; file ACLs and append-only audit are future concerns.

**Next:** implement conflict/staleness policy in CaseManager and trusted result/approval gateways in the Orchestrator; remove `@unittest.expectedFailure` only after the respective security checks truly pass.
