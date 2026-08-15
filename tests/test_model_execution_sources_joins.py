"""
Phase 8D, v2 -- proves ModelGenerator's sources/joins/dedup CTE shape
actually executes correctly against real data on a real engine, not
just that it looks like plausible SQL text (which
tests/test_model_sources_joins.py already covers, unit-only).

Deliberately still read-only, matching 8D v1's exact discipline: no
materialization, no CLI changes, no new Executor method --
Executor.query() already expresses exactly what this needs.

The fixture is the same work_order_source shape already unit-tested
in test_model_sources_joins.py (one joined source, partner_role,
filtered to role_code = 'REQ', deduped by is_current desc, updated_at
desc, left-joined on wo_id) -- grounded in examples/workorder_demo's
real requirements, not invented for this test.

Real data is deliberately designed to exercise three distinct
semantics with exact-value assertions, not just "the query didn't
error":

- wo_id=1: a REQ candidate and a BILL candidate, two is_current
  states -- proves the `filter` genuinely excludes the wrong role
  (not just happens to not match), AND that dedup's primary sort key
  (is_current desc) picks the right REQ row.
- wo_id=2: two REQ candidates tied on is_current -- proves the
  secondary sort key (updated_at desc) actually breaks the tie,
  not just that a dedup rule exists.
- wo_id=3: no REQ row at all -- proves `left join` preserves the row
  with requested_by_name = NULL rather than silently dropping it.

Real PostgreSQL tests here follow tests/test_model_execution.py's
existing convention: gated on STRUCTIFACT_TEST_POSTGRES_DSN, skip
cleanly when unset.
"""

import os

import pytest

from structifact.ir import DatasetSpec, FieldSpec, SourceRef, DedupRule, JoinSpec
from structifact.generators.model import ModelGenerator
from structifact.executors.duckdb import DuckDBExecutor

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)

WORK_ORDER_ROWS = [(1,), (2,), (3,)]

# (wo_id, role_code, contact_name, is_current, updated_at)
PARTNER_ROLE_ROWS = [
    (1, "REQ", "Alice Old", "N", "2024-01-01"),
    (1, "REQ", "Alice Current", "Y", "2024-01-05"),
    (1, "BILL", "Alice Billing", "Y", "2024-01-05"),
    (2, "REQ", "Bob Older", "N", "2024-01-01"),
    (2, "REQ", "Bob Newer", "N", "2024-01-10"),
    # wo_id=3 has no partner_role rows at all.
]

EXPECTED_REQUESTED_BY = {
    1: "Alice Current",
    2: "Bob Newer",
    3: None,
}


def _work_order_source_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="work_order_source",
        fields=[
            FieldSpec(name="wo_id", type="integer"),
            FieldSpec(
                name="requested_by_name", type="string",
                source="partner_requested_by",
                source_column="contact_name",
            ),
        ],
        sources=[
            SourceRef(
                name="partner_requested_by",
                table="partner_role",
                filter="role_code = 'REQ'",
                dedup=DedupRule(
                    partition_by=["wo_id"],
                    order_by=["is_current desc", "updated_at desc"],
                ),
            ),
        ],
        joins=[
            JoinSpec(
                source="partner_requested_by",
                on="work_order_source.wo_id = partner_requested_by.wo_id",
            ),
        ],
    )


def test_model_generator_output_contains_expected_cte_fragments():
    """
    Distinguishes a generator regression from an Executor regression:
    if this fails, the SQL itself is wrong before any engine is
    involved.
    """
    model_sql = ModelGenerator().generate(_work_order_source_dataset()).content

    assert "partner_requested_by as (" in model_sql
    assert "where role_code = 'REQ'" in model_sql
    assert "partition by wo_id" in model_sql
    assert "order by is_current desc, updated_at desc" in model_sql
    assert "left join partner_requested_by" in model_sql


def _load_raw_tables(executor) -> None:
    executor.execute_ddl(
        "CREATE TABLE work_order_source (wo_id INTEGER)"
    )
    executor.load_rows(
        "work_order_source",
        ["wo_id"],
        [{"wo_id": str(wo_id)} for (wo_id,) in WORK_ORDER_ROWS],
    )

    executor.execute_ddl(
        "CREATE TABLE partner_role ("
        "wo_id INTEGER, role_code VARCHAR, contact_name VARCHAR, "
        "is_current VARCHAR, updated_at DATE)"
    )
    executor.load_rows(
        "partner_role",
        ["wo_id", "role_code", "contact_name", "is_current", "updated_at"],
        [
            {
                "wo_id": str(wo_id),
                "role_code": role_code,
                "contact_name": contact_name,
                "is_current": is_current,
                "updated_at": updated_at,
            }
            for wo_id, role_code, contact_name, is_current, updated_at in PARTNER_ROLE_ROWS
        ],
    )


def _assert_correct_requested_by(result) -> None:
    by_wo_id = {row["wo_id"]: row["requested_by_name"] for row in result}
    assert by_wo_id == EXPECTED_REQUESTED_BY


def test_duckdb_executes_sources_joins_model_with_correct_values():
    dataset = _work_order_source_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_tables(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_requested_by(result)


@requires_postgres
def test_postgres_executes_sources_joins_model_with_correct_values():
    """
    Uses a raw connection, independent of the PostgresExecutor under
    test, to drop any leftover tables from a previous run -- same
    pattern as test_model_execution.py's Postgres test.
    """
    import psycopg2

    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS partner_role")
        cur.execute("DROP TABLE IF EXISTS work_order_source")
    conn.close()

    dataset = _work_order_source_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_raw_tables(executor)

    result = executor.query(model_sql)

    executor.close()

    _assert_correct_requested_by(result)
