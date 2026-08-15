import argparse
import os

import pytest

from structifact.adapters.registry import load_spec
from structifact.executors.registry import EXECUTORS
from structifact.executors.duckdb import DuckDBExecutor
from structifact.generators.sql import SQLGenerator
from structifact.cli import execute


# ---------------------------------------------------------------------
# DuckDBExecutor, direct unit tests
# ---------------------------------------------------------------------

def test_duckdb_executor_registered():
    assert EXECUTORS["duckdb"] is DuckDBExecutor


def test_duckdb_executor_connect_and_ddl():
    executor = DuckDBExecutor()
    executor.connect()  # in-memory, no connection arg

    executor.execute_ddl("CREATE TABLE t (id INTEGER)")

    result = executor.query("SELECT * FROM t")
    assert result == []

    executor.close()


def test_duckdb_executor_load_rows_and_query():
    executor = DuckDBExecutor()
    executor.connect()
    executor.execute_ddl("CREATE TABLE t (id INTEGER, name TEXT)")

    executor.load_rows(
        "t", ["id", "name"],
        [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}],
    )

    result = executor.query("SELECT * FROM t ORDER BY id")
    assert len(result) == 2
    assert result[0]["name"] == "a"

    executor.close()


def test_duckdb_executor_load_rows_empty_list_is_noop():
    executor = DuckDBExecutor()
    executor.connect()
    executor.execute_ddl("CREATE TABLE t (id INTEGER)")

    executor.load_rows("t", ["id"], [])  # should not raise

    result = executor.query("SELECT * FROM t")
    assert result == []

    executor.close()


def test_duckdb_executor_requires_connection_before_ddl():
    executor = DuckDBExecutor()

    with pytest.raises(RuntimeError, match="not connected"):
        executor.execute_ddl("CREATE TABLE t (id INTEGER)")


def test_duckdb_executor_requires_connection_before_query():
    executor = DuckDBExecutor()

    with pytest.raises(RuntimeError, match="not connected"):
        executor.query("SELECT 1")


