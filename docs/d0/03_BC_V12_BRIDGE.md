# Node B/C v1.2 -> D.0 Bridge (source-based audit)

Reviewed: `bc_contracts.py`, `case_state.py`, `case_manager.py` in supplied `bc_v1_2` patch. This is not a review of a newer remote branch.

## Already available

- `bc_contracts.target_ref_from_context`, `validate_target_ref`, `same_target_ref`: version `target-ref-v1` with FILE/PROCESS, snapshot, optional verified SHA-256, revalidation required.
- `bc_contracts.evidence_v2`: additive `evidence-v2`, source/provider/limitations/content origin/untrusted content.
- `case_state.build_case_state`: `casestate-v1`, evidence, residual unknowns, revisions, collections, history.
- `case_manager.apply_update`: lock + atomic write, revision increment, HMAC checks for `tool-result`, `response`, `resolve-conflict`, replay nonces, conflict invalidation.

## Exact current Node C ingestion contract

`apply_update(case_path, 'tool-result', payload, authorization=proof, trusted_keys={'tool': verifier_key})` is **trusted backend-only**; do not expose it to an Agent or generic CLI. The current payload requires:

```json
{
  "tool_run_id": "RUN-example001",
  "tool": "static_ember_features",
  "status": "SUCCESS",
  "target_type": "FILE",
  "target": {"path": "C:\\samples\\fixture.exe"},
  "target_ref": {"...": "exact B/C target-ref-v1 object"},
  "tool_version": "0.1.0",
  "provider": {"id": "ember_local", "version": "0.1.0"},
  "observations": [{"facet": "ember_feature_count", "status": "SUCCESS", "value": 2381,
                    "coverage": "limited", "limitations": []}]
}
```

Before ingestion, `_register_tool` must have registered the legacy snake_case tool name in `available_tools`; `context_collector` is reserved. The D2 ID `static.ember_features` **is not a valid legacy Node C name**; D9 must map `tool_id -> legacy tool name` explicitly and collision-free (e.g. `static.ember_features -> static_ember_features`). The mapping is a projection, not a second authority. D9 must retain full ToolSpec and receipt in its own signed audit ledger / artifact store.

**Important status mismatch:** Node C `_append_tool` currently accepts its `STATUSES` (SUCCESS/DEGRADED/FAILED/UNAVAILABLE), not D.0's `PARTIAL`, `TIMEOUT`, `CANCELLED`, `DENIED`, `NOT_COLLECTED`. D9 must translate run outcome to a legacy status while retaining original outcome and reason in immutable receipt. Example: `PARTIAL -> DEGRADED`, `TIMEOUT/CANCELLED -> FAILED`, `DENIED -> no tool-result commit; record denied action/ledger`. Per-facet `NOT_COLLECTED` cannot be passed as a Node C observation until Node C supports it; keep it in D audit / residual unknowns. This translation is lossy and MUST be documented.

**Important evidence limitation:** Node C's `_append_tool` uses `evidence_v2` but does not preserve every D.0 observation field (e.g. explicit `content_origin`, structured coverage and all artifact metadata). D9 must keep original signed result + receipt externally and store only a compatible projection in Node C until C v1.3 is approved.

**Important case revision limitation:** `apply_update` locks and increments revision, but currently does not accept `expected_revision` for tool-result admission. D9 cannot guarantee compare-and-swap by reading the file first. Add a trusted `expected_revision` precondition checked **inside `locked_case`** before mutation, or implement a reservation/commit design. This is a D.3 blocker, not solved by D.0 validators.

**Important trust limitation:** Node C `sign_for_trusted_boundary()` can produce HMAC proofs, but using it in an untrusted process or exposing the key would defeat authorization. D8 must hold keys in trusted backend only; real local login must be verified separately.

## D9 adapter checklist

1. Read case, validate `casestate-v1` + target ref and revision; no trust in Agent-supplied paths.
2. Map canonical tool ID to legacy snake_case name, register only approved tool projection.
3. Verify D7 result + receipt, provider binding, artifact digests and trusted D8 signature.
4. Translate status explicitly, preserve original result and receipt in append-only trusted store.
5. Commit through Node C with protected proof and atomic revision precondition; on mismatch fail/replan, not silent retry.
6. Confirm returned revision/evidence IDs; retain ledger linking `call_id`, `run_id`, `decision_id`, `case_id` and source artifacts.
7. Verify unknown resolution uses correct target+scope; backing-file vs process evidence must not cross-resolve.

## Compatibility tests needed at D.3

- Old CaseState v1 opens without data loss.
- Nested backing-file unknowns remain scoped.
- Stale concurrent revision rejected inside lock.
- Signed result with swapped provider rejected before Node C.
- Failure/cancellation does not become SUCCESS.
- Duplicate call/run cannot execute/commit twice.
- Tampered artifact, untrusted prompt-injection text, and oversized output fail safely.
- Missing hash / unavailable process start time cannot become verified identity.
