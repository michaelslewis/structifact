"""
Proves DatasetSpec.source_filter actually executes correctly against
real data on a real engine -- not just that the generated SQL text
looks right. Same discipline as 8D v1/v2: real DuckDB and PostgreSQL,
exact-value assertions.

The fixture is the real acceptance case this feature was scoped
against (see ir.py/model.py docstrings and DECISION_HISTORY.md): a
primary source (cepc) with its own "current records only" filter,
left-joined to a text source (cepct) that shares a column name
(datbi) with the primary source. Real data is designed so a naive
post-join WHERE would either raise an ambiguous-column error or
silently produce the wrong result -- this proves the CTE-wrapped
implementation avoids both:

- cepc has one active row (datbi='9999-12-31') and one expired row
  (an older datbi) -- the expired row's profit center must not appear
  in the final result at all, even though a matching cepct row exists
  for it.
- cepct has both an English and a German text row for the active
  profit center -- only the English one (its own independent filter)
  should survive.

Real PostgreSQL test here follows the existing convention: gated on
STRUCTIFACT_TEST_POSTGRES_DSN, skips cleanly when unset.
"""

import os

import pytest

from structifact.ir import DatasetSpec, FieldSpec, SourceRef, JoinSpec
from structifact.generators.model import ModelGenerator
from structifact.executors.duckdb import DuckDBExecutor

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)


def _profit_center_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="profit_center",
        source_table="cepc",
        source_filter="datbi = '9999-12-31'",
        fields=[
            FieldSpec(name="prctr", type="string", source_column="prctr"),
            FieldSpec(
                name="ktext", type="string",
                source="cepct", source_column="ktext",
            ),
        ],
        sources=[
            SourceRef(name="cepct", table="cepct", filter="spras = 'E'"),
        ],
        joins=[
            JoinSpec(source="cepct", on="cepc.prctr = cepct.prctr"),
        ],
    )


def _load_data(executor) -> None:
    executor.execute_ddl("CREATE TABLE cepc (prctr VARCHAR, datbi VARCHAR)")
    executor.load_rows(
        "cepc", ["prctr", "datbi"],
        [
            {"prctr": "1000", "datbi": "9999-12-31"},  # active -> should survive
            {"prctr": "2000", "datbi": "2020-01-01"},  # expired -> must be excluded
        ],
    )

    executor.execute_ddl("CREATE TABLE cepct (prctr VARCHAR, spras VARCHAR, datbi VARCHAR, ktext VARCHAR)")
    executor.load_rows(
        "cepct", ["prctr", "spras", "datbi", "ktext"],
        [
            {"prctr": "1000", "spras": "E", "datbi": "9999-12-31", "ktext": "Profit Center 1000 EN"},
            {"prctr": "1000", "spras": "D", "datbi": "9999-12-31", "ktext": "Profit Center 1000 DE"},
            # A matching text row exists for the EXPIRED cepc row too --
            # proves cepc's own filter, not just the join, is what
            # excludes it from the final result.
            {"prctr": "2000", "spras": "E", "datbi": "9999-12-31", "ktext": "Profit Center 2000 EN"},
        ],
    )


def _assert_correct_result(result) -> None:
    # Exactly one row: the active profit center, English text only.
    # If the primary-source filter were missing or ambiguous, this
    # would either error (ambiguous "datbi") or return prctr=2000
    # and/or the German text row too.
    assert len(result) == 1
    assert result[0]["prctr"] == "1000"
    assert result[0]["ktext"] == "Profit Center 1000 EN"


def test_duckdb_executes_source_filter_model_with_correct_values():
    dataset = _profit_center_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_data(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_result(result)


@requires_postgres
def test_postgres_executes_source_filter_model_with_correct_values():
    import psycopg2

    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS cepc")
        cur.execute("DROP TABLE IF EXISTS cepct")
    conn.close()

    dataset = _profit_center_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_data(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_result(result)
