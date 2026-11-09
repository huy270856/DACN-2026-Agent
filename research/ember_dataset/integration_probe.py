"""Research probe: real EMBER v2 extraction through Node B/C and D1-D9.

The trusted provider command is supplied by this operator-run script, never by
the analyzed file or Agent. This is a local integration test with a TEST key.
"""
import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import case_manager as cm
from dacn.application import intake_file
from dacn.config import AppConfig
from orchestrator.case_bridge import CaseBridge
from orchestrator.core import Orchestrator
from orchestrator.policy_engine import PolicyConfig, PolicyEngine
from orchestrator.provider_install import ProviderInstallation
from orchestrator.registry import ToolRegistry
from orchestrator.trust import InMemoryKeyProvider, TrustedSigner


PROVIDER_ID = 'ember_v2_real'
ADAPTER_ID = 'ember_v2_provider'
TOOL_ID = 'static.ember_features'
VERSION = '0.1.0'
LIMITS = {'timeout_ms': 60000, 'max_output_bytes': 262144,
          'max_artifact_bytes': 1048576, 'max_concurrency': 1}


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def probe(target, home, research_python):
    target = Path(target).resolve(strict=True)
    home = Path(home)
    if home.exists():
        raise FileExistsError('Probe home must be new: {}'.format(home))
    py = Path(research_python).resolve(strict=True)
    script = (Path(__file__).parent / 'ember_v2_provider.py').resolve(strict=True)
    config = AppConfig.from_home(home)
    intake = intake_file(str(target), config)
    if intake['collection_status'] != 'SUCCESS':
        raise ValueError('Node B collection failed: {}'.format(intake))
    case_path = Path(intake['case_state_path'])
    state = cm.validate_case(cm.read_json(case_path))
    ref = state['target_ref']
    if ref['kind'] != 'FILE' or not ref['verified_digest']:
        raise ValueError('A verified FILE TargetRef is required')

    provider = {'id': PROVIDER_ID, 'version': VERSION,
                'adapter': ADAPTER_ID, 'runtime': 'subprocess'}
    spec = json.loads((ROOT / 'd0' / 'fixtures' / 'tool_spec.json').read_text(encoding='utf-8'))
    spec.update(tool_id=TOOL_ID, tool_version=VERSION, provider=provider,
                description='Real EMBER v2 extraction from verified staged PE', limits=LIMITS)
    registry = ToolRegistry()
    registry.register_tool(spec)
    pins = [(str(path), file_hash(path)) for path in (py, script)]
    installation = ProviderInstallation()
    installation.install(provider_id=PROVIDER_ID, version=VERSION, adapter_id=ADAPTER_ID,
                         command=(str(py), '-I', str(script)), pins=pins)
    identity = (TOOL_ID, VERSION, PROVIDER_ID)
    policy = PolicyEngine(PolicyConfig(tool_allowlist=frozenset({identity}),
                                       budget_caps=LIMITS))
    orch = Orchestrator(registry=registry, policy=policy,
                        signer=TrustedSigner(InMemoryKeyProvider()),
                        installation=installation,
                        bridge=CaseBridge(audit_ledger_root=config.ledgers_dir),
                        artifact_root=config.artifacts_dir,
                        run_ledger_path=config.run_ledger_path)
    call = json.loads((ROOT / 'd0' / 'fixtures' / 'tool_call.json').read_text(encoding='utf-8'))
    call.update(call_id='CALL-' + uuid.uuid4().hex, case_id=state['case_id'],
                expected_revision=state['revision'], tool_id=TOOL_ID,
                tool_version=VERSION, provider_id=PROVIDER_ID, target_ref=ref,
                arguments={'feature_version': 2},
                reason='Operator-run real EMBER v2 integration probe',
                requested_by='analyst',
                requested_at=datetime.now(timezone.utc).isoformat(),
                budget={'timeout_ms': 60000, 'max_output_bytes': 200000})
    record = orch.run_tool_call(call, case_path)
    final = cm.validate_case(cm.read_json(case_path))
    evidence = [e for e in final['evidence'] if e.get('tool_run_id') == record.run_id
                and e.get('facet') == TOOL_ID]
    report = {'target_path': str(target), 'target_sha256': ref['verified_digest']['value'],
              'context_path': intake['context_path'], 'case_state_path': str(case_path),
              'case_id': state['case_id'], 'call_id': call['call_id'],
              'run_id': record.run_id, 'phase': record.phase, 'outcome': record.outcome,
              'reason_code': record.reason_code, 'error': record.error,
              'revision': final['revision'], 'feature_evidence_ids': [e['evidence_id'] for e in evidence],
              'feature_evidence_inline': [isinstance(e.get('value'), dict) for e in evidence],
              'provider': provider, 'provider_pins': [{'path': p, 'sha256': h} for p, h in pins],
              'artifact_root': str(config.artifacts_dir),
              'audit_ledger_root': str(config.ledgers_dir),
              'signer': 'InMemoryKeyProvider (TEST key)',
              'note': 'Real feature extraction; no LightGBM prediction in D.0 ToolResult.'}
    (config.home / 'integration_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--research-python', type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.file, args.home, args.research_python)
    print(json.dumps(result, indent=2))
    if result['outcome'] != 'SUCCESS' or len(result['feature_evidence_ids']) != 1:
        sys.exit(2)
