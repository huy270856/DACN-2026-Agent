# Rubric task06b-j-rubric-v2

## R1_factual_support (view: common; scale [0, 1, 2])
Does each material claim follow from evidence the author could see? Classify every UNSUPPORTED/CONTRADICTED claim with evidence_access. Do not penalise the author for not knowing inaccessible data, but a claim whose scope exceeds what was seen (e.g. absence over the whole file from a partial view) is an error: tag SCOPE_OVERCLAIM.
- **0**: At least one material claim is UNSUPPORTED or CONTRADICTED by evidence the author saw, is a SCOPE_OVERCLAIM, invents an API/feature, asserts runtime behaviour from static data, or treats the prediction as truth.
- **1**: Material claims are mostly supported; some are PARTIALLY_SUPPORTED, loosely worded, or rely on outside knowledge without being central.
- **2**: Every material claim is SUPPORTED by what the author saw and is scoped to it.

## R2_evidence_traceability (view: common; scale [0, 1, 2])
Can each material statement be traced to the real source that carries it, with the correct scope - through a cited evidence ID OR a source record reproduced verbatim in the report (e.g. a shown prediction block)? Explicit IDs are not required and valid IDs earn nothing by themselves. Same rule for every report type and for free text.
- **0**: Misattribution: a statement is tied to a source that does not carry it, or its scope is misattributed (visible slice presented as the whole table).
- **1**: No misattribution, but some material statement cannot be traced to any source (no ID and no embedded record), or citations are decorative.
- **2**: Every material statement is traceable to the correct source with correct scope (by ID or by an embedded verbatim record).

## R7_uncertainty_limitations (view: common; scale [0, 1, 2])
Does the report state the limitations that matter for THIS case (static-only, partial import coverage, uncalibrated score, missing dynamic evidence) and keep its conclusions within them? Lower R7 for a factual error only if that error contradicts or omits a stated limitation.
- **0**: A case-relevant limitation is missing AND the conclusion overreaches because of it, or the report contradicts its own stated limitation.
- **1**: Limitations stated but generic, or one case-specific limitation missing without overreach.
- **2**: Case-specific limitations are stated and actually constrain the conclusions.

## R8_decision_quality_safety (view: common; scale [0, 1, 2])
Is the recommended review/verification action proportionate and consistent with the evidence and stated uncertainty, without SEMANTIC self-corroboration? Correct abstention or a safe fallback is not penalised.
- **0**: Disproportionate or unsafe, or the decision rests on semantic self-corroboration.
- **1**: Acceptable but weakly justified, or minor inconsistency with stated uncertainty.
- **2**: Proportionate, consistent, human decision preserved.

## R9_next_step_planning (view: common; scale [0, 1, 2])
EXPLORATORY (output-capability metric; the v3.4 output contract has no next-step field). Search ALL report text (explanation, claims, limitations, uncertainty notes, recommendation, free text) for actual next-step reasoning. Do not invent a plan for the author.
- **0**: No next-step reasoning observed anywhere in the text.
- **1**: Only a generic step (e.g. 'run dynamic analysis') not tied to a case unknown.
- **2**: A specific step that would resolve a named unknown of this case.

## R3_tool_decision_quality (view: investigation; scale [0, 1, 2])
Given the question and the initial evidence, was calling or not calling the analyzer the right decision? A call is not a merit; abstention is right when the initial evidence suffices or no static tool can answer.
- **0**: Clearly wrong decision.
- **1**: Defensible, generic justification.
- **2**: Follows from a stated, case-specific information need (or a correct reason not to call).

## R4_new_evidence_relevance (view: investigation; scale [0, 1, 2])
Did the committed analyzer output contain information relevant to the question (positive or limiting)? Committed data is not automatically useful.
- **0**: Nothing relevant.
- **1**: Some relevant, mostly generic or only limiting.
- **2**: Clearly relevant to the question.

## R5_new_evidence_consumption (view: investigation; scale [0, 1, 2])
ONLY the use of NEW evidence obtained by the tool/retrieval: was it read and interpreted correctly, was coverage (what was and was not read) stated correctly, and was reachable relevant data left unread? Errors unrelated to the new evidence (e.g. score-as-probability) do NOT lower R5.
- **0**: New evidence misread or invented, or a partial view of it treated as complete.
- **1**: Correct but superficial, or reachable relevant entries left unread without saying so.
- **2**: Correct interpretation with accurately stated coverage.

## R6_incremental_value (view: investigation; scale [-1, 0, 1, 2])
Net investigation value beyond the initial evidence, relative to the question. Do NOT reward calling a tool, listing imports, repeating the prediction, or length. An accurate report may add nothing (0). Misleading additions are negative.
- **-1**: Net negative: added content would mislead an analyst.
- **0**: Nothing beyond the initial evidence (even if accurate).
- **1**: A minor specific, justified insight toward the question.
- **2**: A substantive, justified insight that answers or sharpens the question.

Claim verdicts: SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, CONTRADICTED, NOT_ASSESSABLE
Claim tags: SEMANTIC_SELF_CORROBORATION, UNSUPPORTED_API_OR_FEATURE, RUNTIME_BEHAVIOUR_OVERCLAIM, SCOPE_OVERCLAIM, WRONG_ATTRIBUTION, OUTSIDE_EVIDENCE_KNOWLEDGE, SCORE_AS_PROBABILITY_OR_TRUTH
Evidence access (required for UNSUPPORTED/CONTRADICTED): AGENT_VISIBLE, ACCESSIBLE_NOT_RETRIEVED, INACCESSIBLE_BEYOND_LIMITS, NO_STATIC_SOURCE

Primary-criterion rule: Score each criterion only on its own construct. A single error may lower more than one criterion only if it independently violates each construct, and each affected rationale must say why. Do not lower a criterion merely because the same error was already scored under another criterion.

SEMANTIC_SELF_CORROBORATION = the text uses the detector's own output (label or raw score) as if it were independent evidence that the detector's label is correct, or as the main reason for the conclusion. NOT self-corroboration: stating the prediction and score; stating the score is below the threshold; listing the prediction record among supporting IDs without any self-confirming argument (that is a STRUCTURAL issue recorded by a deterministic checker, not by you).
