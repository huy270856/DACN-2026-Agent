"""D5 subprocess provider: read the staged PE bytes and emit ember-output-v1.

Runs under the isolated EMBER Python environment. It never executes the PE.
Only stdout JSON is the provider payload; errors go to stderr with nonzero exit.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import ember
import lief
import numpy as np


def extract(target, options):
    if options.get('feature_version') != 2 or options.get('include_feature_vector', True) is not True:
        raise ValueError('Only EMBER v2 with a full feature vector is supported')
    if set(options) - {'feature_version', 'include_feature_vector'}:
        raise ValueError('Unexpected provider arguments')
    with Path(target).open('rb') as stream:
        data = stream.read(50_000_001)
    if len(data) > 50_000_000:
        raise ValueError('Staged PE exceeds the 50 MB research adapter limit')
    if not data.startswith(b'MZ'):
        raise ValueError('Staged target lacks PE DOS magic')
    parsed = lief.PE.parse(list(data))
    if parsed is None:
        raise ValueError('LIEF could not parse the staged PE')
    del parsed
    extractor = ember.PEFeatureExtractor(feature_version=2, print_feature_warning=False)
    if extractor.dim != 2381:
        raise ValueError('Unexpected EMBER feature dimensions')
    vector = np.asarray(extractor.feature_vector(data), dtype=np.float32)
    if vector.shape != (2381,) or not np.isfinite(vector).all():
        raise ValueError('Invalid EMBER feature vector')
    warnings = []
    if not lief.__version__.startswith('0.9.0'):
        warnings.append('LIEF {} differs from the original 0.9.0 feature runtime'.format(lief.__version__))
    return {'schema_version': 'ember-output-v1', 'feature_version': 2,
            'extractor': {'name': 'elastic-ember',
                          'version': 'v2@d97a0b523de02f3fe5ea6089d080abacab6ee931'},
            'target_sha256': hashlib.sha256(data).hexdigest(),
            'feature_count': 2381, 'features': vector.tolist(), 'warnings': warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--arguments-json', required=True)
    args = parser.parse_args()
    try:
        payload = extract(args.target, json.loads(args.arguments_json))
        print(json.dumps(payload, separators=(',', ':'), allow_nan=False), flush=True)
    except Exception as error:
        print('{}: {}'.format(type(error).__name__, error), file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
