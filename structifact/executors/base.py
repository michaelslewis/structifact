from typing import Any, ContextManager, Dict, List


class Executor:
    """
    Base class for all Structifact executors (Phase 8 — Execution and
    Platform Integrations).

    An Executor runs generated SQL against a real database engine —
    a genuinely different responsibility from a Generator, which
    only ever produces text. Where SQLGenerator answers "what SQL
    should exist for this dataset," an Executor answers "does that
    SQL actually work against a real engine."

    connection_args are passed to connect(), never to __init__ or
    stored anywhere persistent — same bring-your-own-credentials
    posture as structifact/llm.py's ANTHROPIC_API_KEY handling. The
    CLI passes a single generic `connection` string, opaque to the
    CLI itself — each Executor decides how to interpret it (DuckDB:
    a file path, or omitted for in-memory; Postgres: a DSN passed
    straight through to its driver). The CLI never learns
    engine-specific connection concepts like host/port/user/password.

    Standalone persistence contract (Phase 8A): calling execute_ddl(),
    load_rows(), or query() directly, outside transaction() below,
    has the same effective persistence semantics as DuckDB's default
    behavior — durable without a separate commit step. This is
    unaffected by transaction() and requires no change to existing
    callers (see PostgresExecutor's autocommit handling).

    Atomic execution contract (Phase 8C-v1): transaction() establishes
    an atomic execution scope. Operations performed through this
    Executor within the scope are committed when the scope exits
    normally; if an exception escapes the scope, every operation
    performed within it is rolled back and the exception is
    re-raised. Operations outside a transaction retain the standalone
    persistence semantics above, unchanged.

    Deliberately a single new public method rather than exposing
    begin()/commit()/rollback() individually: a context manager makes
    "these operations are one atomic unit" impossible to leave half
    -open (Python's `with` guarantees exit runs exactly once), and
    callers never need to know how DuckDB or PostgreSQL implements
    transactions underneath. See docs/DECISION_HISTORY.md for the
    scoping process.

    Connection pooling and retry logic remain deliberately unstarted
    — no current usage pattern in this codebase motivates either yet
    (see docs/FUTURE_WORK.md).
    """

    name: str

    def connect(self, **connection_args: Any) -> None:
        raise NotImplementedError

    def execute_ddl(self, sql: str) -> None:
        raise NotImplementedError

    def load_rows(self, table_name: str, columns: List[str], rows: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def query(self, sql: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def transaction(self) -> ContextManager[None]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
