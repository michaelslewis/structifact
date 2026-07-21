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
    assert "created_at TEXT" in artifact.content


def test_dbt_yaml_generator():
    table = create_customer_table()

    generator = DBTYAMLGenerator()

    artifact = generator.generate(table)

    assert artifact.filename == "customers.yml"
    assert "customer_id" in artifact.content
    assert "Unique customer identifier" in artifact.content