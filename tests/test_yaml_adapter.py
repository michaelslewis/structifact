from structifact.adapters.yaml import load_yaml


def test_load_yaml():
    table = load_yaml("examples/customers.yml")

    assert table.name == "customers"

    assert len(table.fields) == 2

    assert table.fields[0].name == "customer_id"
    assert table.fields[0].type == "string"

    assert table.fields[1].name == "created_at"
    assert table.fields[1].type == "timestamp"