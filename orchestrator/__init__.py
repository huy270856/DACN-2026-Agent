"""Orchestrator package for Trusted Tool Orchestrator (D1-D9).

Package-level exports are intentionally limited to the platform-independent
control-plane modules: D2 (registry), D3 (input_validator), D4 (policy_engine),
D7 (result_validator), D8 (trust), D9 (case_bridge) and the D1 WorkflowEngine.
These depend only on the standard library, `jsonschema` and the frozen D.0
contracts, so ``import orchestrator`` stays importable on any platform used for
contract/validation testing.

Windows-only submodules are NOT re-exported here (to avoid a hard ctypes/wintypes
import at package load on non-Windows contract-test hosts) and must be imported
explicitly by trusted, Windows-hosted integration code:
  * D5/D6: ``from orchestrator.executor import ToolExecutor, PinnedAdapter``
           ``from orchestrator.execution_control import ExecutionControl``
  * D2->D5 binding: ``from orchestrator.provider_install import ProviderInstallation``
  * D1 core: ``from orchestrator.core import Orchestrator``
(``orchestrator.core`` and ``orchestrator.provider_install`` transitively import
the Windows executor, hence are submodule-only like D5/D6.)
"""
from orchestrator.registry import (
    ToolRegistry,
    RegistryError,
    ToolUnknownError,
    ToolDisabledError,
    DuplicateToolError,
    ProviderMismatchError,
    ProviderUnavailableError,
    TargetUnsupportedError,
)
from orchestrator.input_validator import (
    validate_tool_call,
    ValidationError,
)
from orchestrator.result_validator import (
    validate_tool_result,
    normalize_ember_result,
    ResultValidationError,
)
from orchestrator.case_bridge import (
    CaseBridge,
    CaseBridgeError,
    StaleRevisionError,
    DeniedToolResultCommitError,
    ReceiptIntegrityError,
    TargetMismatchBridgeError,
    ToolMappingError,
)
from orchestrator.policy_engine import (
    PolicyEngine,
    PolicyConfig,
    PolicyError,
)
from orchestrator.trust import (
    TrustedSigner,
    MockSigner,
    KeyProvider,
    InMemoryKeyProvider,
    DpapiKeyProvider,
    ApprovalService,
    AnalystAuthenticator,
    LocalOsAuthenticator,
    StaticAuthenticator,
    TrustError,
    AuthenticationError,
    ApprovalExpiredError,
    ApprovalMismatchError,
    KeyCustodyError,
)
from orchestrator.workflow import WorkflowEngine

__all__ = [
    # D2 - Tool Registry
    "ToolRegistry",
    "RegistryError",
    "ToolUnknownError",
    "ToolDisabledError",
    "DuplicateToolError",
    "ProviderMismatchError",
    "ProviderUnavailableError",
    "TargetUnsupportedError",
    # D3 - Input Validator
    "validate_tool_call",
    "ValidationError",
    # D7 - Result Validator
    "validate_tool_result",
    "normalize_ember_result",
    "ResultValidationError",
    # D9 - Case Bridge
    "CaseBridge",
    "CaseBridgeError",
    "StaleRevisionError",
    "DeniedToolResultCommitError",
    "ReceiptIntegrityError",
    "TargetMismatchBridgeError",
    "ToolMappingError",
    # D4 - Policy Engine
    "PolicyEngine",
    "PolicyConfig",
    "PolicyError",
    # D8 - Trust & Approval
    "TrustedSigner",
    "MockSigner",
    "KeyProvider",
    "InMemoryKeyProvider",
    "DpapiKeyProvider",
    "ApprovalService",
    "AnalystAuthenticator",
    "LocalOsAuthenticator",
    "StaticAuthenticator",
    "TrustError",
    "AuthenticationError",
    "ApprovalExpiredError",
    "ApprovalMismatchError",
    "KeyCustodyError",
    # D1 - Workflow routing (core Orchestrator is a Windows-only submodule)
    "WorkflowEngine",
]
