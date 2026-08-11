from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.quality import check_data, QualityResult, QualityIssue


def _orders_schema():
    return DatasetSpec(
        name="orders_data",
        fields=[
            FieldSpec(name="order_id", type="string", nullable=False),
            FieldSpec(name="customer_id", type="string", nullable=False),
            FieldSpec(
                name="order_type", type="string", nullable=False,
                accepted_values=["STD", "RET", "CRM"],
            ),
            FieldSpec(name="quantity", type="integer", nullable=False),
            FieldSpec(name="discount_pct", type="decimal", nullable=True),
        ],
        constraints=[
            ConstraintSpec(type="primary_key", columns=["order_id"]),
        ],
    )


def _clean_row(order_id="ORD-1", customer_id="CUST-1", order_type="STD",
                quantity="5", discount_pct=""):
    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "order_type": order_type,
        "quantity": quantity,
        "discount_pct": discount_pct,
    }


# ---------------------------------------------------------------------
# All-valid dataset
# ---------------------------------------------------------------------

def test_all_valid_data_is_valid():
    table = _orders_schema()
    rows = [
        _clean_row(order_id="ORD-1"),
        _clean_row(order_id="ORD-2"),
        _clean_row(order_id="ORD-3"),
    ]

    result = check_data(table, rows)

    assert result.is_valid is True
    assert result.issues == []


def test_rows_checked_is_correct():
    table = _orders_schema()
    rows = [_clean_row(order_id=f"ORD-{i}") for i in range(7)]

    result = check_data(table, rows)

    assert result.rows_checked == 7


def test_empty_dataset_is_valid():
    table = _orders_schema()

    result = check_data(table, [])

    assert result.rows_checked == 0
    assert result.is_valid is True
    assert result.issues == []


# ---------------------------------------------------------------------
# Required-field (nullable: false) violations
# ---------------------------------------------------------------------

def test_required_field_blank_is_flagged():
    table = _orders_schema()
    rows = [
        _clean_row(order_id="ORD-1"),
        _clean_row(order_id=""),  # data row 2
        _clean_row(order_id="ORD-3"),
    ]

    result = check_data(table, rows)

    required_issues = [i for i in result.issues if i.rule == "required"]
    assert len(required_issues) == 1
    assert required_issues[0].field == "order_id"
    assert required_issues[0].rows == [2]


def test_required_field_missing_key_entirely_is_flagged():
    """
    DictReader returns None (not "") for a row with fewer columns
    than the header — both count as missing.
    """
    table = _orders_schema()
    rows = [
        _clean_row(order_id="ORD-1"),
        {"order_id": None, "customer_id": "CUST-1", "order_type": "STD",
         "quantity": "1", "discount_pct": ""},
    ]

    result = check_data(table, rows)

    required_issues = [i for i in result.issues if i.rule == "required"]
    assert required_issues[0].rows == [2]


def test_nullable_field_can_legitimately_be_blank():
    table = _orders_schema()
    rows = [_clean_row(order_id="ORD-1", discount_pct="")]

    result = check_data(table, rows)

    assert result.is_valid is True


# ---------------------------------------------------------------------
# Uniqueness (primary_key / unique constraint) violations
# ---------------------------------------------------------------------

def test_duplicate_primary_key_is_flagged_grouped():
    table = _orders_schema()
    rows = [
        _clean_row(order_id="ORD-1002"),  # data row 1
        _clean_row(order_id="ORD-1003"),  # data row 2
        _clean_row(order_id="ORD-1002"),  # data row 3 — dup of row 1
    ]

    result = check_data(table, rows)

    uniqueness_issues = [i for i in result.issues if i.rule == "uniqueness"]
    assert len(uniqueness_issues) == 1
    assert uniqueness_issues[0].field == "order_id"
    assert uniqueness_issues[0].value == "ORD-1002"
    assert uniqueness_issues[0].rows == [1, 3]


def test_multiple_duplicate_occurrences_grouped_into_one_issue():
    table = _orders_schema()
    rows = [
        _clean_row(order_id="ORD-1"),
        _clean_row(order_id="ORD-1"),
        _clean_row(order_id="ORD-1"),
        _clean_row(order_id="ORD-2"),
    ]

    result = check_data(table, rows)

    uniqueness_issues = [i for i in result.issues if i.rule == "uniqueness"]
    assert len(uniqueness_issues) == 1
    assert uniqueness_issues[0].rows == [1, 2, 3]


