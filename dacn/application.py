"""Application wiring: call the real Node B / Node C / Node D Python APIs.

No business logic is duplicated here; this module only sequences existing public
APIs and shapes their results for the CLI. Node D (Windows-only) classes are
imported lazily inside ``smoke`` so that ``intake``/``inspect`` never depend on
the Windows executor.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import context_collector as nodeb      # Node B (side-effect-free import)
import case_state as cs                # Node C
import case_manager as cm              # Node C
from .config import AppConfig


class ApplicationError(Exception):
    """Base error surfaced to the CLI with a clean message (no stack trace)."""


class InvalidCaseIdError(ApplicationError):
    pass


class CaseNotFoundError(ApplicationError):
    pass


class TargetMismatchError(ApplicationError):
    pass


class SmokeUnsupportedError(ApplicationError):
    pass


# --------------------------------------------------------------------------- #
# intake
# --------------------------------------------------------------------------- #
def _summarize_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
    facets = ctx.get("facets", {})
    tref = ctx.get("target_ref") or {}
    vd = tref.get("verified_digest") or {}
    fmt_facet = facets.get("format") or {}
    fmt_value = fmt_facet.get("value") if fmt_facet.get("status") == "SUCCESS" else None
    return {
        "collection_id": ctx.get("collection_id"),
        "collection_status": ctx.get("status"),
        "target_type": ctx.get("target_type"),
        "sha256": vd.get("value"),
        "identity_strength": tref.get("identity_strength"),
        "format": (fmt_value or {}).get("format") if fmt_value else fmt_facet.get("status"),
        "format_detail": fmt_value,
    }


def _persist_intake(ctx: Dict[str, Any], config: AppConfig,
                    case_id: Optional[str]) -> Dict[str, Any]:
    # Keep the raw Node B context for provenance (unique dir per collection).
    context_path = nodeb.save_context(ctx, config.collections_dir)
    summary = _summarize_context(ctx)
    summary["context_path"] = str(context_path)

    if case_id is None:
        state = cs.build_case_state(ctx, source_path=str(context_path))
        case_state_path = cs.save_case_state(state, config.cases_dir)
        summary.update(case_id=state["case_id"], revision=state.get("revision", 1),
                       case_action="created", case_state_path=str(case_state_path))
        return summary

    # Update an existing case with a new collection; Node C enforces identity.
    try:
        case_file = cm.case_path(config.cases_dir, case_id)
    except ValueError as exc:
        raise InvalidCaseIdError(f"Invalid case id: {exc}") from exc
    if not case_file.exists():
        raise CaseNotFoundError(f"Case not found: {case_id}")
    try:
        result = cm.apply_update(case_file, "collection", ctx, source_path=str(context_path))
    except ValueError as exc:
        # _append_collection raises on target/identity mismatch or duplicate collection id.
        raise TargetMismatchError(str(exc)) from exc
    summary.update(case_id=result["case_id"], revision=result["revision"],
                   case_action="updated", case_state_path=str(case_file))
    return summary


def intake_file(path: str, config: AppConfig, *, case_id: Optional[str] = None,
                hash_timeout: Optional[float] = None, progress: bool = False) -> Dict[str, Any]:
    config.ensure_dirs()
    ctx = nodeb.collect_file_context(path, progress, hash_timeout)
    return _persist_intake(ctx, config, case_id)


def intake_pid(pid: int, config: AppConfig, *, case_id: Optional[str] = None,
               include_backing_file: bool = False, hash_timeout: Optional[float] = None,
               progress: bool = False) -> Dict[str, Any]:
    config.ensure_dirs()
    ctx = nodeb.collect_process_context(pid, progress, include_backing_file, hash_timeout)
    return _persist_intake(ctx, config, case_id)


# --------------------------------------------------------------------------- #
# inspect
# --------------------------------------------------------------------------- #
def inspect_case(case_id: str, config: AppConfig) -> Dict[str, Any]:
    try:
        case_file = cm.case_path(config.cases_dir, case_id)
    except ValueError as exc:
        raise InvalidCaseIdError(f"Invalid case id: {exc}") from exc
    if not case_file.exists():
        raise CaseNotFoundError(f"Case not found: {case_id}")
    state = cm.validate_case(cm.read_json(case_file))   # reads the REAL persisted state

    def facet_value(name):
        for e in state.get("evidence", []):
            if e.get("facet") == name and e.get("status") == "SUCCESS":
                return e.get("value")
        return None

    fmt = facet_value("format")
    evidence = [{"evidence_id": e.get("evidence_id"), "facet": e.get("facet"),
                 "status": e.get("status"),
                 "source": (e.get("source") or {}).get("kind"),
                 "trust_level": e.get("trust_level")}
                for e in state.get("evidence", [])]
    return {
        "case_id": state["case_id"],
        "revision": state.get("revision", 1),
        "lifecycle_status": state["lifecycle_status"],
        "target_type": state["target_type"],
        "target": state["target"],
        "target_ref": state.get("target_ref"),
        "sha256": facet_value("sha256"),
        "format": (fmt or {}).get("format") if isinstance(fmt, dict) else None,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "residual_unknowns": [{"facet": u.get("facet"), "scope": u.get("scope"),
                               "reason": u.get("reason")}
                              for u in state.get("residual_unknowns", [])],
        "case_state_path": str(case_file),
    }


# --------------------------------------------------------------------------- #
# smoke (Windows-only Node D wiring with a FIXED benign mock analyzer)
# --------------------------------------------------------------------------- #
def _smoke_tool_spec(provider: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "d0-v1", "tool_id": "static.ember_features",
        "tool_version": "0.1.0", "capability": "static.pe_features",
        "description": "Benign mock static feature extractor (smoke only)",
        "input_schema_id": "ember-input-v1", "output_schema_id": "ember-output-v1",
        "provider": provider,
        "effects": {"reads_target": True, "executes_foreign_code": False,
                    "writes_filesystem": False, "mutates_target": False,
                    "requires_human_approval": False, "cleanup_required": False},
        "limits": {"timeout_ms": 30000, "max_output_bytes": 262144,
                   "max_artifact_bytes": 1048576, "max_concurrency": 1},
        "supported_targets": ["FILE"], "enabled": True,
    }


def _smoke_tool_call(case_id: str, target_ref: Dict[str, Any]) -> Dict[str, Any]:
    import copy
    return {
        "schema_version": "d0-v1", "call_id": "CALL-smoke00000001",
        "case_id": case_id, "expected_revision": 1,
        "tool_id": "static.ember_features", "tool_version": "0.1.0",
        "provider_id": "ember_mock", "target_ref": copy.deepcopy(target_ref),
        "arguments": {"feature_version": 2},
        "reason": "unified-application smoke", "requested_by": "workflow",
        "requested_at": "2026-11-08T00:00:00Z",
        "budget": {"timeout_ms": 20000, "max_output_bytes": 200000},
    }


def smoke(config: AppConfig) -> Dict[str, Any]:
    """Initialize and exercise D1-D9 end to end with a FIXED benign mock analyzer.

    The adapter command, pins, policy and signing key are all fixed in app code;
    the CLI exposes NO way to inject an adapter command, executable path or policy.
    The user's analysis target is never involved and never executed. Returns a
    clear unsupported result on non-Windows instead of faking a pass.
    """
    if os.name != "nt":
        return {"supported": False,
                "reason": "Node D executor is Windows-only; smoke is unsupported on this platform"}

    import sys
    import hashlib
    from orchestrator.registry import ToolRegistry
    from orchestrator.policy_engine import PolicyEngine, PolicyConfig
    from orchestrator.trust import TrustedSigner, InMemoryKeyProvider
    from orchestrator.provider_install import ProviderInstallation
    from orchestrator.case_bridge import CaseBridge
    from orchestrator.core import Orchestrator
    from orchestrator.executor import PinnedAdapter

    config.ensure_dirs()
    repo_root = Path(__file__).resolve().parents[1]
    adapter_script = repo_root / "tests" / "fixtures" / "ember_mock_adapter.py"
    if not adapter_script.exists():
        return {"supported": False, "reason": "benign mock analyzer fixture is missing"}

    # 1. Node B collects a benign INTERNAL fixture (never user input, never executed).
    sample = config.artifacts_dir / "_smoke_sample.bin"
    sample.write_bytes(b"MZ benign smoke fixture; not executable\x00" * 40)
    ctx = nodeb.collect_file_context(str(sample))
    target_ref = ctx["target_ref"]

    # 2. Node C creates a case from the real collected context.
    state = cs.build_case_state(ctx)
    case_file = cs.save_case_state(state, config.cases_dir)
    case_id = state["case_id"]

    # 3. Node D assembled from real public APIs; FIXED provider binding + TEST key.
    interpreter = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
    script = str(adapter_script.resolve())
    pins = [[p, hashlib.sha256(Path(p).read_bytes()).hexdigest()] for p in (interpreter, script)]
    adapter = PinnedAdapter("ember_mock", "0.1.0", "ember_mock_adapter",
                            (interpreter, "-I", script), tuple((p, s) for p, s in pins))
    spec = _smoke_tool_spec(adapter.provider())
    registry = ToolRegistry()
    registry.register_tool(spec)
    installation = ProviderInstallation()
    installation.install(provider_id="ember_mock", version="0.1.0",
                         adapter_id="ember_mock_adapter",
                         command=(interpreter, "-I", script), pins=pins)
    policy = PolicyEngine(PolicyConfig(
        tool_allowlist=frozenset({("static.ember_features", "0.1.0", "ember_mock")}),
        budget_caps={"timeout_ms": 30000, "max_output_bytes": 262144,
                     "max_artifact_bytes": 1048576, "max_concurrency": 1}))
    signer = TrustedSigner(InMemoryKeyProvider())   # explicit TEST key provider
    bridge = CaseBridge(audit_ledger_root=config.ledgers_dir)
    orch = Orchestrator(registry=registry, policy=policy, signer=signer,
                        installation=installation, bridge=bridge,
                        artifact_root=config.artifacts_dir,
                        run_ledger_path=config.run_ledger_path)

    record = orch.run_tool_call(_smoke_tool_call(case_id, target_ref), case_file)
    final = cm.read_json(case_file)
    committed = any(e.get("facet") == "static.ember_features"
                    for e in final.get("evidence", []))
    return {
        "supported": True,
        "case_id": case_id,
        "phase": record.phase,
        "outcome": record.outcome,
        "run_id": record.run_id,
        "revision": record.revision,
        "d7_validated_and_d9_committed": bool(committed),
        "signer": "InMemoryKeyProvider (explicit TEST key; not a production key store)",
        "note": "Benign mock analyzer only - NOT real EMBER/LightGBM, Ghidra or REA.",
    }
