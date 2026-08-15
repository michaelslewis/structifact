"""
Phase 8C-v2 -- retry, built on transaction() (Phase 8C-v1) via a
plain module-level function, retry_transaction(), rather than a new
Executor method: retrying means re-running the CALLER's code inside a
fresh transaction() scope, which a context manager can't do to its
own body. Executor, DuckDBExecutor, and PostgresExecutor all need
zero changes.

Two layers, matching the approved paper contract:

1. Deterministic loop-mechanics tests (DuckDBExecutor, a real but
   local/no-network Executor -- no fake/mock Executor needed) using
   plain Python exceptions, not a real database failure, to prove
   retry_transaction()'s own control flow exactly: attempt counts,
   which exception propagates, when it propagates.

2. A real PostgreSQL integration test proving the actual motivating
   claim: a genuinely reproduced, unmocked serialization failure
   (psycopg2.errors.SerializationFailure, SQLSTATE 40001, from two
   real concurrent SERIALIZABLE transactions -- verified interactively
   against a real local server before writing this test) is retried
   correctly. Critically, this proves FULL callback re-execution, not
   just "eventually returns without raising": the callback performs
   TWO separate writes, and after a successful retry, the committed
   state must reflect exactly one complete application of the
   callback's effect -- not zero (proving the failed attempt didn't
   leave partial writes) and not two (proving the failed attempt's
   work wasn't double-counted alongside the retry). A calls counter
   inside the callback independently proves it was invoked exactly
   twice -- once per attempt, not once with an internal resume.

Real PostgreSQL test here follows the existing convention in
tests/test_executors.py / tests/test_executor_transactions.py: gated
on STRUCTIFACT_TEST_POSTGRES_DSN, skips cleanly when unset.
"""

import os
import threading

import pytest

from structifact.executors.base import retry_transaction
from structifact.executors.duckdb import DuckDBExecutor

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)


class _RetryableError(Exception):
    pass


class _NonRetryableError(Exception):
    pass


# ---------------------------------------------------------------------
# Deterministic loop-mechanics tests (real DuckDBExecutor, fake errors)
# ---------------------------------------------------------------------

def test_non_retryable_exception_propagates_on_first_attempt():
    executor = DuckDBExecutor()
    executor.connect()
    calls = []

    def fn():
        calls.append(1)
        raise _NonRetryableError("not eligible for retry")

    with pytest.raises(_NonRetryableError):
        retry_transaction(executor, fn, retry_on=(_RetryableError,))

    executor.close()
    assert len(calls) == 1


def test_retryable_exception_succeeds_on_second_attempt():
    executor = DuckDBExecutor()
    executor.connect()
    calls = []

    def fn():
        calls.append(1)
        if len(calls) == 1:
            raise _RetryableError("transient, first attempt only")

    retry_transaction(executor, fn, retry_on=(_RetryableError,))

    executor.close()
    assert len(calls) == 2


def test_exhausting_max_attempts_raises_the_final_attempts_exception():
    executor = DuckDBExecutor()
    executor.connect()
    calls = []

    def fn():
        calls.append(1)
        raise _RetryableError(f"attempt {len(calls)}")

    with pytest.raises(_RetryableError, match="attempt 3"):
        retry_transaction(executor, fn, retry_on=(_RetryableError,), max_attempts=3)

    executor.close()
    # max_attempts=3 is 3 TOTAL calls to fn(), not 3 retries after a first attempt.
    assert len(calls) == 3


def test_max_attempts_one_means_no_retry_at_all():
    executor = DuckDBExecutor()
    executor.connect()
    calls = []

    def fn():
        calls.append(1)
        raise _RetryableError("always fails")

    with pytest.raises(_RetryableError):
        retry_transaction(executor, fn, retry_on=(_RetryableError,), max_attempts=1)

    executor.close()
    assert len(calls) == 1


# ---------------------------------------------------------------------
# Real PostgreSQL integration test: a genuine, unmocked serialization
# failure, proving full-callback re-execution with exactly-once
# committed effect.
# ---------------------------------------------------------------------

@requires_postgres
def test_postgres_retries_real_serialization_failure_full_callback():
    import psycopg2
    import psycopg2.errors

    from structifact.executors.postgres import PostgresExecutor

    setup_conn = psycopg2.connect(dsn=POSTGRES_DSN)
    setup_conn.autocommit = True
    with setup_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS retry_demo")
        cur.execute("CREATE TABLE retry_demo (id INTEGER PRIMARY KEY, counter INTEGER)")
        cur.execute("INSERT INTO retry_demo VALUES (1, 0), (2, 0)")
    setup_conn.close()

    a_started = threading.Event()
    b_done = threading.Event()

    executor_a = PostgresExecutor()
    executor_a.connect(connection=POSTGRES_DSN)

    call_count = []

    def fn_a():
        # Runs in its entirety on every attempt -- two separate writes,
        # not one, so a retry that only reran the "last statement"
        # would leave this test's final-state assertions wrong.
        call_count.append(1)
        executor_a.execute_ddl("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        executor_a.query("SELECT counter FROM retry_demo WHERE id = 1")

        a_started.set()
        b_done.wait(timeout=5)

        executor_a.execute_ddl("UPDATE retry_demo SET counter = counter + 1 WHERE id = 1")
        executor_a.execute_ddl("UPDATE retry_demo SET counter = counter + 1 WHERE id = 2")

    def thread_b():
        a_started.wait(timeout=5)
        conn = psycopg2.connect(dsn=POSTGRES_DSN)
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        cur.execute("UPDATE retry_demo SET counter = counter + 1 WHERE id = 1")
        conn.commit()
        conn.close()
        b_done.set()

    t = threading.Thread(target=thread_b)
    t.start()

    retry_transaction(
        executor_a,
        fn_a,
        retry_on=(psycopg2.errors.SerializationFailure,),
        max_attempts=3,
    )

    t.join(timeout=5)
    executor_a.close()

    # Proves fn_a was invoked twice: once for the attempt that hit the
    # real serialization conflict, once for the retry that succeeded.
    assert len(call_count) == 2

    verify_conn = psycopg2.connect(dsn=POSTGRES_DSN)
    verify_conn.autocommit = True
    with verify_conn.cursor() as cur:
        cur.execute("SELECT id, counter FROM retry_demo ORDER BY id")
        rows = dict(cur.fetchall())
    verify_conn.close()

    # id=1: +1 from thread_b, +1 from fn_a's ONE successful complete
    # run -- not 0 (would mean the failed attempt's write silently
    # survived, or the retry never ran) and not +2 from fn_a (would
    # mean the failed attempt's work was double-counted).
    assert rows[1] == 2
    # id=2: touched only by fn_a -- must show exactly one application
    # of fn_a's effect, proving the SECOND write inside the callback
    # also only took effect once, not that only the failing statement
    # got retried.
    assert rows[2] == 1
