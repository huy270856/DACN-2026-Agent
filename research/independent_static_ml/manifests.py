"""Provenance / environment manifest helpers."""
from __future__ import annotations

import hashlib
import platform
import sys
from datetime import datetime, timezone


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _ver(mod):
    try:
        return __import__(mod).__version__
    except Exception as exc:  # pragma: no cover
        return f"unavailable: {exc!r}"


def environment_manifest():
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            "numpy": _ver("numpy"),
            "scikit_learn": _ver("sklearn"),
            "lightgbm": _ver("lightgbm"),
            "lief": _ver("lief"),
        },
    }
