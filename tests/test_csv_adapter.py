import tempfile

import pytest

from structifact.adapters.csv import load_csv


def test_load_csv():
    table = load_csv("examples/customers.csv")

    assert table.name == "customers"

    assert len(table.fields) == 2

    assert table.fields[0].name == "customer_id"
    assert table.fields[0].type == "string"

    assert table.fields[1].name == "created_at"
    assert table.fields[1].type == "timestamp"


# ---------------------------------------------------------------------
# Raw-data CSV vs. metadata CSV (real bug: a raw-data CSV -- any real
# user's CSV export, not a contrived example -- previously crashed
# with a bare KeyError on the first data row, since a metadata CSV
# (column_name, type, ...) and a raw-data CSV look identical by
# extension alone. Reproduced against two unrelated real fixtures
# before this fix; both now checked here directly.
# ---------------------------------------------------------------------

def test_load_csv_raises_clear_error_for_raw_data_csv():
    with pytest.raises(ValueError) as excinfo:
        load_csv("tests/fixtures/raw_customers.csv")

    message = str(excinfo.value)
    assert "does not appear to be a Structifact metadata CSV" in message
    assert "column_name" in message
    assert "type" in message
    assert "structifact discover" in message


def test_load_csv_raises_clear_error_for_messy_orders_fixture():
    # The exact file the original crash was reported against.
    with pytest.raises(ValueError) as excinfo:
        load_csv("tests/fixtures/messy_orders.csv")

    assert "does not appear to be a Structifact metadata CSV" in str(excinfo.value)


def test_load_csv_header_only_wrong_columns_now_raises_instead_of_silently_succeeding():
    # Found alongside the crash: a CSV with the wrong header and ZERO
    # data rows never even reached the KeyError -- the row loop body
    # simply never ran, so this previously returned an empty,
    # zero-field DatasetSpec with no error or warning at all. Checking
    # the header up front (not the first row) catches this too.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("order_id,customer_email\n")
        path = f.name

    with pytest.raises(ValueError) as excinfo:
        load_csv(path)

    assert "does not appear to be a Structifact metadata CSV" in str(excinfo.value)


def test_load_csv_error_names_only_the_columns_actually_missing():
    # column_name present, type missing -- confirms the message is
    # precise about which one(s) are absent, not just a blanket "both
    # are missing" regardless of the real header.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("column_name,description\n")
        f.write("customer_id,Unique customer identifier\n")
        path = f.name

    with pytest.raises(ValueError) as excinfo:
        load_csv(path)

    message = str(excinfo.value)
    assert "Missing: type" in message
    assert "column_name" not in message.split("Missing:")[1]
