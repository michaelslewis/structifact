"""
Phase 8C-v1: proves structifact execute's write operations (the
optional DROP, the CREATE, and --data's row load) are atomic as a
whole, via Executor.transaction() — against real data on both real
engines, not mocks.

Directly regresses the bug this phase was scoped against: loading
[1, 2, 1, 4] into a primary_key column previously left rows 1 and 2
silently committed on both DuckDB and PostgreSQL after the CLI
reported "Execution failed" (see docs/DECISION_HISTORY.md). Also
proves --drop-if-exists lives inside the same transaction boundary,
not applied destructively beforehand — the "original data survives a
failed replacement" case.

transaction() is a single new public method (a context manager), not
three (begin/commit/rollback) — see base.py's docstring. Standalone
calls to execute_ddl()/load_rows()/query() outside any transaction()
scope must keep their existing Phase 8A autocommit behavior
unchanged; that's asserted explicitly here too, not just implied by
the rest of the suite still passing.
"""

import argparse
import os

import pytest

from structifact.cli import execute
from structifact.executors.duckdb import DuckDBExecutor

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)


def _args(spec, engine="duckdb", connection=None, data=None, drop_if_exists=False):
    return argparse.Namespace(
        spec=spec, engine=engine, connection=connection, data=data,
        drop_if_exists=drop_if_exists,
    )


def _bad_customers_csv(tmp_path):
    """A duplicate customer_id (the declared primary_key) reproduces the exact [1, 2, 1, 4] bug on the third row."""
    csv_file = tmp_path / "bad_customers.csv"
    csv_file.write_text(
        "customer_id,created_at\n"
        "1,2026-01-01 00:00:00\n"
        "2,2026-01-02 00:00:00\n"
        "1,2026-01-03 00:00:00\n"
        "4,2026-01-04 00:00:00\n"
    )
    return str(csv_file)


def _new_postgres_executor():
    from structifact.executors.postgres import PostgresExecutor

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    return executor


def _drop_customers_table_postgres():
    import psycopg2

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS customers")
    conn.close()


# ---------------------------------------------------------------------
# Direct Executor-level: transaction() itself
# ---------------------------------------------------------------------

