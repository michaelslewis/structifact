import pytest

from structifact.ir import DatasetSpec, FieldSpec
from structifact.reconciliation import (
    FieldMapping, ReconciliationMapping,
    reconcile_data, load_reconciliation_mapping, validate_mapping,
)


def _old_schema():
    return DatasetSpec(
        name="orders_legacy",
        fields=[
            FieldSpec(name="ORD_ID", type="string", nullable=False),
            FieldSpec(name="ORD_AMT", type="decimal", nullable=False),
            FieldSpec(name="ORD_DT", type="date", nullable=False),
        ],
    )


def _new_schema():
    return DatasetSpec(
        name="orders_new",
        fields=[
            FieldSpec(name="order_id", type="string", nullable=False),
            FieldSpec(
                name="order_amount", type="decimal", nullable=False,
                role="measure",
            ),
            FieldSpec(name="order_date", type="date", nullable=False),
        ],
    )


def _mapping():
    return ReconciliationMapping(
        key=FieldMapping(old="ORD_ID", new="order_id"),
        fields=[
            FieldMapping(old="ORD_AMT", new="order_amount"),
            FieldMapping(old="ORD_DT", new="order_date"),
        ],
    )


# ---------------------------------------------------------------------
# reconcile_data: row coverage
# ---------------------------------------------------------------------

def test_fully_matched_identical_data_has_no_issues():
    old_rows = [{"ORD_ID": "1", "ORD_AMT": "10.00", "ORD_DT": "2024-01-01"}]
    new_rows = [{"order_id": "1", "order_amount": "10.00", "order_date": "2024-01-01"}]

    result = reconcile_data(_old_schema(), old_rows, _new_schema(), new_rows, _mapping())

    assert result.is_reconciled is True
    assert result.old_count == 1
    assert result.new_count == 1
    assert result.matched_count == 1
    assert result.issues == []


def test_row_missing_in_new_is_reported():
    old_rows = [
        {"ORD_ID": "1", "ORD_AMT": "10.00", "ORD_DT": "2024-01-01"},
        {"ORD_ID": "2", "ORD_AMT": "20.00", "ORD_DT": "2024-01-02"},
    ]
    new_rows = [{"order_id": "1", "order_amount": "10.00", "order_date": "2024-01-01"}]

    result = reconcile_data(_old_schema(), old_rows, _new_schema(), new_rows, _mapping())

    assert result.matched_count == 1
    missing_in_new = [i for i in result.issues if i.rule == "missing_in_new"]
    assert len(missing_in_new) == 1
    assert missing_in_new[0].keys == ["2"]


def test_row_missing_in_old_is_reported():
    old_rows = [{"ORD_ID": "1", "ORD_AMT": "10.00", "ORD_DT": "2024-01-01"}]
    new_rows = [
        {"order_id": "1", "order_amount": "10.00", "order_date": "2024-01-01"},
        {"order_id": "2", "order_amount": "20.00", "order_date": "2024-01-02"},
    ]

    result = reconcile_data(_old_schema(), old_rows, _new_schema(), new_rows, _mapping())

    assert result.matched_count == 1
    missing_in_old = [i for i in result.issues if i.rule == "missing_in_old"]
    assert len(missing_in_old) == 1
    assert missing_in_old[0].keys == ["2"]


# ---------------------------------------------------------------------
# reconcile_data: aggregate comparison
# ---------------------------------------------------------------------

def test_aggregate_mismatch_on_matched_population_only():
    """
    The reconciliation_demo scenario: a row dropped (1004), a row
    added (1006), and a value that genuinely changed on a matched row
    (1005: 60.00 -> 65.00). The aggregate diff must reflect ONLY the
    matched-row discrepancy (+5.00), not the full-population diff
    (-255.00) that dropping/adding rows would otherwise dominate.
    """
    old_rows = [
        {"ORD_ID": "1001", "ORD_AMT": "250.00", "ORD_DT": "2024-01-05"},
        {"ORD_ID": "1002", "ORD_AMT": "100.00", "ORD_DT": "2024-01-06"},
        {"ORD_ID": "1003", "ORD_AMT": "75.50", "ORD_DT": "2024-01-07"},
        {"ORD_ID": "1004", "ORD_AMT": "300.00", "ORD_DT": "2024-01-08"},
        {"ORD_ID": "1005", "ORD_AMT": "60.00", "ORD_DT": "2024-01-09"},
    ]
    new_rows = [
        {"order_id": "1001", "order_amount": "250.00", "order_date": "2024-01-05"},
        {"order_id": "1002", "order_amount": "100.00", "order_date": "2024-01-06"},
        {"order_id": "1003", "order_amount": "75.50", "order_date": "2024-01-07"},
        {"order_id": "1005", "order_amount": "65.00", "order_date": "2024-01-09"},
        {"order_id": "1006", "order_amount": "40.00", "order_date": "2024-01-10"},
    ]

    result = reconcile_data(_old_schema(), old_rows, _new_schema(), new_rows, _mapping())

    assert result.old_count == 5
    assert result.new_count == 5
    assert result.matched_count == 4

    aggregate_issues = [i for i in result.issues if i.category == "aggregate"]
    assert len(aggregate_issues) == 1
    issue = aggregate_issues[0]
    assert issue.field == "order_amount"
    assert issue.old_value == "485.50"
    assert issue.new_value == "490.50"
    assert issue.diff == "+5.00"

    row_coverage_rules = {i.rule for i in result.issues if i.category == "row_coverage"}
    assert row_coverage_rules == {"missing_in_new", "missing_in_old"}


