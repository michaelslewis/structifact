"""
DatasetSpec.source_filter -- a filter on the *primary* source, found
via real-world use (a real SAP-shaped requirements document, not a
hypothetical): only joined-in sources (SourceRef.filter) could carry
a filter; the primary source had nowhere to express one at all.

The real acceptance case, verified end to end against actual data in
tests/test_model_execution_source_filter.py, is a segment-master-style
dataset: a primary source (SEGMASTER) with its own "current records only"
filter, left-joined to a text/description source (SEGTEXT) that shares
a column name (a "valid to" date) with the primary source -- the
exact real scenario that makes a naive trailing WHERE dangerous, not
just theoretically so. This file covers the unit-level SQL-shape
contract; the linked file proves the shape actually executes
correctly and doesn't hit the ambiguous-column error a naive
implementation would.
"""

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec, SourceRef, JoinSpec
from structifact.validation import validate_table
from structifact.generators.model import ModelGenerator


def _gen():
    return ModelGenerator()


# ---------------------------------------------------------------------
# source_filter alone (no computed fields, no sources/joins)
# ---------------------------------------------------------------------

def test_source_filter_alone_is_enough_to_generate_a_model():
    """
    Mirrors the existing precedent that sources/joins alone (no
    computed fields) still produce a real Artifact, not None -- a
    primary-source filter is exactly the same category of real
    transformation logic.
    """
    dataset = DatasetSpec(
        name="orders",
        source_filter="status = 'ACTIVE'",
        fields=[FieldSpec(name="order_id", type="integer")],
    )

    artifact = _gen().generate(dataset)
    assert artifact is not None


def test_source_filter_alone_produces_trailing_where_no_cte():
    dataset = DatasetSpec(
        name="orders",
        source_filter="status = 'ACTIVE'",
        fields=[FieldSpec(name="order_id", type="integer")],
    )

    artifact = _gen().generate(dataset)

    expected = """select
    orders.order_id as order_id
from orders
where status = 'ACTIVE';"""

    assert artifact.content == expected


def test_no_source_filter_no_sources_joins_unchanged():
    """
    Regression: a plain dataset with none of computed/sources/joins/
    source_filter still returns None, exactly as before this change.
    """
    dataset = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="integer")],
    )

    assert _gen().generate(dataset) is None


def test_no_source_filter_no_sources_joins_no_where_clause():
    """
    Regression: existing simple-form output (computed field, no
    filter, no joins) must not gain a stray WHERE.
    """
    dataset = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(
                name="doubled", type="integer", computed=True,
                expression="order_id * 2",
            ),
        ],
    )

    artifact = _gen().generate(dataset)
    assert "where" not in artifact.content


# ---------------------------------------------------------------------
# source_filter combined with sources/joins -- the CTE-wrapped case
# ---------------------------------------------------------------------

def _segment_master_style_dataset(source_filter="validto = '9999-12-31'"):
    """
    The real, approved acceptance shape: a primary source (segmaster) with
    its own filter, left-joined to a text source (segtext) that shares
    a column name (validto) with the primary -- the exact real-world
    case that motivated this feature.
    """
    return DatasetSpec(
        name="segment_master",
        source_table="segmaster",
        source_filter=source_filter,
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


def test_source_filter_with_joins_wraps_primary_in_its_own_cte():
    dataset = _segment_master_style_dataset()

    artifact = _gen().generate(dataset)

    expected = """with

segmaster as (
    select *
    from segmaster
    where validto = '9999-12-31'
),

segtext as (
    select *
    from segtext
        where langcode = 'E'
),

final as (

    select
        segmaster.segcode as segcode,
        segtext.descrtext as descrtext

    from segmaster
    left join segtext
        on segmaster.segcode = segtext.segcode

)

select * from final;"""

    assert artifact.content == expected


def test_source_filter_primary_cte_comes_before_joined_source_ctes():
    """
    Order matters for readability (and matches how the real reference
    SQL this was scoped against is written) -- the primary source's
    CTE appears first, before any joined-in source CTEs.
    """
    dataset = _segment_master_style_dataset()
    content = _gen().generate(dataset).content

    assert content.index("segmaster as (") < content.index("segtext as (")


def test_no_source_filter_with_joins_primary_stays_bare_table_reference():
    """
    Regression: without source_filter, the primary source must remain
    a bare table reference in `from`, not a CTE -- exact pre-existing
    8D v1/v2 behavior, unchanged.
    """
    dataset = _segment_master_style_dataset(source_filter=None)

    content = _gen().generate(dataset).content

    assert "segmaster as (" not in content
    assert "from segmaster\n" in content


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def test_validate_accepts_valid_source_filter():
    dataset = DatasetSpec(
        name="orders",
        source_filter="status = 'ACTIVE'",
        fields=[FieldSpec(name="order_id", type="integer")],
    )
    validate_table(dataset)  # should not raise


def test_validate_ignores_source_filter_when_unset():
    dataset = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="integer")],
    )
    validate_table(dataset)  # should not raise


def test_validate_rejects_blank_source_filter():
    dataset = DatasetSpec(
        name="orders",
        source_filter="   ",
        fields=[FieldSpec(name="order_id", type="integer")],
    )
    import pytest
    with pytest.raises(ValueError, match="source_filter, if set, cannot be blank"):
        validate_table(dataset)
