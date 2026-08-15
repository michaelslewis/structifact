"""
Phase 8D, v1 — proves ModelGenerator's computed-field SELECT actually
runs against real data on a real engine, not just that it looks like
plausible SQL text.

Deliberately minimal, matching the same real-example-first discipline
as Phase 8A: one dataset, one computed field, a genuinely valid SQL
expression, no sources/joins/dedup. Read-only verification only — no
materialization, no CLI changes, no new Executor methods.
Executor.query() already expresses exactly what this needs.

The backing table here is deliberately a *raw* table (order_id,
quantity, unit_price only) — ModelGenerator's SELECT reads raw
upstream columns and computes line_total fresh; it never reads a
line_total column from the source table. SQLGenerator's DDL (which
would include a line_total column, documented via comment) describes
the dataset's own resulting shape, a different table from the one
this test's model SELECT reads from — see ModelGenerator's own
docstring for that distinction. Not involved in this test at all.

Real PostgreSQL tests here follow tests/test_executors.py's existing
convention: gated on STRUCTIFACT_TEST_POSTGRES_DSN, skip cleanly when
unset.
"""

import os
from decimal import Decimal

import pytest

from structifact.ir import DatasetSpec, FieldSpec
from structifact.generators.model import ModelGenerator
from structifact.executors.duckdb import DuckDBExecutor

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)

# order_id -> (quantity, unit_price, expected line_total)
ROWS = [
    (1, 2, "10.50", "21.00"),
    (2, 3, "7.25", "21.75"),
    (3, 5, "4.00", "20.00"),
]


def _order_items_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="order_items",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(name="quantity", type="integer"),
            FieldSpec(name="unit_price", type="decimal", precision=10, scale=2),
            FieldSpec(
                name="line_total", type="decimal", precision=15, scale=2,
                computed=True, expression="quantity * unit_price",
            ),
        ],
    )


def test_model_generator_output_contains_expected_expression():
    """
    Distinguishes a generator regression from an Executor regression:
    if this fails, the SQL itself is wrong before any engine is
    involved.
    """
    model_sql = ModelGenerator().generate(_order_items_dataset()).content

    assert "quantity * unit_price as line_total" in model_sql
    assert "from order_items" in model_sql


def _load_raw_order_items(executor) -> None:
    executor.execute_ddl(
        "CREATE TABLE order_items (order_id INTEGER, quantity INTEGER, unit_price DECIMAL(10,2))"
    )
    executor.load_rows(
        "order_items",
        ["order_id", "quantity", "unit_price"],
        [
            {"order_id": str(order_id), "quantity": str(qty), "unit_price": price}
            for order_id, qty, price, _ in ROWS
        ],
    )


def _assert_correct_line_totals(result) -> None:
    by_order_id = {row["order_id"]: row["line_total"] for row in result}
    assert len(by_order_id) == len(ROWS)

    for order_id, _, _, expected in ROWS:
        actual = Decimal(str(by_order_id[order_id]))
        assert actual == Decimal(expected), (
            f"order_id={order_id}: expected {expected}, got {actual}"
        )


def test_duckdb_executes_model_select_with_correct_values():
    dataset = _order_items_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_order_items(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_line_totals(result)


@requires_postgres
def test_postgres_executes_model_select_with_correct_values():
    """
    Uses a raw connection, independent of the PostgresExecutor under
    test, to drop any leftover table from a previous run — same
    pattern as test_executors.py's clean_customers_table fixture.
    """
    import psycopg2

    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS order_items")
    conn.close()

    dataset = _order_items_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_raw_order_items(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_line_totals(result)
