from pathlib import Path

from structifact.adapters.yaml import load_yaml

def test_load_yaml_dataset_format():
    dataset = load_yaml("examples/customers.yml")

    assert dataset.name == "customers"

    assert len(dataset.fields) == 2

    assert dataset.fields[0].name == "customer_id"
    assert dataset.fields[0].type == "integer"

    assert dataset.fields[1].name == "created_at"
    assert dataset.fields[1].type == "timestamp"


def test_load_yaml_dataset_format(tmp_path):
    yaml_file = tmp_path / "customers.yml"

    yaml_file.write_text(
        """
dataset:
  name: customers
  description: Customer master data

fields:
  - name: customer_id
    type: integer
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.name == "customers"
    assert dataset.description == "Customer master data"

    assert len(dataset.fields) == 1
    assert dataset.fields[0].name == "customer_id"


def test_load_yaml_constraints(tmp_path):
    yaml_file = tmp_path / "customers.yml"

    yaml_file.write_text(
        """
dataset:
  name: customers

fields:
  - name: customer_id
    type: integer

constraints:
  - type: primary_key
    columns:
      - customer_id
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert len(dataset.constraints) == 1

    constraint = dataset.constraints[0]

    assert constraint.type == "primary_key"
    assert constraint.columns == ["customer_id"]