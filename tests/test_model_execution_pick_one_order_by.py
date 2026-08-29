"""
Real-execution tests for JoinSpec.pick_one_order_by
(docs/PICK_ONE_ORDER_BY_CONTRACT.md), mirroring
test_model_execution_sources_joins.py's discipline: proves the
generated LATERAL SQL actually executes correctly against real
engines, not just that it looks like plausible SQL text (unit/fragment
coverage lives in test_model_pick_one_order_by.py).

Real PostgreSQL tests here follow the same convention as
test_model_execution_sources_joins.py: gated on
STRUCTIFACT_TEST_POSTGRES_DSN, skip cleanly when unset. Ported for the
core scenarios the approved implementation plan calls out (basic
pick-one, zero-qualifying-rows for both join types, ordering/tie
handling, and multiple sequential pick-one joins) -- not for every
DuckDB-only scenario below, matching the plan's stated scope.

Two sections at the end cover the real-world reproductions from the
approved contract:

- examples/value_experiment/: loads the actual CSVs and diffs against
  the actual expected_result_per_order.csv already committed there --
  a real, not synthetic, regression test.
- hard_insurance_claims: NO CSV fixture data is committed anywhere
  under examples/coverage_round1/ for this example (confirmed by
  directory listing) -- the fan-out finding recorded in
  docs/FUTURE_WORK.md was verified against synthetic data that was
  never committed. This test therefore uses a small, self-contained
  inline fixture reproducing the *same failure mechanism* (an as-of
  join with no row-reduction fanning out into duplicate rows), not a
  replay of the original documented real-data artifact.
"""

import csv
import os
import pathlib

import pytest

from structifact.ir import (
    DatasetSpec, FieldSpec, SourceRef, DedupRule, AggregateRule, JoinSpec,
)
from structifact.generators.model import ModelGenerator
from structifact.executors.duckdb import DuckDBExecutor

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)

VALUE_EXPERIMENT_DIR = pathlib.Path(__file__).parent.parent / "examples" / "value_experiment"


# ---------------------------------------------------------------------
# Shared "claims" fixture: multiple qualifying rows, ordering, ties,
# and zero-qualifying rows (both LEFT and INNER), all in one small,
# reusable dataset -- same "several distinct semantics, one fixture"
# discipline test_model_execution_sources_joins.py already uses for
# its wo_id=1/2/3 rows.
#
# (claim_id, effective_date, status, priority)
# - CLM1: two qualifying rows, distinct effective_date -> proves
#   pick_one_order_by's primary key alone selects the latest.
# - CLM2: two qualifying rows tied on effective_date -> proves the
#   secondary key (priority desc) breaks the tie.
# - CLM3: zero qualifying rows -> LEFT preserves the row as NULL,
#   INNER drops it.
# - CLM4: two qualifying rows tied on BOTH ordering keys -> proves
#   exactly one row is still selected (contract §3: no error, no
#   fan-out, no invented tiebreaker -- which specific one wins is
#   deliberately left unasserted, since the contract states that's
#   engine-determined, not Structifact-determined).
# ---------------------------------------------------------------------

CLAIMS_ROWS = [
    ("CLM1", "2024-06-01"),
    ("CLM2", "2024-06-01"),
    ("CLM3", "2024-06-01"),
    ("CLM4", "2024-06-01"),
]

# (claim_id, effective_date, status, priority)
POLICY_STATUS_ROWS = [
    ("CLM1", "2024-01-01", "active", 1),
    ("CLM1", "2024-05-01", "lapsed", 1),   # later effective_date -> wins
    ("CLM2", "2024-02-01", "A", 1),
    ("CLM2", "2024-02-01", "B", 2),        # tied effective_date, higher priority -> wins
    # CLM3: no rows at all.
    ("CLM4", "2024-03-01", "C", 1),
    ("CLM4", "2024-03-01", "D", 1),        # fully tied on both ordering keys
]


def _claims_dataset(join_type: str) -> DatasetSpec:
    return DatasetSpec(
        name="claims",
        fields=[
            FieldSpec(name="claim_id", type="string"),
            FieldSpec(
                name="status", type="string",
                source="policy_status", source_column="status",
            ),
        ],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(
                source="policy_status",
                on="claims.claim_id = policy_status.claim_id and policy_status.effective_date <= claims.claim_date",
                type=join_type,
                pick_one_order_by=["policy_status.effective_date desc", "policy_status.priority desc"],
            ),
        ],
    )


