"""
ModelGenerator must generate a real SELECT for a dataset whose ONLY
transformation is renaming columns via `source_column` -- no computed
fields, no sources/joins, no source_filter. Found via real-world use:
a real single-source dataset (every field renamed from its physical
SAP column, e.g. `biz_aufk_mandt` from `mandt`) had exactly this shape
and nothing else, and previously got silently treated as "nothing to
generate" -- which also silently broke `execute --materialize` for
it, since generate_insert() builds on generate().

`_select_line` already qualified/renamed columns correctly whenever
this generator ran; the bug was purely in the "is there anything to
generate at all" gate, not in the SQL-building logic itself -- so
this file only needs to prove that gate, not re-prove qualification
logic already covered elsewhere.
"""

from structifact.ir import DatasetSpec, FieldSpec
from structifact.generators.model import ModelGenerator


def _gen():
    return ModelGenerator()


def test_source_column_alone_is_enough_to_generate_a_model():
    dataset = DatasetSpec(
        name="internal_order_master",
        source_table="aufk",
        fields=[
            FieldSpec(name="biz_aufk_mandt", type="string", source_column="mandt"),
        ],
    )

    artifact = _gen().generate(dataset)
    assert artifact is not None


def test_source_column_alone_produces_correct_renamed_select():
    dataset = DatasetSpec(
        name="internal_order_master",
        source_table="aufk",
        fields=[
            FieldSpec(name="biz_aufk_mandt", type="string", source_column="mandt"),
            FieldSpec(name="biz_aufk_bukrs", type="string", source_column="bukrs"),
        ],
    )

    artifact = _gen().generate(dataset)

    expected = """select
    aufk.mandt as biz_aufk_mandt,
    aufk.bukrs as biz_aufk_bukrs
from aufk;"""

    assert artifact.content == expected


def test_field_matching_its_own_name_does_not_count_as_renaming():
    """
    Regression: a field whose source_column happens to equal its own
    name (the common case -- no rename at all) must not, by itself,
    justify generating a model. Only a genuine rename does.
    """
    dataset = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="integer", source_column="order_id"),
        ],
    )

    assert _gen().generate(dataset) is None


def test_no_renaming_no_computed_no_sources_no_filter_still_returns_none():
    """
    Regression: the original "nothing to generate" case is unchanged
    when none of the four conditions apply.
    """
    dataset = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="integer")],
    )

    assert _gen().generate(dataset) is None


def test_source_column_alone_also_enables_materialization():
    """
    generate_insert() builds on generate() -- confirms the fix flows
    through to materialization too, not just the plain read-only case.
    """
    dataset = DatasetSpec(
        name="internal_order_master",
        source_table="aufk",
        fields=[
            FieldSpec(name="biz_aufk_mandt", type="string", source_column="mandt"),
        ],
    )

    artifact = _gen().generate_insert(dataset)
    assert artifact is not None
    assert "INSERT INTO internal_order_master" in artifact.content
