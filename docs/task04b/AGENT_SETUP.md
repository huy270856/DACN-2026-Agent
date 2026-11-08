# Local investigation Agent

Windows, Python dependencies from the repository, Ollama local (tested 0.40.15).

```
ollama pull qwen3.5:4b
ollama show qwen3.5:4b
python -m dacn investigate --case-id CASE_ID
```

Default: qwen3.5:4b, thinking OFF, temperature 0.1, seed 42, num_ctx 8192,
num_predict 1536. For explicit comparison only set DACN_AGENT_MODEL=qwen3:1.7b
when that exact model is installed. No fallback or cloud SDK.
DACN_AGENT_THINK=1 (or --think) enables thinking; the measured small output cap
may yield empty answers or timeouts. Do not count these as completed investigations.
DACN_AGENT_MAX_ITERS / DACN_AGENT_MAX_TOOLS configure trusted budgets.
Additional budgets are available through AgentConfig construction.

AgentConfig.known_reputations is an operator-maintained trusted hash snapshot;
use only current, verified and consistent entries. It never reads reputation
claims from malware strings. No reputation provider or freshness refresh is integrated.
Known entries permit a matching verdict only with an existing successful sha256 citation.
All other cases retain static-first. Analyzer is explicitly MOCK, not EMBER inference.

Run unit/mock: python -m unittest discover -s tests -p test_agent.py -v
Set DACN_AGENT_LIVE=1 for strict real-model E2E; thinking defaults OFF.
Run fixed synthetic scenario probes: python tests/benchmark_agent.py
Scenario fixtures are evaluation data, never production evidence.

Local inference contract follows official Ollama documentation:
[structured output](https://docs.ollama.com/capabilities/structured-outputs),
[thinking controls](https://docs.ollama.com/capabilities/thinking),
[usage metadata](https://docs.ollama.com/api/chat).
Runtime show/tags and exact digest are in runtime.json.

Timeout limits the client socket wait and trusted tool timeout_ms. Closing a request
is not proof of immediate server/GPU cancellation. D1/D6 cleanup/commit can extend
past timeout; no hard real-time guarantee. Token accounting records actual prompt/eval
counts and charges at least 8192 + 2*num_predict per turn because thinking accounting
may be incomplete. This is conservative admission control, not proof of exact tokenizer
or hidden reasoning usage. Errors stop the loop without a benign verdict.

No REA/Ghidra adapter, real EMBER/LightGBM inference, dynamic sandbox or response action.
