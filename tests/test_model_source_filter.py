"""
DatasetSpec.source_filter -- a filter on the *primary* source, found
via real-world use (a real SAP-shaped requirements document, not a
hypothetical): only joined-in sources (SourceRef.filter) could carry
a filter; the primary source had nowhere to express one at all.

The real acceptance case, verified end to end against actual data in
tests/test_model_execution_source_filter.py, is a profit-center-style
dataset: a primary source (CEPC) with its own "current records only"
filter, left-joined to a text/description source (CEPCT) that shares
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

def _profit_center_style_dataset(source_filter="datbi = '9999-12-31'"):
    """
    The real, approved acceptance shape: a primary source (cepc) with
    its own filter, left-joined to a text source (cepct) that shares
    a column name (datbi) with the primary -- the exact real-world
    case that motivated this feature.
    """
    return DatasetSpec(
        name="profit_center",
        source_table="cepc",
        source_filter=source_filter,
        fields=[
            FieldSpec(name="prctr", type="string", source_column="prctr"),
            FieldSpec(
                name="ktext", type="string",
                source="cepct", source_column="ktext",
            ),
        ],
        sources=[
            SourceRef(name="cepct", table="cepct", filter="spras = 'E'"),
        ],
        joins=[
            JoinSpec(source="cepct", on="cepc.prctr = cepct.prctr"),
        ],
    )


def test_source_filter_with_joins_wraps_primary_in_its_own_cte():
    dataset = _profit_center_style_dataset()

    artifact = _gen().generate(dataset)

    expected = """with

cepc as (
    select *
    from cepc
    where datbi = '9999-12-31'
),

cepct as (
    select *
    from cepct
        where spras = 'E'
),

final as (

    select
        cepc.prctr as prctr,
        cepct.ktext as ktext

    from cepc
    left join cepct
        on cepc.prctr = cepct.prctr

)

select * from final;"""

    assert artifact.content == expected


def test_source_filter_primary_cte_comes_before_joined_source_ctes():
    """
    Order matters for readability (and matches how the real reference
    SQL this was scoped against is written) -- the primary source's
    CTE appears first, before any joined-in source CTEs.
    """
    dataset = _profit_center_style_dataset()
    content = _gen().generate(dataset).content

    assert content.index("cepc as (") < content.index("cepct as (")


def test_no_source_filter_with_joins_primary_stays_bare_table_reference():
    """
    Regression: without source_filter, the primary source must remain
    a bare table reference in `from`, not a CTE -- exact pre-existing
    8D v1/v2 behavior, unchanged.
    """
    dataset = _profit_center_style_dataset(source_filter=None)

    content = _gen().generate(dataset).content

    assert "cepc as (" not in content
    assert "from cepc\n" in content


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
