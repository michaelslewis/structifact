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


def test_dbt_yaml_generator_source_field_defaults_to_dataset_name_and_field_name():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="customer_id", type="string")],
    )

    content = DBTYAMLGenerator().generate(table).content

    assert "source_field: customers.customer_id" in content


def test_dbt_yaml_generator_source_field_uses_source_table_override():
    table = DatasetSpec(
        name="customers",
        source_table="raw_customers",
        fields=[FieldSpec(name="customer_id", type="string")],
    )

    content = DBTYAMLGenerator().generate(table).content

    assert "source_field: raw_customers.customer_id" in content


def test_dbt_yaml_generator_source_field_uses_field_source_and_source_column():
    """
    Matches ModelGenerator's own qualification logic exactly -- a
    field with an explicit `source`/`source_column` (a joined-in
    source, renamed away from its physical column name) resolves the
    same way in both generators, not two different conventions.
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

    assert "source_field: cepct.ktext" in content
