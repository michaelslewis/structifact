"""
Proves the renaming-only ModelGenerator fix (see
tests/test_model_renaming_only.py, DECISION_HISTORY.md) actually
executes correctly against real data -- not just that the generated
SQL text looks right. Same discipline as every prior model-execution
test: real DuckDB and PostgreSQL, exact-value assertions.

Fixture is a small real-shaped slice of the actual acceptance case
(a single-source dataset, every field renamed via source_column, no
filter/join/computed field) -- proving both the read-only SELECT and
materialization (generate_insert -> a real target table) work.

Real PostgreSQL test here follows the existing convention: gated on
STRUCTIFACT_TEST_POSTGRES_DSN, skips cleanly when unset.
"""

import os

import pytest

from structifact.ir import DatasetSpec, FieldSpec
from structifact.generators.model import ModelGenerator
from structifact.generators.sql import SQLGenerator
from structifact.executors.duckdb import DuckDBExecutor

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)


def _dataset() -> DatasetSpec:
    return DatasetSpec(
        name="internal_order_master",
        source_table="aufk",
        fields=[
            FieldSpec(name="biz_aufk_mandt", type="string", source_column="mandt"),
            FieldSpec(name="biz_aufk_bukrs", type="string", source_column="bukrs"),
        ],
    )


def _load_raw_aufk(executor) -> None:
    executor.execute_ddl("CREATE TABLE aufk (mandt VARCHAR, bukrs VARCHAR)")
    executor.load_rows(
        "aufk", ["mandt", "bukrs"],
        [{"mandt": "100", "bukrs": "US01"}, {"mandt": "200", "bukrs": "US02"}],
    )


def _assert_correct_result(result) -> None:
    by_mandt = {row["biz_aufk_mandt"]: row["biz_aufk_bukrs"] for row in result}
    assert by_mandt == {"100": "US01", "200": "US02"}


def test_duckdb_executes_renaming_only_model_with_correct_values():
    dataset = _dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_aufk(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_result(result)


def test_duckdb_materializes_renaming_only_dataset():
    dataset = _dataset()
    ddl_sql = SQLGenerator().generate(dataset).content
    insert_sql = ModelGenerator().generate_insert(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_aufk(executor)

    with executor.transaction():
        executor.execute_ddl(ddl_sql)
        executor.execute_ddl(insert_sql)

    result = executor.query("SELECT * FROM internal_order_master")
    executor.close()

    _assert_correct_result(result)


@requires_postgres
def test_postgres_executes_renaming_only_model_with_correct_values():
    import psycopg2

    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS aufk")
        cur.execute("DROP TABLE IF EXISTS internal_order_master")
    conn.close()

    dataset = _dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_raw_aufk(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_result(result)
