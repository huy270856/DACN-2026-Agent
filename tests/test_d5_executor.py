import dataclasses
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
import unittest

from d0.validate import validate
from d5_support import ExecutorSetup
from orchestrator.executor import ExecutionRejected, locked_reader


@unittest.skipUnless(os.name == 'nt', 'Windows handle and Job Object integration')
class ExecutorTests(ExecutorSetup):
    def test_success_receipt_artifact_hash_and_unicode_path(self):
        original = self.target.read_bytes()
        result = self.execute()
        validate('execution_receipt', result.receipt)
        self.assertEqual(result.receipt['outcome'], 'SUCCESS')
        self.assertEqual(result.receipt['target_binding']['status'], 'VERIFIED')
        self.assertEqual(result.receipt['cleanup']['status'], 'COMPLETE')
        self.assertEqual(json.loads(self.stdout(result))['sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.target.read_bytes(), original)
        self.assertFalse((result.run_directory / 'target.bin').exists())
        for artifact in result.raw_artifacts:
            data = (self.executor.root / artifact['relative_path']).read_bytes()
            self.assertEqual(artifact['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(artifact['size_bytes'], len(data))
        self.assertEqual(result.receipt['resources']['output_bytes'], sum(a['size_bytes'] for a in result.raw_artifacts))

    def test_denied_and_pending_approval_never_dispatch(self):
        with patch.object(self.executor.control, 'run') as run:
            for decision, code in [('DENY', 'POLICY_DENIED'), ('REQUIRE_APPROVAL', 'APPROVAL_REQUIRED')]:
                self.policy['outcome'] = decision
                with self.assertRaises(ExecutionRejected) as cm:
                    self.execute()
                self.assertEqual(cm.exception.code, code)
            run.assert_not_called()

    def test_foreign_code_and_mutation_never_dispatch_even_with_allow(self):
        with patch.object(self.executor.control, 'run') as run:
            for field in ('executes_foreign_code','mutates_target','writes_filesystem','requires_human_approval'):
                self.spec['effects'][field] = True
                with self.assertRaises(ExecutionRejected): self.execute()
                self.spec['effects'][field] = False
            run.assert_not_called()

    def test_stale_revision_and_wrong_policy_binding(self):
        self.case['revision'] = 2
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'CASE_REVISION_STALE')
        self.case['revision'] = 1
        self.policy['call_id'] = 'CALL-somethingelse'
        with self.assertRaises(ExecutionRejected): self.execute()

    def test_missing_digest_rejected(self):
        self.call['target_ref']['verified_digest'] = None
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'TARGET_IDENTITY_UNAVAILABLE')

    def test_changed_file_same_size_same_mtime_is_rejected_by_hash(self):
        info = self.target.stat()
        self.target.write_bytes(b'x' * info.st_size)
        os.utime(self.target, ns=(info.st_atime_ns,info.st_mtime_ns))
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'TARGET_CHANGED')

    def test_missing_file_is_typed_access_failure(self):
        self.target.unlink()
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'TARGET_IDENTITY_UNAVAILABLE')

    def test_access_denied_does_not_dispatch(self):
        with patch('orchestrator.executor.locked_reader', side_effect=PermissionError('injected deny')):
            with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'PROVIDER_UNAVAILABLE')

    def test_disabled_tool_rejected(self):
        self.spec['enabled'] = False
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'TOOL_DISABLED')

    def test_batch_provider_rejected(self):
        self.adapter = dataclasses.replace(self.adapter, command=(r'C:\fake\adapter.cmd',))
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'PROVIDER_MISMATCH')

    def test_oversized_arguments_rejected_before_dispatch(self):
        self.call['arguments'] = {'payload': 'a' * 30000}
        with patch.object(self.executor.control, 'run') as run:
            with self.assertRaises(ExecutionRejected) as cm: self.execute()
            self.assertEqual(cm.exception.code, 'BUDGET_EXCEEDED')
            run.assert_not_called()

    def test_provider_mismatch_and_pin_change_no_fallback(self):
        self.spec['provider']['version'] = 'other'
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'PROVIDER_MISMATCH')
        self.spec['provider'] = self.adapter.provider()
        self.adapter = dataclasses.replace(self.adapter, pins=tuple((p,'0'*64) for p,h in self.adapter.pins))
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'PROVIDER_MISMATCH')

    def test_shell_characters_are_json_data_and_environment_is_scrubbed(self):
        injected = '" & echo BAD > injected.txt | $(whoami); %COMSPEC%'
        self.call['arguments'] = {'value': injected}
        with patch.dict(os.environ, {'D5_TEST_SECRET':'must-not-reach-provider'}):
            result = self.execute()
        output = json.loads(self.stdout(result))
        self.assertEqual(output['arguments']['value'], injected)
        self.assertFalse(output['secret_present'])
        self.assertFalse((result.run_directory / 'injected.txt').exists())

    def test_read_lock_blocks_write_and_rename_on_actual_windows(self):
        with locked_reader(self.target):
            with self.assertRaises(OSError): self.target.write_bytes(b'changed')
            with self.assertRaises(OSError): self.target.rename(self.root / 'replacement')

    def test_provider_cannot_write_locked_staged_target(self):
        self.call['arguments'] = {'mode':'lock_probe'}
        result = self.execute()
        self.assertEqual(result.receipt['outcome'], 'SUCCESS')
        self.assertIn(b'write_blocked', self.stdout(result))

    def test_unknown_field_rejected_without_execution(self):
        self.call['human_approved'] = True
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'SCHEMA_INVALID')

    def test_reparse_point_rejected_without_requiring_symlink_privilege(self):
        real = Path.lstat
        def fake(path):
            info = real(path)
            if path == self.target:
                from types import SimpleNamespace
                return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400)
            return info
        with patch.object(Path,'lstat',fake):
            with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'TARGET_IDENTITY_UNAVAILABLE')

    def test_no_process_target_backend(self):
        ref=self.call['target_ref']
        ref.update(kind='PROCESS',observed={'pid':os.getpid(),'start_time_epoch':1},verified_digest=None,snapshot={})
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code, 'TARGET_IDENTITY_UNAVAILABLE')

    def test_generated_runs_do_not_overwrite_history(self):
        first = self.execute()
        saved = (first.run_directory/'execution_receipt.json').read_bytes()
        second = self.execute()
        self.assertNotEqual(first.receipt['run_id'],second.receipt['run_id'])
        self.assertEqual(saved,(first.run_directory/'execution_receipt.json').read_bytes())
