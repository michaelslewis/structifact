"""
Proves ModelGenerator's aggregated-joined-source CTE shape (see
AggregateRule in ir.py) actually executes correctly against real
data, not just that it looks like plausible SQL text (which
tests/test_model_aggregate_sources.py already covers, unit-only).

Grounded in a real requirements ticket (a SAP-shaped account-summary
source; see DECISION_HISTORY.md's third real-world-validation entry),
not invented for this test: a joined source (openitem, "customer open
items") must be pre-aggregated -- summed via a conditional sign-flip
on a debit/credit flag, grouped by the join keys -- before being
joined to the primary source.

Real data is deliberately designed to exercise three distinct
semantics with exact-value assertions, not just "the query didn't
error":

- C1: one debit row and one credit row -- proves the sign-flip CASE
  expression actually flips the credit row's sign before summing
  (100.00 - 30.00 = 70.00), not just that SOME sum is produced.
- C2: a single debit row -- a simple baseline sum (50.00), to isolate
  the multi-row collapsing case above from a trivial one.
- C3: no openitem rows at all -- proves the LEFT JOIN still preserves the
  row with a NULL aggregate, rather than the pre-aggregation CTE
  silently dropping customers with nothing to aggregate.

Follows tests/test_model_execution_sources_joins.py's exact
conventions, including the STRUCTIFACT_TEST_POSTGRES_DSN-gated real
PostgreSQL coverage.
"""

import os

import pytest

from structifact.ir import DatasetSpec, FieldSpec, SourceRef, AggregateRule, JoinSpec
from structifact.generators.model import ModelGenerator
from structifact.executors.duckdb import DuckDBExecutor

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)

CREDCTRL_ROWS = [("C1", "1000"), ("C2", "1000"), ("C3", "1000")]

# (custid, ctrlarea, dcind, amtlocal)
OPENITEM_ROWS = [
    ("C1", "1000", "S", "100.00"),
    ("C1", "1000", "H", "30.00"),
    ("C2", "1000", "S", "50.00"),
    # C3 has no openitem rows at all.
]

EXPECTED_SUM_AMTLOCAL = {
    "C1": "70.00",
    "C2": "50.00",
    "C3": None,
}


def _account_summary_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="account_summary",
        source_table="credctrl",
        fields=[
            FieldSpec(name="custid", type="string"),
            FieldSpec(name="ctrlarea", type="string"),
            FieldSpec(
                name="struct_openitem_sum_amtlocal", type="decimal",
                source="openitem", source_column="struct_openitem_sum_amtlocal",
            ),
        ],
        sources=[
            SourceRef(
                name="openitem",
                table="openitem",
                aggregate=AggregateRule(
                    group_by=["custid", "ctrlarea"],
                    aggregates={
                        "struct_openitem_sum_amtlocal": (
                            "SUM(case when dcind = 'S' then amtlocal "
                            "when dcind = 'H' then -amtlocal else 0 end)"
                        ),
                    },
                ),
            ),
        ],
        joins=[
            JoinSpec(
                source="openitem",
                on="credctrl.custid = openitem.custid and credctrl.ctrlarea = openitem.ctrlarea",
            ),
        ],
    )


def test_model_generator_output_contains_expected_cte_fragments():
    """
    Distinguishes a generator regression from an Executor regression:
    if this fails, the SQL itself is wrong before any engine is
    involved.
    """
    model_sql = ModelGenerator().generate(_account_summary_dataset()).content

    assert "openitem as (" in model_sql
    assert "group by custid, ctrlarea" in model_sql
    assert "SUM(case when dcind = 'S' then amtlocal when dcind = 'H' then -amtlocal else 0 end) as struct_openitem_sum_amtlocal" in model_sql
    assert "left join openitem" in model_sql


def _load_raw_tables(executor) -> None:
    executor.execute_ddl("CREATE TABLE credctrl (custid VARCHAR, ctrlarea VARCHAR)")
    executor.load_rows(
        "credctrl",
        ["custid", "ctrlarea"],
        [{"custid": custid, "ctrlarea": ctrlarea} for custid, ctrlarea in CREDCTRL_ROWS],
    )

    executor.execute_ddl(
        "CREATE TABLE openitem (custid VARCHAR, ctrlarea VARCHAR, dcind VARCHAR, amtlocal DECIMAL(13,2))"
    )
    executor.load_rows(
        "openitem",
        ["custid", "ctrlarea", "dcind", "amtlocal"],
        [
            {"custid": custid, "ctrlarea": ctrlarea, "dcind": dcind, "amtlocal": amtlocal}
            for custid, ctrlarea, dcind, amtlocal in OPENITEM_ROWS
        ],
    )


def _assert_correct_sums(result) -> None:
    by_custid = {row["custid"]: row["struct_openitem_sum_amtlocal"] for row in result}
    normalized = {
        custid: (None if value is None else f"{value:.2f}")
        for custid, value in by_custid.items()
    }
    assert normalized == EXPECTED_SUM_AMTLOCAL


def test_duckdb_executes_aggregate_source_model_with_correct_values():
    dataset = _account_summary_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_tables(executor)

    result = executor.query(model_sql.rstrip(";"))
    executor.close()

    _assert_correct_sums(result)


@requires_postgres
def test_postgres_executes_aggregate_source_model_with_correct_values():
    from structifact.executors.postgres import PostgresExecutor

    dataset = _account_summary_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    try:
        executor.execute_ddl("DROP TABLE IF EXISTS openitem")
        executor.execute_ddl("DROP TABLE IF EXISTS credctrl")
        _load_raw_tables(executor)

        result = executor.query(model_sql.rstrip(";"))
        _assert_correct_sums(result)
    finally:
        executor.execute_ddl("DROP TABLE IF EXISTS openitem")
        executor.execute_ddl("DROP TABLE IF EXISTS credctrl")
        executor.close()
