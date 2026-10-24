"""Contract tests for EMBER adapter boundary; no malware execution."""
import copy
import json
import sys
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from d0.validate import SCHEMAS, validate, ContractError

class EmberContractTests(unittest.TestCase):
    def fixture(self, name):
        return json.loads((ROOT / 'd0' / 'fixtures' / (name + '.json')).read_text(encoding='utf-8'))

    def test_schema_integrity(self):
        for name in ('ember-input-v1','ember-output-v1'):
            Draft202012Validator.check_schema(SCHEMAS[name])

    def test_positive_fixtures(self):
        for name in ('ember-input-v1','ember-output-v1'):
            validate(name,self.fixture(name))

    def test_d0_registry_and_call_bind_to_ember_schemas(self):
        spec=self.fixture('tool_spec')
        call=self.fixture('tool_call')
        self.assertEqual(spec['input_schema_id'],'ember-input-v1')
        self.assertEqual(spec['output_schema_id'],'ember-output-v1')
        validate(spec['input_schema_id'],call['arguments'])

    def test_reject_wrong_feature_version(self):
        with self.assertRaises(ContractError):
            validate('ember-input-v1', {'feature_version':3})

    def test_reject_unknown_arguments(self):
        with self.assertRaises(ContractError):
            validate('ember-input-v1', {'feature_version':2,'execute':True})

    def test_reject_wrong_vector_length(self):
        x=self.fixture('ember-output-v1');x['features'].pop()
        with self.assertRaises(ContractError): validate('ember-output-v1',x)

    def test_reject_non_numeric_feature(self):
        x=self.fixture('ember-output-v1');x['features'][0]='0.0'
        with self.assertRaises(ContractError): validate('ember-output-v1',x)

    def test_reject_wrong_hash(self):
        x=self.fixture('ember-output-v1');x['target_sha256']='abc'
        with self.assertRaises(ContractError): validate('ember-output-v1',x)

    def test_reject_non_finite_vector_values(self):
        x=self.fixture('ember-output-v1');x['features'][0]=float('nan')
        with self.assertRaises(ContractError): validate('ember-output-v1',x)

if __name__=='__main__': unittest.main()
