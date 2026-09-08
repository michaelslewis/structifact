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
from structifact.adapters.yaml import load_yaml


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


# ---------------------------------------------------------------------
# Join-risk warning: a non-equality `on` condition correlated with
# another known source, but no pick_one_order_by (found via a real
# investigation comparing two independently-discovered "as-of" bugs --
# examples/value_experiment and examples/coverage_round1's
# hard_insurance_claims; see docs/PICK_ONE_ORDER_BY_CONTRACT.md).
# Deliberately a WARNING (validate_table's return value), never a
# validation failure -- see test_known_false_positive_still_warns
# below for exactly why it can't be a hard error.
# ---------------------------------------------------------------------

def test_correlated_inequality_without_pick_one_order_by_warns():
    table = DatasetSpec(
        name="claims",
        source_table="CLAIM_HDR",
        fields=[FieldSpec(name="claim_id", type="string")],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(
                source="policy_status",
                on="CLAIM_HDR.policy_id = policy_status.policy_id and policy_status.effective_date <= CLAIM_HDR.claim_date",
            ),
        ],
    )

    warnings = validate_table(table)

    assert len(warnings) == 1
    assert "policy_status" in warnings[0]
    assert "pick_one_order_by" in warnings[0]


def test_correlated_inequality_with_pick_one_order_by_does_not_warn():
    # Identical join condition to the test above -- only difference is
    # pick_one_order_by is set, which is exactly the fix
    # docs/PICK_ONE_ORDER_BY_CONTRACT.md §9B specifies for this case.
    table = DatasetSpec(
        name="claims",
        source_table="CLAIM_HDR",
        fields=[FieldSpec(name="claim_id", type="string")],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(
                source="policy_status",
                on="CLAIM_HDR.policy_id = policy_status.policy_id and policy_status.effective_date <= CLAIM_HDR.claim_date",
                pick_one_order_by=["policy_status.effective_date desc"],
            ),
        ],
    )

    assert validate_table(table) == []


def test_ordinary_equality_join_never_warns():
    # The overwhelming common case -- a join that only ever references
    # the primary source via plain equality must never warn, or this
    # would fire on nearly every join in the codebase.
    table = DatasetSpec(
        name="orders",
        source_table="WO_HDR",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[SourceRef(name="lines", table="WO_LINE")],
        joins=[
            JoinSpec(source="lines", on="WO_HDR.wo_id = lines.wo_id"),
        ],
    )

    assert validate_table(table) == []


def test_known_false_positive_still_warns():
    # examples/value_experiment/order_status_and_revenue_candidates.yml
    # is a real, already-shipped, deliberately-uncollapsed intermediate
    # dataset in an older pipeline (a *different* dataset later
    # collapses its fan-out) -- not a bug, but structurally
    # indistinguishable from one using only this dataset's own IR.
    # This is accepted, known noise, not something this check tries to
    # eliminate -- asserted here explicitly so it's a documented
    # trade-off, not a silent gap.
    table = load_yaml("examples/value_experiment/order_status_and_revenue_candidates.yml")

    warnings = validate_table(table)

    assert len(warnings) == 1
    assert "csh" in warnings[0]


def test_inequality_referencing_only_the_joined_sources_own_alias_does_not_warn():
    # The inequality must correlate with ANOTHER known source, not
    # just any inequality anywhere in `on` -- a (contrived) condition
    # comparing the joined source only to itself must not warn.
    table = DatasetSpec(
        name="claims",
        source_table="CLAIM_HDR",
        fields=[FieldSpec(name="claim_id", type="string")],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(
                source="policy_status",
                on="policy_status.start_date <= policy_status.end_date",
            ),
        ],
    )

    assert validate_table(table) == []


def test_join_risk_warning_never_raises_or_blocks_other_errors():
    # A dataset with both a real error and the join-risk pattern still
    # raises for the real error -- warnings never mask or replace
    # errors, and never themselves become one.
    table = DatasetSpec(
        name="claims",
        source_table="CLAIM_HDR",
        fields=[FieldSpec(name="claim_id", type="bogus_type")],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(
                source="policy_status",
                on="CLAIM_HDR.policy_id = policy_status.policy_id and policy_status.effective_date <= CLAIM_HDR.claim_date",
            ),
        ],
    )

    with pytest.raises(ValueError, match="Unsupported type 'bogus_type'"):
        validate_table(table)
