import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from orchestrator.executor import PinnedAdapter, ToolExecutor

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'tests/fixtures/d5_safe_adapter.py'


def fixture(name):
    return json.loads((ROOT / f'd0/fixtures/{name}.json').read_text(encoding='utf-8'))


class ExecutorSetup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='d5-d6-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'mẫu có khoảng trắng.bin'
        self.target.write_bytes(b'MZ harmless fixture; not executable\x00' * 20)
        self.call, self.spec, self.policy = fixture('tool_call'), fixture('tool_spec'), fixture('policy_decision')
        interpreter = str(Path(getattr(sys, '_base_executable', sys.executable)).resolve())
        script = str(ADAPTER.resolve())
        pins = tuple((p, hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in (interpreter, script))
        self.adapter = PinnedAdapter('safe_mock', '0.1.0', 'safe_mock_adapter',
                                     (interpreter, '-I', script), pins)
        self.spec['provider'] = self.adapter.provider()
        self.spec['tool_id'] = self.call['tool_id'] = 'test.readonly'
        self.spec['capability'] = 'test.readonly'
        self.call['provider_id'] = 'safe_mock'
        self.call['arguments'] = {'mode': 'success'}
        info = self.target.stat()
        ref = self.call['target_ref']
        ref['observed']['path'] = str(self.target)
        ref['verified_digest']['value'] = hashlib.sha256(self.target.read_bytes()).hexdigest()
        ref['snapshot'] = {'device': info.st_dev, 'inode': info.st_ino,
                           'size_bytes': info.st_size, 'mtime_ns': info.st_mtime_ns}
        self.case = {'case_id': self.call['case_id'], 'revision': 1, 'target_ref': ref}
        self.executor = ToolExecutor(self.root / 'artifacts')

    def execute(self, **kwargs):
        return self.executor.execute(self.call, self.spec, self.policy, self.case, self.adapter, **kwargs)

    def stdout(self, result):
        return (result.run_directory / 'stdout.bin').read_bytes()
