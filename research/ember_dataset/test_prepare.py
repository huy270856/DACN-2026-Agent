import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
spec = importlib.util.spec_from_file_location('prepare', Path(__file__).with_name('prepare.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class Tests(unittest.TestCase):
    def test_audit_distinguishes_unknown_missing_invalid(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            records=[dict.fromkeys(m.GROUPS, {}) | {'label': x} for x in (0,1,-1,None,True)]
            (root/'train_features_0.jsonl').write_text('\n'.join(map(json.dumps,records)))
            (root/'test_features.jsonl').write_text(json.dumps({'label':1}))
            result=m.audit(root)
            self.assertEqual(result['splits']['train']['labels'],{'0':1,'1':1,'-1':1,'missing_or_null':1,'invalid':1})
            self.assertEqual(result['splits']['test']['missing_feature_groups']['histogram'],1)
    def test_malformed_reports_location(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad.jsonl';p.write_text('{bad}')
            with self.assertRaisesRegex(ValueError,'bad.jsonl:1'):
                list(m.rows([p]))
    def test_digest(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'empty';p.write_bytes(b'')
            self.assertEqual(m.digest(p),'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')

if __name__=='__main__':unittest.main()
