# D.0 EMBER contract patch v1 (2026-10-24)

Adds the two missing schema IDs referenced by `d0/fixtures/tool_spec.json`: `ember-input-v1` and `ember-output-v1`. This is a **proposed internal adapter contract**, not a schema supplied by upstream EMBER.

## Boundaries

- `ember-input-v1` validates `ToolCall.arguments`, not the whole ToolCall. `ToolCall.target_ref` supplies the target identity. D5 must verify it and read the exact approved file.
- `ember-output-v1` validates the **successful feature-extraction provider payload**, not the D.0 `ToolResult` envelope. D7 validates the payload against this schema and then validates the wrapped ToolResult against `tool_result.schema.json`.
- `feature_version=2` is locked to the classic EMBER v2 **2381-dimensional** vector. Huy must confirm the extractor/version in use matches this exact vector before integration; do not silently accept a different EMBER variant.
- `features` is an array of 2381 finite JSON numbers; `target_sha256` binds the extracted features to the file bytes. Check it matches `ToolCall.target_ref.verified_digest.value` and revalidated file hash.
- A failure/unsupported file is expressed using `ToolResult.status/error`, **not** a fake all-zero vector. The included all-zero output is synthetic for contract testing, not real malware data or a valid analytical result.
- This schema is **feature extraction only**, not LightGBM inference. The prediction needs a separate schema after the team decides on model version, threshold, calibration and class semantics.
- `include_feature_vector` is reserved and defaults true. Do not set it false until an artifact-backed output contract is specified.

## Install

Extract `DACN_D0_EMBER_contract_patch_v1.zip` at repository root **after** D.0 files are installed, preserving folders. This patch adds schemas, fixtures, tests and modifies `d0/validate.py` to reject NaN/Infinity.

```powershell
python -m pip install -r requirements-d0.txt
python -m unittest discover -s tests -p "test_ember_contracts.py" -v
python -m unittest discover -s tests -p "test_d0*.py" -v
```

## Owners

- Huy: confirm real EMBER v2 extractor output shape, version, type/finite-value handling and target binding.
- Tuấn: D3 validates `ToolCall.arguments` with `ember-input-v1`; D7 validates provider payload with `ember-output-v1` before accepting the D.0 `ToolResult`.
- Lead: approve contract changes and ensure ToolSpec references these IDs.

Do not execute suspicious samples on the host to validate these contracts.
