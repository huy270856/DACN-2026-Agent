"""Orchestrator package for Trusted Tool Orchestrator (D1-D9).

Package-level exports are intentionally limited to the platform-independent
control-plane modules: D2 (registry), D3 (input_validator), D7 (result_validator)
and D9 (case_bridge). These depend only on the standard library, `jsonschema`
and the frozen D.0 contracts, so ``import orchestrator`` stays importable on any
platform used for contract/validation testing.

D5/D6 (``orchestrator.executor`` / ``orchestrator.execution_control``) are
Windows-only (Win32 locked handles + Job Objects) and MUST be imported
explicitly from their submodules by trusted, Windows-hosted integration code,
e.g. ``from orchestrator.executor import ToolExecutor, PinnedAdapter``. They are
deliberately NOT re-exported here to avoid a hard ctypes/wintypes import at
package load time on non-Windows contract-test hosts.
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
]
