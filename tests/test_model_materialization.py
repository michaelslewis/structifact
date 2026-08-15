"""
Phase 8D, v3 -- materializes ModelGenerator's output into a real
target table, closing the gap 8D v1/v2 deliberately left open
(read-only proof only). The full chain now proven end to end:

    DatasetSpec -> SQLGenerator -> CREATE TABLE target (...)
                -> ModelGenerator.generate_insert()
                -> INSERT INTO target (...) SELECT ...
                -> Executor -> persisted target

Typed INSERT INTO ... SELECT was chosen over CREATE TABLE ... AS
SELECT specifically so the target's types and constraints stay
controlled by Structifact's own declared metadata rather than being
inferred by the engine from the query result -- verified directly
below (test_..._enforces_declared_primary_key_not_engine_inferred).

Reuses Executor.execute_ddl() as-is for the INSERT statement -- no
new Executor method, no rename. Deliberately NO CLI exposure in this
slice, matching 8D v1/v2's exact precedent.

A real, load-bearing design constraint surfaced during investigation:
source_table defaults to the dataset's own `name` when unset, which
is exactly what 8D v1/v2's original fixtures did. Materializing into
a table also named `dataset.name` while reading from a relation of
that same name is a self-referential collision -- every fixture here
therefore sets source_table (and, for the joined case, each source's
table) to a genuinely distinct relation name, the same pattern any
real ELT pipeline already uses (raw/staging vs. final table names).
This is enforced by generate_insert() as a materialization-specific
precondition (see model.py), not a general DatasetSpec validation
rule -- a model reading from its own dataset name may be legitimate
outside of materializing it.

Real PostgreSQL tests here follow the existing convention: gated on
STRUCTIFACT_TEST_POSTGRES_DSN, skip cleanly when unset.
"""

import os
from decimal import Decimal

import pytest

from structifact.ir import (
    DatasetSpec, FieldSpec, ConstraintSpec, SourceRef, DedupRule, JoinSpec,
)
from structifact.generators.model import ModelGenerator
from structifact.generators.sql import SQLGenerator
from structifact.executors.duckdb import DuckDBExecutor

POSTGRES_DSN = os.environ.get("STRUCTIFACT_TEST_POSTGRES_DSN")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="STRUCTIFACT_TEST_POSTGRES_DSN not set — no real PostgreSQL server configured",
)


# ---------------------------------------------------------------------
# Fixtures: 8D v1/v2's exact datasets, now with distinct source_table
# ---------------------------------------------------------------------

# order_id -> (quantity, unit_price, expected line_total)
ORDER_ITEMS_ROWS = [
    (1, 2, "10.50", "21.00"),
    (2, 3, "7.25", "21.75"),
    (3, 5, "4.00", "20.00"),
]


def _order_items_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="order_items",
        source_table="raw_order_items",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(name="quantity", type="integer"),
            FieldSpec(name="unit_price", type="decimal", precision=10, scale=2),
            FieldSpec(
                name="line_total", type="decimal", precision=15, scale=2,
                computed=True, expression="quantity * unit_price",
            ),
        ],
        constraints=[ConstraintSpec(type="primary_key", columns=["order_id"])],
    )


PARTNER_ROLE_ROWS = [
    (1, "REQ", "Alice Old", "N", "2024-01-01"),
    (1, "REQ", "Alice Current", "Y", "2024-01-05"),
    (1, "BILL", "Alice Billing", "Y", "2024-01-05"),
    (2, "REQ", "Bob Older", "N", "2024-01-01"),
    (2, "REQ", "Bob Newer", "N", "2024-01-10"),
    # wo_id=3 has no partner_role rows at all.
]

EXPECTED_REQUESTED_BY = {1: "Alice Current", 2: "Bob Newer", 3: None}


def _work_order_source_dataset() -> DatasetSpec:
    return DatasetSpec(
        name="work_order_source",
        source_table="raw_work_order_source",
        fields=[
            FieldSpec(name="wo_id", type="integer"),
            FieldSpec(
                name="requested_by_name", type="string",
                source="partner_requested_by", source_column="contact_name",
            ),
        ],
        sources=[
            SourceRef(
                name="partner_requested_by", table="partner_role",
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
                on="raw_work_order_source.wo_id = partner_requested_by.wo_id",
            ),
        ],
    )


