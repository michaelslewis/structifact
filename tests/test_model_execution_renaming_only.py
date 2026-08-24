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
        name="job_item_master",
        source_table="jobhdr",
        fields=[
            FieldSpec(name="demo_jobhdr_clientid", type="string", source_column="clientid"),
            FieldSpec(name="demo_jobhdr_companyid", type="string", source_column="companyid"),
        ],
    )


def _load_raw_jobhdr(executor) -> None:
    executor.execute_ddl("CREATE TABLE jobhdr (clientid VARCHAR, companyid VARCHAR)")
    executor.load_rows(
        "jobhdr", ["clientid", "companyid"],
        [{"clientid": "100", "companyid": "US01"}, {"clientid": "200", "companyid": "US02"}],
    )


def _assert_correct_result(result) -> None:
    by_clientid = {row["demo_jobhdr_clientid"]: row["demo_jobhdr_companyid"] for row in result}
    assert by_clientid == {"100": "US01", "200": "US02"}


def test_duckdb_executes_renaming_only_model_with_correct_values():
    dataset = _dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_jobhdr(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_result(result)


def test_duckdb_materializes_renaming_only_dataset():
    dataset = _dataset()
    ddl_sql = SQLGenerator().generate(dataset).content
    insert_sql = ModelGenerator().generate_insert(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_jobhdr(executor)

    with executor.transaction():
        executor.execute_ddl(ddl_sql)
        executor.execute_ddl(insert_sql)

    result = executor.query("SELECT * FROM job_item_master")
    executor.close()

    _assert_correct_result(result)


@requires_postgres
def test_postgres_executes_renaming_only_model_with_correct_values():
    import psycopg2

    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS jobhdr")
        cur.execute("DROP TABLE IF EXISTS job_item_master")
    conn.close()

    dataset = _dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_raw_jobhdr(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_result(result)
