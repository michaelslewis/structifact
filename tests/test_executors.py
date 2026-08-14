import argparse

import pytest

from structifact.executors.registry import EXECUTORS
from structifact.executors.duckdb import DuckDBExecutor
from structifact.cli import execute


# ---------------------------------------------------------------------
# DuckDBExecutor, direct unit tests
# ---------------------------------------------------------------------

def test_duckdb_executor_registered():
    assert EXECUTORS["duckdb"] is DuckDBExecutor


def test_duckdb_executor_connect_and_ddl():
    executor = DuckDBExecutor()
    executor.connect()  # in-memory, no database arg

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


def test_duckdb_executor_file_database(tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    executor = DuckDBExecutor()
    executor.connect(database=db_path)
    executor.execute_ddl("CREATE TABLE t (id INTEGER)")
    executor.load_rows("t", ["id"], [{"id": "1"}])
    executor.close()

    # Reconnect to the same file, confirm data persisted.
    executor2 = DuckDBExecutor()
    executor2.connect(database=db_path)
    result = executor2.query("SELECT * FROM t")
    assert len(result) == 1
    executor2.close()


# ---------------------------------------------------------------------
# CLI-level: structifact execute
# ---------------------------------------------------------------------

def _args(spec, engine="duckdb", database=None, data=None, drop_if_exists=False):
    return argparse.Namespace(
        spec=spec, engine=engine, database=database, data=data,
        drop_if_exists=drop_if_exists,
    )


def test_execute_creates_table_no_data(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    execute(_args("tests/fixtures/customers.yml", database=db_path))

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

    execute(_args(str(yaml_file), database=db_path, data=str(csv_file)))

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


def test_execute_in_memory_when_no_database_given(capsys):
    execute(_args("tests/fixtures/customers.yml", database=None))

    out = capsys.readouterr().out
    assert "✓ Connected: duckdb (in-memory)" in out


def test_execute_rerun_without_drop_if_exists_fails(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    execute(_args("tests/fixtures/customers.yml", database=db_path))
    execute(_args("tests/fixtures/customers.yml", database=db_path))

    out = capsys.readouterr().out
    assert "Execution failed" in out
    assert "already exists" in out


def test_execute_rerun_with_drop_if_exists_succeeds(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    execute(_args("tests/fixtures/customers.yml", database=db_path))
    capsys.readouterr()  # clear first run's output

    execute(_args("tests/fixtures/customers.yml", database=db_path, drop_if_exists=True))

    out = capsys.readouterr().out
    assert "✓ Dropped table 'customers' if it existed" in out
    assert "✓ Executed DDL" in out
    assert "created successfully" in out


def test_execute_drop_if_exists_on_first_run_is_harmless(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    execute(_args("tests/fixtures/customers.yml", database=db_path, drop_if_exists=True))

    out = capsys.readouterr().out
    assert "✓ Dropped table 'customers' if it existed" in out
    assert "✓ Executed DDL" in out
    assert "Execution failed" not in out
