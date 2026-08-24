"""
Proves DatasetSpec.source_filter actually executes correctly against
real data on a real engine -- not just that the generated SQL text
looks right. Same discipline as 8D v1/v2: real DuckDB and PostgreSQL,
exact-value assertions.

The fixture is the real acceptance case this feature was scoped
against (see ir.py/model.py docstrings and DECISION_HISTORY.md): a
primary source (segmaster) with its own "current records only" filter,
left-joined to a text source (segtext) that shares a column name
(validto) with the primary source. Real data is designed so a naive
post-join WHERE would either raise an ambiguous-column error or
silently produce the wrong result -- this proves the CTE-wrapped
implementation avoids both:

- segmaster has one active row (validto='9999-12-31') and one expired row
  (an older validto) -- the expired row's segment master must not appear
  in the final result at all, even though a matching segtext row exists
  for it.
- segtext has both an English and a German text row for the active
  segment master -- only the English one (its own independent filter)
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


def _segment_master_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="segment_master",
        source_table="segmaster",
        source_filter="validto = '9999-12-31'",
        fields=[
            FieldSpec(name="segcode", type="string", source_column="segcode"),
            FieldSpec(
                name="descrtext", type="string",
                source="segtext", source_column="descrtext",
            ),
        ],
        sources=[
            SourceRef(name="segtext", table="segtext", filter="langcode = 'E'"),
        ],
        joins=[
            JoinSpec(source="segtext", on="segmaster.segcode = segtext.segcode"),
        ],
    )


def _load_data(executor) -> None:
    executor.execute_ddl("CREATE TABLE segmaster (segcode VARCHAR, validto VARCHAR)")
    executor.load_rows(
        "segmaster", ["segcode", "validto"],
        [
            {"segcode": "1000", "validto": "9999-12-31"},  # active -> should survive
            {"segcode": "2000", "validto": "2020-01-01"},  # expired -> must be excluded
        ],
    )

    executor.execute_ddl("CREATE TABLE segtext (segcode VARCHAR, langcode VARCHAR, validto VARCHAR, descrtext VARCHAR)")
    executor.load_rows(
        "segtext", ["segcode", "langcode", "validto", "descrtext"],
        [
            {"segcode": "1000", "langcode": "E", "validto": "9999-12-31", "descrtext": "Segment Master 1000 EN"},
            {"segcode": "1000", "langcode": "D", "validto": "9999-12-31", "descrtext": "Segment Master 1000 DE"},
            # A matching text row exists for the EXPIRED segmaster row too --
            # proves segmaster's own filter, not just the join, is what
            # excludes it from the final result.
            {"segcode": "2000", "langcode": "E", "validto": "9999-12-31", "descrtext": "Segment Master 2000 EN"},
        ],
    )


def _assert_correct_result(result) -> None:
    # Exactly one row: the active segment master, English text only.
    # If the primary-source filter were missing or ambiguous, this
    # would either error (ambiguous "validto") or return segcode=2000
    # and/or the German text row too.
    assert len(result) == 1
    assert result[0]["segcode"] == "1000"
    assert result[0]["descrtext"] == "Segment Master 1000 EN"


def test_duckdb_executes_source_filter_model_with_correct_values():
    dataset = _segment_master_dataset()
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
        cur.execute("DROP TABLE IF EXISTS segmaster")
        cur.execute("DROP TABLE IF EXISTS segtext")
    conn.close()

    dataset = _segment_master_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_data(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_result(result)
