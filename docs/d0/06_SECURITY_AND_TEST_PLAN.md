# D.0 security gates, testing and research plan

## Trust boundaries

1. **Untrusted:** sample bytes, PE strings, logs, model output, analyzer stdout, sandbox telemetry, tool descriptions from external packages.
2. **Trusted control plane (to be built):** D2 registry installed by administrator, D4 policy, D5 admission, D8 signer/approval backend, D9 authorized CaseState updates.
3. **Human:** analyst authentication occurs in local trusted service/CLI; the Agent cannot supply proof of human identity.
4. **Execution environment:** host performs safe read-only analysis of approved bytes; foreign code executes **only inside a validated, isolated VM**. A VM is not automatically safe; snapshot, guest/host sharing, networking and escape exposure must be reviewed.
5. **Persistence:** case/ledger/artifact roots must enforce ACLs and path containment, integrity checks, atomic writes and audit retention.

## Threat -> control -> negative test

| Threat | Control | Test |
|---|---|---|
| Same path, replaced file | handle-bound identity + digest before execution | swap file after B collection -> reject |
| PID reuse | PID + process start time | reused PID -> reject |
| Agent tool spoof | allowlisted ToolSpec + provider binding | unknown tool or provider -> deny |
| Tool/provider silent fallback | immutable selected provider | unavailable provider -> explicit error |
| Race with CaseState revision | compare-and-swap inside case lock | concurrent writer -> stale reject |
| Prompt injection in PE/log | untrusted content marker, no command interpretation | instruction-like string stays data |
| Oversized stdout/artifact | hard output limits, external hashed refs | cap breach -> typed error, cleanup |
| Malicious approval JSON | authenticated analyst service + signature/nonce | forged approval -> reject |
| Replay of ToolResult | HMAC + nonce + durable run ledger | duplicate run/nonce -> reject |
| Cancellation leaves child process | process tree ownership + cleanup receipt | incomplete cleanup -> block reuse |
| VM unavailable | fail closed to fixture/human review | no host execution fallback |
| Sandbox evidence replay mislabeled live | provenance mode `REPLAYED` in D audit | fixture cannot claim live |
| ToolResult tampering | canonical digest + D8 authentication | changed args/provider/receipt -> reject |
| Known hash but conflicting fresh evidence | provenance and freshness policy | conflict -> static/review, not blind benign |

## Current runnable D.0 test suite

`tests/test_d0_contracts.py` covers schema correctness, fixtures, mock ToolCall->receipt->result, stale revision, provider mismatch/unavailable, wrong target hash, budget, tampering, success without target verification, untrusted injection, observed-empty vs unavailable, cleanup state, unknown fields and approval expiry.

**Verification:** 21/21 D.0 tests PASS; 108/108 merged local B/C + D.0 tests PASS on Linux excluding the explicitly Windows-only module. Windows-specific tests remain for your machine.

**Not yet covered by runnable tests:** real Windows handle identity, real VM isolation, actual authenticated analyst service, real signing-key isolation, atomic CaseState revision enforcement, executable process cleanup, full analyzer input/output, response action. Those are explicit implementation acceptance gates in D.1–D.4.

## Baseline evaluation design

| Variable | Fixed pipeline | Rule workflow | Workflow-guided Agent |
|---|---|---|---|
| Core static model | same LightGBM artifact | same | same |
| Tool catalog and budgets | same | same | same |
| Known reputation policy | same trust constraints | same | same |
| Route selection | fixed sequence | deterministic conditional rules | rules + Agent follow-up within policy |
| Dynamic VM safety | identical | identical | identical |
| Human approval | identical | identical | identical |

Suggested metrics: detection F1, ROC-AUC/PR-AUC for ML component, FPR/FNR, coverage of unknown cases, time to assessment, tool-call count, unnecessary dynamic invocations, resource use, evidence completeness, escalation quality, invalid/blocked tool requests, response correctness, and safety violations. Split train/validation/test before tuning; avoid dataset contamination and compare on identical cases.

## D.0 exit criteria

- [x] Seven decisions captured in ADRs.
- [x] Source-based B/C v1.2 bridge and known mismatches documented.
- [x] Versioned JSON schemas, fixtures and contract validation prototype.
- [x] REA principle-to-project traceability.
- [x] Module ownership, PR boundaries and acceptance criteria.
- [x] Local schema/fixture mock tests run.
- [ ] Run package on actual Windows repository and capture test log.
- [ ] Implement trusted revision precondition and authenticated service (D.3; **not** D.0 deliverable).
- [ ] Prove real VM isolation and foreign-code execution safety (D.2/D.4; **not** D.0 deliverable).

**Interpretation:** D.0 design is ready for team review and D.1 work after Windows contract checks. This does not mean the complete Node D security boundary is implemented.
