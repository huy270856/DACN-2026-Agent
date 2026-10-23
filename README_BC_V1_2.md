# Node B/C v1.2 — REA-informed Compatibility Upgrade

**Scope:** TargetRef, additive EvidenceRecord v2, scoped unknown resolution, and regression tests. This is a compatibility patch, **not** Node D, an antivirus engine, or a security certification.

## Changes

| File | Change |
|---|---|
| `bc_contracts.py` | New `target-ref-v1`, `evidence-v2` helper contracts, validation, conservative cross-observation comparison |
| `context_collector.py` | New `file_identity` facet (`st_dev`, `st_ino`, size, mtime_ns); emits `target_ref` for FILE and PROCESS. SHA-256 is verified only when completed and file unchanged. |
| `case_state.py` | Preserves `casestate-v1` while adding `target_ref`, evidence provenance (`source`, `provider`, `content_origin`, `trust_level`, `limitations`), and scoped unknown metadata. |
| `case_manager.py` | Rejects changed target snapshots/digests on collection append; checks supplied signed ToolResult TargetRef; resolves gaps by target+scope; upgrades legacy CaseState in memory on valid write. |
| `test_bc_v1_2.py` | 14 tests covering real file replacement, spoofed snapshot, digest changes, nested backing-file scope, evidence provenance and legacy compatibility. |

## Install (PowerShell)

1. Back up the existing `case_manager.py`, `case_state.py`, and `context_collector.py`, or create a Git branch.
2. Extract the ZIP **into the repository root**, overwriting the three existing Python files and adding `bc_contracts.py`, `test_bc_v1_2.py` and this README.
3. Use the same Python virtual environment as Node B/C v1.1.

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_bc_v1_2
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Expected *if the repository still contains the 82 original Windows tests and no extra tests*: **96 total, about 94 pass + 2 skipped** (privileged symlink and optional 512 MiB streaming). Verify actual output; do not treat expected counts as results.

Linux validation for this package: **87/87 PASS** (original cross-platform tests plus 14 new tests; excludes Windows-only module). Windows-specific tests must be rerun on the user's machine.

## Contracts and limitations

### TargetRef v1

- `kind`: FILE or PROCESS
- `observed`: original path or PID+process creation time
- `snapshot`: file device/inode/size/mtime when observed; empty when unknown
- `verified_digest`: SHA-256 only if complete and file unchanged during collection
- `identity_strength`: STRONG, PARTIAL, UNAVAILABLE (descriptive; **not** an authorization)
- `revalidation_required`: always `true`

A file path, stat snapshot or hash **does not authorize execution**. Node D must reopen the actual file safely, check its handle identity and verify the intended binding immediately before use. An unavailable/partial identity cannot be treated as a verified target. Hashes do not prove that loaded process memory equals the backing file.

### Evidence v2 additive fields

- `evidence_schema_version`, `target_ref`, `source.kind/id/version`, nullable `provider`
- `limitations`, `trust_level`, `content_origin`, `parent_evidence_ids`, nullable `analysis_profile`
- All v1 evidence fields remain present, including `facet`, `value`, `status`, `collection_id`, `source_tool`, `coverage`.

`trust_level=UNTRUSTED_CONTENT` means the **content** may be malicious or prompt-injection-bearing even when the ToolResult envelope has a valid HMAC. Node D/Agent must not interpret extracted strings as instructions.

### Scoped unknown resolution

- Unknowns now have `scope` (`target`, `backing_file`, `case`) and target identity.
- A PROCESS tool observation cannot resolve an unknown attached to its FILE backing context merely because the facet names match.
- A successful child-file SHA-256 can resolve the process's explicitly requested `backing_file_sha256` gap.
- Legacy CaseState remains readable and can be updated. When legacy identity metadata is missing, it remains UNAVAILABLE; the patch cannot retroactively verify it.

## Not implemented here (Node D/D.0)

- Authenticated execution identity, protected HMAC key custody, real human authentication and approval workflow.
- Tool Registry, ToolSpec, provider binding, execution receipts, tool policy, sandbox, actual LightGBM integration.
- Artifact store, pagination, robust stale-lock recovery and process handle binding.
- Full REA source parity; design is informed by REA's evidence/tool principles, not copied implementation.

Reference: https://github.com/morluto/rea and the project `REA_BC_TO_D0_REVIEW.md`.

## Git (after Windows tests)

```powershell
git switch -c feat/bc-v1.2
git status
git add bc_contracts.py context_collector.py case_state.py case_manager.py test_bc_v1_2.py README_BC_V1_2.md
git diff --cached --stat
git commit -m "feat: add TargetRef and scoped evidence contracts to Node B/C v1.2"
git push -u origin feat/bc-v1.2
```

Never commit `cases/`, `collections/`, `test_large.bin`, or `windows-tests/large-256MiB.bin`.
