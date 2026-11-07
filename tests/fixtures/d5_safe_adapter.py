"""Benign test provider: reads bytes, emits output, sleeps or starts a sleeper.

Never executes the target. This is not an EMBER/LightGBM implementation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--target', required=True)
p.add_argument('--arguments-json', required=True)
args = p.parse_args()
options = json.loads(args.arguments_json)
mode = options.get('mode', 'success')
if mode == 'tree':
    child = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(60)'])
    print(json.dumps({'child_pid': child.pid}), flush=True)
    if options.get('exit_parent'):
        raise SystemExit(0)
    time.sleep(60)
elif mode == 'sleep':
    print('completed observation before wait', flush=True)
    time.sleep(60)
elif mode == 'flood':
    for _ in range(256):
        os.write(1, b'x' * 4096)
        os.write(2, b'e' * 4096)
elif mode == 'fail':
    print('completed observation before failure', flush=True)
    print('provider diagnostic', file=sys.stderr, flush=True)
    raise SystemExit(7)
elif mode == 'lock_probe':
    try:
        with open(args.target, 'wb') as output:
            output.write(b'wrong')
    except PermissionError:
        print('write_blocked')
    else:
        raise SystemExit(8)
else:
    data = Path(args.target).read_bytes()
    print(json.dumps({'sha256': hashlib.sha256(data).hexdigest(), 'arguments': options,
                      'secret_present': 'D5_TEST_SECRET' in os.environ}, ensure_ascii=True))
