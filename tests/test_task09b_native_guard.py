"""Compile the native lab backend and prove its host/command gates fail closed.
Execution/ACL integration belongs to the dedicated Windows VM, not this suite.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == 'nt', 'Windows .NET Framework compiler required')
class NativeGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        if not compiler.is_file():
            raise unittest.SkipTest('Built-in .NET Framework compiler not available')
        cls.scratch = tempfile.TemporaryDirectory(prefix='task09b-native-guard-')
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.program = Path(cls.scratch.name) / 'NtfsLab.exe'
        source = Path(__file__).resolve().parents[1] / 'response/prevention/NtfsLab.cs'
        result = subprocess.run([str(compiler), '/nologo', '/r:System.Web.Extensions.dll',
                                 '/out:' + str(cls.program), str(source)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def run_command(self, command):
        run = subprocess.run([str(self.program), command], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        return json.loads(run.stdout)

    def test_capabilities_do_not_claim_host_is_lab(self):
        result = self.run_command('capabilities')
        self.assertEqual(result['reason_code'], 'APPROVED_LAB_VM_REQUIRED')

    def test_demo_refuses_host_before_creating_lab_fixtures(self):
        path = Path(r'C:\DACN09B-Lab\LiveRuns')
        before = path.exists()
        result = self.run_command('demo')
        self.assertEqual(result['reason_code'], 'APPROVED_LAB_VM_REQUIRED')
        self.assertEqual(before, path.exists())
        self.assertEqual(result['checks'], [])

    def test_no_arbitrary_command_endpoint(self):
        self.assertEqual(self.run_command('anything-else')['reason_code'], 'COMMAND_NOT_ALLOWED')
