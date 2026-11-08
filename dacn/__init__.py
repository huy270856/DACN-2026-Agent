"""DACN unified application package.

A thin orchestration layer with ONE CLI (`python -m dacn`) that calls the real
Node B (Context Collector), Node C (CaseState/CaseManager) and Node D (D1-D9
Orchestrator) Python APIs directly -- no per-node subprocess, no copied logic.

Importing this package has no side effects: nothing is read, written or executed
at import time. Windows-only Node D modules are imported lazily inside the smoke
path only.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
