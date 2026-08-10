import pytest

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.validation import validate_table
from structifact.generators.sql import SQLGenerator


def _dataset(constraints):
    """Minimal two-field dataset for constraint-focused tests."""
    return DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="integer", nullable=False),
            FieldSpec(name="customer_id", type="integer"),
            FieldSpec(name="quantity", type="integer"),
        ],
        constraints=constraints,
    )


# ---------------------------------------------------------------------
# foreign_key validation
# ---------------------------------------------------------------------

def test_foreign_key_valid_passes_validation():
    table = _dataset([
        ConstraintSpec(
            type="foreign_key",
            columns=["customer_id"],
            target_table="customers",
            target_column="customer_id",
        )
    ])

    # Should not raise.
    validate_table(table)


def test_foreign_key_missing_target_table_fails():
    table = _dataset([
        ConstraintSpec(
            type="foreign_key",
            columns=["customer_id"],
            target_table=None,
            target_column="customer_id",
        )
    ])

    with pytest.raises(ValueError, match="target_table"):
        validate_table(table)


def test_foreign_key_missing_target_column_fails():
    table = _dataset([
        ConstraintSpec(
            type="foreign_key",
            columns=["customer_id"],
            target_table="customers",
            target_column=None,
        )
    ])

    with pytest.raises(ValueError, match="target_column"):
        validate_table(table)


def test_foreign_key_composite_columns_rejected():
    table = _dataset([
        ConstraintSpec(
            type="foreign_key",
            columns=["order_id", "customer_id"],
            target_table="customers",
            target_column="customer_id",
        )
    ])

    with pytest.raises(ValueError, match="exactly one column"):
        validate_table(table)


def test_foreign_key_unknown_column_fails():
    table = _dataset([
        ConstraintSpec(
            type="foreign_key",
            columns=["not_a_real_field"],
            target_table="customers",
            target_column="customer_id",
        )
    ])

    with pytest.raises(ValueError, match="unknown field"):
        validate_table(table)


# ---------------------------------------------------------------------
# check validation
# ---------------------------------------------------------------------

def test_check_valid_expression_passes_validation():
    table = _dataset([
        ConstraintSpec(
            type="check",
            columns=[],
            expression="quantity > 0",
        )
    ])

    # Should not raise.
    validate_table(table)


def test_check_missing_expression_fails():
    table = _dataset([
        ConstraintSpec(
            type="check",
            columns=[],
            expression=None,
        )
    ])

    with pytest.raises(ValueError, match="check constraint requires an expression"):
        validate_table(table)


def test_check_empty_expression_fails():
    table = _dataset([
        ConstraintSpec(
            type="check",
            columns=[],
            expression="",
        )
    ])

    with pytest.raises(ValueError, match="check constraint requires an expression"):
        validate_table(table)


def test_check_does_not_require_columns():
    """
    Unlike primary_key/unique/foreign_key, a check constraint with an
    empty columns list should not trigger the generic
    "requires columns" error — the expression is what matters.
    """
    table = _dataset([
        ConstraintSpec(
            type="check",
            columns=[],
            expression="quantity > 0",
        )
    ])

    # Should not raise, and specifically should not raise a
    # "requires columns" error.
    validate_table(table)


# ---------------------------------------------------------------------
# primary_key / unique regression (unaffected by this change)
# ---------------------------------------------------------------------

def test_primary_key_and_unique_still_require_columns():
    table = _dataset([
        ConstraintSpec(type="primary_key", columns=[]),
    ])

    with pytest.raises(ValueError, match="requires columns"):
        validate_table(table)


# ---------------------------------------------------------------------
# SQL generation
# ---------------------------------------------------------------------

def test_sql_generator_emits_foreign_key():
    table = _dataset([
        ConstraintSpec(
            type="foreign_key",
            columns=["customer_id"],
            target_table="customers",
            target_column="customer_id",
        )
    ])

    artifact = SQLGenerator().generate(table)

    assert "FOREIGN KEY (customer_id) REFERENCES customers (customer_id)" in artifact.content


def test_sql_generator_emits_check():
    table = _dataset([
        ConstraintSpec(
            type="check",
            columns=[],
            expression="quantity > 0",
        )
    ])

    artifact = SQLGenerator().generate(table)

    assert "CHECK (quantity > 0)" in artifact.content


def test_sql_generator_emits_both_fk_and_check_together():
    table = _dataset([
        ConstraintSpec(
            type="foreign_key",
            columns=["customer_id"],
            target_table="customers",
            target_column="customer_id",
        ),
        ConstraintSpec(
            type="check",
            columns=[],
            expression="quantity > 0",
        ),
    ])

    artifact = SQLGenerator().generate(table)

    assert "FOREIGN KEY (customer_id) REFERENCES customers (customer_id)" in artifact.content
    assert "CHECK (quantity > 0)" in artifact.content


def test_sql_generator_still_emits_primary_key_and_unique():
    """Regression check: existing constraint types unaffected."""
    table = _dataset([
        ConstraintSpec(type="primary_key", columns=["order_id"]),
        ConstraintSpec(type="unique", columns=["customer_id"]),
    ])

    artifact = SQLGenerator().generate(table)

    assert "PRIMARY KEY (order_id)" in artifact.content
    assert "UNIQUE (customer_id)" in artifact.content
