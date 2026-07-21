from structifact.ir import (
    DatasetSpec,
    FieldSpec,
    ConstraintSpec,
    TableSpec,
)


def test_dataset_spec_construction():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="integer",
            )
        ],
    )

    assert dataset.name == "customers"
    assert len(dataset.fields) == 1
    assert dataset.fields[0].name == "customer_id"


def test_constraint_spec_construction():
    constraint = ConstraintSpec(
        type="primary_key",
        columns=["customer_id"],
    )

    assert constraint.type == "primary_key"
    assert constraint.columns == ["customer_id"]


def test_dataset_spec_constraints_default_empty():
    dataset = DatasetSpec(
        name="customers",
        fields=[],
    )

    assert dataset.constraints == []


def test_table_spec_compatibility_alias():
    dataset = TableSpec(
        name="customers",
        fields=[],
    )

    assert isinstance(dataset, DatasetSpec)
    assert TableSpec is DatasetSpec