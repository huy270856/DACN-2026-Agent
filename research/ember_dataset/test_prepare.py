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
            records=[dict(dict.fromkeys(m.GROUPS, {}), label=x) for x in (0,1,-1,None,True)]
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

class IntegrityTests(unittest.TestCase):
    def test_resume_and_range_ignored(self):
        import io
        from unittest.mock import patch
        for status, headers, body in [(206, {'Content-Range': 'bytes 3-5/6'}, b'def'),
                                       (200, {'Content-Length': '6'}, b'abcdef')]:
            with tempfile.TemporaryDirectory() as t:
                path = Path(t) / 'download.part'; path.write_bytes(b'abc')
                response = io.BytesIO(body); response.status = status; response.headers = headers
                with patch.object(m.urllib.request, 'urlopen', return_value=response) as opened:
                    m.download_partial(path)
                    self.assertEqual(opened.call_args[0][0].get_header('Range'), 'bytes=3-')
                self.assertEqual(path.read_bytes(), b'abcdef')

    def test_bad_range_preserves_partial(self):
        import io
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'download.part'; path.write_bytes(b'abc')
            response = io.BytesIO(b'def'); response.status = 206
            response.headers = {'Content-Range': 'bytes 0-2/6'}
            with patch.object(m.urllib.request, 'urlopen', return_value=response):
                with self.assertRaisesRegex(ValueError, 'Content-Range'):
                    m.download_partial(path)
            self.assertEqual(path.read_bytes(), b'abc')

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad.jsonl'; p.write_text('{"label":NaN}')
            with self.assertRaisesRegex(ValueError,'Non-finite'):
                list(m.rows([p]))

    def test_cross_split_duplicate(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            row=dict(dict.fromkeys(m.GROUPS,{}), label=0, sha256='a'*64)
            for name in ('train_features_0.jsonl','test_features.jsonl'):
                (root/name).write_text(json.dumps(row))
            report=m.audit(root)
            self.assertEqual(report['splits']['test']['cross_split_overlap_rows'],1)
            self.assertIsNone(report['verified_feature_version'])

    def test_archive_and_extracted_integrity(self):
        import tarfile
        import io
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); archive=root/'ember_dataset_2018_2.tar.bz2'
            names=[f'train_features_{i}.jsonl' for i in range(6)]+['test_features.jsonl']
            with tarfile.open(archive,'w:bz2') as tar:
                for name in names:
                    data=b'{"label":0}\n'
                    (root/name).write_bytes(data)
                    member=tarfile.TarInfo('ember2018/'+name);member.size=len(data)
                    tar.addfile(member,io.BytesIO(data))
            with patch.object(m,'SHA',m.digest(archive)):
                self.assertEqual(m.verify(root)['verified_feature_version'],2)
                (root/names[0]).write_text('tampered')
                with self.assertRaisesRegex(ValueError,'JSONL mismatch'):
                    m.verify(root)
            with patch.object(m,'SHA','0'*64):
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                    m.verify(root)

    def test_matrix_requires_verified_source_before_dependencies(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with self.assertRaises(FileNotFoundError):
                m.matrix(root,root/'output')
            self.assertFalse((root/'output').exists())
