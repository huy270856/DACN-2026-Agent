"""TASK09B: dry-run plans and in-memory MOCK only; no Windows enforcement."""
from .prototype import BlockRequest, Prevention, PrototypeError
from .journal import PersistentMockPrevention

__all__ = ["BlockRequest", "Prevention", "PrototypeError", "PersistentMockPrevention"]
