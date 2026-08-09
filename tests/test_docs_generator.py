"""
Tests for DocsGenerator (Phase 5 — Documentation Generation).

Covers: minimal fields (only required attributes) render without
fabricated placeholders for absent optional metadata; fully-populated
fields render every present attribute; dataset-level description and
constraints are included when present, omitted when not; decimal
precision/scale and varchar length both render via the same type
display; and the generator is correctly wired into the registry as
optional (not default) output.
"""

import pytest

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.generators.docs import DocsGenerator
from structifact.generators.registry import (
    GENERATORS, OPTIONAL_GENERATORS, ALL_GENERATORS,
)


def _gen():
    return DocsGenerator()


def test_filename_matches_dataset_name():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])
    artifact = _gen().generate(table)
    assert artifact.filename == "customers.md"


def test_minimal_field_omits_absent_optional_metadata():
    # Only name/type set — everything else (role, accepted_values,
    # raw_type, description) is None/default. None of those lines
    # should appear; nothing should be fabricated.
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="customer_id", type="integer")],
    )

    content = _gen().generate(table).content

    assert "### customer_id" in content
    assert "**Type:** integer" in content
    assert "**Nullable:** Yes" in content  # FieldSpec defaults nullable=True
    assert "**Role:**" not in content
    assert "**Accepted values:**" not in content
    assert "**Declared as:**" not in content


def test_fully_populated_field_renders_all_present_attributes():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(
                name="status",
                type="string",
                raw_type="VARCHAR(10)",
                description="Current order status",
                role="dimension",
                length=10,
                accepted_values=["OPEN", "CLOSED", "CANCELLED"],
                nullable=False,
            )
        ],
    )

    content = _gen().generate(table).content

    assert "**Type:** string(10)" in content
    assert "**Declared as:** VARCHAR(10)" in content
    assert "**Role:** dimension" in content
    assert "**Nullable:** No" in content
    assert "`OPEN`, `CLOSED`, `CANCELLED`" in content
    assert "Current order status" in content


def test_decimal_field_shows_precision_and_scale():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="unit_price", type="decimal", precision=9, scale=2)],
    )

    content = _gen().generate(table).content

    assert "**Type:** decimal(9,2)" in content


def test_dataset_description_included_when_present():
    table = DatasetSpec(
        name="customers",
        description="Customer master data.",
        fields=[FieldSpec(name="id", type="integer")],
    )

    content = _gen().generate(table).content

    assert "Customer master data." in content


def test_dataset_description_omitted_when_absent():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])

    content = _gen().generate(table).content

    lines = content.splitlines()
    # Second line (after the "# customers" title) should go straight
    # to a blank line then "## Fields" — no stray description text.
    assert lines[0] == "# customers"
    assert "## Fields" in content


def test_constraints_included_when_present():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="integer")],
        constraints=[ConstraintSpec(type="primary_key", columns=["order_id"])],
    )

    content = _gen().generate(table).content

    assert "## Constraints" in content
    assert "**primary_key**: order_id" in content


def test_constraints_section_omitted_when_absent():
    table = DatasetSpec(name="orders", fields=[FieldSpec(name="order_id", type="integer")])

    content = _gen().generate(table).content

    assert "## Constraints" not in content


def test_no_fabricated_computed_logic_section():
    # FieldSpec has no computed/computed_logic_raw attribute at all —
    # this just documents that expectation so a future FieldSpec
    # change doesn't silently start fabricating a section here.
    table = DatasetSpec(name="orders", fields=[FieldSpec(name="net_amount", type="decimal")])

    content = _gen().generate(table).content

    assert "computed" not in content.lower()
    assert "logic" not in content.lower()


def test_docs_generator_is_optional_not_default():
    default_names = {g.name for g in GENERATORS}
    optional_names = {g.name for g in OPTIONAL_GENERATORS}
    all_names = {g.name for g in ALL_GENERATORS}

    assert "docs" not in default_names
    assert "docs" in optional_names
    assert "docs" in all_names
