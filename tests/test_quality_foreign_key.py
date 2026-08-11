import pytest

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.quality import check_data, resolve_references


def _orders_with_fk():
    return DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="string", nullable=False),
            FieldSpec(name="customer_id", type="string", nullable=False),
        ],
        constraints=[
            ConstraintSpec(type="primary_key", columns=["order_id"]),
            ConstraintSpec(
                type="foreign_key", columns=["customer_id"],
                target_table="dq_customers", target_column="customer_id",
            ),
        ],
    )


def _dq_customers_schema():
    return DatasetSpec(
        name="dq_customers",
        fields=[
            FieldSpec(name="customer_id", type="string", nullable=False),
            FieldSpec(name="customer_name", type="string", nullable=False),
        ],
        constraints=[ConstraintSpec(type="primary_key", columns=["customer_id"])],
    )


# ---------------------------------------------------------------------
# resolve_references: configuration/usage errors
# ---------------------------------------------------------------------

def test_missing_ref_for_declared_fk_raises():
    table = _orders_with_fk()
    with pytest.raises(ValueError, match="no reference data was supplied"):
        resolve_references(table, refs={})


def test_ref_schema_name_mismatch_raises():
    table = _orders_with_fk()
    wrong_name_schema = DatasetSpec(
        name="not_dq_customers",  # doesn't match the --ref alias 'dq_customers'
        fields=[FieldSpec(name="customer_id", type="string")],
    )
    refs = {"dq_customers": (wrong_name_schema, [])}

    with pytest.raises(ValueError, match="dataset name is 'not_dq_customers'"):
        resolve_references(table, refs)


def test_target_column_not_in_referenced_schema_raises():
    table = _orders_with_fk()
    schema_missing_column = DatasetSpec(
        name="dq_customers",
        fields=[FieldSpec(name="cust_number", type="string")],  # no customer_id
    )
    refs = {"dq_customers": (schema_missing_column, [])}

    with pytest.raises(ValueError, match="target_column 'customer_id' does not exist"):
        resolve_references(table, refs)


def test_valid_reference_resolves_without_error():
    table = _orders_with_fk()
    ref_rows = [
        {"customer_id": "CUST-001", "customer_name": "Acme"},
        {"customer_id": "CUST-002", "customer_name": "Globex"},
    ]
    refs = {"dq_customers": (_dq_customers_schema(), ref_rows)}

    referenced_values = resolve_references(table, refs)

    assert referenced_values == {"dq_customers": {"CUST-001", "CUST-002"}}


def test_missing_target_values_excluded_from_resolved_set():
    table = _orders_with_fk()
    ref_rows = [
        {"customer_id": "CUST-001", "customer_name": "Acme"},
        {"customer_id": "", "customer_name": "Blank ID"},
    ]
    refs = {"dq_customers": (_dq_customers_schema(), ref_rows)}

    referenced_values = resolve_references(table, refs)

    assert referenced_values == {"dq_customers": {"CUST-001"}}


def test_no_foreign_key_constraints_resolves_to_empty_dict():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
    )
    assert resolve_references(table, refs={}) == {}


# ---------------------------------------------------------------------
# check_data: foreign_key existence checking
# ---------------------------------------------------------------------

def test_valid_reference_is_not_flagged():
    table = _orders_with_fk()
    rows = [{"order_id": "ORD-1", "customer_id": "CUST-001"}]
    referenced_values = {"dq_customers": {"CUST-001", "CUST-002"}}

    result = check_data(table, rows, referenced_values=referenced_values)

    fk_issues = [i for i in result.issues if i.rule == "foreign_key"]
    assert fk_issues == []


def test_orphan_reference_is_flagged():
    table = _orders_with_fk()
    rows = [{"order_id": "ORD-1", "customer_id": "CUST-999"}]
    referenced_values = {"dq_customers": {"CUST-001"}}

    result = check_data(table, rows, referenced_values=referenced_values)

    fk_issues = [i for i in result.issues if i.rule == "foreign_key"]
    assert len(fk_issues) == 1
    assert fk_issues[0].field == "customer_id"
    assert fk_issues[0].value == "CUST-999"
    assert fk_issues[0].rows == [1]


