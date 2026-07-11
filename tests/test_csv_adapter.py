from structifact.adapters.csv import load_csv


def test_load_csv():
    table = load_csv("examples/customers.csv")

    assert table.name == "customers"

    assert len(table.fields) == 2

    assert table.fields[0].name == "customer_id"
    assert table.fields[0].type == "string"

    assert table.fields[1].name == "created_at"
    assert table.fields[1].type == "timestamp"