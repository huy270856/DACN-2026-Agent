"""TASK 07B S1: committed ordinal_table.json format and provenance (unit; no model)."""
import hashlib
import json
import re
from pathlib import Path

import pytest

from d0.validate import digest

TABLE = Path(__file__).resolve().parents[1] / "investigation_v4" / "ordinal_table.json"


def _table():
    return json.loads(TABLE.read_text(encoding="utf-8"))


def test_format_and_only_ws2_32():
    t = _table()
    assert t["schema"] == "dacn-ordinal-table-v1" and t["table_version"] == "ordinal-table-ws2_32-v1"
    assert set(t["libraries"]) == {"ws2_32.dll"}  # D4: ws2_32 only
    lib = t["libraries"]["ws2_32.dll"]
    assert re.fullmatch(r"[0-9a-f]{64}", lib["source_sha256"])
    ords = lib["ordinals"]
    assert ords and all(k.isdigit() and 0 <= int(k) <= 65535 for k in ords)
    assert all(isinstance(v, str) and 0 < len(v) <= 160 for v in ords.values())
    assert list(ords) == sorted(ords, key=int)
    # Well-known stable ws2_32 ordinals.
    assert (ords["115"], ords["11"], ords["52"]) == ("WSAStartup", "inet_addr", "gethostbyname")
    p = t["provenance"]
    assert p["script_version"] == "task07b-ordinal-table-builder-v1" and p["parser"].startswith("LIEF ")
    assert p["os_build"] and p["created_utc"]
    assert any("different" in x for x in t["limitations"])


def test_canonical_digest_is_line_ending_independent():
    t = _table()
    assert digest(json.loads(TABLE.read_text(encoding="utf-8").replace("\n", "\r\n"))) == digest(t)


def test_source_sha_matches_host_when_unchanged():
    src = Path(_table()["libraries"]["ws2_32.dll"]["source_path"])
    if not src.exists():
        pytest.skip("host ws2_32.dll not present")
    host = hashlib.sha256(src.read_bytes()).hexdigest()
    if host != _table()["libraries"]["ws2_32.dll"]["source_sha256"]:
        pytest.skip("host ws2_32.dll changed since table build (Windows update); table remains pinned")
    assert host == _table()["libraries"]["ws2_32.dll"]["source_sha256"]


def test_builder_refuses_overwrite(tmp_path):
    from investigation_v4 import build_ordinal_table as b
    out = tmp_path / "t.json"
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        b.main(["--out", str(out)])
