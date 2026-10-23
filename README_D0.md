# DACN D.0 — REA-informed Contracts & Architecture (v1)

**Status: DESIGN FREEZE CANDIDATE — executable schema fixtures and contract checks PASS; NOT an operational Orchestrator.**

Scope: versioned contracts, trust boundary, workflow decisions, team handoff and Node B/C v1.2 bridge. No malware execution, no actual approval service, no real signing, no response side effects.

## Integration into GitHub repo

Copy the contents of this package into the **root** of `DACN-2026-Agent`. It adds `d0/`, `docs/d0/`, `tests/test_d0_contracts.py`, `requirements-d0.txt`; it does not overwrite B/C files.

```powershell
cd C:\src\idk\DACN-2026-Agent
python -m pip install -r requirements-d0.txt
python -m unittest discover -s tests -p 'test_d0*.py' -v
# Then run existing B/C tests from repository root:
python -m unittest discover -s . -p 'test_*.py' -v
```

D.0 tests import the existing `bc_contracts.py` from B/C v1.2. If that file is missing, mock end-to-end checks intentionally fail. The D.0 suite passed 21/21 locally. A merged local B/C v1.2 smoke run passed 108/108 tests after excluding the explicitly Windows-only test module on Linux; **Windows-specific integration still needs to run in your repository**.

## Read in this order

1. `docs/d0/01_ARCHITECTURE_AND_ADRS.md` — architecture and seven decisions.
2. `docs/d0/02_CONTRACTS_AND_LIFECYCLE.md` — contract semantics, state machines, error classes, ownership.
3. `docs/d0/03_BC_V12_BRIDGE.md` — actual B/C integration; known gaps before D.3.
4. `docs/d0/04_REA_TRACEABILITY.md` — precise REA reference and intentional divergences.
5. `docs/d0/05_TEAM_HANDOFF.md` — 4-person ownership, D1–D9 tickets, acceptance gates.
6. `docs/d0/06_SECURITY_AND_TEST_PLAN.md` — security controls, adversarial tests, baselines.
7. `d0/schemas/*.schema.json` and `d0/fixtures/*.json` — machine-readable contracts.

## Important limits

- Schemas/validators are **design-time prototypes**, not authorization or execution enforcement.
- `verify_tool_call()` checks a CaseState snapshot but cannot prevent concurrent revision changes. Node D must enforce admission atomically with Node C (or re-check while holding the case lock).
- `receipt_sha256` detects accidental mismatch only; a hash is **not a signature**. Trusted D8 signing and secure key isolation are implementation work.
- A matching `TargetRef` is **not** sufficient proof of identity. D5 must revalidate the opened handle/VM-staged bytes, not a mutable path.
- REA is a reference for patterns, not a malware sandbox or a dependency of this package.
- Python orchestrator, language-neutral analyzer adapters: Rust/C++/Go/Node can emit canonical JSON through a restricted subprocess/IPC adapter.