def test_missing_primary_key_values_do_not_produce_uniqueness_errors():
    table = _orders_schema()
    rows = [
        _clean_row(order_id=""),  # data row 1 — missing, required-owned
        _clean_row(order_id=""),  # data row 2 — also missing
    ]

    result = check_data(table, rows)

    uniqueness_issues = [i for i in result.issues if i.rule == "uniqueness"]
    assert uniqueness_issues == []

    required_issues = [i for i in result.issues if i.rule == "required"]
    assert required_issues[0].rows == [1, 2]


def test_no_duplicates_produces_no_uniqueness_issue():
    table = _orders_schema()
    rows = [_clean_row(order_id="ORD-1"), _clean_row(order_id="ORD-2")]

    result = check_data(table, rows)

    assert [i for i in result.issues if i.rule == "uniqueness"] == []


# ---------------------------------------------------------------------
# accepted_values violations
# ---------------------------------------------------------------------

def test_accepted_values_violation_is_flagged():
    table = _orders_schema()
    rows = [
        _clean_row(order_id="ORD-1", order_type="STD"),
        _clean_row(order_id="ORD-2", order_type="XYZ"),  # data row 2
    ]

    result = check_data(table, rows)

    av_issues = [i for i in result.issues if i.rule == "accepted_values"]
    assert len(av_issues) == 1
    assert av_issues[0].field == "order_type"
    assert av_issues[0].value == "XYZ"
    assert av_issues[0].rows == [2]


def test_accepted_values_ignores_missing_value_on_nullable_field():
    # order_type is required in this schema, so use a case where the
    # accepted_values field is independently nullable to confirm
    # missing values are skipped by the accepted_values check itself
    # (not merely caught first by a required check).
    table = DatasetSpec(
        name="t",
        fields=[
            FieldSpec(
                name="status", type="string", nullable=True,
                accepted_values=["OPEN", "CLOSED"],
            ),
        ],
    )
    rows = [{"status": ""}]

    result = check_data(table, rows)

    assert result.is_valid is True


def test_accepted_values_groups_multiple_rows_with_same_bad_value():
    table = _orders_schema()
    rows = [
        _clean_row(order_id="ORD-1", order_type="XYZ"),
        _clean_row(order_id="ORD-2", order_type="XYZ"),
    ]

    result = check_data(table, rows)

    av_issues = [i for i in result.issues if i.rule == "accepted_values"]
    assert len(av_issues) == 1
    assert av_issues[0].rows == [1, 2]


# ---------------------------------------------------------------------
# Multiple simultaneous violations (the full approved contract example)
# ---------------------------------------------------------------------

def test_multiple_simultaneous_violations():
    table = _orders_schema()
    rows = [
        _clean_row(order_id="ORD-1001"),
        _clean_row(order_id="ORD-1002"),
        _clean_row(order_id="ORD-1003"),
        _clean_row(order_id=""),                              # required
        _clean_row(order_id="ORD-1002"),                      # uniqueness dup
        _clean_row(order_id="ORD-1005", order_type="XYZ"),    # accepted_values
        _clean_row(order_id="ORD-1006", quantity=""),         # required
    ]

    result = check_data(table, rows)

    assert result.rows_checked == 7
    assert result.is_valid is False

    required = [i for i in result.issues if i.rule == "required"]
    uniqueness = [i for i in result.issues if i.rule == "uniqueness"]
    accepted = [i for i in result.issues if i.rule == "accepted_values"]

    assert len(required) == 2  # order_id (row 4), quantity (row 7)
    assert len(uniqueness) == 1
    assert uniqueness[0].rows == [2, 5]
    assert len(accepted) == 1
    assert accepted[0].rows == [6]


# ---------------------------------------------------------------------
# QualityResult basics
# ---------------------------------------------------------------------

def test_is_valid_false_when_issues_present():
    result = QualityResult(dataset="t", rows_checked=1, issues=[
        QualityIssue(rule="required", field="x", rows=[1]),
    ])
    assert result.is_valid is False


def test_is_valid_true_when_no_issues():
    result = QualityResult(dataset="t", rows_checked=1, issues=[])
    assert result.is_valid is True