def test_duckdb_transaction_commits_on_success():
    executor = DuckDBExecutor()
    executor.connect()
    executor.execute_ddl("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    with executor.transaction():
        executor.load_rows("t", ["id"], [{"id": "1"}, {"id": "2"}])

    assert executor.query("SELECT * FROM t ORDER BY id") == [{"id": 1}, {"id": 2}]
    executor.close()


def test_duckdb_transaction_rolls_back_entire_batch_on_failure():
    executor = DuckDBExecutor()
    executor.connect()
    executor.execute_ddl("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    with pytest.raises(Exception):
        with executor.transaction():
            executor.load_rows("t", ["id"], [{"id": "1"}, {"id": "2"}, {"id": "1"}, {"id": "4"}])

    assert executor.query("SELECT * FROM t") == []
    executor.close()


def test_duckdb_direct_calls_outside_transaction_still_autocommit():
    """Confirms transaction() didn't change standalone (Phase 8A) behavior."""
    executor = DuckDBExecutor()
    executor.connect()
    executor.execute_ddl("CREATE TABLE t (id INTEGER)")
    executor.load_rows("t", ["id"], [{"id": "1"}])

    assert executor.query("SELECT * FROM t") == [{"id": 1}]
    executor.close()


@requires_postgres
def test_postgres_transaction_commits_on_success():
    import psycopg2
    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS t")
    conn.close()

    executor = _new_postgres_executor()
    executor.execute_ddl("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    with executor.transaction():
        executor.load_rows("t", ["id"], [{"id": "1"}, {"id": "2"}])

    assert executor.query("SELECT * FROM t ORDER BY id") == [{"id": 1}, {"id": 2}]
    executor.close()


@requires_postgres
def test_postgres_transaction_rolls_back_entire_batch_on_failure():
    import psycopg2
    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS t")
    conn.close()

    executor = _new_postgres_executor()
    executor.execute_ddl("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    with pytest.raises(Exception):
        with executor.transaction():
            executor.load_rows("t", ["id"], [{"id": "1"}, {"id": "2"}, {"id": "1"}, {"id": "4"}])

    assert executor.query("SELECT * FROM t") == []
    executor.close()


@requires_postgres
def test_postgres_direct_calls_outside_transaction_still_autocommit():
    import psycopg2
    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS t")
    conn.close()

    executor = _new_postgres_executor()
    executor.execute_ddl("CREATE TABLE t (id INTEGER)")
    executor.load_rows("t", ["id"], [{"id": "1"}])

    assert executor.query("SELECT * FROM t") == [{"id": 1}]
    executor.close()


# ---------------------------------------------------------------------
# CLI-level: structifact execute — the actual regression scenario
# ---------------------------------------------------------------------

def test_duckdb_execute_failed_load_leaves_no_table_on_fresh_target(capsys, tmp_path):
    """
    Fresh target, no --drop-if-exists: CREATE is inside the same
    transaction as the failed load, so it rolls back too — the table
    shouldn't exist at all afterward, not just be empty.
    """
    db_path = str(tmp_path / "test.duckdb")
    bad_csv = _bad_customers_csv(tmp_path)

    execute(_args("tests/fixtures/customers.yml", connection=db_path, data=bad_csv))

    out = capsys.readouterr().out
    assert "Execution failed" in out
    assert "Verification query" not in out

    executor = DuckDBExecutor()
    executor.connect(connection=db_path)
    with pytest.raises(Exception):
        executor.query("SELECT * FROM customers")
    executor.close()


def test_duckdb_execute_drop_if_exists_failure_restores_original_table(capsys, tmp_path):
    """
    The centerpiece test: seed a table with real data, attempt a
    failing --drop-if-exists reload, confirm the DROP itself rolled
    back too — the original table and its original data survive.
    """
    db_path = str(tmp_path / "test.duckdb")

    good_csv = tmp_path / "good.csv"
    good_csv.write_text("customer_id,created_at\n99,2026-01-01 00:00:00\n")
    execute(_args("tests/fixtures/customers.yml", connection=db_path, data=str(good_csv)))
    capsys.readouterr()

    bad_csv = _bad_customers_csv(tmp_path)
    execute(_args(
        "tests/fixtures/customers.yml", connection=db_path,
        data=bad_csv, drop_if_exists=True,
    ))

    out = capsys.readouterr().out
    assert "Execution failed" in out

    executor = DuckDBExecutor()
    executor.connect(connection=db_path)
    result = executor.query("SELECT * FROM customers")
    executor.close()

    assert len(result) == 1
    assert result[0]["customer_id"] == 99


@requires_postgres
def test_postgres_execute_failed_load_leaves_no_table_on_fresh_target(capsys, tmp_path):
    _drop_customers_table_postgres()
    bad_csv = _bad_customers_csv(tmp_path)

    execute(_args(
        "tests/fixtures/customers.yml", engine="postgres",
        connection=POSTGRES_DSN, data=bad_csv,
    ))

    out = capsys.readouterr().out
    assert "Execution failed" in out
    assert "Verification query" not in out

    executor = _new_postgres_executor()
    with pytest.raises(Exception):
        executor.query("SELECT * FROM customers")
    executor.close()


@requires_postgres
def test_postgres_execute_drop_if_exists_failure_restores_original_table(capsys, tmp_path):
    _drop_customers_table_postgres()

    good_csv = tmp_path / "good.csv"
    good_csv.write_text("customer_id,created_at\n99,2026-01-01 00:00:00\n")
    execute(_args(
        "tests/fixtures/customers.yml", engine="postgres",
        connection=POSTGRES_DSN, data=str(good_csv),
    ))
    capsys.readouterr()

    bad_csv = _bad_customers_csv(tmp_path)
    execute(_args(
        "tests/fixtures/customers.yml", engine="postgres",
        connection=POSTGRES_DSN, data=bad_csv, drop_if_exists=True,
    ))

    out = capsys.readouterr().out
    assert "Execution failed" in out

    executor = _new_postgres_executor()
    result = executor.query("SELECT * FROM customers")
    executor.close()

    assert len(result) == 1
    assert result[0]["customer_id"] == 99