def _load_claims_fixture(executor) -> None:
    executor.execute_ddl("CREATE TABLE claims (claim_id VARCHAR, claim_date DATE)")
    executor.load_rows(
        "claims", ["claim_id", "claim_date"],
        [{"claim_id": c, "claim_date": d} for c, d in CLAIMS_ROWS],
    )

    executor.execute_ddl(
        "CREATE TABLE policy_status_history "
        "(claim_id VARCHAR, effective_date DATE, status VARCHAR, priority INTEGER)"
    )
    executor.load_rows(
        "policy_status_history",
        ["claim_id", "effective_date", "status", "priority"],
        [
            {"claim_id": c, "effective_date": d, "status": s, "priority": p}
            for c, d, s, p in POLICY_STATUS_ROWS
        ],
    )


def _by_claim_id(result):
    return {row["claim_id"]: row for row in result}


def test_duckdb_pick_one_join_left_type_multiple_ordering_and_ties():
    dataset = _claims_dataset("left")
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_claims_fixture(executor)
    result = executor.query(model_sql)
    executor.close()

    assert len(result) == 4  # no fan-out for CLM1/CLM2/CLM4, row preserved for CLM3

    by_id = _by_claim_id(result)
    assert by_id["CLM1"]["status"] == "lapsed"   # multiple qualifying rows, ordering picks latest
    assert by_id["CLM2"]["status"] == "B"        # tie broken by secondary key
    assert by_id["CLM3"]["status"] is None       # zero qualifying rows, LEFT preserves the row
    assert by_id["CLM4"]["status"] in ("C", "D")  # fully tied: exactly one row, either winner acceptable


def test_duckdb_pick_one_join_inner_type_drops_zero_candidate_row():
    dataset = _claims_dataset("inner")
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_claims_fixture(executor)
    result = executor.query(model_sql)
    executor.close()

    ids = {row["claim_id"] for row in result}
    assert ids == {"CLM1", "CLM2", "CLM4"}  # CLM3 dropped: zero qualifying rows, INNER


@requires_postgres
def test_postgres_pick_one_join_left_type_multiple_ordering_and_ties():
    import psycopg2
    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS policy_status_history")
        cur.execute("DROP TABLE IF EXISTS claims")
    conn.close()

    dataset = _claims_dataset("left")
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_claims_fixture(executor)
    result = executor.query(model_sql)
    executor.close()

    assert len(result) == 4
    by_id = _by_claim_id(result)
    assert by_id["CLM1"]["status"] == "lapsed"
    assert by_id["CLM2"]["status"] == "B"
    assert by_id["CLM3"]["status"] is None
    assert by_id["CLM4"]["status"] in ("C", "D")


@requires_postgres
def test_postgres_pick_one_join_inner_type_drops_zero_candidate_row():
    import psycopg2
    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS policy_status_history")
        cur.execute("DROP TABLE IF EXISTS claims")
    conn.close()

    dataset = _claims_dataset("inner")
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_claims_fixture(executor)
    result = executor.query(model_sql)
    executor.close()

    ids = {row["claim_id"] for row in result}
    assert ids == {"CLM1", "CLM2", "CLM4"}


# ---------------------------------------------------------------------
# Multiple sequential pick-one joins (contract §5): the second join's
# `on`/`pick_one_order_by` references a column produced by the first,
# already-resolved pick-one join.
# ---------------------------------------------------------------------

def _sequential_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="claims2",
        fields=[
            FieldSpec(name="claim_id", type="string"),
            FieldSpec(name="a_val", type="string", source="rank_a", source_column="a_val"),
            FieldSpec(name="b_val", type="string", source="rank_b", source_column="b_val"),
        ],
        sources=[
            SourceRef(name="rank_a", table="rank_a_candidates"),
            SourceRef(name="rank_b", table="rank_b_candidates"),
        ],
        joins=[
            JoinSpec(
                source="rank_a",
                on="claims2.claim_id = rank_a.claim_id",
                pick_one_order_by=["rank_a.rank desc"],
            ),
            JoinSpec(
                # References rank_a's already-resolved a_val column --
                # proves join B's LATERAL scope sees join A's output.
                source="rank_b",
                on="rank_b.a_val_ref = rank_a.a_val",
                pick_one_order_by=["rank_b.rank desc"],
            ),
        ],
    )


