# DACN — Node C v1.1 Security Hardening

## Scope

Node B remains **Context Collector** (`context.json`). Node C remains **CaseState Builder + CaseManager** (`case_state.json`). No malware verdict generation, AI decision loop, OS quarantine, or external API is implemented here.

This package replaces only the four Node C files and adds one test file:

- `case_manager.py` — hardened CaseManager
- `case_state.py` — initializes conflict/authentication audit fields
- `test_case_manager.py` — adjusted existing regression tests for signed tool/response ingestion
- `test_security_resilience.py` — previously expected-failure P0 tests are now normal tests
- `test_node_c_hardening.py` — 20 additional security/recovery regression tests

Keep the existing `context_collector.py`, `test_context_collector.py`, `test_node_b_timeout.py`, `test_case_state.py`, `test_windows_advanced.py` in your repository.

## Install on Windows PowerShell

Run in repository root:

```powershell
Copy-Item .\case_manager.py .\case_manager_v1_backup.py
Copy-Item .\case_state.py .\case_state_v1_backup.py
Copy-Item .\test_case_manager.py .\test_case_manager_v1_backup.py
Copy-Item .\test_security_resilience.py .\test_security_resilience_v1_backup.py
```

Extract package ZIP into repository root and overwrite these four files; add `test_node_c_hardening.py`.

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_case_state test_case_manager test_security_resilience test_node_c_hardening
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Expected counts if your repository has the previous **62 tests** (including 9 P0 tests and 9 Windows advanced tests) + **20 new tests**: **82 total**, with **2 Windows skips** (symlink privilege and optional 512 MiB). The 73 cross-platform tests plus 9 Windows advanced tests make 82. In this package the original 9 P0 tests now run without expected failures. Exact totals may vary if extra test files exist.

Our Linux test: **73 tests, OK**, excluding Windows-only `test_windows_advanced.py`. Three real collector JSON files and one earlier `case_state.json` were also loaded successfully. Windows must be validated by you.

## Changes

1. `evidence_conflicts`: when SUCCESS observations for the same target and facet disagree, preserve both evidence records and add a potential conflict. Different times can legitimately explain changing values; conflict means **review needed**, not automatic evidence tampering.
2. Assessment cannot cite evidence in an unresolved conflict.
3. If later evidence conflicts with an existing assessment's cited evidence, mark `assessment.validity = STALE_CONFLICT`. Prevent closing a case or approving response while stale.
4. `resolve-conflict` is an analyst-review operation requiring signed authorization. It records selected evidence and rationale. A stale assessment can then be superseded; old assessment is preserved in `assessment_history`.
5. Tool results require a detached HMAC-SHA256 proof (case_id, role, payload, timestamp, nonce), checked before mutation; nonces are persisted to reject replay. Response records require a **separate** approval key and approver subject bound into the proof.
6. Public CLI refuses `tool-result`, `response`, and `resolve-conflict`; these must be ingested through a trusted adapter. Existing `init`, `show`, `collection`, `register-tool`, `action`, and `assessment` CLI operations remain available.

## Trust boundary — IMPORTANT

The HMAC verification code is **not an authentication server**. `apply_update(... trusted_keys=...)` is a **trusted in-process API**. A caller able to supply arbitrary `trusted_keys`, run arbitrary Python inside the trusted process, or read the keys can sign their own forged payloads. Thus the tests prove **envelope validation**, not protection against a malicious caller with code execution in the same Python process.

For real protection, implement a separate Orchestrator service/process under a different Windows account. The Agent and tools submit results to the Orchestrator via authenticated IPC; they must never call `apply_update` directly or access verifier keys. The Orchestrator must bind the actual executed tool identity and run ID to the signed payload. Human approval requires a separately authenticated human UI/service that verifies user identity and intent *before* signing the exact response description. The `approver` field and `human_approved` boolean alone are never proof. Enforce Windows ACLs on case files and key storage; otherwise an attacker can bypass the Python checks by editing JSON directly.

**Do not claim P0-08/P0-09 are end-to-end secure until the external trust boundary is implemented and tested.** Node C v1.1 defines and validates the ingestion contract only.

## Trusted adapter illustration (not a standalone auth service)

```python
import secrets
import case_manager as cm

# In a trusted Orchestrator/approval service only; never in the Agent/tool process.
keys = {'tool': secrets.token_bytes(32), 'approval': secrets.token_bytes(32)}
state = cm.read_json(case_path)
proof = cm.sign_for_trusted_boundary(state['case_id'], 'tool-result', tool_result, keys['tool'])
cm.apply_update(case_path, 'tool-result', tool_result, authorization=proof, trusted_keys=keys)
```

The snippet illustrates message integrity, **not** how to establish trust. Do not generate new keys per request in production; use protected persistent secrets with key rotation and an authenticated transport. Do not pass arbitrary caller-supplied keys into the verifier.

## Known limitations / future integration tests

- The existing `.json.lock` may remain after a process crash; it is not auto-removed. Recovery needs owner/PID verification and operational policy. Never blindly delete an active lock.
- Hash timeout in Node B is best-effort; blocked kernel I/O cannot be forcibly interrupted in-process.
- `evidence_conflicts` conservatively flags changing runtime observations. A future Agent needs temporal semantics, evidence quality, and resolution policies.
- The case file has an 8 MiB limit; large evidence should be stored as referenced artifacts.
- Approval signature verifies only that the configured approval signer signed the message, **not** that the signer correctly authenticated a human. This must be tested in the actual UI/IPC integration.
- HMAC key rotation, durable key management, signed audit chains, ACL verification, stale lock recovery, real PID reuse, and crash-after-replace durability are not exhaustively tested.

## How to interpret PASS

A test PASS means the specified behavior was observed. It does not mean the entire malware detection/response system is secure or complete. Node C is ready for **functional integration with a properly isolated Orchestrator**, not for autonomous execution of destructive responses.
