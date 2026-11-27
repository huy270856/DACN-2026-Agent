"""TASK 07B (D4): build `ordinal_table.json` ONCE, offline, from the host ws2_32.dll export table.

Trusted operator script. Read-only static parse with LIEF; never loads or executes the DLL.
The analyzer later reads only the committed JSON (pinned), never System32.

Limitation recorded in the output: the table reflects THIS host's Windows build; a target may
bind a different ws2_32 version, so a resolved name is an annotation, not an observation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_VERSION = "task07b-ordinal-table-builder-v1"
TABLE_SCHEMA = "dacn-ordinal-table-v1"
SOURCES = {"ws2_32.dll": Path("C:/Windows/System32/ws2_32.dll")}
OUT = Path(__file__).with_name("ordinal_table.json")


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def os_build() -> dict:
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        return {k2: str(winreg.QueryValueEx(k, k2)[0]) for k2 in ("CurrentBuild", "UBR", "DisplayVersion")}
    except OSError:
        return {"platform": platform.platform()}


def exports(path: Path) -> dict:
    import lief
    b = lief.PE.parse(str(path))
    if b is None or not b.has_exports:
        raise ValueError(f"no export table: {path}")
    out = {}
    for e in b.get_export().entries:
        name = e.name
        if not name or not isinstance(name, str) or len(name) > 160:
            continue  # ordinal-only exports have nothing to resolve
        if not 0 <= int(e.ordinal) <= 65535:
            raise ValueError("ordinal out of range")
        if str(e.ordinal) in out and out[str(e.ordinal)] != name:
            raise ValueError("duplicate ordinal")
        out[str(int(e.ordinal))] = name
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def build() -> dict:
    import lief
    libs = {}
    for lib, path in SOURCES.items():
        libs[lib] = {"source_path": str(path), "source_sha256": file_sha(path), "ordinals": exports(path)}
    return {"schema": TABLE_SCHEMA, "table_version": "ordinal-table-ws2_32-v1",
            "libraries": libs,
            "provenance": {"script_version": SCRIPT_VERSION, "parser": "LIEF " + lief.__version__,
                           "os_build": os_build(), "created_utc": datetime.now(timezone.utc).isoformat()},
            "limitations": ["Resolved from this host's ws2_32.dll export table; a target may bind a different "
                            "ws2_32 version. A resolved name is an analyzer annotation, not an observed import name."]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise FileExistsError(f"refusing to overwrite {a.out}")
    a.out.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    print(a.out)


if __name__ == "__main__":
    main()