def _load_sequential_fixture(executor) -> None:
    executor.execute_ddl("CREATE TABLE claims2 (claim_id VARCHAR)")
    executor.load_rows("claims2", ["claim_id"], [{"claim_id": "CLM1"}])

    executor.execute_ddl(
        "CREATE TABLE rank_a_candidates (claim_id VARCHAR, a_val VARCHAR, rank INTEGER)"
    )
    executor.load_rows(
        "rank_a_candidates", ["claim_id", "a_val", "rank"],
        [
            {"claim_id": "CLM1", "a_val": "X", "rank": 1},
            {"claim_id": "CLM1", "a_val": "Y", "rank": 2},  # higher rank -> wins, a_val='Y'
        ],
    )

    executor.execute_ddl(
        "CREATE TABLE rank_b_candidates (a_val_ref VARCHAR, b_val VARCHAR, rank INTEGER)"
    )
    executor.load_rows(
        "rank_b_candidates", ["a_val_ref", "b_val", "rank"],
        [
            {"a_val_ref": "Y", "b_val": "B-for-Y-old", "rank": 1},
            {"a_val_ref": "Y", "b_val": "B-for-Y-new", "rank": 2},  # higher rank -> wins
            {"a_val_ref": "X", "b_val": "B-for-X", "rank": 5},      # not reachable: a_val resolved to 'Y'
        ],
    )


def test_duckdb_multiple_sequential_pick_one_joins_compose():
    dataset = _sequential_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_sequential_fixture(executor)
    result = executor.query(model_sql)
    executor.close()

    assert len(result) == 1
    assert result[0]["a_val"] == "Y"
    assert result[0]["b_val"] == "B-for-Y-new"


@requires_postgres
def test_postgres_multiple_sequential_pick_one_joins_compose():
    import psycopg2
    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS rank_b_candidates")
        cur.execute("DROP TABLE IF EXISTS rank_a_candidates")
        cur.execute("DROP TABLE IF EXISTS claims2")
    conn.close()

    dataset = _sequential_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_sequential_fixture(executor)
    result = executor.query(model_sql)
    executor.close()

    assert len(result) == 1
    assert result[0]["a_val"] == "Y"
    assert result[0]["b_val"] == "B-for-Y-new"


# ---------------------------------------------------------------------
# Interaction with DedupRule (contract §6): redundant-but-harmless.
# ---------------------------------------------------------------------

def test_duckdb_pick_one_order_by_with_dedup_source_is_harmless():
    dataset = DatasetSpec(
        name="work_orders",
        fields=[
            FieldSpec(name="wo_id", type="integer"),
            FieldSpec(
                name="requested_by_name", type="string",
                source="partner", source_column="contact_name",
            ),
        ],
        sources=[
            SourceRef(
                name="partner", table="partner_role",
                dedup=DedupRule(partition_by=["wo_id"], order_by=["is_current desc"]),
            ),
        ],
        joins=[
            JoinSpec(
                source="partner",
                on="work_orders.wo_id = partner.wo_id",
                # Redundant with dedup.partition_by == the join key --
                # contract §6: harmless, not rejected.
                pick_one_order_by=["is_current desc"],
            ),
        ],
    )
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    executor.execute_ddl("CREATE TABLE work_orders (wo_id INTEGER)")
    executor.load_rows("work_orders", ["wo_id"], [{"wo_id": "1"}])
    executor.execute_ddl(
        "CREATE TABLE partner_role (wo_id INTEGER, contact_name VARCHAR, is_current VARCHAR)"
    )
    executor.load_rows(
        "partner_role", ["wo_id", "contact_name", "is_current"],
        [
            {"wo_id": "1", "contact_name": "Alice", "is_current": "Y"},
            {"wo_id": "1", "contact_name": "AliceOld", "is_current": "N"},
        ],
    )
    result = executor.query(model_sql)
    executor.close()

    assert len(result) == 1
    assert result[0]["requested_by_name"] == "Alice"


# ---------------------------------------------------------------------
# Interaction with AggregateRule (contract §6): almost always a true
# no-op, since the aggregated CTE is already exactly one row per
# group_by key by construction.
# ---------------------------------------------------------------------

