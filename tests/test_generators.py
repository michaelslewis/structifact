from structifact.ir import DatasetSpec, FieldSpec
from structifact.generators.sql import SQLGenerator
from structifact.generators.dbt_yaml import DBTYAMLGenerator


def create_customer_table():
    return DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="customer_id",
                type="string",
                description="Unique customer identifier"
            ),
            FieldSpec(
                name="created_at",
                type="timestamp",
                description="Account creation time"
            ),
        ]
    )


def test_sql_generator():
    table = create_customer_table()

    generator = SQLGenerator()

    artifact = generator.generate(table)

    assert artifact.filename == "customers.sql"
    assert "CREATE TABLE customers" in artifact.content
    assert "customer_id TEXT" in artifact.content
    assert "created_at TIMESTAMP" in artifact.content


def test_sql_generator_decimal_uses_precision_and_scale():
    table = DatasetSpec(
        name="transactions",
        fields=[
            FieldSpec(
                name="amount",
                type="decimal",
                precision=13,
                scale=2,
            ),
        ]
    )

    artifact = SQLGenerator().generate(table)

    assert "amount DECIMAL(13,2)" in artifact.content


def test_sql_generator_string_uses_length():
    table = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="mandt",
                type="string",
                length=3,
            ),
        ]
    )

    artifact = SQLGenerator().generate(table)

    assert "mandt VARCHAR(3)" in artifact.content


def test_sql_generator_string_without_length_stays_text():
    # No real-world reference has ever motivated an unbounded-string
    # default other than TEXT -- only presence of a declared length
    # changes the emitted type, matching decimal's own
    # precision/scale-gated behavior above.
    table = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(
                name="notes",
                type="string",
            ),
        ]
    )

    artifact = SQLGenerator().generate(table)

    assert "notes TEXT" in artifact.content


def test_dbt_yaml_generator():
    table = create_customer_table()

    generator = DBTYAMLGenerator()

    artifact = generator.generate(table)

    assert artifact.filename == "customers.yml"
    assert "customer_id" in artifact.content
    assert "Unique customer identifier" in artifact.content


def test_dbt_yaml_generator_emits_role_when_set():
    table = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(name="customer_id", type="string", role="dimension"),
            FieldSpec(name="lifetime_value", type="decimal", role="measure"),
        ],
    )

    content = DBTYAMLGenerator().generate(table).content

    assert "role: dimension" in content
    assert "role: measure" in content


def test_dbt_yaml_generator_omits_role_when_unset():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="customer_id", type="string")],
    )

    content = DBTYAMLGenerator().generate(table).content

    assert "role:" not in content


def test_dbt_yaml_generator_emits_comment_when_set():
    table = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(name="customer_id", type="string", comment="Cust ID"),
        ],
    )

    content = DBTYAMLGenerator().generate(table).content

    assert "comment: Cust ID" in content


def test_dbt_yaml_generator_omits_comment_when_unset():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="customer_id", type="string")],
    )

    content = DBTYAMLGenerator().generate(table).content

    assert "comment:" not in content


def test_dbt_yaml_generator_source_field_is_field_name_with_dots_for_underscores():
    """
    Confirmed by two independent real reference files, identically:
    source_field is the field's own display name with every
    underscore replaced by a dot -- NOT derived from the physical
    source/source_column (the first, incorrect implementation's
    assumption). See DECISION_HISTORY.md.
    """
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="struct_cepc_mandt", type="string")],
    )

    content = DBTYAMLGenerator().generate(table).content

    assert "source_field: struct.cepc.mandt" in content


def test_dbt_yaml_generator_source_field_splits_the_display_name_not_the_physical_column():
    """
    The exact disambiguating real case: a field whose PHYSICAL column
    (verak_user, one word) contains an underscore that doesn't appear
    in a table.column sense at all -- the real reference file still
    split it into `verak.user`, proving the split operates on the
    field's own declared name, not on any physical column reference.
    """
    table = DatasetSpec(
        name="profit_center",
        fields=[FieldSpec(name="struct_cepc_verak_user", type="string")],
    )

    content = DBTYAMLGenerator().generate(table).content

    assert "source_field: struct.cepc.verak.user" in content


def test_dbt_yaml_generator_source_field_ignores_source_table_source_and_source_column():
    """
    Regression guard: source_table/source/source_column must NOT
    affect source_field at all, now that it's confirmed to be a pure
    function of the field's own display name.
    """
    table = DatasetSpec(
        name="profit_center",
        source_table="cepc",
        fields=[
            FieldSpec(
                name="struct_cepct_ktext", type="string",
                source="cepct", source_column="ktext",
            ),
        ],
    )

    content = DBTYAMLGenerator().generate(table).content

    assert "source_field: struct.cepct.ktext" in content
    assert "source_field: cepct.ktext" not in content
