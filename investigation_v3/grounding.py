"""Literal new-fact checks; semantic relevance remains unverified."""
import copy
from evaluation.task06a.verification import screen
from .imports_tool import FACET


def verify(proposal, facts, initial_ids, prediction):
    visible = {e["evidence_id"]: e for e in facts["evidence"]}
    checks_facts = copy.deepcopy(facts)
    for e in checks_facts["evidence"]:
        if e["facet"] == FACET and isinstance(e["value"], dict):
            entries = e["value"]["entries"]
            e["facet"] = "static.imports_summary"
            e["value"] = {"libraries": sorted({x["library"] for x in entries}),
                          "sampled_imports": [x["library"] + ":" + (x["symbol"] or "ordinal" + str(x["ordinal"])) for x in entries]}
    checks = screen(proposal["assessment"], checks_facts, prediction)
    uses, invalid = [], []
    for use in proposal["new_fact_uses"]:
        ev = visible.get(use["evidence_id"], {})
        valid = (use["evidence_id"] not in initial_ids and ev.get("facet") == FACET
                 and any(x["library"] == use["library"] and x["symbol"] == use["symbol"]
                         for x in (ev.get("value") or {}).get("entries", [])))
        (uses if valid else invalid).append(use)
    if invalid:
        checks["effective_recommendation"].update(action="MANUAL_REVIEW", review_required=True)
    checks.update(literal_new_fact_uses=uses, unsupported_new_fact_uses_suspected=invalid,
                  semantic_relevance="PENDING_INDEPENDENT_REVIEW")
    return checks
