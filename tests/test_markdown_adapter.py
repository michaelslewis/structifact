"""
Tests for the Markdown adapter: field-level parity with the CSV/Excel
adapters (role, accepted_values, nullable, computed, expression,
depends_on, min_value/max_value, pattern), plus the parsing concerns
unique to a Markdown table -- surrounding prose, no outer pipes, and
an escaped pipe inside a cell -- that CSV/Excel don't have since their
entire file IS the table.
"""

import os
import tempfile

import pytest

from structifact.adapters.markdown import load_markdown
from structifact.types import parse_bool, parse_list


def _write_md(text: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


# ---------------------------------------------------------------------
# Golden-path example
# ---------------------------------------------------------------------

def test_load_markdown():
    table = load_markdown("examples/customers.md")

    assert table.name == "customers"

    assert len(table.fields) == 2

    assert table.fields[0].name == "customer_id"
    assert table.fields[0].type == "string"

    assert table.fields[1].name == "created_at"
    assert table.fields[1].type == "timestamp"


# ---------------------------------------------------------------------
# Field-level parity with CSV/Excel (same cases test_csv_excel_adapters.py
# covers for those two adapters)
# ---------------------------------------------------------------------

def test_markdown_parses_role_and_accepted_values():
    path = _write_md(
        "| column_name | type | description | role | accepted_values |\n"
        "|---|---|---|---|---|\n"
        "| status | VARCHAR(10) | Order status | dimension | OPEN;CLOSED |\n"
    )
    table = load_markdown(path)
    f = table.fields[0]
    assert f.role == "dimension"
    assert f.accepted_values == ["OPEN", "CLOSED"]


def test_markdown_parses_nullable_false():
    path = _write_md(
        "| column_name | type | nullable |\n"
        "|---|---|---|\n"
        "| order_id | INTEGER | false |\n"
    )
    table = load_markdown(path)
    assert table.fields[0].nullable is False


def test_markdown_missing_nullable_column_defaults_true():
    path = _write_md(
        "| column_name | type |\n"
        "|---|---|\n"
        "| order_id | INTEGER |\n"
    )
    table = load_markdown(path)
    assert table.fields[0].nullable is True


def test_markdown_parses_computed_expression_depends_on():
    path = _write_md(
        "| column_name | type | computed | expression | depends_on |\n"
        "|---|---|---|---|---|\n"
        "| gross_amount | DECIMAL(15,2) | true | qty * unit_price | qty;unit_price |\n"
    )
    table = load_markdown(path)
    f = table.fields[0]
    assert f.computed is True
    assert f.expression == "qty * unit_price"
    assert f.depends_on == ["qty", "unit_price"]


def test_markdown_parses_min_max_pattern():
    path = _write_md(
        "| column_name | type | min_value | max_value | pattern |\n"
        "|---|---|---|---|---|\n"
        "| qty | INTEGER | 1 | 100 | ^[0-9]+$ |\n"
    )
    table = load_markdown(path)
    f = table.fields[0]
    assert str(f.min_value) == "1"
    assert str(f.max_value) == "100"
    assert f.pattern == "^[0-9]+$"


def test_markdown_unrecognized_boolean_raises_with_field_context():
    path = _write_md(
        "| column_name | type | nullable |\n"
        "|---|---|---|\n"
        "| order_id | INTEGER | maybe |\n"
    )
    with pytest.raises(ValueError, match="order_id.nullable"):
        load_markdown(path)


# ---------------------------------------------------------------------
# Markdown-specific parsing: table location, pipe styles, escaping
# ---------------------------------------------------------------------

def test_markdown_table_surrounded_by_prose_is_found():
    path = _write_md(
        "# Customers\n"
        "\n"
        "Some introductory notes about this dataset, written by a human,\n"
        "that aren't part of the table at all.\n"
        "\n"
        "| column_name | type | description |\n"
        "|---|---|---|\n"
        "| customer_id | string | Unique customer identifier |\n"
        "\n"
        "Trailing notes after the table.\n"
    )
    table = load_markdown(path)
    assert len(table.fields) == 1
    assert table.fields[0].name == "customer_id"


def test_markdown_table_without_outer_pipes():
    path = _write_md(
        "column_name | type\n"
        "--- | ---\n"
        "customer_id | string\n"
    )
    table = load_markdown(path)
    assert len(table.fields) == 1
    assert table.fields[0].name == "customer_id"
    assert table.fields[0].type == "string"


def test_markdown_escaped_pipe_in_cell():
    path = _write_md(
        "| column_name | type | accepted_values |\n"
        "|---|---|---|\n"
        "| status | string | A\\|B;C |\n"
    )
    table = load_markdown(path)
    assert table.fields[0].accepted_values == ["A|B", "C"]


def test_markdown_no_table_raises():
    path = _write_md("Just some prose. No table here at all.\n")
    with pytest.raises(ValueError, match="No Markdown table found"):
        load_markdown(path)


def test_markdown_table_missing_required_columns_raises():
    path = _write_md(
        "| description |\n"
        "|---|\n"
        "| just a description, no column_name or type |\n"
    )
    with pytest.raises(ValueError, match="column_name"):
        load_markdown(path)
