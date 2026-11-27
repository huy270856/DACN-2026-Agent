"""CLI accepts only capabilities or a self-contained MOCK demo, no target paths."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .prototype import BlockRequest, Prevention
from .journal import PersistentMockPrevention
from .capabilities import collect_capabilities


def powershell_capabilities():
    if os.name != "nt":
        return {"status": "UNSUPPORTED", "reason_code": "WINDOWS_REQUIRED", "live_status": "BLOCKED"}
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = system_root / "System32/WindowsPowerShell/v1.0/powershell.exe"
    probe = Path(__file__).with_name("capabilities.ps1")
    try:
        run = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-File", str(probe)],
                             capture_output=True, text=True, timeout=25, check=False)
        if run.returncode != 0:
            reason = ("POWERSHELL_SCRIPT_EXECUTION_DENIED" if "UnauthorizedAccess" in run.stderr
                      else "READ_ONLY_PROBE_FAILED")
            return {"status": "BLOCKED", "reason_code": reason,
                    "exit_code": run.returncode, "live_status": "BLOCKED"}
        return json.loads(run.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"status": "BLOCKED", "reason_code": type(exc).__name__, "live_status": "BLOCKED"}


def demo(persistent=False):
    with tempfile.TemporaryDirectory(prefix="task09b-mock-") as directory:
        # Synthetic header-only data: NOT a runnable executable. Never executed.
        data = bytearray(128)
        data[:2] = b"MZ"
        data[60:64] = (64).to_bytes(4, "little")
        data[64:68] = b"PE\0\0"
        (Path(directory) / "fixture.exe").write_bytes(data)
        request = BlockRequest("mock-request-1", "mock-case", 1, "fixture.exe",
                               hashlib.sha256(data).hexdigest())
        engine = (PersistentMockPrevention(directory, authorize=lambda r, op: True) if persistent
                  else Prevention(directory, mode="mock", authorize=lambda r, op: True))
        outputs = [engine.plan_block(request), engine.apply_block(request)]
        if persistent:
            engine = PersistentMockPrevention(directory, authorize=lambda r, op: True)
        outputs.extend([engine.verify_block(request), engine.rollback_block(request)])
        audit_count = len(engine.inspect()["audit"]) if persistent else len(engine.audit)
        return {"evaluation_type": "MOCK", "fixture": "SYNTHETIC_HEADER_NOT_RUNNABLE",
                "live_status": "BLOCKED", "results": outputs, "audit_count": audit_count,
                "reopened_after_apply": persistent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["capabilities", "capabilities-powershell", "demo", "demo-persistent"])
    args = parser.parse_args()
    command = {"capabilities": collect_capabilities, "capabilities-powershell": powershell_capabilities,
               "demo": demo, "demo-persistent": lambda: demo(persistent=True)}[args.command]
    print(json.dumps(command(),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
