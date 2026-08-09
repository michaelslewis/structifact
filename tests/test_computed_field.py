"""
Tests for minimal computed-field support (Phase 7 — Transformation
Framework, first step).

Scope, deliberately: FieldSpec can now represent that a field is
computed, with a SQL `expression` and a `depends_on` list of other
field names. This is NOT SQL generation — SQLGenerator is untouched
by this step — and `expression` is assumed-valid SQL, not the
freeform pseudocode `discover --requirements --ai` extracts.
"""

import os
import tempfile

import pytest

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.validation import validate_table
from structifact.adapters.yaml import load_yaml
from structifact.generators.docs import DocsGenerator


# ---------------------------------------------------------------------
# FieldSpec defaults
# ---------------------------------------------------------------------

def test_fieldspec_computed_defaults_to_false():
    f = FieldSpec(name="x", type="integer")
    assert f.computed is False
    assert f.expression is None
    assert f.depends_on is None


# ---------------------------------------------------------------------
# YAML adapter
# ---------------------------------------------------------------------

def _write_yaml(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yml")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


def test_yaml_adapter_parses_computed_field():
    path = _write_yaml("""
dataset:
  name: orders
fields:
  - name: qty
    type: integer
  - name: unit_price
    type: decimal(9,2)
  - name: gross_amount
    type: decimal(15,2)
    computed: true
    expression: "qty * unit_price"
    depends_on: [qty, unit_price]
""")
    table = load_yaml(path)
    gross = next(f for f in table.fields if f.name == "gross_amount")

    assert gross.computed is True
    assert gross.expression == "qty * unit_price"
    assert gross.depends_on == ["qty", "unit_price"]


def test_yaml_adapter_defaults_computed_false_when_absent():
    path = _write_yaml("""
dataset:
  name: orders
fields:
  - name: qty
    type: integer
""")
    table = load_yaml(path)
    assert table.fields[0].computed is False
    assert table.fields[0].depends_on is None


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def _table(fields, constraints=None):
    return DatasetSpec(name="orders", fields=fields, constraints=constraints or [])


def test_valid_computed_field_passes():
    table = _table([
        FieldSpec(name="qty", type="integer"),
        FieldSpec(name="unit_price", type="decimal"),
        FieldSpec(
            name="gross_amount", type="decimal", computed=True,
            expression="qty * unit_price", depends_on=["qty", "unit_price"],
        ),
    ])
    validate_table(table)  # should not raise


def test_computed_true_without_expression_raises():
    table = _table([
        FieldSpec(name="x", type="integer", computed=True),
    ])
    with pytest.raises(ValueError, match="no expression"):
        validate_table(table)


def test_expression_without_computed_true_raises():
    table = _table([
        FieldSpec(name="x", type="integer", expression="1 + 1"),
    ])
    with pytest.raises(ValueError, match="not marked computed"):
        validate_table(table)


def test_depends_on_without_computed_true_raises():
    table = _table([
        FieldSpec(name="a", type="integer"),
        FieldSpec(name="x", type="integer", depends_on=["a"]),
    ])
    with pytest.raises(ValueError, match="not marked computed"):
        validate_table(table)


def test_depends_on_unknown_field_raises():
    table = _table([
        FieldSpec(
            name="x", type="integer", computed=True,
            expression="y + 1", depends_on=["y"],
        ),
    ])
    with pytest.raises(ValueError, match="unknown field 'y'"):
        validate_table(table)


def test_self_referential_depends_on_raises():
    table = _table([
        FieldSpec(
            name="x", type="integer", computed=True,
            expression="x + 1", depends_on=["x"],
        ),
    ])
    with pytest.raises(ValueError, match="own depends_on"):
        validate_table(table)


def test_depends_on_forward_reference_is_valid():
    # A computed field can depend on a field declared LATER in the
    # same file — the two-pass validation (build field_names fully,
    # then check dependencies) must allow this.
    table = _table([
        FieldSpec(
            name="gross_amount", type="decimal", computed=True,
            expression="qty * unit_price", depends_on=["qty", "unit_price"],
        ),
        FieldSpec(name="qty", type="integer"),
        FieldSpec(name="unit_price", type="decimal"),
    ])
    validate_table(table)  # should not raise


# ---------------------------------------------------------------------
# Docs rendering
# ---------------------------------------------------------------------

def test_docs_renders_computed_field_details():
    table = _table([
        FieldSpec(name="qty", type="integer"),
        FieldSpec(name="unit_price", type="decimal"),
        FieldSpec(
            name="gross_amount", type="decimal", computed=True,
            expression="qty * unit_price", depends_on=["qty", "unit_price"],
        ),
    ])
    content = DocsGenerator().generate(table).content

    assert "**Computed:** Yes" in content
    assert "**Expression:** `qty * unit_price`" in content
    assert "**Depends on:** qty, unit_price" in content


def test_docs_omits_computed_section_for_non_computed_field():
    table = _table([FieldSpec(name="qty", type="integer")])
    content = DocsGenerator().generate(table).content

    assert "**Computed:**" not in content
    assert "**Expression:**" not in content
    assert "**Depends on:**" not in content
