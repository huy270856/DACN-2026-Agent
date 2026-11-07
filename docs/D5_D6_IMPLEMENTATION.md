# D5 and D6 Windows prototype

Scope: tickets D5-01 and D6-01 only, based on main commit
`5f6f2a95548f510a8b6257e12d5134669fc8c9e0`. This change adds a real Windows
subprocess controller and a safe mock analyzer. It does not implement EMBER,
LightGBM, D1/D2/D3/D4/D7/D8/D9, process-target telemetry, or malware execution.
The `d0/schemas/` contracts are unchanged.

## Integration API

`ToolExecutor(artifact_root).execute(call, spec, policy, case_snapshot, adapter,
cancel=threading.Event())` is a **trusted backend Python API**, not a public
Agent API. A supplied ALLOW JSON document is not authorization. D1 must invoke
this only after real D3/D4/D8 admission and manage revision reservations,
idempotency, durable rejection audit and global concurrency. D2 supplies the
installed `PinnedAdapter`; do not construct it from Agent arguments.

Input schemas: `tool_call`, `tool_spec`, `policy_decision`, `target_ref`,
`provider`, `limits` under `d0/schemas/`. Versions are `d0-v1` and
`target-ref-v1`. The case snapshot is the existing B/C projection with
`case_id`, `revision`, `target_ref`; it is not a new schema.

Output: the Python `ExecutionOutput` carries an `execution_receipt` conforming
to D.0, a tuple of `artifact` records, internal error information, exit code
and local run directory. This Python carrier is NOT a new serialized contract.
D7 must validate/normalize raw bytes into observations and ToolResult; D8 must
attest; D9 must commit. D5/D6 do not write CaseState or make malware verdicts.

Pre-dispatch failure raises `ExecutionRejected(code, message)` without starting
an adapter. D1 records the rejected attempt. Internal codes use the uppercase
taxonomy from D.0; `PROVIDER_FAILED` additionally distinguishes nonzero adapter
exit. The task owner approved keeping internal uppercase codes and letting D7
map them into lowercase `ToolResult.error.code`. Team integration review must
agree that mapping, including `PROVIDER_FAILED`; no schema was modified.

## D5 behavior

- Read-only FILE targets with an existing SHA-256 are supported. PROCESS,
  foreign-code execution, writes/mutation and approval-required tools are
  rejected. A future VM backend is not silently replaced with host execution.
- Validate schema, call/policy/case identity and provider identity/version.
  Effective limits are the minimum of spec, policy and applicable call budgets.
  One executor instance admits at most one run, conservatively below its limit.
- Provider executable and declared code files have installation-time SHA-256
  pins. Digests are checked while Windows handles deny write/delete sharing.
  Fixed argv comes from trusted configuration. Batch files are rejected.
- Target is opened read-only without write/delete sharing. Known file
  identity/size/mtime fields and actual SHA-256 must match the collected ref.
  Bytes copied from that handle are rehashed, then the staging file stays
  read-locked until process cleanup. Adapter never receives the mutable source
  path as its input. Existing parent/final reparse points, UNC/device/ADS paths
  are rejected.
- Installed adapter protocol:
  `<fixed argv> --target <staged path> --arguments-json <canonical JSON object>`.
  It reads target bytes as data. Target file is never used as the executable.
  The trusted installer's fixed command and code pins must cover the adapter.
- stdout and stderr are untrusted binary artifacts with SHA-256, byte size and
  case-root-relative paths. There are at most two captured stream artifacts.
  Size and streaming capture digest are checked again after cleanup, detecting
  same-size artifact tampering as well. Receipt is separate control
  metadata; it is not a signed artifact or an authenticated claim.

## D6 behavior

- Starts a trusted Python bootstrap which waits on stdin. Parent assigns it
  to a Windows Job Object before releasing the fixed provider command. Uses
  the real Python interpreter rather than a venv redirector for this bootstrap.
- Job has kill-on-close and no breakaway flag. Timeout, cancellation, output
  cap, provider failure, and normal parent exit all trigger descendant cleanup.
  Active process accounting confirms job cleanup; no global PID sweep or
  `taskkill /IM` is used. Assignment failure never releases the provider.
- Two reader threads share one combined output cap, further reduced by
  `max_artifact_bytes`. Raw bytes completed before failure/cancellation remain
  available. Exceeding the cap produces FAILED/BUDGET_EXCEEDED, not SUCCESS.
  `resources.output_bytes` records retained bytes, not the number the provider
  attempted to emit. D7 must preserve the error/truncation context.
- Cancellation event and monotonic timeout are distinct. Staging/preparation
  checks the same deadline between read chunks; kernel-blocked preparation I/O
  cannot be interrupted by this synchronous implementation.
- Cleanup failure is recorded as INCOMPLETE and quarantines the executor
  instance. If timeout/cancel occurred first, that outcome remains, with
  incomplete cleanup independently visible. Staging is retained for remediation
  when cleanup cannot be confirmed. No automatic retry is performed.
- `VMResetGate` only models a trusted VM-owner handshake: verified reset,
  snapshot and isolation are required before reuse. Its tests are simulated;
  it does not verify a hypervisor or authorize execution. There is no VM adapter.

## Run tests

From the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-d0.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_d*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s . -p 'test_*.py' -v
```

Run both discovery commands: the existing root discovery does not recurse into
the non-package `tests/` directory in the tested environment.

D5/D6 tests derive the existing ToolCall/ToolSpec/PolicyDecision fixtures,
replace their target with a temporary harmless file and bind `test.readonly`
to a safe mock provider. They do not claim that `static.ember_features` ran.

Real Windows checks: Unicode/spaced paths; locked source and staging bytes;
same-size/same-mtime content replacement; provider pin mismatch; shell syntax
as inert JSON; environment-secret removal; timeout/cancel; descendant cleanup
including early parent exit; shared output cap; artifact budget and integrity;
nonzero exits; rejection before execution; concurrency; history retention.
Mock checks: access failure, reparse detection without privileged link creation,
cleanup accounting failure, PARTIAL preservation, VM reset/isolation state.

## Remaining integration and security gates

This is **not production-ready or a sandbox for malicious analyzers**.
Adapters execute under the current Windows user. Environment inheritance is
restricted, but Windows token/ACL/network isolation is not implemented here.
Trusted backend must protect provider installations, artifact roots and keys;
keys must not be accessible to the adapter's account. Imports/DLL dependencies
of the pinned program are trusted installation dependencies, not transitively
pinned by this implementation. Concurrent malicious modification of unprotected
parent directories is outside this prototype's guarantees.

Only captured stdout/stderr are budgeted artifacts. Arbitrary filesystem writes
by a faulty/untrusted adapter are not prevented or quota-controlled by a Job
Object; read-only adapters are an installation requirement. Staging disk space,
CPU/RAM and long blocking preparation I/O are not hard-limited here. Production
isolation and richer resource limits require a separate reviewed backend.

Still required before full end-to-end acceptance: D1 admission/ledger and
cross-instance concurrency; real D4 policy/D8 authentication and key isolation;
D7 normalization/error mapping; D9 atomic case commit and artifact verification
on read; crash recovery/ACL audit; real VM reset/isolation tests. Replayed
telemetry must be labeled by the future audit/backend, never represented as live.

Native API references used for this implementation:

- https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
