import pytest

from structifact.adapters.yaml import load_yaml
from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.validation import validate_table


# --- accepted_values: YAML parsing ---

def test_yaml_adapter_parses_accepted_values(tmp_path):
    yaml_file = tmp_path / "orders.yml"
    yaml_file.write_text(
        """
dataset:
  name: orders

fields:
  - name: status
    type: string
    accepted_values: [pending, shipped, cancelled]
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.fields[0].accepted_values == ["pending", "shipped", "cancelled"]


def test_yaml_adapter_accepted_values_absent_by_default():
    dataset = load_yaml("tests/fixtures/customers.yml")

    assert all(f.accepted_values is None for f in dataset.fields)


def test_yaml_adapter_normalizes_accepted_values_to_strings(tmp_path):
    yaml_file = tmp_path / "orders.yml"
    yaml_file.write_text(
        """
dataset:
  name: orders

fields:
  - name: priority
    type: integer
    accepted_values: [1, 2, 3]
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.fields[0].accepted_values == ["1", "2", "3"]


# --- accepted_values: validation ---

def test_validate_accepts_valid_accepted_values():
    dataset = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="status", type="string", accepted_values=["a", "b"])
        ]
    )

    validate_table(dataset)  # should not raise


def test_validate_rejects_empty_accepted_values_list():
    dataset = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="status", type="string", accepted_values=[])]
    )

    with pytest.raises(ValueError, match="empty accepted_values"):
        validate_table(dataset)


def test_validate_rejects_duplicate_accepted_value():
    dataset = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(
                name="status", type="string",
                accepted_values=["a", "b", "a"]
            )
        ]
    )

    with pytest.raises(ValueError, match="Duplicate accepted_value"):
        validate_table(dataset)


def test_validate_ignores_accepted_values_when_unset():
    dataset = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="status", type="string")]
    )

    validate_table(dataset)  # should not raise


# --- duplicate primary_key detection ---

def test_validate_accepts_single_primary_key():
    dataset = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="customer_id", type="integer")],
        constraints=[
            ConstraintSpec(type="primary_key", columns=["customer_id"])
        ]
    )

    validate_table(dataset)  # should not raise


def test_validate_rejects_multiple_primary_keys():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(name="customer_id", type="integer"),
            FieldSpec(name="email", type="string"),
        ],
        constraints=[
            ConstraintSpec(type="primary_key", columns=["customer_id"]),
            ConstraintSpec(type="primary_key", columns=["email"]),
        ]
    )

    with pytest.raises(ValueError, match="at most one"):
        validate_table(dataset)


def test_validate_accepts_no_primary_key():
    dataset = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="customer_id", type="integer")],
    )

    validate_table(dataset)  # should not raise — primary key is optional
