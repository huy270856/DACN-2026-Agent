"""Observe actual trusted stages, without changing decisions or logging key material."""
import copy


def attach(orch, events):
    policy, bridge = orch._policy, orch._bridge
    class Policy:
        def evaluate(self, *args):
            decision = policy.evaluate(*args)
            events.append({"stage": "D4", "decision": copy.deepcopy(decision)})
            return decision
    class Bridge:
        def __getattr__(self, name):
            return getattr(bridge, name)
        def commit_tool_result(self, case_path, result, receipt, **kwargs):
            try:
                committed = bridge.commit_tool_result(case_path, result, receipt, **kwargs)
            except Exception as exc:
                events.append({"stage": "D9_FAILED", "error_type": type(exc).__name__})
                raise
            events.append({"stage": "D9_COMMITTED", "commit": copy.deepcopy(committed)})
            return committed
    orch._policy, orch._bridge = Policy(), Bridge()
    for tool_id, normalizer in list(orch._result_adapters.items()):
        def wrapped(output, call, spec, *, artifact_root, _normalizer=normalizer):
            events.append({"stage": "D5_D6_RECEIPT", "receipt": copy.deepcopy(output.receipt),
                           "exit_code": output.exit_code})
            result = _normalizer(output, call, spec, artifact_root=artifact_root)
            events.append({"stage": "D7_VALIDATED", "result": copy.deepcopy(result)})
            return result
        orch._result_adapters[tool_id] = wrapped
    return policy  # discovery uses pure policy, without recording it as authorization
