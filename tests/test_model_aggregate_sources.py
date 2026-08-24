import pytest

from structifact.ir import (
    DatasetSpec, FieldSpec, SourceRef, JoinSpec, DedupRule, AggregateRule,
)
from structifact.validation import validate_table
from structifact.generators.model import ModelGenerator


def _gen():
    return ModelGenerator()


def _credit_dataset():
    """
    The minimal real-world contract this was scoped against (see
    DECISION_HISTORY.md's third real-world-validation entry): a
    primary source (credctrl) left-joined to a source (openitem) that must be
    pre-aggregated -- summed via a conditional sign-flip, grouped by
    the join keys -- before the join happens.
    """
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


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def test_dedup_and_aggregate_together_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[
            SourceRef(
                name="customers", table="cust_mst",
                dedup=DedupRule(partition_by=["customer_id"], order_by=["updated_at desc"]),
                aggregate=AggregateRule(group_by=["customer_id"], aggregates={"total": "SUM(amount)"}),
            ),
        ],
    )

    with pytest.raises(ValueError, match="both a dedup rule and an aggregate rule"):
        validate_table(table)


def test_aggregate_with_empty_group_by_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[
            SourceRef(
                name="openitem", table="openitem",
                aggregate=AggregateRule(group_by=[], aggregates={"total": "SUM(amount)"}),
            ),
        ],
    )

    with pytest.raises(ValueError, match="empty group_by"):
        validate_table(table)


def test_aggregate_with_no_aggregates_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[
            SourceRef(
                name="openitem", table="openitem",
                aggregate=AggregateRule(group_by=["customer_id"], aggregates={}),
            ),
        ],
    )

    with pytest.raises(ValueError, match="no aggregates declared"):
        validate_table(table)


def test_aggregate_with_blank_expression_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[
            SourceRef(
                name="openitem", table="openitem",
                aggregate=AggregateRule(group_by=["customer_id"], aggregates={"total": ""}),
            ),
        ],
    )

    with pytest.raises(ValueError, match="blank expression"):
        validate_table(table)


def test_valid_aggregate_rule_passes_validation():
    validate_table(_credit_dataset())


# ---------------------------------------------------------------------
# Generated SQL shape
# ---------------------------------------------------------------------

def test_aggregate_source_produces_grouped_cte():
    sql = _gen().generate(_credit_dataset()).content

    expected_cte = """openitem as (
    select
        custid, ctrlarea,
        SUM(case when dcind = 'S' then amtlocal when dcind = 'H' then -amtlocal else 0 end) as struct_openitem_sum_amtlocal
    from openitem
    group by custid, ctrlarea
)"""
    assert expected_cte in sql


def test_aggregate_source_field_qualified_by_source_alias():
    sql = _gen().generate(_credit_dataset()).content
    assert "openitem.struct_openitem_sum_amtlocal as struct_openitem_sum_amtlocal" in sql


def test_aggregate_source_with_filter_applies_before_group_by():
    table = _credit_dataset()
    table.sources[0].filter = "clientid = '100'"

    sql = _gen().generate(table).content

    expected_cte = """openitem as (
    select
        custid, ctrlarea,
        SUM(case when dcind = 'S' then amtlocal when dcind = 'H' then -amtlocal else 0 end) as struct_openitem_sum_amtlocal
    from openitem
        where clientid = '100'
    group by custid, ctrlarea
)"""
    assert expected_cte in sql
