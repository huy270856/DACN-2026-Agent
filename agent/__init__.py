"""DACN local investigation Agent (MVP).

An LLM (local Qwen via local Ollama) proposes investigation actions; a
deterministic Controller validates every proposal and drives tool execution
ONLY through the D1-D9 trusted orchestrator. The LLM never runs shells, opens
binaries, calls analyzers, grants approvals or bypasses D4/D8. Evidence from
Node C is treated as UNTRUSTED_CONTENT and is never interpreted as instructions.

Importing this package has no side effects.
"""
__all__ = ["__version__"]
__version__ = "0.1.0"
