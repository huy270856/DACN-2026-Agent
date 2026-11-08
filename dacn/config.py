"""Application configuration: storage roots and runtime paths.

No machine-specific paths or secrets are hardcoded. Defaults are relative to a
configurable application home (``--home`` / ``DACN_HOME`` / current directory).
Signing keys are NEVER stored here; Node D smoke uses an explicit in-memory test
key provider chosen at call time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Resolved storage layout for one application run."""
    home: Path
    collections_dir: Path
    cases_dir: Path
    artifacts_dir: Path
    run_ledger_path: Path
    ledgers_dir: Path

    @classmethod
    def from_home(cls, home: str | os.PathLike | None = None) -> "AppConfig":
        base = Path(home) if home is not None else Path(
            os.environ.get("DACN_HOME") or Path.cwd() / "dacn_data")
        base = base.expanduser().resolve()
        return cls(
            home=base,
            collections_dir=base / "collections",
            cases_dir=base / "cases",
            artifacts_dir=base / "artifacts",
            run_ledger_path=base / "run_ledger.jsonl",
            ledgers_dir=base / "ledgers",
        )

    def ensure_dirs(self) -> None:
        for d in (self.home, self.collections_dir, self.cases_dir,
                  self.artifacts_dir, self.ledgers_dir):
            d.mkdir(parents=True, exist_ok=True)
