import pytest

from structifact.ir import DatasetSpec, FieldSpec
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