# ---------------------------------------------------------------------
# generate_insert(): unit-level contract (no database involved)
# ---------------------------------------------------------------------

def test_generate_insert_produces_expected_sql_shape():
    dataset = _order_items_dataset()
    artifact = ModelGenerator().generate_insert(dataset)

    assert artifact.content.startswith(
        "INSERT INTO order_items (order_id, quantity, unit_price, line_total)\n"
    )
    assert "quantity * unit_price as line_total" in artifact.content
    assert "from raw_order_items" in artifact.content


def test_generate_insert_returns_none_when_nothing_to_materialize():
    dataset = DatasetSpec(
        name="plain",
        fields=[FieldSpec(name="id", type="integer")],
    )
    assert ModelGenerator().generate_insert(dataset) is None


def test_generate_insert_raises_on_primary_source_target_collision():
    """
    source_table unset -> falls back to dataset.name -> the model
    reads from a relation of the same name it would materialize into.
    """
    dataset = DatasetSpec(
        name="order_items",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(
                name="line_total", type="decimal", computed=True,
                expression="quantity * unit_price",
            ),
        ],
    )

    with pytest.raises(ValueError, match="reads from a relation of the same name"):
        ModelGenerator().generate_insert(dataset)


def test_generate_insert_raises_on_joined_source_target_collision():
    """
    source_table is set correctly, but a JOINED source's table
    collides with the target -- the invariant covers every relation
    the SELECT reads from, not just the primary one.
    """
    dataset = DatasetSpec(
        name="work_order_source",
        source_table="raw_work_order_source",
        fields=[
            FieldSpec(name="wo_id", type="integer"),
            FieldSpec(
                name="requested_by_name", type="string",
                source="partner_requested_by", source_column="contact_name",
            ),
        ],
        sources=[
            SourceRef(name="partner_requested_by", table="work_order_source"),
        ],
        joins=[
            JoinSpec(
                source="partner_requested_by",
                on="raw_work_order_source.wo_id = partner_requested_by.wo_id",
            ),
        ],
    )

    with pytest.raises(ValueError, match="reads from a relation of the same name"):
        ModelGenerator().generate_insert(dataset)


# ---------------------------------------------------------------------
# Real end-to-end materialization: computed-field case (order_items)
# ---------------------------------------------------------------------

def _load_raw_order_items(executor, rows=ORDER_ITEMS_ROWS) -> None:
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


def _materialize(executor, dataset) -> None:
    ddl_sql = SQLGenerator().generate(dataset).content
    insert_sql = ModelGenerator().generate_insert(dataset).content

    with executor.transaction():
        executor.execute_ddl(ddl_sql)
        executor.execute_ddl(insert_sql)


def _assert_correct_persisted_line_totals(executor, table_name="order_items") -> None:
    result = executor.query(f"SELECT * FROM {table_name}")
    by_order_id = {row["order_id"]: row["line_total"] for row in result}
    assert len(by_order_id) == len(ORDER_ITEMS_ROWS)

    for order_id, _, _, expected in ORDER_ITEMS_ROWS:
        actual = Decimal(str(by_order_id[order_id]))
        assert actual == Decimal(expected), (
            f"order_id={order_id}: expected {expected}, got {actual}"
        )


def test_duckdb_materializes_computed_field_with_correct_persisted_values():
    dataset = _order_items_dataset()

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_order_items(executor)

    _materialize(executor, dataset)
    _assert_correct_persisted_line_totals(executor)

    # Target schema comes from Structifact's SQLGenerator DDL, not
    # engine type inference: the declared primary_key constraint must
    # actually be enforced on the persisted table, which a bare
    # CREATE TABLE ... AS SELECT would not have given us for free.
    with pytest.raises(Exception):
        executor.execute_ddl(
            "INSERT INTO order_items (order_id, quantity, unit_price, line_total) "
            "VALUES (1, 99, 1.00, 99.00)"
        )

    executor.close()


