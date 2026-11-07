"""Build known-source Windows PE fixtures; never execute the generated binaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zig', required=True, type=Path)
    args = parser.parse_args()
    zig = args.zig.resolve()
    out = ROOT / 'build'
    out.mkdir(exist_ok=True)
    manifest_path = out / 'manifest.json'
    manifest_path.unlink(missing_ok=True)  # A failed build must not leave stale success metadata.
    env = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(out / 'zig-cache'))
    version = subprocess.check_output([str(zig), 'version'], text=True, env=env).strip()
    if version != '0.13.0':
        raise SystemExit('This baseline requires Zig 0.13.0; record a new baseline for other versions.')
    flags = ['-target', 'x86_64-windows-gnu', '-O0', '-g', '-fno-inline', '-lkernel32']
    manifest = {'compiler': {'name': 'zig cc', 'version': version,
                            'path': str(zig), 'sha256': sha256(zig)},
                'target': 'PE32+ AMD64', 'flags': flags, 'samples': []}
    for source in sorted((ROOT / 'src').glob('*.c')):
        binary = out / (source.stem + '.exe')
        command = [str(zig), 'cc', *flags, str(source), '-o', str(binary)]
        subprocess.run(command, check=True, timeout=300, env=env)
        manifest['samples'].append({'id': source.stem, 'source': source.relative_to(ROOT).as_posix(),
                                    'source_sha256': sha256(source), 'license': 'MIT',
                                    'binary': binary.relative_to(ROOT).as_posix(),
                                    'binary_sha256': sha256(binary), 'size_bytes': binary.stat().st_size,
                                    'argv': command})
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Built', len(manifest['samples']), 'samples; manifest:', manifest_path)


if __name__ == '__main__':
    main()
