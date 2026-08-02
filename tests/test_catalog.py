import pytest

from structifact.adapters.yaml import load_yaml
from structifact.ir import DatasetSpec, FieldSpec
from structifact.validation import validate_table
from structifact.generators.catalog import CatalogCSVGenerator


# --- YAML adapter: role parsing ---

def test_yaml_adapter_parses_role():
    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")

    by_name = {f.name: f for f in dataset.fields}

    assert by_name["customer_id"].role == "dimension"
    assert by_name["lifetime_value"].role == "measure"
    assert by_name["created_at"].role == "dimension"


def test_yaml_adapter_role_defaults_to_none_when_absent():
    # the existing golden-path fixture has no role: keys — must keep
    # working exactly as before, role should just be unset
    dataset = load_yaml("tests/fixtures/customers.yml")

    for f in dataset.fields:
        assert f.role is None


# --- validation: role checking ---

def test_validate_accepts_dimension_and_measure():
    dataset = DatasetSpec(
        name="customers",
        fields=[
            FieldSpec(name="a", type="string", role="dimension"),
            FieldSpec(name="b", type="integer", role="measure"),
        ]
    )

    validate_table(dataset)  # should not raise


def test_validate_accepts_missing_role():
    dataset = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="a", type="string")]
    )

    validate_table(dataset)  # should not raise, role is optional


def test_validate_rejects_unknown_role():
    dataset = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="a", type="string", role="dimenson")]  # typo
    )

    with pytest.raises(ValueError, match="Unsupported role"):
        validate_table(dataset)


# --- catalog generator ---

def test_catalog_generator_filename():
    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    artifact = CatalogCSVGenerator().generate(dataset)

    assert artifact.filename == "customers_catalog.csv"


def test_catalog_generator_content():
    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    artifact = CatalogCSVGenerator().generate(dataset)

    lines = artifact.content.strip("\n").split("\n")

    assert lines[0] == "name,description,role,type,length"
    assert "customer_id,Unique customer identifier,dimension,integer," in lines[1]
    assert "lifetime_value,Total lifetime spend,measure,decimal," in lines[2]
    assert "created_at,Record creation timestamp,dimension,timestamp," in lines[3]


def test_catalog_generator_omits_role_when_unset():
    dataset = DatasetSpec(
        name="widgets",
        fields=[FieldSpec(name="widget_id", type="integer")]
    )

    artifact = CatalogCSVGenerator().generate(dataset)

    assert "widget_id,,,integer," in artifact.content


def test_catalog_generator_shows_decimal_precision_and_scale():
    dataset = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(
                name="amount", type="decimal", role="measure",
                precision=13, scale=2,
            )
        ]
    )

    artifact = CatalogCSVGenerator().generate(dataset)

    # length contains a comma, so a correct CSV writer quotes it —
    # parse properly rather than assume a specific raw string
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert rows[0]["length"] == "13,2"


# --- registry / CLI integration ---

def test_catalog_generator_registered():
    from structifact.generators.registry import GENERATORS

    assert any(
        gen.__class__.__name__ == "CatalogCSVGenerator" for gen in GENERATORS
    )
