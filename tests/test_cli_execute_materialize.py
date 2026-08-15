"""
Phase 8D, v4 -- CLI exposure for materialization: `structifact execute
--materialize`. The underlying capability (typed CREATE TABLE +
INSERT INTO ... SELECT, atomic, source/target collision protection)
was already proven directly against Executor in Phase 8D v3
(tests/test_model_materialization.py) -- this file proves only the
CLI wiring on top of it: argument validation, fail-fast behavior,
message/verification-query reuse, and that --materialize does not
change any existing execute() behavior (plain execute, --data,
--drop-if-exists) it doesn't touch.

Reuses the exact order_items/raw_order_items fixture from 8D v1/v3,
now written as a real YAML file (execute() only accepts a spec path,
not an in-memory DatasetSpec), with raw upstream tables pre-populated
directly via a raw Executor -- never through the CLI, matching the
documented boundary that `structifact execute` does not create or
populate the upstream tables a model reads from.

Real PostgreSQL tests here follow the existing convention
(tests/test_executors.py): gated on STRUCTIFACT_TEST_POSTGRES_DSN,
skip cleanly when unset.
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

ORDER_ITEMS_YAML = """
dataset:
  name: order_items

source_table: raw_order_items

constraints:
  - type: primary_key
    columns: [order_id]

fields:
  - name: order_id
    type: integer
  - name: quantity
    type: integer
  - name: unit_price
    type: decimal(10,2)
  - name: line_total
    type: decimal(15,2)
    computed: true
    expression: "quantity * unit_price"
