# Ti?n ?? th?c nghi?m TASK 04B

H? th?ng d?ng SLM local Qwen3.5-4B Q4_K_M tr?n Ollama 0.40.15, kh?ng g?i cloud API.
Model ?? xu?t action JSON; Python Controller ki?m schema, evidence, revision, workflow v? budgets.
Node C l?u CaseState; tool execution ?i qua trusted orchestrator D1?D9.

Hai l??t live E2E thinking OFF ?? th?nh c?ng: model sinh TOOL_CALL, analyzer MOCK ch?y qua
D1?D9, Node C c?p nh?t revision 3, model ??c evidence m?i v? FINISH INSUFFICIENT_EVIDENCE.
??y l? th?nh c?ng c?a v?ng ?i?u ph?i, kh?ng ph?i b?ng ch?ng kh? n?ng ph?t hi?n malware.
Analyzer ch? tr? placeholder, kh?ng c? classifier inference.

Unit agent 27 PASS; mock E2E 1 PASS. Regression 239 tests OK (1 SKIP), 129 tests OK (2 SKIP).
Benchmark s?u scenario, m?i scenario l?p hai l?n cho m?i thinking mode: t?ng 24 proposal probes.
Thinking OFF ??t rubric 10/12; JSON/schema/controller h?p l? 12/12. Hai l?i l? assessment
known-benign ch?a ??ng k? v?ng. Thinking ON kh?ng ??t trong cap 15 gi?y/proposal;
kh?ng ???c coi timeout l? ho?n t?t. S? li?u latency v? usage n?m trong benchmark_summary.json.
C?c probe d?ng fixture t?ng h?p tr?n intake benign th?t; kh?ng ph?i 24 full investigation E2E.
Model 1.7B kh?ng c?n local n?n kh?ng c? so s?nh c?ng c?u h?nh; k?t qu? c? kh?ng g?p chung.

Tr?ng th?i TASK 04B: PARTIAL. REA/Ghidra ch?a t?ch h?p; EMBER/LightGBM ch?a inference;
sandbox dynamic ch?a tri?n khai. Kh?ng ch?y binary ??ch, kh?ng response/quarantine t? ??ng.
Ch?a c? b?ng ch?ng v? accuracy ph?t hi?n malware ho?c an to?n ng? ngh?a tr??c m?i prompt injection.
