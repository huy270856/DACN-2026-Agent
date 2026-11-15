"""Pinned standalone read-only PE imports analyzer. No shell/network/target execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

MAX_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 64


def inspect_bytes(data):
    if len(data) > MAX_BYTES:
        raise ValueError("PE exceeds 8 MiB analyzer budget")
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("Invalid PE")
    import lief
    binary = lief.PE.parse(list(data))
    if binary is None:
        raise ValueError("PE parser returned no binary")
    entries, libraries, total = [], set(), 0
    # Preserve declaration order; bounded output is deterministic, not risk-ranked.
    for delay, table in ((False, binary.imports), (True, binary.delay_imports)):
        for lib in table:
            name = lib.name
            if not name or len(name) > 128:
                raise ValueError("Import library exceeds name budget")
            libraries.add(name)
            for item in lib.entries:
                ordinal = int(item.ordinal) if item.is_ordinal else None
                symbol = None if item.is_ordinal else item.name
                if symbol is not None and (not symbol or len(symbol) > 160):
                    raise ValueError("Import symbol exceeds name budget")
                total += 1
                if total <= MAX_ENTRIES:
                    entries.append({"library": name, "symbol": symbol, "ordinal": ordinal, "delay": delay})
                if total > 100000 or len(libraries) > 4096:
                    raise ValueError("Import table resource budget exceeded")
    return {"schema_version": "pe-imports-output-v1", "target_sha256": hashlib.sha256(data).hexdigest(),
            "parser": "LIEF " + lief.__version__, "library_count": len(libraries),
            "total_entries": total, "returned_entries": len(entries),
            "truncated": total > MAX_ENTRIES, "entries": entries,
            "limitations": ["Declared static imports only; does not prove runtime use or maliciousness.",
                            "Dynamically resolved APIs are not enumerated.",
                            "First 64 declarations in file order; absence from truncated output is unknown."]}


def inspect_file(path):
    with open(path, "rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    return inspect_bytes(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--arguments-json", required=True)
    args = ap.parse_args()
    try:
        if json.loads(args.arguments_json) != {"max_entries": MAX_ENTRIES}:
            raise ValueError("Invalid imports arguments")
        payload = inspect_file(args.target)
        sys.stdout.write(json.dumps(payload, ensure_ascii=True, allow_nan=False))
    except Exception as exc:
        sys.stderr.write("imports_adapter: " + type(exc).__name__ + ": " + str(exc)[:200])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