"""

# order_id -> (quantity, unit_price, expected line_total)
ORDER_ITEMS_ROWS = [
    (1, 2, "10.50", "21.00"),
    (2, 3, "7.25", "21.75"),
]


def _args(spec, engine="duckdb", connection=None, data=None,
          drop_if_exists=False, materialize=False):
    return argparse.Namespace(
        spec=spec, engine=engine, connection=connection, data=data,
        drop_if_exists=drop_if_exists, materialize=materialize,
    )


def _spec_file(tmp_path):
    spec_path = tmp_path / "order_items.yml"
    spec_path.write_text(ORDER_ITEMS_YAML)
    return str(spec_path)


def _load_raw_order_items_directly(db_path, rows=ORDER_ITEMS_ROWS) -> None:
    """
    Populates raw_order_items via a raw Executor call, NOT through the
    CLI -- structifact execute never creates or populates the upstream
    tables a model reads from, so the test setup must not either.
    """
    executor = DuckDBExecutor()
    executor.connect(connection=db_path)
    executor.execute_ddl(
        "CREATE TABLE raw_order_items (order_id INTEGER, quantity INTEGER, unit_price DECIMAL(10,2))"
    )
    executor.load_rows(
        "raw_order_items",
        ["order_id", "quantity", "unit_price"],
        [
            {"order_id": str(order_id), "quantity": str(qty), "unit_price": price}
            for order_id, qty, price, _ in rows
        ],
    )
    executor.close()


# ---------------------------------------------------------------------
# Existing behavior stays unchanged when --materialize is absent
# ---------------------------------------------------------------------

def test_plain_execute_unaffected_by_materialize_flag_existing(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")

    execute(_args("tests/fixtures/customers.yml", connection=db_path))

    out = capsys.readouterr().out
    assert "✓ Executed DDL" in out
    assert "created successfully" in out
    assert "materialize" not in out.lower()


def test_data_flag_unaffected_by_materialize_addition(capsys, tmp_path):
    yaml_file = tmp_path / "customers.yml"
    yaml_file.write_text(
        "dataset:\n  name: customers\nfields:\n"
        "  - name: customer_id\n    type: integer\n"
        "  - name: customer_name\n    type: string\n"
    )
    csv_file = tmp_path / "customers.csv"
    csv_file.write_text("customer_id,customer_name\n1,Alice\n")

    db_path = str(tmp_path / "test.duckdb")
    execute(_args(str(yaml_file), connection=db_path, data=str(csv_file)))

    out = capsys.readouterr().out
    assert "✓ Loaded 1 rows" in out
    assert "created and populated successfully" in out


# ---------------------------------------------------------------------
# --materialize argument validation (fails fast, before connecting)
# ---------------------------------------------------------------------

def test_materialize_and_data_together_rejected_before_connecting(capsys, tmp_path):
    execute(_args(
        _spec_file(tmp_path), connection=str(tmp_path / "test.duckdb"),
        data="tests/fixtures/customers.csv", materialize=True,
    ))

    out = capsys.readouterr().out
    assert "cannot be used together" in out
    assert "✓ Connected" not in out


def test_materialize_nothing_to_materialize_fails_before_connecting(capsys, tmp_path):
    yaml_file = tmp_path / "plain.yml"
    yaml_file.write_text(
        "dataset:\n  name: plain\nfields:\n  - name: id\n    type: integer\n"
    )

    execute(_args(str(yaml_file), connection=str(tmp_path / "test.duckdb"), materialize=True))

    out = capsys.readouterr().out
    assert "nothing to materialize" in out
    assert "✓ Connected" not in out


def test_materialize_source_target_collision_fails_before_connecting(capsys, tmp_path):
    yaml_file = tmp_path / "order_items.yml"
    yaml_file.write_text(
        "dataset:\n  name: order_items\nfields:\n"
        "  - name: order_id\n    type: integer\n"
        "  - name: line_total\n    type: decimal(15,2)\n"
        "    computed: true\n    expression: \"quantity * unit_price\"\n"
    )

    execute(_args(str(yaml_file), connection=str(tmp_path / "test.duckdb"), materialize=True))

    out = capsys.readouterr().out
    assert "Cannot materialize" in out
    assert "relation of the same name" in out
    assert "✓ Connected" not in out


# ---------------------------------------------------------------------
# Real materialization via the CLI, DuckDB
# ---------------------------------------------------------------------

def test_duckdb_materialize_end_to_end(capsys, tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    _load_raw_order_items_directly(db_path)

    execute(_args(_spec_file(tmp_path), connection=db_path, materialize=True))

    out = capsys.readouterr().out
    assert "✓ Executed DDL: CREATE TABLE order_items" in out
    assert "✓ Executed model INSERT: INSERT INTO order_items" in out
    assert "✓ Verification query: 2 rows in order_items" in out
    assert "created and materialized successfully" in out

    executor = DuckDBExecutor()
    executor.connect(connection=db_path)
    result = executor.query("SELECT * FROM order_items ORDER BY order_id")
    executor.close()

    assert [str(row["line_total"]) for row in result] == ["21.00", "21.75"]


def test_duckdb_materialize_against_existing_table_without_drop_fails(capsys, tmp_path):
    """
    --materialize does not require --drop-if-exists, and does not
    silently replace an existing target -- same fail-loudly semantics
    as the plain/--data paths, since --materialize only changes how
    the table gets rows, never the DROP/CREATE step's behavior.
    """
    db_path = str(tmp_path / "test.duckdb")
    _load_raw_order_items_directly(db_path)

    execute(_args(_spec_file(tmp_path), connection=db_path, materialize=True))
    capsys.readouterr()  # clear first run's output

    execute(_args(_spec_file(tmp_path), connection=db_path, materialize=True))

    out = capsys.readouterr().out
    assert "Execution failed" in out
    assert "already exists" in out


def test_duckdb_materialize_atomic_rollback_on_real_constraint_violation(capsys, tmp_path):
    """
    A genuine primary-key violation during the model INSERT rolls
    back the whole transaction() scope, including the CREATE -- no
    target table left behind at all, matching 8D v3's Executor-level
    proof, now confirmed through the actual CLI path.
    """
    db_path = str(tmp_path / "test.duckdb")
    _load_raw_order_items_directly(db_path, rows=ORDER_ITEMS_ROWS + [(1, 1, "1.00", "1.00")])

    execute(_args(_spec_file(tmp_path), connection=db_path, materialize=True))

    out = capsys.readouterr().out
    assert "Execution failed" in out

    executor = DuckDBExecutor()
    executor.connect(connection=db_path)
    with pytest.raises(Exception):
        executor.query("SELECT * FROM order_items")
    executor.close()


# ---------------------------------------------------------------------
# Real materialization via the CLI, PostgreSQL
# ---------------------------------------------------------------------

@requires_postgres
def test_postgres_materialize_end_to_end(capsys, tmp_path):
    import psycopg2

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS order_items")
        cur.execute("DROP TABLE IF EXISTS raw_order_items")
    conn.close()

    from structifact.executors.postgres import PostgresExecutor

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    executor.execute_ddl(
        "CREATE TABLE raw_order_items (order_id INTEGER, quantity INTEGER, unit_price DECIMAL(10,2))"
    )
    executor.load_rows(
        "raw_order_items",
        ["order_id", "quantity", "unit_price"],
        [
            {"order_id": str(order_id), "quantity": str(qty), "unit_price": price}
            for order_id, qty, price, _ in ORDER_ITEMS_ROWS
        ],
    )
    executor.close()

    execute(_args(_spec_file(tmp_path), engine="postgres", connection=POSTGRES_DSN, materialize=True))

    out = capsys.readouterr().out
    assert "✓ Executed model INSERT: INSERT INTO order_items" in out
    assert "created and materialized successfully" in out

    verify = PostgresExecutor()
    verify.connect(connection=POSTGRES_DSN)
    result = verify.query("SELECT * FROM order_items ORDER BY order_id")
    verify.close()

    assert [str(row["line_total"]) for row in result] == ["21.00", "21.75"]