def test_duckdb_executor_file_connection(tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    executor = DuckDBExecutor()
    executor.connect(connection=db_path)
    executor.execute_ddl("CREATE TABLE t (id INTEGER)")
    executor.load_rows("t", ["id"], [{"id": "1"}])
    executor.close()

    # Reconnect to the same file, confirm data persisted.
    executor2 = DuckDBExecutor()
    executor2.connect(connection=db_path)
    result = executor2.query("SELECT * FROM t")
    assert len(result) == 1
    executor2.close()


# ---------------------------------------------------------------------
# CLI-level: structifact execute
# ---------------------------------------------------------------------

def _args(spec, engine="duckdb", connection=None, data=None, drop_if_exists=False):
    return argparse.Namespace(
        spec=spec, engine=engine, connection=connection, data=data,
        drop_if_exists=drop_if_exists,
    )


def test_execute_creates_table_no_data(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    execute(_args("tests/fixtures/customers.yml", connection=db_path))

    out = capsys.readouterr().out
    assert "✓ Loaded schema: customers" in out
    assert "✓ Connected: duckdb" in out
    assert "✓ Executed DDL" in out
    assert "created successfully" in out
    assert "populated" not in out


def test_execute_with_data_loads_and_verifies(capsys, tmp_path):
    yaml_file = tmp_path / "customers.yml"
    yaml_file.write_text(
        """
dataset:
  name: customers

fields:
  - name: customer_id
    type: integer
  - name: customer_name
    type: string
"""
    )

    csv_file = tmp_path / "customers.csv"
    csv_file.write_text("customer_id,customer_name\n1,Alice\n2,Bob\n")

    db_path = str(tmp_path / "test.duckdb")

    execute(_args(str(yaml_file), connection=db_path, data=str(csv_file)))

    out = capsys.readouterr().out
    assert "✓ Loaded schema: customers" in out
    assert "✓ Executed DDL" in out
    assert "✓ Loaded 2 rows" in out
    assert "✓ Verification query: 2 rows in customers" in out
    assert "created and populated successfully" in out


def test_execute_unknown_engine(capsys):
    execute(_args("tests/fixtures/customers.yml", engine="not_a_real_engine"))

    out = capsys.readouterr().out
    assert "Unknown engine 'not_a_real_engine'" in out
    assert "duckdb" in out


def test_execute_invalid_spec_prints_validation_failure(capsys):
    execute(_args("tests/fixtures/bad.yml"))

    out = capsys.readouterr().out
    assert "Validation failed" in out
    assert "✓" not in out


def test_execute_in_memory_when_no_connection_given(capsys):
    execute(_args("tests/fixtures/customers.yml", connection=None))

    out = capsys.readouterr().out
    assert "✓ Connected: duckdb (in-memory)" in out


def test_execute_rerun_without_drop_if_exists_fails(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    execute(_args("tests/fixtures/customers.yml", connection=db_path))
    execute(_args("tests/fixtures/customers.yml", connection=db_path))

    out = capsys.readouterr().out
    assert "Execution failed" in out
    assert "already exists" in out


def test_execute_rerun_with_drop_if_exists_succeeds(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    execute(_args("tests/fixtures/customers.yml", connection=db_path))
    capsys.readouterr()  # clear first run's output

    execute(_args("tests/fixtures/customers.yml", connection=db_path, drop_if_exists=True))

    out = capsys.readouterr().out
    assert "✓ Dropped table 'customers' if it existed" in out
    assert "✓ Executed DDL" in out
    assert "created successfully" in out


def test_execute_drop_if_exists_on_first_run_is_harmless(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    execute(_args("tests/fixtures/customers.yml", connection=db_path, drop_if_exists=True))

    out = capsys.readouterr().out
    assert "✓ Dropped table 'customers' if it existed" in out
    assert "✓ Executed DDL" in out
    assert "Execution failed" not in out


# ---------------------------------------------------------------------
# PostgresExecutor, real-server integration tests (Phase 8A)
#
# These are deliberately real, not mocked — proving Structifact-
# generated DDL/rows actually work against a real PostgreSQL server,
# the same discipline DuckDB was held to. They only run when a real
# server is configured via STRUCTIFACT_TEST_POSTGRES_DSN; otherwise
# they skip cleanly rather than failing or silently passing. CI
# supplies this via a postgres:16 service (see
# .github/workflows/tests.yml); local runs are opt-in.
# ---------------------------------------------------------------------

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)


def test_postgres_executor_registered():
    from structifact.executors.postgres import PostgresExecutor

    assert EXECUTORS["postgres"] is PostgresExecutor


def test_postgres_executor_requires_connection_string():
    from structifact.executors.postgres import PostgresExecutor

    executor = PostgresExecutor()
    with pytest.raises(ValueError, match="requires a --connection DSN"):
        executor.connect()


@pytest.fixture
def clean_customers_table():
    """
    Drops any leftover 'customers' table before a test runs, using a
    raw connection independent of the PostgresExecutor under test —
    so each test starts from a known-clean slate in the same real,
    shared database.
    """
    import psycopg2

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS customers")
    conn.close()
    yield


@requires_postgres
def test_postgres_executor_ddl_creates_real_table(clean_customers_table):
    """Test A: the same customers.yml fixture, same SQLGenerator output DuckDB uses, run against real PostgreSQL."""
    table = load_spec("tests/fixtures/customers.yml")
    ddl = SQLGenerator().generate(table).content

    from structifact.executors.postgres import PostgresExecutor

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    executor.execute_ddl(ddl)

    columns = executor.query(
        "select column_name, data_type from information_schema.columns "
        "where table_name = 'customers' order by ordinal_position"
    )
    assert columns == [
        {"column_name": "customer_id", "data_type": "integer"},
        {"column_name": "created_at", "data_type": "timestamp without time zone"},
    ]

    pk = executor.query(
        "select column_name from information_schema.key_column_usage "
        "where table_name = 'customers' and constraint_name like '%_pkey'"
    )
    assert pk == [{"column_name": "customer_id"}]

    executor.close()


@requires_postgres
def test_postgres_executor_load_rows_accepts_raw_csv_strings(clean_customers_table):
    """
    Test B: load_rows() receives raw strings straight from CSV (see
    quality.py's load_data_rows — no type coercion happens before
    this call for any engine). This proves PostgreSQL's parameterized
    INSERT casts "1"/"2026-01-01 00:00:00" into INTEGER/TIMESTAMP
    correctly, the same way DuckDB already does — rather than
    assuming it on paper.
    """
    table = load_spec("tests/fixtures/customers.yml")
    ddl = SQLGenerator().generate(table).content

    from structifact.executors.postgres import PostgresExecutor

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    executor.execute_ddl(ddl)

    executor.load_rows(
        "customers",
        ["customer_id", "created_at"],
        [
            {"customer_id": "1", "created_at": "2026-01-01 00:00:00"},
            {"customer_id": "2", "created_at": "2026-01-02 00:00:00"},
        ],
    )

    result = executor.query("select * from customers order by customer_id")
    assert len(result) == 2
    assert result[0]["customer_id"] == 1  # cast from "1" to a real int by Postgres itself

    executor.close()


@requires_postgres
def test_postgres_executor_query_returns_list_of_dicts(clean_customers_table):
    """Test C: query() shape matches DuckDBExecutor's — List[Dict[str, Any]], keyed by column name."""
    from structifact.executors.postgres import PostgresExecutor

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    executor.execute_ddl("CREATE TABLE customers (customer_id INTEGER, created_at TIMESTAMP)")
    executor.load_rows("customers", ["customer_id", "created_at"], [{"customer_id": "1", "created_at": "2026-01-01"}])

    result = executor.query("SELECT * FROM customers")

    assert isinstance(result, list)
    assert isinstance(result[0], dict)
    assert set(result[0].keys()) == {"customer_id", "created_at"}

    executor.close()


@requires_postgres
def test_postgres_executor_persists_across_reconnect(clean_customers_table):
    """
    Test D: the autocommit fix's actual point — data survives close()
    and a brand-new connection, with no explicit commit() anywhere in
    the Executor interface. Mirrors test_duckdb_executor_file_database.
    """
    from structifact.executors.postgres import PostgresExecutor

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    executor.execute_ddl("CREATE TABLE customers (customer_id INTEGER, created_at TIMESTAMP)")
    executor.load_rows("customers", ["customer_id"], [{"customer_id": "1"}])
    executor.close()

    executor2 = PostgresExecutor()
    executor2.connect(connection=POSTGRES_DSN)
    result = executor2.query("SELECT * FROM customers")
    assert len(result) == 1
    executor2.close()


@requires_postgres
def test_postgres_executor_duplicate_primary_key_raises(clean_customers_table):
    """
    Test E: a real constraint violation propagates uncaught — no
    exception-translation layer exists yet, matching DuckDBExecutor's
    current behavior of letting the raw driver error surface.
    """
    from structifact.executors.postgres import PostgresExecutor

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    executor.execute_ddl("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY)")
    executor.load_rows("customers", ["customer_id"], [{"customer_id": "1"}])

    with pytest.raises(Exception, match="duplicate key"):
        executor.load_rows("customers", ["customer_id"], [{"customer_id": "1"}])

    executor.close()


@requires_postgres
def test_execute_cli_against_real_postgres(capsys, clean_customers_table):
    """Full path: structifact execute --engine postgres, through the same CLI code DuckDB already goes through."""
    execute(_args("tests/fixtures/customers.yml", engine="postgres", connection=POSTGRES_DSN))

    out = capsys.readouterr().out
    assert "✓ Loaded schema: customers" in out
    assert "✓ Connected: postgres" in out
    assert "✓ Executed DDL" in out
    assert "created successfully" in out
