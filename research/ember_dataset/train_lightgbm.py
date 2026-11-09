"""Train an EMBER2018-v2 LightGBM baseline with a chronological validation split.

The official November/December test split is opened only after the model and
operating threshold have been fixed using the October validation split.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from load_dataset import load_split, metadata_rows


FEATURE_COUNT = 2381
VALIDATION_MONTH = '2018-10'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def chronological_masks(matrix, expected_rows):
    months = [row['appeared'][:7] for row in metadata_rows(matrix, 'train')]
    if len(months) != expected_rows or any(not month for month in months):
        raise ValueError('Expected dated labeled training rows')
    train = np.fromiter((month < VALIDATION_MONTH for month in months), dtype=np.bool_, count=len(months))
    valid = np.fromiter((month == VALIDATION_MONTH for month in months), dtype=np.bool_, count=len(months))
    if not train.any() or not valid.any() or np.count_nonzero(train | valid) != len(months):
        raise ValueError('Unexpected chronology in official training split')
    return train, valid


def threshold_for_fpr(benign_scores, max_fpr):
    scores = np.asarray(benign_scores, dtype=np.float64)
    if scores.ndim != 1 or not len(scores) or not np.isfinite(scores).all():
        raise ValueError('Need finite benign validation scores')
    if not 0 < max_fpr < 1:
        raise ValueError('max_fpr must be between 0 and 1')
    allowed = int(math.floor(max_fpr * len(scores)))
    sorted_scores = np.sort(scores)
    return float(np.nextafter(sorted_scores[len(scores) - allowed - 1], np.inf))


def metrics(y, scores, threshold):
    y = np.asarray(y)
    scores = np.asarray(scores)
    if set(np.unique(y)) != {0, 1} or not np.isfinite(scores).all():
        raise ValueError('Both binary classes and finite scores required')
    pred = scores >= threshold
    benign = y == 0
    malicious = y == 1
    fp = int(np.count_nonzero(pred & benign))
    tn = int(np.count_nonzero(~pred & benign))
    tp = int(np.count_nonzero(pred & malicious))
    fn = int(np.count_nonzero(~pred & malicious))
    return {'rows': int(len(y)), 'labels': {'0': int(np.count_nonzero(benign)),
                                           '1': int(np.count_nonzero(malicious))},
            'roc_auc': float(roc_auc_score(y, scores)),
            'partial_auc_fpr_0_01': float(roc_auc_score(y, scores, max_fpr=0.01)),
            'average_precision': float(average_precision_score(y, scores)),
            'threshold': float(threshold), 'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn,
            'fpr': fp / (fp + tn), 'tpr': tp / (tp + fn)}


def train(matrix, output, max_rounds, max_fpr, threads):
    matrix = Path(matrix)
    output = Path(output)
    if output.exists():
        raise FileExistsError('Output must be a new directory: {}'.format(output))
    complete = json.loads((matrix / 'COMPLETE.json').read_text(encoding='utf-8'))
    if complete['archive_sha256'] != 'b6052eb8d350a49a8d5a5396fbe7d16cf42848b86ff969b77464434cf2997812':
        raise ValueError('Unexpected EMBER archive provenance')
    if complete['verified_feature_version'] != 2:
        raise ValueError('Expected verified EMBER v2')
    X, y = load_split(matrix, 'train')
    train_mask, valid_mask = chronological_masks(matrix, len(y))
    y_fit, y_valid = y[train_mask], y[valid_mask]
    if set(np.unique(y_fit)) != {0, 1} or set(np.unique(y_valid)) != {0, 1}:
        raise ValueError('Both classes required in train and validation')
    params = {'objective': 'binary', 'metric': 'auc', 'boosting_type': 'gbdt',
              'learning_rate': 0.05, 'num_leaves': 64, 'max_bin': 255,
              'min_data_in_leaf': 50, 'feature_fraction': 0.8,
              'feature_fraction_seed': 2026, 'seed': 2026,
              'num_threads': threads, 'verbosity': -1}
    output.mkdir(parents=True)
    (output / 'RUNNING.json').write_text(json.dumps({'matrix': str(matrix),
        'train_rows': int(train_mask.sum()), 'validation_rows': int(valid_mask.sum()),
        'validation_month': VALIDATION_MONTH, 'params': params,
        'max_rounds': max_rounds, 'max_fpr': max_fpr}, indent=2), encoding='utf-8')
    fit = lgb.Dataset(X[train_mask], label=y_fit, free_raw_data=True)
    validation = lgb.Dataset(X[valid_mask], label=y_valid, reference=fit, free_raw_data=True)
    first = lgb.train(params, fit, num_boost_round=max_rounds,
                      valid_sets=[validation], valid_names=['october_validation'],
                      callbacks=[lgb.early_stopping(30, verbose=True), lgb.log_evaluation(25)])
    rounds = int(first.best_iteration)
    if rounds <= 0:
        raise ValueError('No selected boosting iteration')
    valid_scores = first.predict(X[valid_mask], num_iteration=rounds, num_threads=threads)
    threshold = threshold_for_fpr(valid_scores[y_valid == 0], max_fpr)
    validation_result = metrics(y_valid, valid_scores, threshold)
    (output / 'VALIDATION.json').write_text(json.dumps({'best_iteration': rounds,
        'metrics': validation_result}, indent=2), encoding='utf-8')
    model_path = output / 'model.txt'
    first.save_model(str(model_path), num_iteration=rounds)
    del fit, validation, valid_scores
    # The official test set is read only after all fitting and threshold selection.
    X_test, y_test = load_split(matrix, 'test')
    test_scores = first.predict(X_test, num_iteration=rounds, num_threads=threads)
    test_result = metrics(y_test, test_scores, threshold)
    report = {'dataset': 'EMBER2018 v2', 'feature_version': 2,
              'feature_count': FEATURE_COUNT, 'archive_sha256': complete['archive_sha256'],
              'matrix': str(matrix), 'matrix_complete_sha256': sha256(matrix / 'COMPLETE.json'),
              'training': {'rows': int(train_mask.sum()), 'validation_rows': int(valid_mask.sum()),
                           'validation_month': VALIDATION_MONTH,
                           'best_iteration': rounds, 'params': params},
              'threshold_selection': {'source': 'October 2018 benign validation rows',
                                      'target_max_fpr': max_fpr},
              'validation': validation_result, 'official_test': test_result,
              'model': {'path': str(model_path), 'sha256': sha256(model_path)},
              'versions': {'lightgbm': lgb.__version__, 'numpy': np.__version__},
              'limitations': ['EMBER labels are retrospective; benchmark does not establish current-world detection.',
                              'LightGBM scores are not calibrated probabilities.',
                              'Feature JSON vectorization does not independently verify raw PE parsing.']}
    (output / 'REPORT.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'RUNNING.json').unlink()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-rounds', type=int, default=300)
    parser.add_argument('--max-fpr', type=float, default=0.01)
    parser.add_argument('--threads', type=int, default=8)
    args = parser.parse_args()
    if args.max_rounds < 1 or args.threads < 1:
        parser.error('max-rounds and threads must be positive')
    print(json.dumps(train(args.matrix, args.output, args.max_rounds, args.max_fpr, args.threads), indent=2))
