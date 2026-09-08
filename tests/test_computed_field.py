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
# Expression identifier resolution (found via a real vertical-slice
# exercise against examples/workorder_demo — see DECISION_HISTORY.md.
# A real, reproduced bug: discover --ai produced an expression
# referencing a field that was never defined anywhere in the dataset
# — structifact validate passed cleanly, and the gap was only found
# by actually generating and executing the SQL. These tests cover the
# check added to catch this at validate time instead.)
# ---------------------------------------------------------------------

def test_expression_referencing_a_known_source_column_passes():
    table = _table([
        FieldSpec(name="qty", type="integer", source_column="qty_raw"),
        FieldSpec(name="unit_price", type="decimal", source_column="price_raw"),
        FieldSpec(
            name="gross_amount", type="decimal", computed=True,
            expression="qty_raw * price_raw",
        ),
    ])
    validate_table(table)  # should not raise


def test_expression_referencing_a_sibling_field_name_passes():
    # A computed field can reference another computed field's own
    # output alias directly (the exact pattern ModelGenerator already
    # relies on — see ir.py's JoinSpec docstring on sibling-alias
    # references), not just raw source_columns.
    table = _table([
        FieldSpec(name="wo_type", type="string", source_column="src_wo_type"),
        FieldSpec(
            name="sign_adjustment", type="integer", computed=True,
            expression="CASE WHEN src_wo_type IN ('CRM') THEN -1 ELSE 1 END",
        ),
        FieldSpec(
            name="amount_lc", type="decimal", computed=True,
            expression="raw_hours * sign_adjustment",
            source_column=None,
        ),
        FieldSpec(name="hours", type="decimal", source_column="raw_hours"),
    ])
    validate_table(table)  # should not raise


def test_expression_with_unknown_identifier_raises():
    # The real bug this check exists to catch: an expression
    # referencing a field name/source_column that isn't defined
    # anywhere in the dataset (examples/workorder_demo's AI-extracted
    # draft referenced `resolved_fx_rate`, which was never declared).
    table = _table([
        FieldSpec(name="qty", type="integer", source_column="qty_raw"),
        FieldSpec(
            name="total", type="decimal", computed=True,
            expression="qty_raw * resolved_fx_rate",
        ),
    ])
    with pytest.raises(ValueError, match="unknown identifier 'resolved_fx_rate'"):
        validate_table(table)


def test_expression_with_qualified_reference_is_never_checked():
    # alias.column (a joined-in source's own raw column, referenced
    # directly per ir.py's JoinSpec docstring) is deliberately outside
    # this check's scope — resolving whether `alias` is a real
    # declared source, or `column` a real column on it, is a
    # source-table-attribution problem this check does not attempt.
    # Neither `fx_rate` nor `rate_to_usd` is declared anywhere in this
    # dataset's fields, and this must still pass.
    table = _table([
        FieldSpec(
            name="resolved_fx_rate", type="decimal", computed=True,
            expression="COALESCE(fx_rate.rate_to_usd, 1.0)",
        ),
    ])
    validate_table(table)  # should not raise


def test_expression_sql_keywords_and_literals_are_not_flagged():
    # CASE/WHEN/THEN/ELSE/END, AND/OR/IN/IS/NULL, COALESCE, and the
    # contents of string literals must never be treated as unresolved
    # identifiers — only real column/field-shaped bare words should be.
    table = _table([
        FieldSpec(name="status", type="string", source_column="status_raw"),
        FieldSpec(
            name="priority", type="string", computed=True,
            expression=(
                "CASE WHEN status_raw IS NULL THEN 'unknown' "
                "WHEN status_raw IN ('urgent', 'high') THEN 'top' "
                "ELSE COALESCE(status_raw, 'none') END"
            ),
        ),
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
