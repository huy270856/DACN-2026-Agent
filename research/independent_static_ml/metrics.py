"""Shared evaluation metrics (threshold selection + full metric suite)."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             roc_auc_score)


def threshold_at_fpr(y_true, scores, target_fpr):
    """Smallest threshold whose FPR on (y_true, scores) is <= target_fpr.

    Computed on a validation set only. Returns a float threshold in [0, 1].
    """
    y_true = np.asarray(y_true)
    scores = np.asarray(scores)
    neg = scores[y_true == 0]
    if neg.size == 0:
        return 0.5
    # threshold = (1 - target_fpr) quantile of negative scores; predictions use
    # score >= threshold, so at most target_fpr of negatives are flagged.
    q = np.quantile(neg, 1.0 - target_fpr, method="higher")
    return float(min(max(q, 0.0), 1.0))


def compute_metrics(y_true, scores, threshold):
    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores, dtype=float)
    y_pred = (scores >= threshold).astype(int)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0            # TPR
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    try:
        auc = float(roc_auc_score(y_true, scores))
    except ValueError:
        auc = None
    try:
        ap = float(average_precision_score(y_true, scores))
    except ValueError:
        ap = None

    return {
        "threshold": float(threshold),
        "n": int(y_true.size),
        "n_benign": int((y_true == 0).sum()),
        "n_malicious": int((y_true == 1).sum()),
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "precision": precision,
        "recall_tpr": recall,
        "f1": f1,
        "false_positive_rate": fpr,
        "roc_auc": auc,
        "average_precision": ap,
    }
