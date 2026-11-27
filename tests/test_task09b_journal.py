"""SQLite MOCK restart/crash tests; no policy or fixture execution."""
import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from response.prevention import BlockRequest, PersistentMockPrevention, PrototypeError


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task09b-journal-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        data = bytearray(128)
        data[:2] = b"MZ"
        data[60:64] = (64).to_bytes(4, "little")
        data[64:68] = b"PE\0\0"
        (self.root / "fixture.exe").write_bytes(data)
        self.request = BlockRequest("r1", "case1", 1, "fixture.exe", hashlib.sha256(data).hexdigest())
        self.engine = self.open()

    def open(self, authorize=None):
        return PersistentMockPrevention(self.root, authorize=authorize or (lambda r, op: True))

    def plan_apply(self):
        self.assertEqual(self.engine.plan_block(self.request)["status"], "PLANNED")
        self.assertEqual(self.engine.apply_block(self.request)["status"], "MOCK_APPLIED")

    def test_restart_keeps_receipt_audit_and_rollback(self):
        self.plan_apply()
        reopened = self.open()
        self.assertEqual(reopened.verify_block(self.request)["status"], "MOCK_VERIFIED")
        self.assertEqual(reopened.apply_block(self.request)["reason_code"], "DUPLICATE_APPLY_USE_VERIFY")
        self.assertEqual(reopened.rollback_block(self.request)["status"], "MOCK_ROLLED_BACK")
        snapshot = self.open().inspect()
        self.assertEqual(snapshot["rules"], {})
        self.assertEqual(len(snapshot["audit"]), 5)
        self.assertTrue(all(row["audit_metadata"]["durability"] == "SQLITE_TRANSACTION_MOCK_ONLY"
                            for row in snapshot["audit"]))

    def test_reopened_engine_does_not_restore_authorization(self):
        self.plan_apply()
        denied = PersistentMockPrevention(self.root)
        self.assertEqual(denied.rollback_block(self.request)["reason_code"], "MOCK_HARNESS_AUTHORIZATION_DENIED")
        self.assertEqual(len(denied.inspect()["rules"]), 1)

    def test_two_instances_use_latest_state(self):
        second = self.open()
        self.plan_apply()
        self.assertEqual(second.apply_block(self.request)["reason_code"], "DUPLICATE_APPLY_USE_VERIFY")
        self.assertEqual(second.rollback_block(self.request)["status"], "MOCK_ROLLED_BACK")
        self.assertEqual(self.engine.inspect()["rules"], {})

    def test_failure_after_state_write_rolls_back_and_records_failure(self):
        self.engine.plan_block(self.request)
        def fail():
            raise RuntimeError("fixture failure before commit")
        self.engine._before_commit = fail
        result = self.engine.apply_block(self.request)
        self.assertEqual(result["status"], "FAILED")
        snapshot = self.open().inspect()
        self.assertEqual(snapshot["rules"], {})
        self.assertEqual(snapshot["audit"][-1]["reason_code"], "MOCK_TRANSACTION_ABORTED")
        self.assertEqual(self.engine.apply_block(self.request)["status"], "MOCK_APPLIED")

    def test_rollback_commit_failure_preserves_rule(self):
        self.plan_apply()
        def fail():
            raise OSError("fixture disk failure")
        self.engine._before_commit = fail
        self.assertEqual(self.engine.rollback_block(self.request)["status"], "FAILED")
        self.assertEqual(len(self.open().inspect()["rules"]), 1)
        self.assertEqual(self.engine.rollback_block(self.request)["status"], "MOCK_ROLLED_BACK")

    def test_unavailable_journal_never_reports_success_or_durable_audit(self):
        self.engine.plan_block(self.request)
        with patch.object(self.engine, "_connect", side_effect=PermissionError):
            result = self.engine.apply_block(self.request)
        self.assertEqual(result["reason_code"], "MOCK_JOURNAL_UNAVAILABLE")
        self.assertEqual(result["audit_metadata"]["durability"], "UNAVAILABLE_NOT_RECORDED")
        self.assertEqual(self.open().inspect()["rules"], {})

    def test_corrupt_metadata_refused_without_overwriting(self):
        with closing(sqlite3.connect(self.engine.path)) as connection, connection:
            connection.execute("UPDATE metadata SET version=999")
        with self.assertRaises(PrototypeError):
            self.open()
        with closing(sqlite3.connect(self.engine.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT version FROM metadata").fetchone()[0], 999)

    def test_invalid_json_state_is_not_reset_to_empty(self):
        with closing(sqlite3.connect(self.engine.path)) as connection, connection:
            connection.execute("UPDATE state SET payload='broken'")
        result = self.engine.apply_block(self.request)
        self.assertEqual(result["reason_code"], "MOCK_JOURNAL_UNAVAILABLE")
        with closing(sqlite3.connect(self.engine.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT payload FROM state").fetchone()[0], "broken")

    def test_abrupt_child_exit_before_commit_recovers_last_committed_state(self):
        self.engine.plan_block(self.request)
        # The child runs our Python harness only; it never executes fixture.exe.
        script = """
import json, os, sys
from response.prevention import BlockRequest, PersistentMockPrevention
engine = PersistentMockPrevention(sys.argv[1], authorize=lambda r, op: True)
engine._before_commit = lambda: os._exit(17)
engine.apply_block(BlockRequest(**json.loads(sys.argv[2])))
"""
        from dataclasses import asdict
        child = subprocess.run([sys.executable, "-c", script, str(self.root), json.dumps(asdict(self.request))],
                               cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 17, child.stderr.decode(errors="replace"))
        reopened = self.open()
        snapshot = reopened.inspect()
        self.assertEqual(snapshot["rules"], {})
        self.assertEqual(len(snapshot["audit"]), 1)
        self.assertEqual(reopened.apply_block(self.request)["status"], "MOCK_APPLIED")
        self.assertEqual(reopened.rollback_block(self.request)["status"], "MOCK_ROLLED_BACK")


if __name__ == "__main__":
    unittest.main()
