"""
Unit/fragment-level tests for JoinSpec.pick_one_order_by
(docs/PICK_ONE_ORDER_BY_CONTRACT.md) -- SQL-shape and validation
assertions only. Real execution against DuckDB/PostgreSQL, including
both real-world reproductions, lives in
test_model_execution_pick_one_order_by.py, matching the existing split
between test_model_sources_joins.py and
test_model_execution_sources_joins.py.
"""

import pytest

from structifact.ir import (
    DatasetSpec, FieldSpec, SourceRef, DedupRule, AggregateRule, JoinSpec,
)
from structifact.validation import validate_table
from structifact.generators.model import ModelGenerator


def _gen():
    return ModelGenerator()


# ---------------------------------------------------------------------
# SQL shape
# ---------------------------------------------------------------------

def test_pick_one_join_renders_left_join_lateral():
    table = DatasetSpec(
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
                on="claims.policy_id = policy_status.policy_id and policy_status.effective_date <= claims.claim_date",
                pick_one_order_by=["policy_status.effective_date desc"],
            ),
        ],
    )

    content = _gen().generate(table).content

    assert "left join lateral (" in content
    assert "        select *\n" in content
    assert "        from policy_status\n" in content
    assert "        where claims.policy_id = policy_status.policy_id and policy_status.effective_date <= claims.claim_date\n" in content
    assert "        order by policy_status.effective_date desc\n" in content
    assert "        limit 1\n" in content
    assert "    ) as policy_status on true" in content
    # The plain, non-LATERAL "on" clause form must NOT appear.
    assert "\n        on claims.policy_id" not in content


def test_pick_one_join_renders_inner_join_lateral():
    table = DatasetSpec(
        name="claims",
        fields=[FieldSpec(name="claim_id", type="string")],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(
                source="policy_status",
                on="claims.policy_id = policy_status.policy_id",
                type="inner",
                pick_one_order_by=["policy_status.effective_date desc"],
            ),
        ],
    )

    content = _gen().generate(table).content
    assert "inner join lateral (" in content
    assert "left join lateral" not in content


def test_multiple_pick_one_order_by_entries_join_with_commas():
    table = DatasetSpec(
        name="claims",
        fields=[FieldSpec(name="claim_id", type="string")],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(
                source="policy_status",
                on="claims.policy_id = policy_status.policy_id",
                pick_one_order_by=["effective_date desc", "updated_at desc"],
            ),
        ],
    )

    content = _gen().generate(table).content
    assert "order by effective_date desc, updated_at desc" in content


def test_plain_join_unaffected_by_pick_one_order_by_default():
    """
    Backward compatibility (contract §7): a join with
    pick_one_order_by left as the None default must produce the exact
    pre-existing fragment, asserted directly rather than only inferred
    from other tests continuing to pass.
    """
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="string"),
            FieldSpec(
                name="customer_name", type="string",
                source="customers", source_column="name",
            ),
        ],
        sources=[SourceRef(name="customers", table="cust_mst")],
        joins=[
            JoinSpec(
                source="customers",
                on="orders.customer_id = customers.customer_id",
            ),
        ],
    )

    content = _gen().generate(table).content
    assert "    left join customers\n        on orders.customer_id = customers.customer_id" in content
    assert "lateral" not in content


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def _base_table(pick_one_order_by):
    return DatasetSpec(
        name="claims",
        fields=[FieldSpec(name="claim_id", type="string")],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(
                source="policy_status",
                on="claims.policy_id = policy_status.policy_id",
                pick_one_order_by=pick_one_order_by,
            ),
        ],
    )


def test_pick_one_order_by_non_list_fails_validation():
    table = _base_table("effective_date desc")  # a bare string, not a list

    with pytest.raises(ValueError, match="pick_one_order_by that is not a list"):
        validate_table(table)


def test_pick_one_order_by_empty_list_fails_validation():
    table = _base_table([])

    with pytest.raises(ValueError, match="empty pick_one_order_by"):
        validate_table(table)


def test_pick_one_order_by_blank_entry_fails_validation():
    table = _base_table(["effective_date desc", "   "])

    with pytest.raises(ValueError, match="blank pick_one_order_by entry"):
        validate_table(table)


def test_pick_one_order_by_valid_passes_validation():
    table = _base_table(["effective_date desc"])
    validate_table(table)  # should not raise


def test_pick_one_order_by_none_passes_validation_unchanged():
    table = _base_table(None)
    validate_table(table)  # should not raise


# ---------------------------------------------------------------------
# Coexistence with DedupRule / AggregateRule (contract §6) -- valid,
# not rejected, no new validation rule for the interaction itself.
# ---------------------------------------------------------------------

def test_pick_one_order_by_coexists_with_dedup_without_validation_error():
    table = DatasetSpec(
        name="claims",
        fields=[FieldSpec(name="claim_id", type="string")],
        sources=[
            SourceRef(
                name="claimant", table="party_role",
                filter="role_code = 'CLAIMANT'",
                dedup=DedupRule(
                    partition_by=["claim_id"],
                    order_by=["is_current desc"],
                ),
            ),
        ],
        joins=[
            JoinSpec(
                source="claimant",
                on="claims.claim_id = claimant.claim_id",
                pick_one_order_by=["is_current desc"],
            ),
        ],
    )

    validate_table(table)  # should not raise


def test_pick_one_order_by_coexists_with_aggregate_without_validation_error():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
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
                pick_one_order_by=["order_id desc"],
            ),
        ],
    )

    validate_table(table)  # should not raise
