import pytest

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.validation import validate_table


def test_valid_table():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="string"
            )
        ]
    )

    validate_table(dataset)


def test_unknown_type():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="unknown",
                raw_type="banana"
            )
        ]
    )

    with pytest.raises(ValueError):
        validate_table(dataset)


def test_duplicate_field_names():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="string"
            ),
            FieldSpec(
                name="customer_id",
                type="string"
            )
        ]
    )

    with pytest.raises(ValueError):
        validate_table(dataset)


def test_missing_table_name():
    dataset = DatasetSpec(
        name="",
        fields=[
            FieldSpec(
                name="customer_id",
                type="string"
            )
        ]
    )

    with pytest.raises(ValueError):
        validate_table(dataset)


def test_empty_fields():
    dataset = DatasetSpec(
        name="customers",
        fields=[]
    )

    with pytest.raises(ValueError):
        validate_table(dataset)


def test_valid_primary_key_constraint():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="integer"
            )
        ],
        constraints=[
            ConstraintSpec(
                type="primary_key",
                columns=["customer_id"]
            )
        ]
    )

    validate_table(dataset)


def test_constraint_references_missing_field():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="integer"
            )
        ],
        constraints=[
            ConstraintSpec(
                type="primary_key",
                columns=["missing_column"]
            )
        ]
    )

    with pytest.raises(ValueError):
        validate_table(dataset)


def test_unknown_constraint_type():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="integer"
            )
        ],
        constraints=[
            ConstraintSpec(
                type="unknown_constraint",
                columns=["customer_id"]
            )
        ]
    )

    with pytest.raises(ValueError):
        validate_table(dataset)


def test_constraint_without_columns():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="integer"
            )
        ],
        constraints=[
            ConstraintSpec(
                type="primary_key",
                columns=[]
            )
        ]
    )

    with pytest.raises(ValueError):
        validate_table(dataset)
