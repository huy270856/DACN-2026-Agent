"""D2 - Tool Registry implementation for DACN D.0 Orchestrator.

Manages versioned ToolSpec entries, capabilities, provider binding,
and availability without silent fallbacks.
"""
from __future__ import annotations
import copy
from typing import Any, Dict, List, Optional, Tuple

from d0.validate import validate, ContractError


class RegistryError(Exception):
    """Base exception for D2 Tool Registry errors."""
    pass


class ToolUnknownError(RegistryError):
    """Raised when looking up an unregistered tool ID."""
    pass


class ToolDisabledError(RegistryError):
    """Raised when accessing a tool that is currently disabled."""
    pass


class DuplicateToolError(RegistryError):
    """Raised when registering a tool with an identical tool_id and tool_version."""
    pass


class ProviderMismatchError(RegistryError):
    """Raised when a caller requests a provider differing from the pinned ToolSpec provider."""
    pass


class ProviderUnavailableError(RegistryError):
    """Raised when a pinned provider is marked unavailable."""
    pass


class TargetUnsupportedError(RegistryError):
    """Raised when a tool is requested for an unsupported target kind."""
    pass


class ToolRegistry:
    """Versioned Tool Registry for Node D (D2).
    
    Guarantees:
    - Immutable provider binding (ADR-005): each ToolSpec binds exactly one provider.
    - No silent fallback: mismatched or unavailable providers raise typed errors.
    - Strict schema validation using d0.validate.
    - Capabilities discovery and target kind filtering.
    """

    def __init__(self) -> None:
        # Key: (tool_id, tool_version) -> tool_spec dict
        self._tools: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # Key: tool_id -> list of versions registered (in order of registration)
        self._version_index: Dict[str, List[str]] = {}
        # Key: capability -> list of (tool_id, tool_version)
        self._capability_index: Dict[str, List[Tuple[str, str]]] = {}
        # Key: provider_id -> bool (availability status, default True)
        self._provider_status: Dict[str, bool] = {}

    def register_tool(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new ToolSpec.

        Args:
            spec: ToolSpec dictionary conforming to d0/schemas/tool_spec.schema.json.

        Returns:
            The validated ToolSpec stored in the registry.

        Raises:
            ContractError: If the ToolSpec fails d0 schema or invariant validation.
            DuplicateToolError: If (tool_id, tool_version) already exists.
        """
        # Validate against D.0 schema and constraints
        validate('tool_spec', spec)

        tool_id: str = spec['tool_id']
        tool_version: str = spec['tool_version']
        key = (tool_id, tool_version)

        if key in self._tools:
            raise DuplicateToolError(
                f"Tool '{tool_id}' version '{tool_version}' is already registered."
            )

        stored_spec = copy.deepcopy(spec)
        self._tools[key] = stored_spec

        # Update version index
        if tool_id not in self._version_index:
            self._version_index[tool_id] = []
        self._version_index[tool_id].append(tool_version)

        # Update capability index
        capability: str = spec['capability']
        if capability not in self._capability_index:
            self._capability_index[capability] = []
        if key not in self._capability_index[capability]:
            self._capability_index[capability].append(key)

        # Initialize provider availability if not tracked yet
        provider_id = spec['provider']['id']
        if provider_id not in self._provider_status:
            self._provider_status[provider_id] = True

        return copy.deepcopy(stored_spec)

    def get_tool(
        self,
        tool_id: str,
        tool_version: Optional[str] = None,
        *,
        require_enabled: bool = True
    ) -> Dict[str, Any]:
        """Retrieve a registered ToolSpec by tool_id and optional version.

        Args:
            tool_id: The canonical tool ID.
            tool_version: Optional version string. If None, the latest registered version is used.
            require_enabled: If True, raises ToolDisabledError when the tool is disabled.

        Returns:
            A deep copy of the ToolSpec.

        Raises:
            ToolUnknownError: If tool_id (or specified version) is not found.
            ToolDisabledError: If tool is disabled and require_enabled is True.
        """
        if tool_id not in self._version_index or not self._version_index[tool_id]:
            raise ToolUnknownError(f"Tool '{tool_id}' is not registered.")

        if tool_version is None:
            # Default to the most recently registered version
            resolved_version = self._version_index[tool_id][-1]
        else:
            resolved_version = tool_version

        key = (tool_id, resolved_version)
        if key not in self._tools:
            raise ToolUnknownError(
                f"Tool '{tool_id}' version '{resolved_version}' is not registered."
            )

        spec = self._tools[key]
        if require_enabled and not spec.get('enabled', False):
            raise ToolDisabledError(
                f"Tool '{tool_id}' version '{resolved_version}' is currently disabled."
            )

        return copy.deepcopy(spec)

    def set_enabled(
        self,
        tool_id: str,
        enabled: bool,
        tool_version: Optional[str] = None
    ) -> None:
        """Enable or disable a tool.

        Args:
            tool_id: Canonical tool ID.
            enabled: Boolean flag to enable or disable.
            tool_version: Optional version. If None, applies to all versions of the tool.

        Raises:
            ToolUnknownError: If tool_id (or version) is not found.
        """
        if tool_id not in self._version_index:
            raise ToolUnknownError(f"Tool '{tool_id}' is not registered.")

        if tool_version is not None:
            key = (tool_id, tool_version)
            if key not in self._tools:
                raise ToolUnknownError(
                    f"Tool '{tool_id}' version '{tool_version}' is not registered."
                )
            self._tools[key]['enabled'] = bool(enabled)
        else:
            for version in self._version_index[tool_id]:
                self._tools[(tool_id, version)]['enabled'] = bool(enabled)

    def set_provider_availability(self, provider_id: str, is_available: bool) -> None:
        """Set the availability status of an underlying provider."""
        self._provider_status[provider_id] = bool(is_available)

    def is_provider_available(self, provider_id: str) -> bool:
        """Check if a provider is marked available."""
        return self._provider_status.get(provider_id, True)

    def resolve_provider(
        self,
        tool_id: str,
        tool_version: Optional[str] = None,
        requested_provider_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve and verify provider binding for a tool invocation (ADR-005).

        Args:
            tool_id: Canonical tool ID.
            tool_version: Optional tool version.
            requested_provider_id: Optional provider ID requested by caller.

        Returns:
            The bound provider dictionary (`id`, `version`, `adapter`, `runtime`).

        Raises:
            ToolUnknownError: If tool not registered.
            ToolDisabledError: If tool is disabled.
            ProviderMismatchError: If requested_provider_id does not match the pinned provider.
            ProviderUnavailableError: If the bound provider is unavailable.
        """
        spec = self.get_tool(tool_id, tool_version, require_enabled=True)
        pinned_provider = spec['provider']
        pinned_id = pinned_provider['id']

        if requested_provider_id is not None and requested_provider_id != pinned_id:
            raise ProviderMismatchError(
                f"Requested provider '{requested_provider_id}' mismatch with pinned provider "
                f"'{pinned_id}' for tool '{tool_id}'. Silent fallback is prohibited (ADR-005)."
            )

        if not self.is_provider_available(pinned_id):
            raise ProviderUnavailableError(
                f"Provider '{pinned_id}' for tool '{tool_id}' is currently unavailable."
            )

        return copy.deepcopy(pinned_provider)

    def validate_target_support(
        self,
        tool_id: str,
        target_kind: str,
        tool_version: Optional[str] = None
    ) -> bool:
        """Check whether a tool supports the specified target kind ('FILE' or 'PROCESS').

        Raises:
            TargetUnsupportedError: If target_kind is not supported.
        """
        spec = self.get_tool(tool_id, tool_version, require_enabled=False)
        supported = spec.get('supported_targets', [])
        if target_kind not in supported:
            raise TargetUnsupportedError(
                f"Tool '{tool_id}' does not support target kind '{target_kind}'. "
                f"Supported targets: {supported}"
            )
        return True

    def list_tools(self, only_enabled: bool = False) -> List[Dict[str, Any]]:
        """List all registered tools."""
        results = []
        for spec in self._tools.values():
            if only_enabled and not spec.get('enabled', False):
                continue
            results.append(copy.deepcopy(spec))
        return results

    def list_capabilities(self) -> List[str]:
        """List all distinct capabilities registered."""
        return sorted(self._capability_index.keys())

    def find_by_capability(
        self,
        capability: str,
        *,
        target_kind: Optional[str] = None,
        only_enabled: bool = True
    ) -> List[Dict[str, Any]]:
        """Find tools offering a specific capability, optionally filtered by target kind."""
        keys = self._capability_index.get(capability, [])
        matches = []
        for key in keys:
            spec = self._tools[key]
            if only_enabled and not spec.get('enabled', False):
                continue
            if target_kind is not None and target_kind not in spec.get('supported_targets', []):
                continue
            matches.append(copy.deepcopy(spec))
        return matches

    def unregister_tool(self, tool_id: str, tool_version: str) -> bool:
        """Remove a tool version from the registry (primarily for test cleanup)."""
        key = (tool_id, tool_version)
        if key not in self._tools:
            return False
        spec = self._tools.pop(key)
        if tool_id in self._version_index:
            self._version_index[tool_id] = [v for v in self._version_index[tool_id] if v != tool_version]
            if not self._version_index[tool_id]:
                del self._version_index[tool_id]
        capability = spec.get('capability')
        if capability in self._capability_index:
            self._capability_index[capability] = [k for k in self._capability_index[capability] if k != key]
            if not self._capability_index[capability]:
                del self._capability_index[capability]
        return True
