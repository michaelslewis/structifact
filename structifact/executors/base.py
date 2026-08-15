from typing import Any, Callable, ContextManager, Dict, List, Tuple, Type


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


def retry_transaction(
    executor: "Executor",
    fn: Callable[[], None],
    retry_on: Tuple[Type[BaseException], ...],
    max_attempts: int = 3,
) -> None:
    """
    Phase 8C-v2 — retry, built on top of transaction() (Phase 8C-v1)
    rather than a new Executor method: retrying means re-running the
    CALLER's code inside a fresh transaction() scope, and a context
    manager cannot re-invoke its own `with`-block body, so this is a
    plain function taking that code as `fn`, not a new abstract method
    every Executor subclass would have to implement. Deliberately
    requires no changes to Executor, DuckDBExecutor, or PostgresExecutor.

    fn MUST represent the complete unit of work for one transaction
    attempt, and MUST be safe to run again from the beginning --
    retry_transaction re-executes fn() in its entirety on each retry,
    not just the statement that failed. This means fn must confine its
    effects to the transaction itself: no irreversible action outside
    the database (sending an email, calling an external API, writing a
    file) belongs inside fn, since a retry will re-run it.

    If fn() raises an exception matching retry_on, the transaction
    rolls back (transaction()'s existing behavior) and fn() is called
    again from the start in a new transaction() scope. max_attempts is
    the TOTAL number of times fn() may be called, including the first
    attempt -- max_attempts=3 means at most 3 calls to fn(), not 3
    retries after an initial attempt.

    Any exception NOT matching retry_on propagates immediately,
    without retrying. If every attempt raises a retry_on exception, the
    exception from the FINAL attempt propagates once max_attempts is
    exhausted.

    The only retry_on condition verified against real engine behavior
    so far is psycopg2.errors.SerializationFailure (PostgreSQL SQLSTATE
    40001, from two genuinely concurrent SERIALIZABLE transactions --
    see tests/test_executor_retry.py). This function doesn't validate
    or restrict what's passed as retry_on, but callers should treat
    that as the only concretely justified case until a different real
    transient failure motivates another.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            with executor.transaction():
                fn()
            return
        except retry_on:
            if attempt == max_attempts:
                raise
            continue
