from decimal import Decimal

import pytest

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.validation import validate_table
from structifact.quality import check_data


def _bounded_field(min_value=None, max_value=None, type_="decimal", nullable=True):
    return FieldSpec(
        name="discount_pct", type=type_, nullable=nullable,
        min_value=Decimal(str(min_value)) if min_value is not None else None,
        max_value=Decimal(str(max_value)) if max_value is not None else None,
    )


def _patterned_field(pattern, type_="string", nullable=True):
    return FieldSpec(name="order_id", type=type_, nullable=nullable, pattern=pattern)


# ---------------------------------------------------------------------
# Metadata validation: range well-formedness
# ---------------------------------------------------------------------

def test_min_value_on_non_numeric_type_fails_validation():
    table = DatasetSpec(
        name="t",
        fields=[FieldSpec(name="x", type="string", min_value=Decimal("0"))],
    )
    with pytest.raises(ValueError, match="does not support range validation"):
        validate_table(table)


def test_max_value_on_non_numeric_type_fails_validation():
    table = DatasetSpec(
        name="t",
        fields=[FieldSpec(name="x", type="string", max_value=Decimal("10"))],
    )
    with pytest.raises(ValueError, match="does not support range validation"):
        validate_table(table)


def test_min_greater_than_max_fails_validation():
    table = DatasetSpec(
        name="t",
        fields=[FieldSpec(
            name="x", type="integer",
            min_value=Decimal("10"), max_value=Decimal("5"),
        )],
    )
    with pytest.raises(ValueError, match="greater than max_value"):
        validate_table(table)


def test_min_only_passes_validation():
    table = DatasetSpec(
        name="t",
        fields=[FieldSpec(name="x", type="integer", min_value=Decimal("0"))],
    )
    validate_table(table)  # should not raise


def test_max_only_passes_validation():
    table = DatasetSpec(
        name="t",
        fields=[FieldSpec(name="x", type="integer", max_value=Decimal("100"))],
    )
    validate_table(table)  # should not raise


def test_valid_range_on_decimal_passes_validation():
    table = DatasetSpec(
        name="t",
        fields=[FieldSpec(
            name="x", type="decimal",
            min_value=Decimal("0"), max_value=Decimal("1"),
        )],
    )
    validate_table(table)  # should not raise


# ---------------------------------------------------------------------
# Metadata validation: pattern well-formedness
# ---------------------------------------------------------------------

def test_pattern_on_non_string_type_fails_validation():
    table = DatasetSpec(
        name="t",
        fields=[FieldSpec(name="x", type="integer", pattern="^[0-9]+$")],
    )
    with pytest.raises(ValueError, match="does not support pattern validation"):
        validate_table(table)


def test_invalid_regex_fails_validation():
    table = DatasetSpec(
        name="t",
        fields=[FieldSpec(name="x", type="string", pattern="[")],
    )
    with pytest.raises(ValueError, match="invalid pattern"):
        validate_table(table)


def test_valid_pattern_passes_validation():
    table = DatasetSpec(
        name="t",
        fields=[FieldSpec(name="x", type="string", pattern="^ORD-[0-9]+$")],
    )
    validate_table(table)  # should not raise


# ---------------------------------------------------------------------
# check_data: range checking
# ---------------------------------------------------------------------

def test_value_within_bounds_is_not_flagged():
    table = DatasetSpec(name="t", fields=[_bounded_field(0, 1)])
    rows = [{"discount_pct": "0.5"}]
    result = check_data(table, rows)
    assert result.is_valid is True


def test_value_at_inclusive_boundary_is_not_flagged():
    table = DatasetSpec(name="t", fields=[_bounded_field(0, 1)])
    rows = [{"discount_pct": "0"}, {"discount_pct": "1"}]
    result = check_data(table, rows)
    assert result.is_valid is True


def test_value_just_above_max_is_flagged():
    table = DatasetSpec(name="t", fields=[_bounded_field(0, 1)])
    rows = [{"discount_pct": "1.01"}]
    result = check_data(table, rows)
    range_issues = [i for i in result.issues if i.rule == "range"]
    assert len(range_issues) == 1
    assert range_issues[0].value == "1.01"
    assert range_issues[0].rows == [1]


def test_value_just_below_min_is_flagged():
    table = DatasetSpec(name="t", fields=[_bounded_field(0, 1)])
    rows = [{"discount_pct": "-0.01"}]
    result = check_data(table, rows)
    range_issues = [i for i in result.issues if i.rule == "range"]
    assert len(range_issues) == 1


def test_min_only_flags_below_but_not_above():
    table = DatasetSpec(name="t", fields=[_bounded_field(min_value=0)])
    rows = [{"discount_pct": "-1"}, {"discount_pct": "1000"}]
    result = check_data(table, rows)
    range_issues = [i for i in result.issues if i.rule == "range"]
    assert len(range_issues) == 1
    assert range_issues[0].rows == [1]


def test_max_only_flags_above_but_not_below():
    table = DatasetSpec(name="t", fields=[_bounded_field(max_value=1)])
    rows = [{"discount_pct": "-1000"}, {"discount_pct": "2"}]
    result = check_data(table, rows)
    range_issues = [i for i in result.issues if i.rule == "range"]
    assert len(range_issues) == 1
    assert range_issues[0].rows == [2]


def test_missing_value_not_flagged_as_range_violation():
    table = DatasetSpec(name="t", fields=[_bounded_field(0, 1, nullable=True)])
    rows = [{"discount_pct": ""}]
    result = check_data(table, rows)
    assert result.is_valid is True


