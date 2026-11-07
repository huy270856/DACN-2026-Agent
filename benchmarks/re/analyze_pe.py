"""Independent static PE baseline, NOT a Ghidra/REA analysis or D.0 ToolResult."""
import hashlib
import json
from pathlib import Path
import re
import pefile

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((ROOT / 'build/manifest.json').read_text(encoding='utf-8'))
    expected = json.loads((ROOT / 'expected.json').read_text(encoding='utf-8'))
    results = []
    for sample in manifest['samples']:
        binary = ROOT / sample['binary']
        if digest(binary) != sample['binary_sha256'] or digest(ROOT / sample['source']) != sample['source_sha256']:
            raise SystemExit('Source/binary changed since build: ' + sample['id'])
        with pefile.PE(str(binary)) as pe:
            if pe.FILE_HEADER.Machine != 0x8664 or pe.OPTIONAL_HEADER.Magic != 0x20b:
                raise SystemExit('Expected AMD64 PE32+')
            imports = [{'dll': entry.dll.decode('ascii'), 'name': item.name.decode('ascii') if item.name else None,
                        'ordinal': item.ordinal, 'iat_va': hex(item.address)}
                       for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []) for item in entry.imports]
            exports = [{'name': symbol.name.decode('ascii'), 'rva': hex(symbol.address)}
                       for symbol in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', []) if symbol.name]
        strings = [{'text': match.group().decode('ascii'), 'file_offset': hex(match.start())}
                   for match in re.finditer(rb'[\x20-\x7e]{4,}', binary.read_bytes())]
        oracle = expected[sample['id']]
        missing = {
            'strings': [s for s in oracle['strings'] if not any(s in x['text'] for x in strings)],
            'imports': sorted(set(oracle['imports']) - {x['name'] for x in imports}),
            'exported_functions': sorted(set(oracle['exported_functions']) - {x['name'] for x in exports})}
        results.append({'id': sample['id'], 'sha256': sample['binary_sha256'], 'imports': imports,
                        'exports': exports, 'marker_strings': [x for x in strings if any(s in x['text'] for s in oracle['strings'])],
                        'ascii_string_count': len(strings), 'missing_expected': missing,
                        'passed': not any(missing.values())})
    result = {'producer': 'pefile ' + pefile.__version__, 'analysis': 'static PE tables and raw ASCII scan',
              'ghidra_executed': False, 'functions_recovered': None,
              'limitations': ['Exports are anchors, not complete recovered functions.',
                              'ASCII scan may include non-string bytes; only known markers checked.',
                              'No runtime behavior, decompilation, malware classification or D.0 integration tested.'],
              'samples': results}
    (ROOT / 'build/pe-evidence.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    for sample in results:
        print(sample['id'], 'PASS' if sample['passed'] else 'FAIL', sample['missing_expected'])
    if not all(sample['passed'] for sample in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
