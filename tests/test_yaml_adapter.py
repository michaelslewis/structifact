from structifact.adapters.yaml import load_yaml
from pathlib import Path


def test_load_yaml():
    table = load_yaml("examples/customers.yml")

    assert table.name == "customers"
    assert table.fields[0].name == "customer_id"
    assert table.fields[1].name == "created_at"
    assert table.fields[1].type == "timestamp"


def test_load_dataset_yaml(tmp_path: Path):
    metadata = tmp_path / "customers.yml"
    metadata.write_text(
        """
dataset:
  name: customers
  description: Customer master data

fields:
  - name: customer_id
    type: integer

constraints:
  - type: primary_key
    columns:
      - customer_id
"""
    )

    dataset = load_yaml(str(metadata))

    assert dataset.name == "customers"
    assert dataset.description == "Customer master data"
    assert len(dataset.fields) == 1
    assert dataset.fields[0].name == "customer_id"

    assert len(dataset.constraints) == 1
    assert dataset.constraints[0].type == "primary_key"
    assert dataset.constraints[0].columns == ["customer_id"]


def test_load_legacy_table_yaml(tmp_path: Path):
    metadata = tmp_path / "customers.yml"
    metadata.write_text(
        """
table: customers

fields:
  - name: customer_id
    type: integer
"""
    )

    dataset = load_yaml(str(metadata))

    assert dataset.name == "customers"
    assert dataset.description is None
    assert dataset.constraints == []