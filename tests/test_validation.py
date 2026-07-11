import pytest

from structifact.ir import TableSpec, FieldSpec
from structifact.validation import validate_table


def test_valid_table():
    table = TableSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="string"
            )
        ]
    )

    validate_table(table)


def test_unknown_type():
    table = TableSpec(
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
        validate_table(table)


def test_duplicate_field_names():
    table = TableSpec(
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
        validate_table(table)


def test_missing_table_name():
    table = TableSpec(
        name="",
        fields=[
            FieldSpec(
                name="customer_id",
                type="string"
            )
        ]
    )

    with pytest.raises(ValueError):
        validate_table(table)


def test_empty_fields():
    table = TableSpec(
        name="customers",
        fields=[]
    )

    with pytest.raises(ValueError):
        validate_table(table)