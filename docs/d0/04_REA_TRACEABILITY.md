# REA -> DACN D.0 traceability

**Public references** (checked 2026-10-23):

- REA README: https://github.com/morluto/rea
- REA MCP runtime contracts: https://github.com/morluto/rea/blob/main/docs/mcp-contracts.md
- REA tool design: https://github.com/morluto/rea/blob/main/docs/tool-design.md

The following table distinguishes **REA documented behavior** from **our design**. No REA source code was copied; this package is original Python/JSON contract scaffolding.

| REA documented concept | Our D.0 adaptation | Divergence / owner |
|---|---|---|
| `structuredContent.normalized_result` separate from `raw_result` | `tool_result.observations` + `raw_artifacts` | No MCP transport; D7/D9 |
| Evidence IDs, analysis profile, per-facet coverage, unknown vs observed-empty | B/C Evidence v2; `observation.status/coverage/value` | C v1.2 projection loses detail; D7/D9 |
| Selected concrete provider/version; no automatic fallback after failure | `tool_spec.provider`, `tool_call.provider_id`, immutable `execution_receipt.provider` | One provider per ToolSpec version; D2/D5 |
| Tool availability distinct from capability discovery | D2 registry and D4 policy independently check enabled/available/authorized | CLI Python not REA MCP; D2/D4 |
| Target-derived text marked untrusted even on errors | `content_origin` + `trust_level` per observation; Agent prompt boundary | Mark provider output untrusted by default; D7/Agent |
| Cancellation distinct from timeout, cleanup state retained | `execution_receipt.outcome` + `cleanup` | D6 must implement process ownership/cleanup |
| Bounded result views; full Evidence retained | `artifact` refs with hashes; bounded inline observations | D5/D7/D9; do not inline huge logs |
| Tool effect metadata describes behavior but does not grant permission | `effects` contract plus separate `policy_decision` | Our policy is stricter for malware execution; D4 |
| Canonical schemas validated before dispatch | JSON Schema + Python semantic checks | D3/D7; cross-field + OS controls required |
| REA's experimental Windows Ghidra P0 restricted to approved PE | Optional read-only reverse engineering adapter later | Not a malware sandbox; no requirement to integrate REA runtime |

## Deliberately NOT imported

- MCP SDK, TypeScript tool catalog, Hopper/Ghidra internals, REA session model, REA installer and remote transports.
- REA's product-specific decompilation workflow as a replacement for EMBER/LightGBM.
- Any assumption that REA supports safely executing arbitrary malware on the Windows host.

## Citation discipline for thesis

Use the linked REA docs as inspiration for design choices. Attribute concepts, not invented API compatibility. Describe Node D contracts as **our implementation** and note that REA's `Evidence v2` and our `evidence-v2` are **not the same schema**, despite sharing a name. Record REA commit/version in final thesis bibliography when the team freezes its external references.
