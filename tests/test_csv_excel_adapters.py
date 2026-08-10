"""
Tests for CSV/Excel adapter field parity with the YAML adapter:
role, accepted_values, nullable, computed, expression, depends_on.

Tabular formats (CSV/Excel) have no native boolean or list type, so
these introduce format-specific conventions not needed for YAML:
  - booleans (nullable, computed) are parsed from text
    (true/false/1/0/yes/no, case-insensitive); a genuinely
    unrecognized non-empty value raises ValueError rather than
    silently guessing
  - lists (accepted_values, depends_on) are semicolon-delimited

Excel specifically needs NaN-blank-cell handling: pandas represents
a blank cell as NaN (a float), not None/"", and passing that through
unchanged would silently produce the literal string "nan" instead of
treating the cell as unspecified. This also covers the pre-existing
description bug this fix incidentally corrects.
"""

import csv
import os
import tempfile

import pytest

from structifact.adapters.csv import load_csv
from structifact.adapters.excel import load_excel
from structifact.types import parse_bool, parse_list


# ---------------------------------------------------------------------
# Shared helpers: parse_bool / parse_list
# ---------------------------------------------------------------------

@pytest.mark.parametrize("text", ["true", "True", "TRUE", "1", "yes", "Yes"])
def test_parse_bool_true_tokens(text):
    assert parse_bool(text, field_name="x") is True


@pytest.mark.parametrize("text", ["false", "False", "FALSE", "0", "no", "No"])
def test_parse_bool_false_tokens(text):
    assert parse_bool(text, field_name="x") is False


def test_parse_bool_none_returns_default():
    assert parse_bool(None, field_name="x", default=True) is True
    assert parse_bool(None, field_name="x", default=False) is False


def test_parse_bool_blank_string_returns_default():
    assert parse_bool("", field_name="x", default=True) is True
    assert parse_bool("   ", field_name="x", default=False) is False


def test_parse_bool_unrecognized_raises():
    with pytest.raises(ValueError, match="x.nullable"):
        parse_bool("flase", field_name="x.nullable")


def test_parse_list_none_returns_none():
    assert parse_list(None) is None


def test_parse_list_blank_returns_none():
    assert parse_list("") is None
    assert parse_list("   ") is None


def test_parse_list_splits_and_strips():
    assert parse_list("OPEN; CLOSED ;CANCELLED") == ["OPEN", "CLOSED", "CANCELLED"]


# ---------------------------------------------------------------------
# CSV adapter
# ---------------------------------------------------------------------

def _write_csv(rows, fieldnames):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def test_csv_parses_role_and_accepted_values():
    path = _write_csv(
        [{
            "column_name": "status", "type": "VARCHAR(10)",
            "description": "Order status",
            "role": "dimension", "accepted_values": "OPEN;CLOSED",
        }],
        fieldnames=["column_name", "type", "description", "role", "accepted_values"],
    )
    table = load_csv(path)
    f = table.fields[0]
    assert f.role == "dimension"
    assert f.accepted_values == ["OPEN", "CLOSED"]


def test_csv_parses_nullable_false():
    path = _write_csv(
        [{"column_name": "order_id", "type": "INTEGER", "nullable": "false"}],
        fieldnames=["column_name", "type", "nullable"],
    )
    table = load_csv(path)
    assert table.fields[0].nullable is False


def test_csv_missing_nullable_column_defaults_true():
    path = _write_csv(
        [{"column_name": "order_id", "type": "INTEGER"}],
        fieldnames=["column_name", "type"],
    )
    table = load_csv(path)
    assert table.fields[0].nullable is True


def test_csv_parses_computed_expression_depends_on():
    path = _write_csv(
        [{
            "column_name": "gross_amount", "type": "DECIMAL(15,2)",
            "computed": "true", "expression": "qty * unit_price",
            "depends_on": "qty;unit_price",
        }],
        fieldnames=["column_name", "type", "computed", "expression", "depends_on"],
    )
    table = load_csv(path)
    f = table.fields[0]
    assert f.computed is True
    assert f.expression == "qty * unit_price"
    assert f.depends_on == ["qty", "unit_price"]


def test_csv_unrecognized_boolean_raises_with_field_context():
    path = _write_csv(
        [{"column_name": "order_id", "type": "INTEGER", "nullable": "maybe"}],
        fieldnames=["column_name", "type", "nullable"],
    )
    with pytest.raises(ValueError, match="order_id.nullable"):
        load_csv(path)


# ---------------------------------------------------------------------
# Excel adapter (requires pandas + openpyxl, already a project dep
# for load_excel)
# ---------------------------------------------------------------------

pd = pytest.importorskip("pandas")


def _write_excel(rows):
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def test_excel_parses_role_and_accepted_values():
    path = _write_excel([{
        "column_name": "status", "type": "VARCHAR(10)",
        "description": "Order status",
        "role": "dimension", "accepted_values": "OPEN;CLOSED",
    }])
    table = load_excel(path)
    f = table.fields[0]
    assert f.role == "dimension"
    assert f.accepted_values == ["OPEN", "CLOSED"]


def test_excel_parses_nullable_false():
    path = _write_excel([
        {"column_name": "order_id", "type": "INTEGER", "nullable": "false"}
    ])
    table = load_excel(path)
    assert table.fields[0].nullable is False


def test_excel_blank_optional_cells_do_not_become_literal_nan_string():
    # The core bug this fix addresses: pandas represents a blank cell
    # as NaN, and naive handling turns that into the string "nan".
    # Mixing a row WITH a role value and a row WITHOUT one forces
    # pandas to actually produce NaN for the blank cell (a column
    # that's blank in every row may just be dropped/typed differently).
    path = _write_excel([
        {"column_name": "order_id", "type": "INTEGER", "role": "dimension", "description": "ID"},
        {"column_name": "notes", "type": "VARCHAR(100)", "role": None, "description": None},
    ])
    table = load_excel(path)
    notes = next(f for f in table.fields if f.name == "notes")

    assert notes.role != "nan"
    assert notes.role is None
    assert notes.description != "nan"
    assert notes.description == ""


def test_excel_missing_nullable_column_defaults_true():
    path = _write_excel([{"column_name": "order_id", "type": "INTEGER"}])
    table = load_excel(path)
    assert table.fields[0].nullable is True


def test_excel_parses_computed_expression_depends_on():
    path = _write_excel([{
        "column_name": "gross_amount", "type": "DECIMAL(15,2)",
        "computed": "true", "expression": "qty * unit_price",
        "depends_on": "qty;unit_price",
    }])
    table = load_excel(path)
    f = table.fields[0]
    assert f.computed is True
    assert f.expression == "qty * unit_price"
    assert f.depends_on == ["qty", "unit_price"]
