"""Trusted provider installation binding (D2 Registry -> D5 Executor).

The D2 ToolRegistry (``orchestrator.registry``) stores a ToolSpec whose
``provider`` block names ``id``/``version``/``adapter``/``runtime`` but carries
NO executable path and NO code pins. The D5 executor
(``orchestrator.executor.ToolExecutor.execute``) instead requires a
``PinnedAdapter`` with the absolute command and its SHA-256 pins. This module is
the minimal trusted binding that closes that gap.

SECURITY — the installation data (command + pins) comes ONLY from a trusted
backend configuration supplied out-of-band by the operator/installer. It is
NEVER derived from a ToolCall, from ToolSpec fields, from Agent input or from
any provider payload. ``pinned_adapter_for`` only *looks up* an installation by
the ToolSpec's provider identity; it cannot inject a path. No execution, no
network IO, no filesystem IO happens here. This is control-plane wiring that
would normally be owned by D1/the backend installer, not by D2/D5 themselves.

This module imports the Windows-only D5 submodule (``orchestrator.executor``)
because the ``PinnedAdapter`` type lives with the executor it feeds; it is used
only on the Windows execution path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from orchestrator.executor import PinnedAdapter


class ProviderInstallError(Exception):
    """Base error for provider installation binding."""


class ProviderNotInstalledError(ProviderInstallError):
    """Raised when no trusted installation matches a ToolSpec provider."""


class ProviderBindingMismatchError(ProviderInstallError):
    """Raised when the ToolSpec provider block disagrees with the installation."""


class InvalidInstallationError(ProviderInstallError):
    """Raised when a trusted-config entry is structurally invalid."""


def _check_pin(path: str, sha: str) -> Tuple[str, str]:
    p = Path(path)
    if not isinstance(path, str) or not p.is_absolute() or str(p).startswith(("\\\\", "//")):
        raise InvalidInstallationError("Pinned path must be a local absolute path")
    if ".." in p.parts or any(":" in part for part in p.parts[1:]):
        raise InvalidInstallationError("Pinned path contains traversal or alternate stream")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha.lower()):
        raise InvalidInstallationError("Pin SHA-256 must be 64 lowercase hex chars")
    return (str(p), sha.lower())


class ProviderInstallation:
    """Registry of trusted provider installations, keyed by provider identity.

    Keyed by ``(provider_id, version, adapter_id)`` — the same tuple a D2
    ToolSpec pins via ADR-005. Only the operator/installer populates it.
    """

    def __init__(self) -> None:
        self._installed: Dict[Tuple[str, str, str], PinnedAdapter] = {}

    def install(self, *, provider_id: str, version: str, adapter_id: str,
                command: Sequence[str], pins: Sequence[Sequence[str]],
                runtime: str = "subprocess") -> PinnedAdapter:
        """Install one trusted provider binding from backend configuration.

        command: fixed executable + adapter prefix (absolute paths for code).
        pins: iterable of (absolute_path, sha256_hex) covering every code-bearing
              file, including command[0].
        """
        if runtime != "subprocess":
            raise InvalidInstallationError("Only the subprocess runtime is supported by D5")
        if not command or not all(isinstance(part, str) and part for part in command):
            raise InvalidInstallationError("command must be a non-empty tuple of strings")
        exe = Path(command[0])
        if not exe.is_absolute():
            raise InvalidInstallationError("command[0] must be an absolute executable path")
        if exe.suffix.lower() != ".exe":
            raise InvalidInstallationError("command[0] must be a native .exe (no batch/shell launcher)")
        checked_pins = tuple(_check_pin(path, sha) for path, sha in pins)
        pin_paths = {path for path, _ in checked_pins}
        if command[0] not in pin_paths:
            raise InvalidInstallationError("command[0] must be pinned")
        # Every absolute code argument must also be pinned (mirrors executor policy).
        for arg in command:
            if Path(arg).is_absolute() and arg not in pin_paths:
                raise InvalidInstallationError(f"Unpinned absolute command argument: {arg}")
        if not all(isinstance(x, str) and x for x in (provider_id, version, adapter_id)):
            raise InvalidInstallationError("provider_id/version/adapter_id must be non-empty strings")
        adapter = PinnedAdapter(
            provider_id=provider_id, version=version, adapter_id=adapter_id,
            command=tuple(command), pins=checked_pins,
        )
        self._installed[(provider_id, version, adapter_id)] = adapter
        return adapter

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "ProviderInstallation":
        """Build from a trusted config dict: {'providers': [ {...}, ... ]}.

        The caller must have loaded this from a trusted source (operator-owned
        file / secret store), never from Agent/ToolCall/provider output.
        """
        if not isinstance(config, Mapping) or not isinstance(config.get("providers"), list):
            raise InvalidInstallationError("config must be a mapping with a 'providers' list")
        inst = cls()
        for entry in config["providers"]:
            if not isinstance(entry, Mapping):
                raise InvalidInstallationError("Each provider entry must be a mapping")
            inst.install(
                provider_id=entry.get("provider_id"),
                version=entry.get("version"),
                adapter_id=entry.get("adapter_id"),
                command=entry.get("command", ()),
                pins=entry.get("pins", ()),
                runtime=entry.get("runtime", "subprocess"),
            )
        return inst

    def pinned_adapter_for(self, spec: Mapping[str, Any]) -> PinnedAdapter:
        """Return the installed PinnedAdapter bound to this ToolSpec's provider.

        Looks up strictly by the ToolSpec provider identity; raises if the tool
        has no trusted installation (no silent fallback, ADR-005).
        """
        provider = spec.get("provider")
        if not isinstance(provider, Mapping):
            raise ProviderBindingMismatchError("ToolSpec has no provider block")
        key = (provider.get("id"), provider.get("version"), provider.get("adapter"))
        adapter = self._installed.get(key)
        if adapter is None:
            raise ProviderNotInstalledError(
                f"No trusted installation for provider {key}; refusing silent fallback"
            )
        if provider.get("runtime") != "subprocess":
            raise ProviderBindingMismatchError("ToolSpec provider runtime is not subprocess")
        if adapter.provider() != dict(provider):
            raise ProviderBindingMismatchError(
                "Installed adapter provider block differs from ToolSpec provider"
            )
        return adapter

    def is_installed(self, spec: Mapping[str, Any]) -> bool:
        provider = spec.get("provider") or {}
        return (provider.get("id"), provider.get("version"),
                provider.get("adapter")) in self._installed
