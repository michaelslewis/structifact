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
    primary source (knkk) left-joined to a source (bsid) that must be
    pre-aggregated -- summed via a conditional sign-flip, grouped by
    the join keys -- before the join happens.
    """
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
                name="bsid", table="bsid",
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
                name="bsid", table="bsid",
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
                name="bsid", table="bsid",
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

    expected_cte = """bsid as (
    select
        kunnr, kkber,
        SUM(case when shkzg = 'S' then dmbtr when shkzg = 'H' then -dmbtr else 0 end) as struct_bsid_sum_dmbtr
    from bsid
    group by kunnr, kkber
)"""
    assert expected_cte in sql


def test_aggregate_source_field_qualified_by_source_alias():
    sql = _gen().generate(_credit_dataset()).content
    assert "bsid.struct_bsid_sum_dmbtr as struct_bsid_sum_dmbtr" in sql


def test_aggregate_source_with_filter_applies_before_group_by():
    table = _credit_dataset()
    table.sources[0].filter = "mandt = '100'"

    sql = _gen().generate(table).content

    expected_cte = """bsid as (
    select
        kunnr, kkber,
        SUM(case when shkzg = 'S' then dmbtr when shkzg = 'H' then -dmbtr else 0 end) as struct_bsid_sum_dmbtr
    from bsid
        where mandt = '100'
    group by kunnr, kkber
)"""
    assert expected_cte in sql
