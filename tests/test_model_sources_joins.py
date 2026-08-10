import pytest

from structifact.ir import DatasetSpec, FieldSpec, SourceRef, DedupRule, JoinSpec
from structifact.validation import validate_table
from structifact.generators.model import ModelGenerator


def _gen():
    return ModelGenerator()


def _minimal_work_order_dataset():
    """
    The minimal end-to-end contract example approved before
    implementation: one joined source (partner_role, filtered to the
    REQ role), with a priority-based dedup rule, joined into the
    dataset's primary source, with one field pulled from it.
    """
    return DatasetSpec(
        name="work_order_source",
        fields=[
            FieldSpec(name="wo_id", type="string"),
            FieldSpec(
                name="requested_by_name", type="string",
                source="partner_requested_by",
                source_column="contact_name",
            ),
        ],
        sources=[
            SourceRef(
                name="partner_requested_by",
                table="partner_role",
                filter="role_code = 'REQ'",
                dedup=DedupRule(
                    partition_by=["wo_id"],
                    order_by=["is_current desc", "updated_at desc"],
                ),
            ),
        ],
        joins=[
            JoinSpec(
                source="partner_requested_by",
                on="work_order_source.wo_id = partner_requested_by.wo_id",
            ),
        ],
    )


# ---------------------------------------------------------------------
# End-to-end contract: exact approved SQL shape
# ---------------------------------------------------------------------

def test_minimal_example_produces_approved_sql_contract():
    table = _minimal_work_order_dataset()

    artifact = _gen().generate(table)

    expected = """with

partner_requested_by as (
    select *
    from (
        select *,
            row_number() over (
                partition by wo_id
                order by is_current desc, updated_at desc
            ) as rn
        from partner_role
        where role_code = 'REQ'
    ) t
    where rn = 1
),

final as (

    select
        work_order_source.wo_id as wo_id,
        partner_requested_by.contact_name as requested_by_name

    from work_order_source
    left join partner_requested_by
        on work_order_source.wo_id = partner_requested_by.wo_id

)

select * from final;"""

    assert artifact.content == expected


def test_minimal_example_filename():
    table = _minimal_work_order_dataset()
    artifact = _gen().generate(table)
    assert artifact.filename == "work_order_source_model.sql"


def test_dataset_with_only_sources_joins_no_computed_still_generates():
    """
    Sources/joins alone (no computed fields at all) should still
    produce an Artifact, not None — there's real transformation
    logic here even without a computed field.
    """
    table = _minimal_work_order_dataset()
    artifact = _gen().generate(table)
    assert artifact is not None


# ---------------------------------------------------------------------
# Multiple joined instances of the same physical table
# ---------------------------------------------------------------------

def test_same_table_joined_multiple_times_under_different_roles():
    table = DatasetSpec(
        name="work_order_source",
        fields=[
            FieldSpec(name="wo_id", type="string"),
            FieldSpec(
                name="requested_by_name", type="string",
                source="partner_requested_by", source_column="contact_name",
            ),
            FieldSpec(
                name="billed_to_name", type="string",
                source="partner_billed_to", source_column="contact_name",
            ),
        ],
        sources=[
            SourceRef(
                name="partner_requested_by", table="partner_role",
                filter="role_code = 'REQ'",
                dedup=DedupRule(
                    partition_by=["wo_id"],
                    order_by=["is_current desc", "updated_at desc"],
                ),
            ),
            SourceRef(
                name="partner_billed_to", table="partner_role",
                filter="role_code = 'BILL'",
                dedup=DedupRule(
                    partition_by=["wo_id"],
                    order_by=["is_current desc", "updated_at desc"],
                ),
            ),
        ],
        joins=[
            JoinSpec(
                source="partner_requested_by",
                on="work_order_source.wo_id = partner_requested_by.wo_id",
            ),
            JoinSpec(
                source="partner_billed_to",
                on="work_order_source.wo_id = partner_billed_to.wo_id",
            ),
        ],
    )

    artifact = _gen().generate(table)
    content = artifact.content

    # Both CTEs present, independently, from the same physical table.
    assert "partner_requested_by as (" in content
    assert "partner_billed_to as (" in content
    assert content.count("from partner_role") == 2
    assert "where role_code = 'REQ'" in content
    assert "where role_code = 'BILL'" in content

    # Both joins present.
    assert "left join partner_requested_by" in content
    assert "left join partner_billed_to" in content

    # Both fields qualified with their own source alias.
    assert "partner_requested_by.contact_name as requested_by_name" in content
    assert "partner_billed_to.contact_name as billed_to_name" in content


