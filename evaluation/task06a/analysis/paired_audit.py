"""Evaluator-only diagnostics of ALL saved pairs; never calls an LLM.

Review normalization uses the published 05C-R2 mapping, separate from raw flags.
These supplemental diagnostics were added after DEV; they are not confirmatory.
"""
from collections import Counter
from pathlib import Path
from evaluation.task05c.repair.triage import normalized_review
from evaluation.task06a.experiment import digest, read, write_new, validate_freeze


def binary_rates(predicted, truth):
    tp = sum(p and y for p, y in zip(predicted, truth))
    tn = sum(not p and not y for p, y in zip(predicted, truth))
    positives = sum(truth)
    negatives = len(truth) - positives
    return {"n_errors": positives, "n_correct": negatives,
            "review_error_sensitivity": tp / positives if positives else None,
            "review_error_specificity": tn / negatives if negatives else None}


def main():
    out = Path("evaluation/task06a/results/dev_v2_1")
    validate_freeze(out)
    manifest = read(out / "manifest_EVALUATOR_ONLY.json")
    inputs = read(out / "inputs.json")
    error_truth = [r["correctness"].startswith("F") for r in manifest["samples"]]
    rows, aggregate = [], {}
    for arm in ("v1", "v2"):
        raw_flags, normalized_flags, effective_flags = [], [], []
        own_verdict = Counter()
        mismatches = 0
        for i, item in enumerate(inputs):
            path = out / "responses" / f"{i:03d}_{arm}.json"
            r = read(path)
            a = r["assessment"]
            norm = normalized_review(a.get("recommendation"))
            raw_review = a.get("review_required")
            if raw_review is not norm:
                mismatches += 1
            own_verdict[a.get("agent_own_verdict", "NOT_IN_V2_ASSESSMENT_CONTRACT")] += 1
            raw_flags.append(raw_review is True)
            normalized_flags.append(norm is True)
            effective_flags.append(r["screen"]["effective_recommendation"]["review_required"])
            rows.append({"index": i, "sha256": item["sha256"], "arm": arm,
                         "classifier_correctness_EVALUATOR_ONLY": manifest["samples"][i]["correctness"],
                         "response_sha256": digest(path), "response": path.as_posix(),
                         "raw_review": raw_review, "normalized_review": norm,
                         "review_action_disagreement": raw_review is not norm,
                         "effective_review": effective_flags[-1],
                         "screen_flags": r["screen"]["flags"],
                         "decision_flags": r["screen"]["consistency"]["flags"],
                         "claim_flags": r["screen"]["claim_flags"],
                         "semantic_grade": "PENDING independent assessment"})
        aggregate[arm] = {"raw_review_action_disagreement": mismatches,
                          "raw_action_normalized_review_count": sum(normalized_flags),
                          "own_verdict_distribution": dict(own_verdict),
                          "raw_bool_error_review": binary_rates(raw_flags, error_truth),
                          "raw_action_error_review": binary_rates(normalized_flags, error_truth),
                          "effective_error_review": binary_rates(effective_flags, error_truth)}
    result = {"method": "EVALUATOR_ONLY_POST_DEV_DIAGNOSTIC_NO_INFERENCE_NO_GRADING",
              "source_sha256": digest(Path(__file__)), "aggregate": aggregate, "all_cases": rows,
              "caveat": "Only one FN and no FP; ratios do not establish detector-error discovery/generalization"}
    write_new(out / "supplemental_audit_EVALUATOR_ONLY.json", result)
    print(aggregate)


if __name__ == "__main__":
    main()
