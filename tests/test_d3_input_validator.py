"""D3 tests use D.0 fixtures and a TEST-ONLY argument schema, not EMBER's API."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchestrator.input_validator import ValidationError, validate_tool_call


def fixture(name):
    return json.loads((ROOT / 'd0' / 'fixtures' / f'{name}.json').read_text(
        encoding='utf8'))


class InputValidatorTests(unittest.TestCase):
    def setUp(self):
        self.call = fixture('tool_call')
        self.spec = fixture('tool_spec')
        self.case = dict(case_id=self.call['case_id'], revision=1,
                         target_ref=fixture('target_ref'))
        # Explicit mock contract. The real schema must be supplied by the team.
        self.spec['input_schema_id'] = 'test-only-input-v1'
        self.schemas = {'test-only-input-v1': {
            'type': 'object', 'required': ['feature_version'],
            'properties': {'feature_version': {'type': 'integer', 'const': 2}},
            'additionalProperties': False,
        }}

    def run_validation(self, **kwargs):
        return validate_tool_call(self.call, self.spec, self.case,
                                  input_schemas=self.schemas, **kwargs)

    def reject(self, code, **kwargs):
        with self.assertRaises(ValidationError) as caught:
            self.run_validation(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.call_id, self.call.get('call_id'))

    def test_valid_candidate_is_separate_and_inputs_unchanged(self):
        before = copy.deepcopy((self.call, self.spec, self.case))
        result = self.run_validation()
        self.assertEqual(result, self.call)
        result['arguments']['feature_version'] = 99
        self.assertEqual((self.call, self.spec, self.case), before)

    def test_bad_envelope(self):
        for change in ('missing', 'extra', 'bad_type'):
            with self.subTest(change=change):
                self.call = fixture('tool_call')
                if change == 'missing':
                    del self.call['reason']
                elif change == 'extra':
                    self.call['human_approved'] = True
                else:
                    self.call['expected_revision'] = '1'
                self.reject('SCHEMA_INVALID')

    def test_unknown_tool(self):
        self.spec = None
        self.reject('TOOL_UNKNOWN')

    def test_wrong_registered_tool(self):
        self.call['tool_id'] = 'other.tool'
        self.reject('TOOL_UNKNOWN')

    def test_disabled(self):
        self.spec['enabled'] = False
        self.reject('TOOL_DISABLED')

    def test_provider_and_version_binding(self):
        for key in ('provider_id', 'tool_version'):
            with self.subTest(key=key):
                self.call = fixture('tool_call')
                self.call[key] = 'other'
                self.reject('PROVIDER_MISMATCH')

    def test_unavailable_provider(self):
        self.reject('PROVIDER_UNAVAILABLE', provider_available=False)

    def test_unsupported_target(self):
        self.spec['supported_targets'] = ['PROCESS']
        self.reject('SCHEMA_INVALID')

    def test_wrong_case(self):
        self.call['case_id'] = 'CASE-other'
        self.reject('SCHEMA_INVALID')

    def test_stale_revision(self):
        self.case['revision'] = 2
        self.reject('CASE_REVISION_STALE')

    def test_target_changed(self):
        self.call['target_ref']['verified_digest']['value'] = 'b' * 64
        self.reject('TARGET_CHANGED')

    def test_identity_unavailable(self):
        self.call['target_ref']['identity_strength'] = 'UNAVAILABLE'
        self.reject('TARGET_IDENTITY_UNAVAILABLE')

    def test_target_missing_path(self):
        self.call['target_ref']['observed'] = {'other': 'value'}
        self.reject('SCHEMA_INVALID')

    def test_budget_boundaries(self):
        for key in ('timeout_ms', 'max_output_bytes'):
            with self.subTest(key=key):
                self.call = fixture('tool_call')
                self.call['budget'][key] = self.spec['limits'][key]
                self.run_validation()
                self.call['budget'][key] += 1
                self.reject('BUDGET_EXCEEDED')

    def test_arguments_rejected(self):
        for arguments in ({}, {'feature_version': '2'},
                          {'feature_version': 2, 'shell': 'arbitrary command'}):
            with self.subTest(arguments=arguments):
                self.call['arguments'] = arguments
                self.reject('SCHEMA_INVALID')

    def test_missing_schema_fails_closed(self):
        self.schemas = {}
        self.reject('SCHEMA_INVALID')

    def test_invalid_schema(self):
        self.schemas['test-only-input-v1'] = {'type': 'made-up-type'}
        self.reject('SCHEMA_INVALID')

    def test_unresolved_reference_fails_closed(self):
        self.schemas['test-only-input-v1'] = {'$ref': 'https://example.invalid/missing'}
        self.reject('SCHEMA_INVALID')

    def test_bad_case_snapshot(self):
        self.case['revision'] = True
        self.reject('SCHEMA_INVALID')

    def test_non_json_number(self):
        self.call['arguments']['extra'] = float('nan')
        self.reject('SCHEMA_INVALID')


class EmberInputTests(unittest.TestCase):
    def setUp(self):
        self.call = fixture('tool_call')
        self.spec = fixture('tool_spec')
        self.case = dict(case_id=self.call['case_id'], revision=1,
                         target_ref=fixture('target_ref'))

    def test_real_schema_default_and_explicit_vector(self):
        for arguments in (fixture('ember-input-v1'),
                          {'feature_version': 2, 'include_feature_vector': True}):
            with self.subTest(arguments=arguments):
                self.call['arguments'] = arguments
                self.assertEqual(validate_tool_call(self.call, self.spec, self.case), self.call)

    def test_invalid_ember_arguments(self):
        for arguments in ({'feature_version': 3}, {'feature_version': '2'},
                          {'feature_version': 2, 'include_feature_vector': False},
                          {'feature_version': 2, 'include_feature_vector': 'true'},
                          {'feature_version': 2, 'path': 'different.exe'},
                          {'feature_version': 2, 'execute': True}):
            with self.subTest(arguments=arguments):
                self.call['arguments'] = arguments
                with self.assertRaises(ValidationError) as caught:
                    validate_tool_call(self.call, self.spec, self.case)
                self.assertEqual(caught.exception.code, 'SCHEMA_INVALID')


if __name__ == '__main__':
    unittest.main()