# ---------------------------------------------------------------------
# Source without a dedup rule -> simpler CTE shape
# ---------------------------------------------------------------------

def test_source_without_dedup_uses_simple_cte():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="string"),
            FieldSpec(
                name="customer_name", type="string",
                source="customers", source_column="name",
            ),
        ],
        sources=[
            SourceRef(name="customers", table="cust_mst"),
        ],
        joins=[
            JoinSpec(
                source="customers",
                on="orders.customer_id = customers.customer_id",
            ),
        ],
    )

    artifact = _gen().generate(table)
    content = artifact.content

    assert "row_number()" not in content
    assert "customers as (\n    select *\n    from cust_mst\n)" in content


def test_join_type_inner_renders_inner_join():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="string"),
            FieldSpec(
                name="customer_name", type="string",
                source="customers", source_column="name",
            ),
        ],
        sources=[SourceRef(name="customers", table="cust_mst")],
        joins=[
            JoinSpec(
                source="customers",
                on="orders.customer_id = customers.customer_id",
                type="inner",
            ),
        ],
    )

    artifact = _gen().generate(table)
    assert "inner join customers" in artifact.content


# ---------------------------------------------------------------------
# Validation: relationship checks (not the raw SQL fragments)
# ---------------------------------------------------------------------

def test_valid_sources_joins_pass_validation():
    table = _minimal_work_order_dataset()
    validate_table(table)  # should not raise


def test_duplicate_source_name_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[
            SourceRef(name="dup", table="a"),
            SourceRef(name="dup", table="b"),
        ],
    )

    with pytest.raises(ValueError, match="Duplicate source name"):
        validate_table(table)


def test_join_referencing_unknown_source_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[SourceRef(name="customers", table="cust_mst")],
        joins=[
            JoinSpec(source="does_not_exist", on="orders.id = does_not_exist.id"),
        ],
    )

    with pytest.raises(ValueError, match="unknown source 'does_not_exist'"):
        validate_table(table)


def test_field_referencing_unknown_source_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(
                name="customer_name", type="string",
                source="does_not_exist", source_column="name",
            ),
        ],
    )

    with pytest.raises(ValueError, match="unknown source 'does_not_exist'"):
        validate_table(table)


def test_dedup_with_empty_partition_by_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[
            SourceRef(
                name="customers", table="cust_mst",
                dedup=DedupRule(partition_by=[], order_by=["updated_at desc"]),
            ),
        ],
    )

    with pytest.raises(ValueError, match="empty partition_by"):
        validate_table(table)


def test_dedup_with_empty_order_by_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[
            SourceRef(
                name="customers", table="cust_mst",
                dedup=DedupRule(partition_by=["customer_id"], order_by=[]),
            ),
        ],
    )

    with pytest.raises(ValueError, match="empty order_by"):
        validate_table(table)


def test_unsupported_join_type_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[SourceRef(name="customers", table="cust_mst")],
        joins=[
            JoinSpec(
                source="customers",
                on="orders.customer_id = customers.customer_id",
                type="full outer",
            ),
        ],
    )

    with pytest.raises(ValueError, match="Unsupported join type"):
        validate_table(table)


def test_supported_join_types_pass_validation():
    for join_type in ("left", "inner"):
        table = DatasetSpec(
            name="orders",
            fields=[FieldSpec(name="order_id", type="string")],
            sources=[SourceRef(name="customers", table="cust_mst")],
            joins=[
                JoinSpec(
                    source="customers",
                    on="orders.customer_id = customers.customer_id",
                    type=join_type,
                ),
            ],
        )
        validate_table(table)  # should not raise


def test_join_missing_on_condition_fails_validation():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="string")],
        sources=[SourceRef(name="customers", table="cust_mst")],
        joins=[JoinSpec(source="customers", on="")],
    )

    with pytest.raises(ValueError, match="requires an 'on' condition"):
        validate_table(table)


# ---------------------------------------------------------------------
# Backward compatibility: empty sources/joins behaves as before
# ---------------------------------------------------------------------

def test_dataset_with_no_sources_or_joins_still_validates_and_generates():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(
                name="doubled", type="integer", computed=True,
                expression="order_id * 2",
            ),
        ],
    )

    validate_table(table)  # should not raise

    artifact = _gen().generate(table)
    assert artifact is not None
    assert "with" not in artifact.content.split("\n")[0]
