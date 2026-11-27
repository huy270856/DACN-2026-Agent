"""Atomic SQLite recovery for MOCK state only; never stores Windows policies.

The trusted harness configures the lab root and authorizer. A transaction binds
mock state + result + audit. This is durability, not a tamper-proof security log.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from .prototype import Prevention, PrototypeError


class PersistentMockPrevention:
    """Same five operations, always MOCK. DB is fixed inside configured lab.

    No live mode. Each operation reloads committed state under BEGIN IMMEDIATE;
    separate instances/processes serialize rather than overwriting stale state.
    Keep the lab private. A same-user attacker can rewrite the DB or swap paths.
    """

    def __init__(self, lab_root, *, authorize=None):
        engine = Prevention(lab_root, mode="mock", authorize=authorize)
        self.root = engine.root
        self.path = self.root / ".task09b-mock.sqlite3"
        self.authorize = authorize
        self._before_commit = None  # trusted test harness fault/crash injection only
        self.binding = hashlib.sha256(str(self.root).encode()).hexdigest()
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if tables and tables != {"metadata", "state", "audit"}:
                    raise PrototypeError("JOURNAL_SCHEMA_MISMATCH")
                if not tables:
                    connection.execute("CREATE TABLE metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER, binding TEXT)")
                    connection.execute("CREATE TABLE state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL)")
                    connection.execute("CREATE TABLE audit (sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
                    connection.execute("INSERT INTO metadata VALUES (1, 1, ?)", (self.binding,))
                    connection.execute("INSERT INTO state VALUES (1, ?)", (json.dumps(self._snapshot(engine)),))
                self._check_metadata(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _connect(self):
        Prevention._no_links(self.root)
        if self.path.exists() or self.path.is_symlink():
            Prevention._no_links(self.path)
        connection = sqlite3.connect(str(self.path), timeout=1, isolation_level=None)
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _check_metadata(self, connection):
        metadata = connection.execute("SELECT version, binding FROM metadata WHERE singleton=1").fetchone()
        if metadata != (1, self.binding):
            raise PrototypeError("JOURNAL_SCHEMA_OR_ROOT_MISMATCH")

    @staticmethod
    def _snapshot(engine):
        return {"rules": engine.rules, "plans": engine.plans, "bindings": engine.bindings,
                "results": [[list(key), value] for key, value in engine.results.items()]}

    def _load(self, connection):
        self._check_metadata(connection)
        row = connection.execute("SELECT payload FROM state WHERE singleton=1").fetchone()
        if row is None:
            raise PrototypeError("JOURNAL_STATE_MISSING")
        state = json.loads(row[0])
        if not isinstance(state, dict) or set(state) != {"rules", "plans", "bindings", "results"}:
            raise PrototypeError("JOURNAL_STATE_INVALID")
        for name in ("rules", "plans", "bindings"):
            if not isinstance(state[name], dict):
                raise PrototypeError("JOURNAL_STATE_INVALID")
        engine = Prevention(self.root, mode="mock", authorize=self.authorize)
        engine.rules, engine.plans, engine.bindings = (state[name] for name in ("rules", "plans", "bindings"))
        engine.results = {tuple(key): value for key, value in state["results"]}
        engine.audit = [json.loads(row[0]) for row in connection.execute("SELECT payload FROM audit ORDER BY sequence")]
        return engine

    def _save(self, connection, engine, result):
        result["audit_metadata"]["durability"] = "SQLITE_TRANSACTION_MOCK_ONLY"
        engine.audit[-1] = result
        connection.execute("UPDATE state SET payload=? WHERE singleton=1", (json.dumps(self._snapshot(engine)),))
        connection.execute("INSERT INTO audit(sequence,payload) VALUES (?,?)",
                           (len(engine.audit), json.dumps(result)))

    def _execute(self, operation, request):
        if not hasattr(request, "request_id"):
            raise PrototypeError("BLOCK_REQUEST_REQUIRED")
        try:
            with closing(self._connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    engine = self._load(connection)
                    result = getattr(engine, operation)(request)
                    self._save(connection, engine, result)
                    if self._before_commit is not None:
                        hook, self._before_commit = self._before_commit, None
                        hook()
                    connection.commit()
                    return result
                except Exception:
                    connection.rollback()
                    raise
        except (sqlite3.Error, OSError, PrototypeError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            reason = str(exc) if isinstance(exc, PrototypeError) else type(exc).__name__
            return self._record_failure(request, operation, reason)

    def _record_failure(self, request, operation, reason):
        # Reload last COMMITTED state. Failed mock mutations never become success.
        try:
            with closing(self._connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    engine = self._load(connection)
                    result = engine._result(request, operation, "FAILED", "MOCK_TRANSACTION_ABORTED",
                                            error_code=reason)
                    self._save(connection, engine, result)
                    connection.commit()
                    return result
                except Exception:
                    connection.rollback()
                    raise
        except Exception:
            return {"request_id": request.request_id, "operation": operation,
                    "status": "FAILED", "reason_code": "MOCK_JOURNAL_UNAVAILABLE",
                    "error_code": reason, "timestamp": datetime.now(timezone.utc).isoformat(),
                    "evaluation_type": "MOCK", "live_execution_verified": False,
                    "policy_state": None, "rollback_reference": None,
                    "audit_metadata": {"durability": "UNAVAILABLE_NOT_RECORDED"}}

    def capabilities(self):
        return {"mode": "persistent-mock", "live_supported": False,
                "reason_code": "MOCK_ONLY_NO_WINDOWS_BACKEND",
                "policy_side_effects": "NONE", "filesystem_side_effects": "LAB_SQLITE_JOURNAL_ONLY"}

    def plan_block(self, request):
        return self._execute("plan_block", request)

    def apply_block(self, request):
        return self._execute("apply_block", request)

    def verify_block(self, request):
        return self._execute("verify_block", request)

    def rollback_block(self, request):
        return self._execute("rollback_block", request)

    def inspect(self):
        """Read a committed snapshot for the lab harness; no target execution."""
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN")
                engine = self._load(connection)
                snapshot = {**self._snapshot(engine), "audit": engine.audit}
                connection.commit()
                return snapshot
            except Exception:
                connection.rollback()
                raise