def test_duckdb_pick_one_order_by_with_aggregate_source_is_no_op():
    dataset = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="string"),
            FieldSpec(name="revenue", type="decimal", source="lines", source_column="revenue"),
        ],
        sources=[
            SourceRef(
                name="lines", table="order_lines",
                aggregate=AggregateRule(
                    group_by=["order_id"],
                    aggregates={"revenue": "sum(quantity * unit_price)"},
                ),
            ),
        ],
        joins=[
            JoinSpec(
                source="lines",
                on="orders.order_id = lines.order_id",
                # Matches the aggregate's own group_by -- contract §6:
                # structurally guaranteed to be a no-op.
                pick_one_order_by=["order_id desc"],
            ),
        ],
    )
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    executor.execute_ddl("CREATE TABLE orders (order_id VARCHAR)")
    executor.load_rows("orders", ["order_id"], [{"order_id": "O1"}])
    executor.execute_ddl(
        "CREATE TABLE order_lines (order_id VARCHAR, quantity INTEGER, unit_price DOUBLE)"
    )
    executor.load_rows(
        "order_lines", ["order_id", "quantity", "unit_price"],
        [
            {"order_id": "O1", "quantity": "2", "unit_price": "10.0"},
            {"order_id": "O1", "quantity": "1", "unit_price": "5.0"},
        ],
    )
    result = executor.query(model_sql)
    executor.close()

    assert len(result) == 1  # no fan-out from the (no-op) pick_one_order_by
    assert result[0]["revenue"] == 25.0  # (2 * 10.0) + (1 * 5.0), unaffected by pick_one_order_by


# ---------------------------------------------------------------------
# Real reproduction A: examples/value_experiment/
#
# Collapses the existing two-stage workaround
# (order_status_and_revenue_candidates.yml -> order_status_resolved.yml)
# into the single JoinSpec shown in contract §9A, executed against the
# actual committed CSVs, and diffed against the actual committed
# expected_result_per_order.csv -- a real, not synthetic, regression.
# ---------------------------------------------------------------------

def _value_experiment_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="order_status_and_revenue",
        source_table="orders",
        fields=[
            FieldSpec(name="order_id", type="string", nullable=False),
            FieldSpec(name="customer_id", type="string", nullable=False),
            FieldSpec(name="order_date", type="date", nullable=False),
            FieldSpec(name="status", type="string", source="csh", source_column="status"),
            FieldSpec(name="revenue", type="decimal", source="lines", source_column="revenue"),
        ],
        sources=[
            SourceRef(name="csh", table="customer_status_history"),
            SourceRef(
                name="lines", table="order_lines",
                aggregate=AggregateRule(
                    group_by=["order_id"],
                    aggregates={"revenue": "sum(quantity * unit_price)"},
                ),
            ),
        ],
        joins=[
            JoinSpec(
                source="csh",
                on="csh.customer_id = orders.customer_id and csh.effective_date <= orders.order_date",
                type="left",
                pick_one_order_by=["csh.effective_date desc"],
            ),
            JoinSpec(
                source="lines",
                on="lines.order_id = orders.order_id",
                type="left",
            ),
        ],
    )


def _load_value_experiment_csvs(executor) -> None:
    for table, filename in [
        ("orders", "orders.csv"),
        ("customer_status_history", "customer_status_history.csv"),
        ("order_lines", "order_lines.csv"),
    ]:
        path = VALUE_EXPERIMENT_DIR / filename
        executor.execute_ddl(
            f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto('{path.as_posix()}')"
        )


def _load_expected_value_experiment_results():
    expected = {}
    with open(VALUE_EXPERIMENT_DIR / "expected_result_per_order.csv", newline="") as f:
        for row in csv.DictReader(f):
            expected[row["order_id"]] = row
    return expected


