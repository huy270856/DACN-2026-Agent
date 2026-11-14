"""TASK 05A — Independent EMBER2018 v2 -> LightGBM static PE malware detection.

This package is an INDEPENDENT rebuild produced for TASK 05A. It does not import,
reuse, or depend on any prior-work model checkpoint, benchmark, or training
implementation from other team members. The only external authority it relies on
is the *official* EMBER2018 feature specification (elastic/ember, feature
version 2, 2381 dimensions) and the official dataset archive, both verified by
checksum at ingest time.

Modules:
    ember_v2      Independent reimplementation of the official EMBER v2 feature
                  vectorizer (raw feature record -> 2381-dim float32 vector).
    pe_extractor  Read-only raw-PE -> raw features -> vector path (LIEF based,
                  inference only; never executes the input).
    dataset       JSONL ingest, label semantics, dataset audit, vectorization.
    train_lightgbm  Independent LightGBM training CLI.
    evaluate      Labeled-test evaluation CLI.
    predict_cli   Read-only single-file inference CLI.
    manifests     Environment / provenance manifest helpers.
"""

FEATURE_VERSION = 2
FEATURE_COUNT = 2381

# Independent extractor identity (distinct from the upstream `ember` package).
EXTRACTOR_NAME = "dacn-independent-ember-v2"
EXTRACTOR_VERSION = "0.1.0"

__all__ = ["FEATURE_VERSION", "FEATURE_COUNT", "EXTRACTOR_NAME", "EXTRACTOR_VERSION"]
