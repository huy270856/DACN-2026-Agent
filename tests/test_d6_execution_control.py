import json
import os
import threading
import time
import unittest
from unittest.mock import patch

import psutil
from d0.validate import validate
from d5_support import ExecutorSetup
from orchestrator.execution_control import WindowsJob, VMResetGate, ControlResult
from orchestrator.executor import ExecutionRejected


@unittest.skipUnless(os.name == 'nt', 'Windows Job Object integration')
class ControlTests(ExecutorSetup):
    def test_timeout_keeps_completed_output_and_cleans_up(self):
        self.call['arguments']={'mode':'sleep'}
        self.call['budget']['timeout_ms']=1500
        result=self.execute()
        self.assertEqual(result.receipt['outcome'],'TIMEOUT')
        self.assertEqual(result.error['code'],'TIMEOUT')
        self.assertEqual(result.receipt['cleanup']['status'],'COMPLETE')
        self.assertIn(b'completed observation',self.stdout(result))
        validate('execution_receipt',result.receipt)

    def test_combined_stdout_stderr_cap(self):
        self.call['arguments']={'mode':'flood'}
        self.call['budget']['max_output_bytes']=2000
        result=self.execute()
        self.assertEqual(result.receipt['outcome'],'FAILED')
        self.assertEqual(result.error['code'],'BUDGET_EXCEEDED')
        self.assertEqual(sum(a['size_bytes'] for a in result.raw_artifacts),2000)
        self.assertEqual(result.receipt['cleanup']['status'],'COMPLETE')

    def test_policy_artifact_limit_tightens_call_budget(self):
        self.call['arguments']={'mode':'flood'}
        self.policy['effective_limits']['max_artifact_bytes']=100
        result=self.execute()
        self.assertEqual(result.error['code'],'BUDGET_EXCEEDED')
        self.assertEqual(result.receipt['resources']['output_bytes'],100)

    def test_nonzero_exit_preserves_raw_output(self):
        self.call['arguments']={'mode':'fail'}
        result=self.execute()
        self.assertEqual(result.receipt['outcome'],'FAILED')
        self.assertEqual(result.exit_code,7)
        self.assertIn(b'completed observation',self.stdout(result))

    def test_partial_receipt_is_not_promoted_to_success(self):
        partial=ControlResult('PARTIAL',None,0,0,1,'COMPLETE',())
        with patch.object(self.executor.control,'run',return_value=partial):
            result=self.execute()
        self.assertEqual(result.receipt['outcome'],'PARTIAL')
        validate('execution_receipt',result.receipt)

    def test_artifact_size_tamper_after_capture_rejected(self):
        original=self.executor.control.run
        def tamper(*args,**kwargs):
            result=original(*args,**kwargs)
            (args[1]/'stdout.bin').write_bytes(b'x'*10000)
            return result
        with patch.object(self.executor.control,'run',side_effect=tamper):
            result=self.execute()
        self.assertEqual(result.receipt['outcome'],'FAILED')
        self.assertEqual(result.error['code'],'ARTIFACT_INTEGRITY_FAILED')

    def test_same_size_artifact_tamper_rejected_by_capture_digest(self):
        original=self.executor.control.run
        def tamper(*args,**kwargs):
            result=original(*args,**kwargs)
            path=args[1]/'stdout.bin'
            path.write_bytes(b'x'*path.stat().st_size)
            return result
        with patch.object(self.executor.control,'run',side_effect=tamper):
            result=self.execute()
        self.assertEqual(result.receipt['outcome'],'FAILED')
        self.assertEqual(result.error['code'],'ARTIFACT_INTEGRITY_FAILED')

    def test_timeout_kills_owned_child(self):
        self.call['arguments']={'mode':'tree'}
        self.call['budget']['timeout_ms']=1800
        result=self.execute()
        child=json.loads(self.stdout(result))['child_pid']
        self.assertEqual(result.receipt['outcome'],'TIMEOUT')
        self.assertFalse(psutil.pid_exists(child))

    def test_normal_parent_exit_still_cleans_descendant(self):
        self.call['arguments']={'mode':'tree','exit_parent':True}
        result=self.execute()
        child=json.loads(self.stdout(result))['child_pid']
        self.assertEqual(result.receipt['outcome'],'SUCCESS')
        self.assertEqual(result.receipt['cleanup']['status'],'COMPLETE')
        self.assertFalse(psutil.pid_exists(child))

    def test_cancel_tree_after_output_and_reject_concurrent_run(self):
        self.call['arguments']={'mode':'tree'}
        cancel=threading.Event()
        received=[]
        def execute():
            try: received.append(self.execute(cancel=cancel))
            except BaseException as exc: received.append(exc)
        worker=threading.Thread(target=execute)
        worker.start()
        try:
            end=time.monotonic()+5
            ready=False
            while time.monotonic()<end:
                for path in self.executor.root.glob('RUN-*/stdout.bin'):
                    if path.stat().st_size:
                        ready=True
                        break
                if ready: break
                time.sleep(.02)
            self.assertTrue(ready,'benign adapter did not start')
            with self.assertRaises(ExecutionRejected) as cm: self.execute()
            self.assertEqual(cm.exception.code,'BUDGET_EXCEEDED')
        finally:
            cancel.set()
            worker.join(8)
        self.assertFalse(worker.is_alive())
        result=received[0]
        if isinstance(result,BaseException): raise result
        self.assertEqual(result.receipt['outcome'],'CANCELLED')
        self.assertEqual(result.receipt['cleanup']['status'],'COMPLETE')
        self.assertFalse(psutil.pid_exists(json.loads(self.stdout(result))['child_pid']))

    def test_cancel_before_dispatch(self):
        cancel=threading.Event();cancel.set()
        with patch.object(self.executor.control,'run') as run:
            with self.assertRaises(ExecutionRejected) as cm: self.execute(cancel=cancel)
            self.assertEqual(cm.exception.code,'CANCELLED')
            run.assert_not_called()

    def test_assignment_failure_never_releases_adapter(self):
        with patch.object(WindowsJob,'assign',side_effect=OSError('test assignment denied')):
            result=self.execute()
        self.assertEqual(result.receipt['outcome'],'FAILED')
        self.assertEqual(result.receipt['resources']['output_bytes'],0)
        self.assertEqual(result.receipt['cleanup']['status'],'COMPLETE')

    def test_cleanup_unverified_quarantines_executor(self):
        original=WindowsJob.cleanup
        def incomplete(job):
            original(job)  # Actually clean safe test processes; only receipt failure is injected.
            return False
        with patch.object(WindowsJob,'cleanup',incomplete):
            result=self.execute()
        self.assertEqual(result.receipt['outcome'],'FAILED')
        self.assertEqual(result.receipt['cleanup']['status'],'INCOMPLETE')
        self.assertEqual(result.error['code'],'CLEANUP_INCOMPLETE')
        with self.assertRaises(ExecutionRejected) as cm: self.execute()
        self.assertEqual(cm.exception.code,'CLEANUP_INCOMPLETE')


class VMGateTests(unittest.TestCase):
    def test_reset_and_isolation_required_each_run(self):
        gate=VMResetGate()
        with self.assertRaises(RuntimeError): gate.begin(isolation_verified=True,snapshot_verified=True)
        gate.record_reset(verified=True)
        with self.assertRaises(RuntimeError): gate.begin(isolation_verified=False,snapshot_verified=True)
        gate.begin(isolation_verified=True,snapshot_verified=True)
        self.assertFalse(gate.ready)
        gate.record_reset(verified=False)
        with self.assertRaises(RuntimeError): gate.begin(isolation_verified=True,snapshot_verified=True)