def test_value_experiment_reproduction_matches_expected_output():
    dataset = _value_experiment_dataset()
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_value_experiment_csvs(executor)
    result = executor.query(model_sql)
    executor.close()

    expected = _load_expected_value_experiment_results()
    assert len(result) == len(expected) == 39

    by_order_id = {row["order_id"]: row for row in result}
    assert set(by_order_id) == set(expected)

    for order_id, expected_row in expected.items():
        actual_row = by_order_id[order_id]

        expected_status = expected_row["as_of_status"]
        if expected_status == "UNKNOWN_NO_HISTORY_YET":
            # O032: predates the customer's earliest recorded status --
            # zero qualifying rows, left join, NULL expected (not the
            # ground-truth file's own readability sentinel).
            assert actual_row["status"] is None, order_id
        else:
            assert actual_row["status"] == expected_status, order_id

        assert actual_row["revenue"] == pytest.approx(float(expected_row["order_revenue"])), order_id


# ---------------------------------------------------------------------
# Real reproduction B: hard_insurance_claims fan-out (see module
# docstring for why this uses an inline fixture rather than committed
# CSVs: none exist for this example).
# ---------------------------------------------------------------------

def _hard_insurance_claims_dataset(pick_one: bool) -> DatasetSpec:
    join_kwargs = {}
    if pick_one:
        join_kwargs["pick_one_order_by"] = ["policy_status.effective_date desc"]

    return DatasetSpec(
        name="claim_ledger_summary",
        source_table="CLAIM_HDR",
        fields=[
            FieldSpec(name="claim_id", type="string"),
            FieldSpec(
                name="policy_status_as_of_claim", type="string",
                source="policy_status", source_column="status",
            ),
        ],
        sources=[SourceRef(name="policy_status", table="POLICY_STATUS_HISTORY")],
        joins=[
            JoinSpec(
                source="policy_status",
                on="CLAIM_HDR.policy_id = policy_status.policy_id and policy_status.effective_date <= CLAIM_HDR.claim_date",
                **join_kwargs,
            ),
        ],
    )


def _load_hard_insurance_claims_fixture(executor) -> None:
    executor.execute_ddl(
        "CREATE TABLE CLAIM_HDR (claim_id VARCHAR, policy_id VARCHAR, claim_date DATE)"
    )
    executor.load_rows(
        "CLAIM_HDR", ["claim_id", "policy_id", "claim_date"],
        [
            {"claim_id": "CLM001", "policy_id": "POL001", "claim_date": "2024-06-15"},
            {"claim_id": "CLM002", "policy_id": "POL002", "claim_date": "2024-03-01"},
        ],
    )

    executor.execute_ddl(
        "CREATE TABLE POLICY_STATUS_HISTORY "
        "(policy_id VARCHAR, effective_date DATE, status VARCHAR)"
    )
    executor.load_rows(
        "POLICY_STATUS_HISTORY", ["policy_id", "effective_date", "status"],
        [
            # POL001: two rows both qualify for CLM001's claim_date --
            # this is the exact shape that fans out without pick_one.
            {"policy_id": "POL001", "effective_date": "2024-01-01", "status": "active"},
            {"policy_id": "POL001", "effective_date": "2024-05-01", "status": "lapsed"},
            # POL002: single qualifying row -- unaffected baseline.
            {"policy_id": "POL002", "effective_date": "2024-02-01", "status": "active"},
        ],
    )


def test_hard_insurance_claims_fan_out_reproduced_without_pick_one():
    """
    Negative control: documents the exact failure mechanism this
    feature fixes. The pre-fix join (no pick_one_order_by, matching
    hard_insurance_claims.discovered.yml's actual policy_status join)
    produces two output rows for CLM001 -- a silent duplicate, per the
    finding recorded in docs/FUTURE_WORK.md.
    """
    dataset = _hard_insurance_claims_dataset(pick_one=False)
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_hard_insurance_claims_fixture(executor)
    result = executor.query(model_sql)
    executor.close()

    clm001_rows = [r for r in result if r["claim_id"] == "CLM001"]
    assert len(clm001_rows) == 2  # the bug: one correct row, one stale duplicate


def test_hard_insurance_claims_fan_out_is_fixed_with_pick_one_order_by():
    dataset = _hard_insurance_claims_dataset(pick_one=True)
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_hard_insurance_claims_fixture(executor)
    result = executor.query(model_sql)
    executor.close()

    assert len(result) == 2  # one row per claim, no fan-out

    by_claim_id = {row["claim_id"]: row for row in result}
    assert by_claim_id["CLM001"]["policy_status_as_of_claim"] == "lapsed"  # most recent qualifying row
    assert by_claim_id["CLM002"]["policy_status_as_of_claim"] == "active"