@requires_postgres
def test_postgres_materializes_computed_field_with_correct_persisted_values():
    import psycopg2

    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS order_items")
        cur.execute("DROP TABLE IF EXISTS raw_order_items")
    conn.close()

    dataset = _order_items_dataset()

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_raw_order_items(executor)

    _materialize(executor, dataset)
    _assert_correct_persisted_line_totals(executor)

    with pytest.raises(Exception):
        executor.execute_ddl(
            "INSERT INTO order_items (order_id, quantity, unit_price, line_total) "
            "VALUES (1, 99, 1.00, 99.00)"
        )

    executor.close()


# ---------------------------------------------------------------------
# Real end-to-end materialization: sources/joins/dedup case
# ---------------------------------------------------------------------

def _load_raw_work_order_tables(executor) -> None:
    executor.execute_ddl("CREATE TABLE raw_work_order_source (wo_id INTEGER)")
    executor.load_rows(
        "raw_work_order_source", ["wo_id"], [{"wo_id": "1"}, {"wo_id": "2"}, {"wo_id": "3"}],
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
                "wo_id": str(wo_id), "role_code": role_code, "contact_name": contact_name,
                "is_current": is_current, "updated_at": updated_at,
            }
            for wo_id, role_code, contact_name, is_current, updated_at in PARTNER_ROLE_ROWS
        ],
    )


def _assert_correct_persisted_requested_by(executor) -> None:
    result = executor.query("SELECT * FROM work_order_source")
    by_wo_id = {row["wo_id"]: row["requested_by_name"] for row in result}
    assert by_wo_id == EXPECTED_REQUESTED_BY


def test_duckdb_materializes_sources_joins_with_correct_persisted_values():
    dataset = _work_order_source_dataset()

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_work_order_tables(executor)

    _materialize(executor, dataset)
    _assert_correct_persisted_requested_by(executor)

    executor.close()


@requires_postgres
def test_postgres_materializes_sources_joins_with_correct_persisted_values():
    import psycopg2

    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS work_order_source")
        cur.execute("DROP TABLE IF EXISTS raw_work_order_source")
        cur.execute("DROP TABLE IF EXISTS partner_role")
    conn.close()

    dataset = _work_order_source_dataset()

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_raw_work_order_tables(executor)

    _materialize(executor, dataset)
    _assert_correct_persisted_requested_by(executor)

    executor.close()


# ---------------------------------------------------------------------
# Atomicity: a failed materialization leaves no target table at all,
# building directly on transaction() (Phase 8C-v1) -- CREATE and
# INSERT are one atomic unit, matching how cli.py's execute() already
# wraps DROP/CREATE/load.
# ---------------------------------------------------------------------

def test_duckdb_failed_materialization_leaves_no_target_table():
    dataset = _order_items_dataset()

    executor = DuckDBExecutor()
    executor.connect()
    # A genuine duplicate order_id in the raw data -> a real
    # primary-key violation when materialized, not a simulated one.
    _load_raw_order_items(executor, rows=ORDER_ITEMS_ROWS + [(1, 1, "1.00", "1.00")])

    with pytest.raises(Exception):
        _materialize(executor, dataset)

    with pytest.raises(Exception):
        executor.query("SELECT * FROM order_items")

    executor.close()


@requires_postgres
def test_postgres_failed_materialization_leaves_no_target_table():
    import psycopg2

    from structifact.executors.postgres import PostgresExecutor

    conn = psycopg2.connect(dsn=POSTGRES_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS order_items")
        cur.execute("DROP TABLE IF EXISTS raw_order_items")
    conn.close()

    dataset = _order_items_dataset()

    executor = PostgresExecutor()
    executor.connect(connection=POSTGRES_DSN)
    _load_raw_order_items(executor, rows=ORDER_ITEMS_ROWS + [(1, 1, "1.00", "1.00")])

    with pytest.raises(Exception):
        _materialize(executor, dataset)

    with pytest.raises(Exception):
        executor.query("SELECT * FROM order_items")

    executor.close()
