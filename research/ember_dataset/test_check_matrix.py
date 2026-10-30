"""Tiny synthetic tests; these counts are not dataset measurements."""
import json
from pathlib import Path
import tempfile
import unittest

try:
    import numpy as np
except ImportError:
    np = None


@unittest.skipIf(np is None, 'Requires the isolated research NumPy environment')
class MatrixChecks(unittest.TestCase):
    def setUp(self):
        import check_matrix
        self.module = check_matrix
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / 'data'
        self.output = Path(self.temp.name) / 'matrix'
        self.data.mkdir(); self.output.mkdir()
        complete = {'splits': {}}
        for split, label in [('train', 0), ('test', 1)]:
            record = {'sha256': str(label) * 64, 'appeared': '2018-01', 'label': label}
            name = 'train_features_0.jsonl' if split == 'train' else 'test_features.jsonl'
            (self.data / name).write_text(json.dumps(record) + '\n', encoding='utf-8')
            (self.output / f'{split}_metadata.jsonl').write_text(json.dumps(record) + '\n', encoding='utf-8')
            np.save(self.output / f'X_{split}.npy', np.zeros((1, 2381), dtype='float32'))
            np.save(self.output / f'y_{split}.npy', np.array([label], dtype='int8'))
            complete['splits'][split] = {'labels': {str(label): 1}, 'files': [
                {'name': name, 'sha256': self.module.digest(self.data / name)}]}
        (self.output / 'COMPLETE.json').write_text(json.dumps(complete), encoding='utf-8')

    def test_complete_source_linkage(self):
        result = self.module.check(self.data, self.output)
        self.assertTrue(result['source_hashes_verified'])
        self.assertEqual(result['splits']['train']['metadata_rows_verified'], 1)

    def test_nonfinite_rejected(self):
        x = np.zeros((1, 2381), dtype='float32'); x[0, 42] = np.nan
        np.save(self.output / 'X_train.npy', x)
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            self.module.check(self.data, self.output)

    def test_wrong_metadata_rejected(self):
        (self.output / 'train_metadata.jsonl').write_text('{}\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'metadata/source mismatch'):
            self.module.check(self.data, self.output)

    def test_wrong_dtype_rejected(self):
        np.save(self.output / 'y_train.npy', np.array([0], dtype='float32'))
        with self.assertRaisesRegex(ValueError, 'dtype mismatch'):
            self.module.check(self.data, self.output)

    def test_wrong_vector_source_linkage_rejected(self):
        with self.assertRaisesRegex(ValueError, 'vector/source mismatch'):
            self.module.check(self.data, self.output, lambda record: np.ones(2381, dtype='float32'))

    def test_sampled_vector_source_linkage(self):
        result = self.module.check(self.data, self.output, lambda record: np.zeros(2381, dtype='float32'))
        self.assertEqual(result['splits']['train']['vector_rows_recomputed'], 1)

    def test_readonly_loader_and_metadata(self):
        from load_dataset import load_split, metadata_rows
        X, y = load_split(self.output, 'train')
        self.assertFalse(X.flags.writeable)
        self.assertFalse(y.flags.writeable)
        self.assertEqual(next(metadata_rows(self.output, 'train'))['label'], int(y[0]))
        del X, y

    def test_loader_requires_complete(self):
        from load_dataset import load_split
        (self.output / 'COMPLETE.json').unlink()
        with self.assertRaises(FileNotFoundError):
            load_split(self.output, 'train')


if __name__ == '__main__':
    unittest.main()
