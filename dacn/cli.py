"""Unified CLI: ``python -m dacn <intake|inspect|smoke> ...``.

Calls the real Node B/C/D APIs via :mod:`dacn.application`. Errors are reported
as clean messages with non-zero exit codes, never raw stack traces. The ``smoke``
command exposes NO way to pass an adapter command, executable path or policy.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from typing import Any, Dict

from .config import AppConfig
from . import application as app


def _print(result: Dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dacn", description="DACN unified application CLI")
    parser.add_argument("--home", default=None,
                        help="Application storage root (default: $DACN_HOME or ./dacn_data). "
                             "Place before the subcommand.")
    sub = parser.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("intake", help="Collect context (Node B) and persist a case (Node C)")
    target = pi.add_mutually_exclusive_group(required=True)
    target.add_argument("--file", help="Path to a file target (read-only; never executed)")
    target.add_argument("--pid", type=int, help="PID of a running process target")
    pi.add_argument("--case-id", default=None,
                    help="Append this collection to an existing case instead of creating one")
    pi.add_argument("--include-backing-file", action="store_true",
                    help="For --pid: also collect the executable backing file")
    pi.add_argument("--hash-timeout", type=float, default=None,
                    help="Best-effort SHA-256 time budget in seconds")
    pi.add_argument("--progress", action="store_true", help="Hash progress on stderr")

    ps = sub.add_parser("inspect", help="Read a persisted CaseState (Node C)")
    ps.add_argument("--case-id", required=True, help="Case id, e.g. CASE-<32 hex>")

    sub.add_parser("smoke", help="Initialize and exercise D1-D9 with a benign mock analyzer (Windows)")

    pv = sub.add_parser("investigate",
                        help="Real EMBER/LightGBM prediction + Qwen assessment + report (Windows)")
    pvt = pv.add_mutually_exclusive_group(required=True)
    pvt.add_argument("--file", help="Path to a PE file to investigate (read-only; never executed)")
    pvt.add_argument("--case-id", help="Investigate an existing case id instead of a new file")
    pv.add_argument("--max-iters", type=int, default=None, help="Max investigation iterations")
    pv.add_argument("--think", action="store_true", help="Enable Qwen thinking mode")
    pv.add_argument("--no-agent", action="store_true",
                    help="Run detector + report only, skip the SLM assessment")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.from_home(args.home)

    try:
        if args.command == "intake":
            if args.pid is not None and args.pid <= 0:
                parser.error("--pid must be positive")
            if args.hash_timeout is not None and not (0 < args.hash_timeout < float("inf")):
                parser.error("--hash-timeout must be a finite positive number")
            if args.include_backing_file and args.pid is None:
                parser.error("--include-backing-file only applies to --pid")
            if args.file is not None:
                result = app.intake_file(args.file, config, case_id=args.case_id,
                                         hash_timeout=args.hash_timeout, progress=args.progress)
            else:
                result = app.intake_pid(args.pid, config, case_id=args.case_id,
                                        include_backing_file=args.include_backing_file,
                                        hash_timeout=args.hash_timeout, progress=args.progress)
            _print(result)
            # A failed collection (e.g. missing file) still persists a case; signal via status.
            return 0 if result.get("collection_status") != "FAILED" else 2

        if args.command == "inspect":
            _print(app.inspect_case(args.case_id, config))
            return 0

        if args.command == "smoke":
            result = app.smoke(config)
            _print(result)
            if not result.get("supported", False):
                return 3  # unsupported platform - explicit, not a fake pass
            return 0 if result.get("outcome") in ("SUCCESS", "PARTIAL") else 4

        if args.command == "investigate":
            from agent.config import AgentConfig
            acfg = AgentConfig.from_env()
            if args.max_iters is not None:
                acfg = replace(acfg, max_iterations=args.max_iters)
            if args.think:
                acfg = replace(acfg, think=True)
            result = app.investigate_real(config, file=args.file, case_id=args.case_id,
                                          agent_config=acfg, run_agent=not args.no_agent)
            # Avoid dumping the full nested report object twice; print a summary + paths.
            summary = {k: v for k, v in result.items() if k != "report"}
            _print(summary)
            if not result.get("supported", False):
                return 3
            return 0 if result.get("overall_status") == "COMPLETED" else 4

    except app.ApplicationError as exc:
        print(f"dacn error: {exc}", file=sys.stderr)
        return 5
    parser.error("no command")  # unreachable (required=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