def test_repeated_orphan_reference_grouped():
    table = _orders_with_fk()
    rows = [
        {"order_id": "ORD-1", "customer_id": "CUST-999"},
        {"order_id": "ORD-2", "customer_id": "CUST-001"},
        {"order_id": "ORD-3", "customer_id": "CUST-999"},
    ]
    referenced_values = {"dq_customers": {"CUST-001"}}

    result = check_data(table, rows, referenced_values=referenced_values)

    fk_issues = [i for i in result.issues if i.rule == "foreign_key"]
    assert len(fk_issues) == 1
    assert fk_issues[0].rows == [1, 3]


def test_missing_source_value_not_flagged_as_foreign_key_violation():
    """
    A blank customer_id is owned by required-field validation, not
    foreign_key — same ownership rule as v1's uniqueness check.
    """
    table = _orders_with_fk()
    rows = [{"order_id": "ORD-1", "customer_id": ""}]
    referenced_values = {"dq_customers": {"CUST-001"}}

    result = check_data(table, rows, referenced_values=referenced_values)

    fk_issues = [i for i in result.issues if i.rule == "foreign_key"]
    assert fk_issues == []

    required_issues = [i for i in result.issues if i.rule == "required"]
    assert required_issues[0].field == "customer_id"
    assert required_issues[0].rows == [1]


def test_foreign_key_is_existence_not_uniqueness_on_target_side():
    """
    Required test from the v3 contract review: a target value that
    occurs more than once in the referenced data is NOT a
    foreign_key concern. The referenced dataset's own primary_key/
    unique validation owns duplicate target values, not this check.
    """
    table = _orders_with_fk()
    rows = [{"order_id": "ORD-1", "customer_id": "CUST-001"}]
    # CUST-001 appears twice in the underlying reference data — but
    # resolve_references() collapses that into a set, and even if it
    # didn't, check_data() only cares whether the value is present.
    referenced_values = {"dq_customers": {"CUST-001"}}  # already deduped, as resolve_references produces

    result = check_data(table, rows, referenced_values=referenced_values)

    fk_issues = [i for i in result.issues if i.rule == "foreign_key"]
    assert fk_issues == []  # valid reference, no violation regardless of target-side duplication


def test_foreign_key_constraint_with_no_matching_referenced_values_entry_is_skipped():
    """
    If referenced_values doesn't contain an entry for a declared FK's
    target_table (e.g. resolve_references() wasn't called first),
    check_data() stays defensive and skips that constraint rather
    than crashing — resolve_references() is where a missing --ref is
    supposed to raise, not here.
    """
    table = _orders_with_fk()
    rows = [{"order_id": "ORD-1", "customer_id": "CUST-999"}]

    result = check_data(table, rows, referenced_values={})  # no dq_customers entry

    fk_issues = [i for i in result.issues if i.rule == "foreign_key"]
    assert fk_issues == []


def test_no_referenced_values_arg_at_all_does_not_crash():
    table = _orders_with_fk()
    rows = [{"order_id": "ORD-1", "customer_id": "CUST-999"}]

    result = check_data(table, rows)  # referenced_values defaults to None

    fk_issues = [i for i in result.issues if i.rule == "foreign_key"]
    assert fk_issues == []


# ---------------------------------------------------------------------
# Full end-to-end: resolve_references() -> check_data() together
# ---------------------------------------------------------------------

def test_full_resolve_and_check_flow():
    table = _orders_with_fk()
    order_rows = [
        {"order_id": "ORD-1", "customer_id": "CUST-001"},  # valid
        {"order_id": "ORD-2", "customer_id": "CUST-999"},  # orphan
        {"order_id": "ORD-3", "customer_id": ""},           # missing, required-owned
    ]
    ref_rows = [
        {"customer_id": "CUST-001", "customer_name": "Acme"},
        {"customer_id": "CUST-002", "customer_name": "Globex"},
    ]
    refs = {"dq_customers": (_dq_customers_schema(), ref_rows)}

    referenced_values = resolve_references(table, refs)
    result = check_data(table, order_rows, referenced_values=referenced_values)

    fk_issues = [i for i in result.issues if i.rule == "foreign_key"]
    required_issues = [i for i in result.issues if i.rule == "required"]

    assert len(fk_issues) == 1
    assert fk_issues[0].value == "CUST-999"
    assert fk_issues[0].rows == [2]

    assert len(required_issues) == 1
    assert required_issues[0].rows == [3]
