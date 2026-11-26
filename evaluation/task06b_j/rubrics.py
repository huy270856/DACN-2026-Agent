"""Rubric version registry. v1 stays the default for every pre-existing artifact."""
from evaluation.task06b_j import rubric as v1, rubric_v2 as v2

REGISTRY = {v1.RUBRIC_ID: v1, v2.RUBRIC_ID: v2}


def get(rubric_id: str):
    if rubric_id not in REGISTRY:
        raise KeyError(f"unknown rubric {rubric_id!r}")
    return REGISTRY[rubric_id]