def test_matched_aggregate_equal_has_no_aggregate_issue():
    old_rows = [{"ORD_ID": "1", "ORD_AMT": "10.00", "ORD_DT": "2024-01-01"}]
    new_rows = [{"order_id": "1", "order_amount": "10.00", "order_date": "2024-01-01"}]

    result = reconcile_data(_old_schema(), old_rows, _new_schema(), new_rows, _mapping())

    assert [i for i in result.issues if i.category == "aggregate"] == []


def test_non_measure_mapped_field_is_not_aggregated():
    """order_date is mapped but has no role: measure, so a genuine
    mismatch there must not produce an aggregate issue in v1 —
    per-field comparison on non-measure fields is v2."""
    old_rows = [{"ORD_ID": "1", "ORD_AMT": "10.00", "ORD_DT": "2024-01-01"}]
    new_rows = [{"order_id": "1", "order_amount": "10.00", "order_date": "2099-12-31"}]

    result = reconcile_data(_old_schema(), old_rows, _new_schema(), new_rows, _mapping())

    assert result.issues == []


def test_unparseable_measure_value_is_excluded_from_sum_not_flagged():
    old_rows = [{"ORD_ID": "1", "ORD_AMT": "not-a-number", "ORD_DT": "2024-01-01"}]
    new_rows = [{"order_id": "1", "order_amount": "10.00", "order_date": "2024-01-01"}]

    result = reconcile_data(_old_schema(), old_rows, _new_schema(), new_rows, _mapping())

    aggregate_issues = [i for i in result.issues if i.category == "aggregate"]
    assert len(aggregate_issues) == 1
    assert aggregate_issues[0].old_value == "0"
    assert aggregate_issues[0].new_value == "10.00"


# ---------------------------------------------------------------------
# load_reconciliation_mapping
# ---------------------------------------------------------------------

def test_load_real_reconciliation_demo_mapping():
    mapping = load_reconciliation_mapping(
        "examples/reconciliation_demo/reconciliation.yml"
    )

    assert mapping.key == FieldMapping(old="ORD_ID", new="order_id")
    assert FieldMapping(old="ORD_AMT", new="order_amount") in mapping.fields


def test_load_mapping_missing_key_raises(tmp_path):
    bad = tmp_path / "bad_mapping.yml"
    bad.write_text("fields:\n  - old: A\n    new: a\n")

    with pytest.raises(ValueError, match="must declare a 'key'"):
        load_reconciliation_mapping(str(bad))


def test_load_mapping_field_entry_missing_new_raises(tmp_path):
    bad = tmp_path / "bad_mapping.yml"
    bad.write_text("key:\n  old: ID\n  new: id\nfields:\n  - old: A\n")

    with pytest.raises(ValueError, match="missing 'old' or 'new'"):
        load_reconciliation_mapping(str(bad))


def test_load_mapping_missing_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_reconciliation_mapping("does_not_exist.yml")


# ---------------------------------------------------------------------
# validate_mapping
# ---------------------------------------------------------------------

def test_validate_mapping_unknown_old_key_field_raises():
    mapping = ReconciliationMapping(
        key=FieldMapping(old="NOT_A_FIELD", new="order_id"), fields=[],
    )

    with pytest.raises(ValueError, match="NOT_A_FIELD.*not a declared field"):
        validate_mapping(mapping, _old_schema(), _new_schema())


def test_validate_mapping_unknown_new_field_entry_raises():
    mapping = ReconciliationMapping(
        key=FieldMapping(old="ORD_ID", new="order_id"),
        fields=[FieldMapping(old="ORD_AMT", new="not_a_field")],
    )

    with pytest.raises(ValueError, match="not_a_field.*not a declared field"):
        validate_mapping(mapping, _old_schema(), _new_schema())


def test_validate_mapping_valid_mapping_does_not_raise():
    validate_mapping(_mapping(), _old_schema(), _new_schema())