def test_unparseable_value_not_flagged_as_range_violation():
    """
    The deliberate v2 boundary: a present-but-non-numeric value is
    NOT reported as a range violation. Type validation is a separate,
    future rule.
    """
    table = DatasetSpec(name="t", fields=[_bounded_field(0, 1)])
    rows = [{"discount_pct": "banana"}]
    result = check_data(table, rows)
    assert result.is_valid is True


def test_range_uses_decimal_precision_not_float():
    """
    0.1 + 0.2 != 0.3 in float, but should compare cleanly as Decimal.
    A bound of exactly 0.3 should not spuriously flag a value of
    0.3 due to float artifacts.
    """
    table = DatasetSpec(name="t", fields=[_bounded_field(min_value="0.3", max_value="0.3")])
    rows = [{"discount_pct": "0.3"}]
    result = check_data(table, rows)
    assert result.is_valid is True


def test_multiple_rows_same_out_of_range_value_grouped():
    table = DatasetSpec(name="t", fields=[_bounded_field(0, 1)])
    rows = [{"discount_pct": "5"}, {"discount_pct": "5"}]
    result = check_data(table, rows)
    range_issues = [i for i in result.issues if i.rule == "range"]
    assert len(range_issues) == 1
    assert range_issues[0].rows == [1, 2]


# ---------------------------------------------------------------------
# check_data: pattern checking
# ---------------------------------------------------------------------

def test_matching_pattern_is_not_flagged():
    table = DatasetSpec(name="t", fields=[_patterned_field("^ORD-[0-9]+$")])
    rows = [{"order_id": "ORD-1001"}]
    result = check_data(table, rows)
    assert result.is_valid is True


def test_non_matching_pattern_is_flagged():
    table = DatasetSpec(name="t", fields=[_patterned_field("^ORD-[0-9]+$")])
    rows = [{"order_id": "BADID"}]
    result = check_data(table, rows)
    pattern_issues = [i for i in result.issues if i.rule == "pattern"]
    assert len(pattern_issues) == 1
    assert pattern_issues[0].value == "BADID"
    assert pattern_issues[0].rows == [1]


def test_pattern_uses_fullmatch_not_search():
    """
    A pattern without explicit ^/$ should still require the whole
    value to match, not merely contain a match somewhere.
    """
    table = DatasetSpec(name="t", fields=[_patterned_field("ORD-[0-9]+")])
    rows = [{"order_id": "XXORD-1001"}]  # contains a match, but isn't one
    result = check_data(table, rows)
    pattern_issues = [i for i in result.issues if i.rule == "pattern"]
    assert len(pattern_issues) == 1


def test_missing_value_not_flagged_as_pattern_violation():
    table = DatasetSpec(name="t", fields=[_patterned_field("^ORD-[0-9]+$", nullable=True)])
    rows = [{"order_id": ""}]
    result = check_data(table, rows)
    assert result.is_valid is True


def test_multiple_rows_same_bad_pattern_value_grouped():
    table = DatasetSpec(name="t", fields=[_patterned_field("^ORD-[0-9]+$")])
    rows = [{"order_id": "BADID"}, {"order_id": "BADID"}]
    result = check_data(table, rows)
    pattern_issues = [i for i in result.issues if i.rule == "pattern"]
    assert len(pattern_issues) == 1
    assert pattern_issues[0].rows == [1, 2]


# ---------------------------------------------------------------------
# Full extended example (orders_data v2): all five rule types together
# ---------------------------------------------------------------------

def test_full_extended_example_all_rule_types():
    table = DatasetSpec(
        name="orders_data",
        fields=[
            FieldSpec(name="order_id", type="string", nullable=False,
                       pattern="^ORD-[0-9]+$"),
            FieldSpec(name="customer_id", type="string", nullable=False),
            FieldSpec(name="order_type", type="string", nullable=False,
                       accepted_values=["STD", "RET", "CRM"]),
            FieldSpec(name="quantity", type="integer", nullable=False),
            FieldSpec(name="discount_pct", type="decimal", nullable=True,
                       min_value=Decimal("0"), max_value=Decimal("1")),
        ],
        constraints=[ConstraintSpec(type="primary_key", columns=["order_id"])],
    )

    rows = [
        {"order_id": "ORD-1001", "customer_id": "CUST-1", "order_type": "STD", "quantity": "5", "discount_pct": "0.1"},
        {"order_id": "ORD-1002", "customer_id": "CUST-2", "order_type": "RET", "quantity": "2", "discount_pct": "0"},
        {"order_id": "", "customer_id": "CUST-3", "order_type": "STD", "quantity": "3", "discount_pct": "0"},
        {"order_id": "ORD-1002", "customer_id": "CUST-4", "order_type": "CRM", "quantity": "1", "discount_pct": "0"},
        {"order_id": "ORD-1005", "customer_id": "CUST-2", "order_type": "XYZ", "quantity": "4", "discount_pct": "0"},
        {"order_id": "ORD-1006", "customer_id": "CUST-5", "order_type": "STD", "quantity": "", "discount_pct": "0"},
        {"order_id": "ORD-1007", "customer_id": "CUST-3", "order_type": "RET", "quantity": "2", "discount_pct": "1.5"},
        {"order_id": "BADID", "customer_id": "CUST-9", "order_type": "STD", "quantity": "3", "discount_pct": "0.05"},
    ]

    result = check_data(table, rows)

    rules_found = {i.rule for i in result.issues}
    assert rules_found == {"required", "uniqueness", "accepted_values", "range", "pattern"}

    assert len([i for i in result.issues if i.rule == "required"]) == 2
    assert len([i for i in result.issues if i.rule == "uniqueness"]) == 1
    assert len([i for i in result.issues if i.rule == "accepted_values"]) == 1
    assert len([i for i in result.issues if i.rule == "range"]) == 1
    assert len([i for i in result.issues if i.rule == "pattern"]) == 1
