# D.0 Contracts, semantics, and lifecycle

## Machine-readable contracts (Draft 2020-12)

All schemas in `d0/schemas/` are **d0-v1**. JSON Schema checks shape; `d0/validate.py` additionally checks cross-field invariants. Schema IDs use `example.invalid` placeholders to identify internal documents; they are **not network URLs to fetch**.

| Contract | Producer -> consumer | Purpose |
|---|---|---|
| `target_ref` | B -> C/D | Reuse exact `target-ref-v1` B/C envelope; mutable observation, not authority |
| `provider` | D2 -> D1/D5/D7 | Concrete ID/version/adapter/runtime |
| `effects` | D2 -> D4 | Possible side effects; metadata is not permission |
| `limits` | D2/D4 -> D5/D6 | Upper bounds; effective budget must be <= spec and policy |
| `tool_spec` | D2 -> D3/D4/Agent discovery | One versioned capability and one bound provider |
| `tool_call` | Workflow/Agent/analyst -> D3 | Request with case/revision/target and explicit budgets |
| `policy_decision` | D4 -> D1 | ALLOW / DENY / REQUIRE_APPROVAL and reason |
| `execution_receipt` | D5/D6 -> D7/D8 | Immutable observed run facts, target binding, cleanup state |
| `observation` | adapter/D7 -> D9 | Per-facet status/coverage/value/trust/artifact |
| `tool_result` | D7 -> D8/D9 | Normalized observations + raw artifact refs + receipt digest |
| `artifact` | D5/D7 -> store | Relative artifact reference with digest, size and media type |
| `approval_request` | response planner -> approval service | Exact proposed action; status PENDING |
| `approval_event` | authenticated analyst service -> D8 | Signed/attested decision record; schema alone does not authenticate |
| `workflow_decision` | workflow -> D1/Agent | Deterministic routing decision, independent of LLM |

## Tool execution lifecycle

```text
PROPOSED -> VALIDATED -> POLICY_EVALUATED
                           | DENY -> REJECTED (no execution)
                           | REQUIRE_APPROVAL -> WAITING_APPROVAL -> [recheck]
                           | ALLOW
                           v
                 ADMITTED -> TARGET_REVALIDATED
                                | fail -> REJECTED
                                v
                             RUNNING
                 /SUCCESS/PARTIAL/FAILED/TIMEOUT/CANCELLED\
                                v
                       CLEANUP (complete/incomplete)
                                v
                   VALIDATE -> SIGN -> COMMIT TO CASE
```

**Atomicity:** D3 snapshot check is advisory. D1/D9 must hold an appropriate case lock / atomic compare-and-swap during final admission/commit. A stale case revision must cause replan/re-evaluation, not overwrite a newer case. Locking during long tool runs is undesirable; use reservation/lease or revision-aware commit with revalidation. Exact mechanism is D.3 implementation work.

**Idempotency:** `call_id` unique per request; `run_id` unique per attempt; `decision_id` unique per policy decision. D1 maintains a durable ledger. Same `call_id` with same canonical payload must not execute twice; same ID with different payload -> `IDEMPOTENCY_CONFLICT`. Retries require new run ID and a fresh policy decision if the original run may have started. No blind retries for foreign code or mutating effects.

**Target binding:** Re-check actual opened file handle (or immutable VM-staged copy and its SHA-256), process PID + start time, file identity, path/reparse constraints. Do not treat `same_target_ref()` alone as verified binding. The execution receipt must record `VERIFIED`, `REJECTED`, or `UNAVAILABLE`; success requires verified binding.

**Results:** `SUCCESS` means tool operation completed, not that malware is benign or all facets were observed. For each facet: `SUCCESS + COMPLETE + []` means observed empty; `UNAVAILABLE + NONE + null` means unknown; `NOT_COLLECTED` is distinct. `PARTIAL` at run level can retain completed observations. A non-success observation must have null inline value in this contract; completed partial evidence goes in a separate SUCCESS observation or artifact with explicit coverage.

**Trust:** Provider/target content is `UNTRUSTED_CONTENT` even if result envelope is signed. Never interpret strings, logs, code or stdout as instructions to the Agent. HMAC authenticates a producer boundary, not malware verdict truth. `receipt_sha256` is only a linkage digest, not authentication.

**Artifacts:** Keep large raw outputs outside CaseState; digest-verify at read and write. Relative path must be resolved under an approved case-owned root with reparse/symlink protections; JSON Schema cannot enforce path containment. Output budget, max artifact bytes, file count and pagination must be enforced in D5/D7; limits here are illustrative per-tool bounds, not global defaults.

**Approval:** Pending approval is not authorization. Approval event must be bound to exact action, case revision, target, expiration, authenticated analyst, and single-use nonce/signature. The sample `approval_event.json` is only a structural fixture and MUST NOT be treated as an authorized approval. D8 service must verify real authentication and persist audit.

## Typed error taxonomy (proposed for implementation)

`SCHEMA_INVALID`, `TOOL_UNKNOWN`, `TOOL_DISABLED`, `PROVIDER_UNAVAILABLE`, `PROVIDER_MISMATCH`, `TARGET_IDENTITY_UNAVAILABLE`, `TARGET_CHANGED`, `CASE_REVISION_STALE`, `POLICY_DENIED`, `APPROVAL_REQUIRED`, `APPROVAL_EXPIRED`, `AUTHENTICATION_FAILED`, `BUDGET_EXCEEDED`, `TIMEOUT`, `CANCELLED`, `CLEANUP_INCOMPLETE`, `RESULT_INVALID`, `ARTIFACT_INTEGRITY_FAILED`, `IDEMPOTENCY_CONFLICT`, `INTERNAL_ERROR`.

Errors should include stable `code`, human-readable `message`, relevant IDs, and optional untrusted diagnostic artifact refs; never secrets or raw stack traces. `TIMEOUT` and `CANCELLED` differ; cleanup failure must remain visible even if earlier operation produced observations.

## Workflow state machine

```text
INTAKE -> REPUTATION
  KNOWN + trusted/fresh/consistent -> ASSESSMENT
  UNKNOWN/UNAVAILABLE/CONFLICT -> STATIC
STATIC -> ASSESSMENT if sufficient and policy permits
STATIC -> DYNAMIC only if additional evidence needed and isolated VM ready
STATIC -> HUMAN_REVIEW if dynamic needed but VM unavailable
DYNAMIC -> ASSESSMENT or HUMAN_REVIEW
ASSESSMENT -> RESPONSE_PROPOSAL -> POLICY -> AUTHENTICATED_APPROVAL
 -> RESPONSE_EXECUTION -> VERIFY -> CLOSED
```

No inference from missing evidence to benign. Dynamic is a separate authorized tool with `executes_foreign_code=true` and strict VM policy; a host subprocess must not be used to execute an untrusted PE.
