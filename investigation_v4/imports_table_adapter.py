"""TASK 07B pinned standalone read-only PE import-TABLE analyzer (pe-imports-table-output-v1).

New file based on investigation_v3/import_adapter.py (frozen, untouched). No shell, network or
target execution. Reads only the target bytes and the pinned `ordinal_table.json` beside this
script. Declaration order is preserved (imports, then delay_imports); index = array position.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

MAX_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 1024
OUTPUT_BUDGET = 120000          # bytes of compact stdout JSON; spec max_output_bytes is 131072
SCHEMA = "pe-imports-table-output-v1"
TABLE_PATH = Path(__file__).with_name("ordinal_table.json")
LIMITATIONS = [
    "Declared static imports only; does not prove runtime use or maliciousness.",
    "Dynamically resolved APIs are not enumerated.",
    "resolved_symbol is an analyzer annotation from a pinned host ws2_32 export table; the target may bind a different DLL version. The original symbol stays null.",
]


def canonical_digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode("utf8")).hexdigest()


def load_ordinal_table(path=TABLE_PATH):
    table = json.loads(Path(path).read_text(encoding="utf-8"))
    if table.get("schema") != "dacn-ordinal-table-v1":
        raise ValueError("Unsupported ordinal table")
    lookup = {lib.lower(): {int(k): v for k, v in spec["ordinals"].items()}
              for lib, spec in table["libraries"].items()}
    return table, lookup


def parse_table(data):
    """Full declaration-order list [(library, delay, symbol, ordinal)], bounded."""
    if len(data) > MAX_BYTES:
        raise ValueError("PE exceeds 8 MiB analyzer budget")
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("Invalid PE")
    import lief
    binary = lief.PE.parse(list(data))
    if binary is None:
        raise ValueError("PE parser returned no binary")
    blocks, total = [], 0
    for delay, table in ((False, binary.imports), (True, binary.delay_imports)):
        for lib in table:
            name = lib.name
            if not name or len(name) > 128:
                raise ValueError("Import library exceeds name budget")
            items = []
            for item in lib.entries:
                ordinal = int(item.ordinal) if item.is_ordinal else None
                symbol = None if item.is_ordinal else item.name
                if symbol is not None and (not symbol or len(symbol) > 160):
                    raise ValueError("Import symbol exceeds name budget")
                items.append((symbol, ordinal))
                total += 1
                if total > 100000:
                    raise ValueError("Import table resource budget exceeded")
            blocks.append((name, delay, items))
            if len(blocks) > 4096:
                raise ValueError("Import table resource budget exceeded")
    return blocks, total, "LIEF " + lief.__version__


def build_payload(blocks, total, parser, target_sha256, table, lookup, limit):
    """Payload with at most `limit` entries; library index covers EVERY declared block."""
    libraries, entries = [], []
    for li, (name, delay, items) in enumerate(blocks):
        first = len(entries) if len(entries) < limit and items else None
        for symbol, ordinal in items:
            if len(entries) >= limit:
                break
            resolved = None
            if symbol is None and name.lower() in lookup:
                resolved = lookup[name.lower()].get(ordinal)
            entries.append([li, symbol, ordinal, delay, resolved])
        returned = (len(entries) - first) if first is not None else 0
        libraries.append({"name": name, "delay": delay, "declared_count": len(items), "returned_count": returned,
                          "first_index": first if returned else None,
                          "last_index": (first + returned - 1) if returned else None})
    any_resolved = any(e[4] is not None for e in entries)
    truncated = total > len(entries)
    return {"schema_version": SCHEMA, "target_sha256": target_sha256, "parser": parser,
            "total_entries": total, "returned_entries": len(entries), "truncated": truncated,
            "truncation_reason": None, "libraries": libraries, "entries": entries,
            "resolution_source": (table["table_version"] + " (host ws2_32 export table)") if any_resolved else None,
            "ordinal_table_version": table["table_version"], "ordinal_table_sha256": canonical_digest(table),
            "limitations": list(LIMITATIONS)}


def encode(payload):
    return json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def inspect_bytes(data, *, table_path=TABLE_PATH, budget=OUTPUT_BUDGET):
    table, lookup = load_ordinal_table(table_path)
    blocks, total, parser = parse_table(data)
    sha = hashlib.sha256(data).hexdigest()
    payload = build_payload(blocks, total, parser, sha, table, lookup, MAX_ENTRIES)
    if payload["truncated"]:
        payload["truncation_reason"] = "MAX_ENTRIES"
        payload["limitations"].append(f"Only the first {MAX_ENTRIES} declarations in file order; absence beyond them is unknown.")
    if len(encode(payload)) > budget:
        # Deterministic controlled reduction: largest entry count whose encoding fits the budget.
        lo, hi = 0, payload["returned_entries"]
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(encode(build_payload(blocks, total, parser, sha, table, lookup, mid))) <= budget - 400:
                lo = mid
            else:
                hi = mid - 1
        payload = build_payload(blocks, total, parser, sha, table, lookup, lo)
        payload["truncation_reason"] = "OUTPUT_BYTES"
        payload["limitations"].append(f"Output byte budget: only the first {lo} declarations returned; absence beyond them is unknown.")
        if len(encode(payload)) > budget:
            raise ValueError("Import table output exceeds byte budget")
    return payload


def inspect_file(path, **kw):
    with open(path, "rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    return inspect_bytes(data, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--arguments-json", required=True)
    args = ap.parse_args()
    try:
        if json.loads(args.arguments_json) != {"max_entries": MAX_ENTRIES}:
            raise ValueError("Invalid imports table arguments")
        sys.stdout.write(encode(inspect_file(args.target)))
    except Exception as exc:
        sys.stderr.write("imports_table_adapter: " + type(exc).__name__ + ": " + str(exc)[:200])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
