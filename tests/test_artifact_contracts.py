from pathlib import Path

from structifact.adapters.yaml import load_yaml
from structifact.generators.sql import SQLGenerator
from structifact.generators.dbt_yaml import DBTYAMLGenerator


FIXTURE = Path("tests/fixtures/customers.yml")
GOLDEN = Path("tests/golden")


def test_customers_sql_artifact_contract():
    dataset = load_yaml(FIXTURE)

    artifact = SQLGenerator().generate(dataset)

    expected = (GOLDEN / "customers.sql").read_text()

    assert artifact.content == expected


def test_customers_dbt_artifact_contract():
    dataset = load_yaml(FIXTURE)

    artifact = DBTYAMLGenerator().generate(dataset)

    expected = (GOLDEN / "customers.yml").read_text()

    assert artifact.content == expected