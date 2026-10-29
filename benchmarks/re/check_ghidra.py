"""Compare actual Ghidra facts with predeclared markers and independent PE export RVAs."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, default=ROOT / 'build/ghidra/hello-evidence.json')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'build/pe-evidence.json')
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding='utf-8'))
    baseline = next(s for s in json.loads(args.baseline.read_text(encoding='utf-8'))['samples'] if s['id'] == 'hello')
    expected = json.loads((ROOT / 'expected.json').read_text(encoding='utf-8'))['hello']
    if evidence['binary_sha256'] != baseline['sha256'] or evidence['analysis_timed_out']:
        raise SystemExit('Wrong target or partial analysis')
    image_base = int(evidence['image_base'], 16)
    function_entries = {int(f['entry_va'], 16) for f in evidence['functions']}
    export_rvas = {f['name']: int(f['rva'], 16) for f in baseline['exports']}
    checks = {
        'imports': {name: any(s['name'] == name for s in evidence['external_symbols']) for name in expected['imports']},
        'strings': {value: any(value in s['value'] for s in evidence['defined_strings']) for value in expected['strings']},
        'function_entry_matches_pe_export': {name: name in export_rvas and image_base + export_rvas[name] in function_entries
                                             for name in expected['exported_functions']}}
    passed = all(all(group.values()) for group in checks.values())
    result = {'passed': passed, 'binary_sha256': evidence['binary_sha256'],
              'ghidra_version': evidence['ghidra_version'], 'checks': checks,
              'function_count': len(evidence['functions']), 'external_symbol_count': len(evidence['external_symbols']),
              'defined_string_count': len(evidence['defined_strings']),
              'scope': 'Known hello sample markers only; not complete precision/recall or REA integration.'}
    print(json.dumps(result, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
