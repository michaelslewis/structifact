"""
Tests for ModelGenerator's base (no sources/joins) behavior:
computed-field expressions, non-computed passthrough, the None
contract, and source_table fallback/override.

Sources/joins/dedup behavior (the bigger sources/joins milestone) is
covered separately in tests/test_model_sources_joins.py.

Note: as of the sources/joins milestone, ModelGenerator qualifies
every non-computed field with its source alias (previously it did
not), and its SQL keywords are lowercase (previously "SELECT"/"AS").
This is a deliberate output change — existing metadata remains valid
and semantically equivalent, but generated SQL now looks like
`orders.order_id as order_id` instead of `order_id AS order_id`.
"""

from structifact.ir import DatasetSpec, FieldSpec
from structifact.generators.model import ModelGenerator


def _gen():
    return ModelGenerator()


# ---------------------------------------------------------------------
# No computed fields, no sources/joins -> None
# ---------------------------------------------------------------------

def test_no_computed_fields_no_sources_returns_none():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(name="customer_id", type="integer"),
        ],
    )

    result = _gen().generate(table)

    assert result is None


def test_none_return_does_not_crash_cli_style_loop():
    """
    Mirrors how cli.py's generate() consumes a generator's output:
    it must be safe to check `if artifact is None: continue` without
    ever touching `.filename`/`.content` on a None result.
    """
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="integer")],
    )

    artifact = _gen().generate(table)

    if artifact is None:
        written = False
    else:
        written = True

    assert written is False


# ---------------------------------------------------------------------
# Computed field -> real SELECT expression, unqualified
# ---------------------------------------------------------------------

def test_computed_field_emits_expression_in_select():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="qty", type="integer"),
            FieldSpec(name="unit_price", type="decimal"),
            FieldSpec(
                name="gross_amount", type="decimal", computed=True,
                expression="qty * unit_price",
            ),
        ],
    )

    artifact = _gen().generate(table)

    assert artifact is not None
    assert "qty * unit_price as gross_amount" in artifact.content


def test_computed_field_output_is_select_not_create_table():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="qty", type="integer"),
            FieldSpec(
                name="doubled", type="integer", computed=True,
                expression="qty * 2",
            ),
        ],
    )

    artifact = _gen().generate(table)

    assert artifact.content.startswith("select")
    assert "CREATE TABLE" not in artifact.content


# ---------------------------------------------------------------------
# Non-computed fields -> qualified passthrough
# ---------------------------------------------------------------------

def test_non_computed_field_qualified_with_primary_source():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(
                name="doubled", type="integer", computed=True,
                expression="order_id * 2",
            ),
        ],
    )

    artifact = _gen().generate(table)

    assert "orders.order_id as order_id" in artifact.content


def test_mixed_fields_all_appear_in_select_list():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(name="qty", type="integer"),
            FieldSpec(name="unit_price", type="decimal"),
            FieldSpec(
                name="gross_amount", type="decimal", computed=True,
                expression="qty * unit_price",
            ),
        ],
    )

    artifact = _gen().generate(table)
    content = artifact.content

    assert "orders.order_id as order_id" in content
    assert "orders.qty as qty" in content
    assert "orders.unit_price as unit_price" in content
    assert "qty * unit_price as gross_amount" in content


# ---------------------------------------------------------------------
# source_table override vs fallback to dataset name
# ---------------------------------------------------------------------

def test_falls_back_to_dataset_name_when_source_table_unset():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="qty", type="integer"),
            FieldSpec(
                name="doubled", type="integer", computed=True,
                expression="qty * 2",
            ),
        ],
    )

    artifact = _gen().generate(table)

    assert "from orders;" in artifact.content


def test_uses_explicit_source_table_when_set():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="qty", type="integer"),
            FieldSpec(
                name="doubled", type="integer", computed=True,
                expression="qty * 2",
            ),
        ],
        source_table="stg_orders_raw",
    )

    artifact = _gen().generate(table)

    assert "from stg_orders_raw;" in artifact.content
    assert "stg_orders_raw.qty as qty" in artifact.content
    assert "from orders;" not in artifact.content


# ---------------------------------------------------------------------
# Filename / artifact shape
# ---------------------------------------------------------------------

def test_output_filename_matches_dataset_name_model_pattern():
    table = DatasetSpec(
        name="customer_summary",
        fields=[
            FieldSpec(name="customer_id", type="integer"),
            FieldSpec(
                name="lifetime_value", type="decimal", computed=True,
                expression="sum(order_total)",
            ),
        ],
    )

    artifact = _gen().generate(table)

    assert artifact.filename == "customer_summary_model.sql"


def test_generator_name_is_model():
    assert ModelGenerator().name == "model"
