"""Tests for the DACN unified application (dacn package).

intake/inspect are cross-platform; smoke and the Node D DENY test are Windows-only.
No analysis target is ever executed; the Node D smoke uses the benign mock analyzer.
"""
import hashlib
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import case_manager as cm
from dacn.config import AppConfig
from dacn import application as app


def make_pe(machine=0x8664, characteristics=0x0002, magic=0x20B):
    optional_size = 112 if magic == 0x20B else 96
    dos = bytearray(64); dos[0:2] = b"MZ"; struct.pack_into("<I", dos, 60, 64)
    coff = b"PE\0\0" + struct.pack("<HHIIIHH", machine, 0, 0, 0, 0, optional_size, characteristics)
    return bytes(dos) + coff + struct.pack("<H", magic) + b"\0" * (optional_size - 2) + b"\0" * 8


class DacnAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dacn-test-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg = AppConfig.from_home(self.tmp / "home")

    def _write(self, name, data):
        p = self.tmp / name
        p.write_bytes(data)
        return p

    # -- intake -------------------------------------------------------------
    def test_intake_file_pe_creates_case(self):
        p = self._write("a.exe", make_pe())
        r = app.intake_file(str(p), self.cfg)
        self.assertEqual(r["case_action"], "created")
        self.assertEqual(r["collection_status"], "SUCCESS")
        self.assertEqual(r["format"], "PE")
        self.assertEqual(r["target_type"], "FILE")
        self.assertEqual(r["identity_strength"], "STRONG")
        # SHA-256 is exactly the file's digest -> read-only, target not executed.
        self.assertEqual(r["sha256"], hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertTrue(Path(r["case_state_path"]).exists())

    def test_intake_pid_creates_process_case(self):
        r = app.intake_pid(os.getpid(), self.cfg)
        self.assertEqual(r["target_type"], "PROCESS")
        self.assertEqual(r["case_action"], "created")
        self.assertTrue(r["case_id"].startswith("CASE-"))

    def test_intake_non_pe_is_unknown(self):
        p = self._write("note.txt", b"just text, not a binary")
        self.assertEqual(app.intake_file(str(p), self.cfg)["format"], "UNKNOWN")

    def test_intake_malformed_pe(self):
        p = self._write("stub.bin", b"MZ" + b"\x00" * 10)
        self.assertEqual(app.intake_file(str(p), self.cfg)["format"], "MALFORMED")

    def test_intake_missing_file_does_not_crash(self):
        r = app.intake_file(str(self.tmp / "nope.bin"), self.cfg)
        self.assertEqual(r["collection_status"], "FAILED")
        self.assertEqual(r["case_action"], "created")  # a case is still persisted

    def test_intake_file_changed_during_collection(self):
        p = self._write("changing.bin", make_pe())
        with mock.patch("context_collector.same_observation", return_value=False):
            r = app.intake_file(str(p), self.cfg)
        self.assertIsNone(r["sha256"])  # digest withheld when file changed
        self.assertEqual(r["format"], "UNAVAILABLE")

    def test_duplicate_intake_creates_distinct_cases(self):
        p = self._write("dup.exe", make_pe())
        a = app.intake_file(str(p), self.cfg)
        b = app.intake_file(str(p), self.cfg)
        self.assertNotEqual(a["case_id"], b["case_id"])

    def test_append_same_target_updates_case(self):
        p = self._write("same.exe", make_pe())
        a = app.intake_file(str(p), self.cfg)
        b = app.intake_file(str(p), self.cfg, case_id=a["case_id"])
        self.assertEqual(b["case_action"], "updated")
        self.assertEqual(b["case_id"], a["case_id"])
        self.assertGreater(b["revision"], 1)

    def test_target_mismatch_rejected(self):
        a = app.intake_file(str(self._write("one.exe", make_pe())), self.cfg)
        with self.assertRaises(app.TargetMismatchError):
            app.intake_file(str(self._write("two.exe", make_pe(magic=0x10B, machine=0x14C))),
                            self.cfg, case_id=a["case_id"])

    # -- inspect ------------------------------------------------------------
    def test_inspect_reloads_persisted_state(self):
        p = self._write("x.exe", make_pe())
        intake = app.intake_file(str(p), self.cfg)
        got = app.inspect_case(intake["case_id"], self.cfg)
        self.assertEqual(got["case_id"], intake["case_id"])
        self.assertEqual(got["sha256"], intake["sha256"])
        self.assertEqual(got["format"], "PE")
        self.assertGreater(got["evidence_count"], 0)
        self.assertIn("target_ref", got)
        # Evidence provenance present and untrusted.
        self.assertTrue(all(e["trust_level"] == "UNTRUSTED_CONTENT" for e in got["evidence"]))

    def test_inspect_invalid_case_id(self):
        with self.assertRaises(app.InvalidCaseIdError):
            app.inspect_case("not-a-case-id", self.cfg)

    def test_inspect_case_not_found(self):
        with self.assertRaises(app.CaseNotFoundError):
            app.inspect_case("CASE-" + "a" * 32, self.cfg)

    # -- config / storage ---------------------------------------------------
    def test_config_isolated_roots(self):
        self.cfg.ensure_dirs()
        self.assertTrue(self.cfg.cases_dir.is_dir())
        self.assertTrue(self.cfg.collections_dir.is_dir())


class DacnCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dacn-cli-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.home = str(self.tmp / "home")

    def _run(self, *args):
        from dacn.cli import main
        return main(["--home", self.home, *args])

    def test_cli_intake_and_inspect(self):
        p = self.tmp / "h.exe"; p.write_bytes(make_pe())
        self.assertEqual(self._run("intake", "--file", str(p)), 0)

    def test_cli_pid_must_be_positive(self):
        with self.assertRaises(SystemExit):
            self._run("intake", "--pid", "0")

    def test_cli_backing_file_requires_pid(self):
        p = self.tmp / "h.exe"; p.write_bytes(make_pe())
        with self.assertRaises(SystemExit):
            self._run("intake", "--file", str(p), "--include-backing-file")

    def test_cli_inspect_requires_case_id(self):
        with self.assertRaises(SystemExit):
            self._run("inspect")

    def test_cli_missing_file_returns_nonzero(self):
        self.assertEqual(self._run("intake", "--file", str(self.tmp / "nope.bin")), 2)


@unittest.skipUnless(os.name == "nt", "Node D smoke is Windows-only")
class DacnSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dacn-smoke-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg = AppConfig.from_home(self.tmp / "home")

    def test_smoke_runs_full_d1_d9_chain(self):
        r = app.smoke(self.cfg)
        self.assertTrue(r["supported"])
        self.assertEqual(r["phase"], "COMMITTED")
        self.assertEqual(r["outcome"], "SUCCESS")
        self.assertTrue(r["d7_validated_and_d9_committed"])
        # The real case now holds the committed analyzer evidence.
        state = app.inspect_case(r["case_id"], self.cfg)
        self.assertTrue(any(e["facet"] == "static.ember_features" for e in state["evidence"]))

    def test_deny_policy_does_not_execute_tool(self):
        # Build the real Node D stack but with an empty allowlist -> D4 DENY.
        import hashlib as _h
        from orchestrator.registry import ToolRegistry
        from orchestrator.policy_engine import PolicyEngine, PolicyConfig
        from orchestrator.trust import TrustedSigner, InMemoryKeyProvider
        from orchestrator.provider_install import ProviderInstallation
        from orchestrator.case_bridge import CaseBridge
        from orchestrator.core import Orchestrator
        from orchestrator.executor import PinnedAdapter
        import context_collector as nodeb, case_state as cs
        self.cfg.ensure_dirs()
        sample = self.cfg.artifacts_dir / "s.bin"; sample.write_bytes(b"MZ benign\x00" * 40)
        ctx = nodeb.collect_file_context(str(sample))
        state = cs.build_case_state(ctx); cf = cs.save_case_state(state, self.cfg.cases_dir)
        interp = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
        script = str((ROOT / "tests" / "fixtures" / "ember_mock_adapter.py").resolve())
        pins = [[p, _h.sha256(Path(p).read_bytes()).hexdigest()] for p in (interp, script)]
        ad = PinnedAdapter("ember_mock", "0.1.0", "ember_mock_adapter",
                           (interp, "-I", script), tuple((p, s) for p, s in pins))
        reg = ToolRegistry(); reg.register_tool(app._smoke_tool_spec(ad.provider()))
        inst = ProviderInstallation(); inst.install(
            provider_id="ember_mock", version="0.1.0", adapter_id="ember_mock_adapter",
            command=(interp, "-I", script), pins=pins)
        orch = Orchestrator(
            registry=reg, policy=PolicyEngine(PolicyConfig(tool_allowlist=frozenset())),
            signer=TrustedSigner(InMemoryKeyProvider()), installation=inst,
            bridge=CaseBridge(audit_ledger_root=self.cfg.ledgers_dir),
            artifact_root=self.cfg.artifacts_dir, run_ledger_path=self.cfg.run_ledger_path)
        rec = orch.run_tool_call(app._smoke_tool_call(state["case_id"], ctx["target_ref"]), cf)
        self.assertEqual(rec.outcome, "DENY")
        final = cm.read_json(cf)
        self.assertFalse(any(e.get("facet") == "static.ember_features"
                             for e in final["evidence"]))


if __name__ == "__main__":
    unittest.main()
