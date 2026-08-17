"""
Proves ModelGenerator's aggregated-joined-source CTE shape (see
AggregateRule in ir.py) actually executes correctly against real
data, not just that it looks like plausible SQL text (which
tests/test_model_aggregate_sources.py already covers, unit-only).

Grounded in a real requirements ticket (a SAP-shaped customer-credit
source; see DECISION_HISTORY.md's third real-world-validation entry),
not invented for this test: a joined source (bsid, "customer open
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
- C3: no bsid rows at all -- proves the LEFT JOIN still preserves the
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

KNKK_ROWS = [("C1", "1000"), ("C2", "1000"), ("C3", "1000")]

# (kunnr, kkber, shkzg, dmbtr)
BSID_ROWS = [
    ("C1", "1000", "S", "100.00"),
    ("C1", "1000", "H", "30.00"),
    ("C2", "1000", "S", "50.00"),
    # C3 has no bsid rows at all.
]

EXPECTED_SUM_DMBTR = {
    "C1": "70.00",
    "C2": "50.00",
    "C3": None,
}


def _customer_credit_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="customer_credit",
        source_table="knkk",
        fields=[
            FieldSpec(name="kunnr", type="string"),
            FieldSpec(name="kkber", type="string"),
            FieldSpec(
                name="struct_bsid_sum_dmbtr", type="decimal",
                source="bsid", source_column="struct_bsid_sum_dmbtr",
            ),
        ],
        sources=[
            SourceRef(
                name="bsid",
                table="bsid",
                aggregate=AggregateRule(
                    group_by=["kunnr", "kkber"],
                    aggregates={
                        "struct_bsid_sum_dmbtr": (
                            "SUM(case when shkzg = 'S' then dmbtr "
                            "when shkzg = 'H' then -dmbtr else 0 end)"
                        ),
                    },
                ),
            ),
        ],
        joins=[
            JoinSpec(
                source="bsid",
                on="knkk.kunnr = bsid.kunnr and knkk.kkber = bsid.kkber",
            ),
        ],
    )


def test_model_generator_output_contains_expected_cte_fragments():
    """
    Distinguishes a generator regression from an Executor regression:
    if this fails, the SQL itself is wrong before any engine is
    involved.
    """
    model_sql = ModelGenerator().generate(_customer_credit_dataset()).content

    assert "bsid as (" in model_sql
    assert "group by kunnr, kkber" in model_sql
    assert "SUM(case when shkzg = 'S' then dmbtr when shkzg = 'H' then -dmbtr else 0 end) as struct_bsid_sum_dmbtr" in model_sql
    assert "left join bsid" in model_sql


def _load_raw_tables(executor) -> None:
    executor.execute_ddl("CREATE TABLE knkk (kunnr VARCHAR, kkber VARCHAR)")
    executor.load_rows(
        "knkk",
        ["kunnr", "kkber"],
        [{"kunnr": kunnr, "kkber": kkber} for kunnr, kkber in KNKK_ROWS],
    )

    executor.execute_ddl(
        "CREATE TABLE bsid (kunnr VARCHAR, kkber VARCHAR, shkzg VARCHAR, dmbtr DECIMAL(13,2))"
    )
    executor.load_rows(
        "bsid",
        ["kunnr", "kkber", "shkzg", "dmbtr"],
        [
            {"kunnr": kunnr, "kkber": kkber, "shkzg": shkzg, "dmbtr": dmbtr}
            for kunnr, kkber, shkzg, dmbtr in BSID_ROWS
        ],
    )


def _assert_correct_sums(result) -> None:
    by_kunnr = {row["kunnr"]: row["struct_bsid_sum_dmbtr"] for row in result}
    normalized = {
        kunnr: (None if value is None else f"{value:.2f}")
        for kunnr, value in by_kunnr.items()
    }
    assert normalized == EXPECTED_SUM_DMBTR


def test_duckdb_executes_aggregate_source_model_with_correct_values():
    dataset = _customer_credit_dataset()
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

    dataset = _customer_credit_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    try:
        executor.execute_ddl("DROP TABLE IF EXISTS bsid")
        executor.execute_ddl("DROP TABLE IF EXISTS knkk")
        _load_raw_tables(executor)

        result = executor.query(model_sql.rstrip(";"))
        _assert_correct_sums(result)
    finally:
        executor.execute_ddl("DROP TABLE IF EXISTS bsid")
        executor.execute_ddl("DROP TABLE IF EXISTS knkk")
        executor.close()
