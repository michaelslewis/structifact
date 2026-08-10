import pytest

from structifact.ir import DatasetSpec, FieldSpec
from structifact.generators.model import ModelGenerator


def _gen():
    return ModelGenerator()


# ---------------------------------------------------------------------
# No computed fields -> None
# ---------------------------------------------------------------------

def test_no_computed_fields_returns_none():
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
        # This branch should be taken — nothing to write.
        written = False
    else:
        written = True

    assert written is False


# ---------------------------------------------------------------------
# Computed field -> real SELECT expression
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
    assert "qty * unit_price AS gross_amount" in artifact.content


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

    assert artifact.content.startswith("SELECT")
    assert "CREATE TABLE" not in artifact.content


# ---------------------------------------------------------------------
# Non-computed fields -> passthrough via AS
# ---------------------------------------------------------------------

def test_non_computed_field_passes_through_with_as():
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

    assert "order_id AS order_id" in artifact.content


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

    assert "order_id AS order_id" in content
    assert "qty AS qty" in content
    assert "unit_price AS unit_price" in content
    assert "qty * unit_price AS gross_amount" in content


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

    assert "FROM orders;" in artifact.content


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

    assert "FROM stg_orders_raw;" in artifact.content
    assert "FROM orders;" not in artifact.content


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
