"""
DBTExtendedYAMLGenerator -- dataset-level dbt metadata not
representable anywhere else in the IR (config/tags, schema, a dataset
description, and a meta block), scoped from two independent real
reference files rather than one, confirming the same shape recurs.
See DECISION_HISTORY.md and ROADMAP.md's "Real-World Validation"
section for the full account.
"""

import pytest
import yaml as pyyaml

from structifact.ir import DatasetSpec, FieldSpec
from structifact.validation import validate_table
from structifact.generators.dbt_yaml import DBTYAMLGenerator
from structifact.generators.dbt_yaml_extended import DBTExtendedYAMLGenerator
from structifact.generators.registry import GENERATORS, OPTIONAL_GENERATORS, ALL_GENERATORS


def _dataset(**overrides):
    defaults = dict(
        name="segment_master",
        fields=[FieldSpec(name="struct_segmaster_clientid", type="string", role="dimension")],
    )
    defaults.update(overrides)
    return DatasetSpec(**defaults)


def test_not_in_default_set():
    assert "dbt_extended" not in {g.name for g in GENERATORS}


def test_available_but_optional():
    assert "dbt_extended" in {g.name for g in OPTIONAL_GENERATORS}
    assert "dbt_extended" in {g.name for g in ALL_GENERATORS}


def test_filename():
    artifact = DBTExtendedYAMLGenerator().generate(_dataset())
    assert artifact.filename == "segment_master_dbt_extended.yml"


def test_tags_always_include_dataset_name_as_final_tag():
    dataset = _dataset(dbt_tags=["tableau", "sap"])
    content = DBTExtendedYAMLGenerator().generate(dataset).content
    parsed = pyyaml.safe_load(content)

    assert parsed["models"][0]["config"]["tags"] == ["tableau", "sap", "segment_master"]


def test_tags_are_just_the_dataset_name_when_dbt_tags_unset():
    content = DBTExtendedYAMLGenerator().generate(_dataset()).content
    parsed = pyyaml.safe_load(content)

    assert parsed["models"][0]["config"]["tags"] == ["segment_master"]


def test_datasource_name_defaults_to_title_cased_dataset_name():
    dataset = _dataset(name="job_item_master")
    content = DBTExtendedYAMLGenerator().generate(dataset).content
    parsed = pyyaml.safe_load(content)

    assert parsed["models"][0]["meta"]["datasource_name"] == "Job Item Master"


def test_datasource_name_explicit_override_wins():
    dataset = _dataset(dbt_datasource_name="Segment Master (Custom)")
    content = DBTExtendedYAMLGenerator().generate(dataset).content
    parsed = pyyaml.safe_load(content)

    assert parsed["models"][0]["meta"]["datasource_name"] == "Segment Master (Custom)"


def test_schema_omitted_when_unset():
    content = DBTExtendedYAMLGenerator().generate(_dataset()).content
    parsed = pyyaml.safe_load(content)

    assert "schema" not in parsed["models"][0]


def test_schema_emitted_when_set():
    dataset = _dataset(dbt_schema="PUBLIC")
    content = DBTExtendedYAMLGenerator().generate(dataset).content
    parsed = pyyaml.safe_load(content)

    assert parsed["models"][0]["schema"] == "PUBLIC"


def test_description_reuses_existing_dataset_level_description_field():
    """
    No separate dbt_description field -- the dataset-level dbt
    `description:` key reuses DatasetSpec.description, the same
    concept, not a second one.
    """
    dataset = _dataset(description="Model for Segment Masters.")
    content = DBTExtendedYAMLGenerator().generate(dataset).content
    parsed = pyyaml.safe_load(content)

    assert parsed["models"][0]["description"] == "Model for Segment Masters."


def test_description_omitted_when_unset():
    content = DBTExtendedYAMLGenerator().generate(_dataset()).content
    parsed = pyyaml.safe_load(content)

    assert "description" not in parsed["models"][0]


def test_datasource_project_extract_data_catalog_omitted_when_unset():
    """
    Deliberately never fabricated, even though both real reference
    examples happened to share identical values -- one project's
    convention isn't a universal default.
    """
    content = DBTExtendedYAMLGenerator().generate(_dataset()).content
    parsed = pyyaml.safe_load(content)

    meta = parsed["models"][0]["meta"]
    assert "datasource_project" not in meta
    assert "datasource_extract" not in meta
    assert "data_catalog" not in meta


def test_datasource_project_extract_data_catalog_emitted_when_set():
    dataset = _dataset(
        dbt_datasource_project="Public",
        dbt_datasource_extract=True,
        dbt_data_catalog=True,
    )
    content = DBTExtendedYAMLGenerator().generate(dataset).content
    parsed = pyyaml.safe_load(content)

    meta = parsed["models"][0]["meta"]
    assert meta["datasource_project"] == "Public"
    assert meta["datasource_extract"] is True
    assert meta["data_catalog"] is True


def test_column_level_output_matches_plain_dbt_generator():
    """
    Column-level shape (role, source_field) must be identical to the
    plain DBTYAMLGenerator -- this generator only adds dataset-level
    keys on top, it doesn't reinvent column handling.
    """
    dataset = _dataset(
        fields=[
            FieldSpec(name="struct_segmaster_clientid", type="string", role="dimension"),
        ],
    )

    plain = pyyaml.safe_load(DBTYAMLGenerator().generate(dataset).content)
    extended = pyyaml.safe_load(DBTExtendedYAMLGenerator().generate(dataset).content)

    assert extended["models"][0]["columns"] == plain["models"][0]["columns"]


def test_comment_emitted_when_set():
    dataset = _dataset(
        fields=[
            FieldSpec(name="struct_segmaster_clientid", type="string", comment="Client"),
        ],
    )

    content = DBTExtendedYAMLGenerator().generate(dataset).content

    assert "comment: Client" in content


def test_exposures_key_always_present():
    content = DBTExtendedYAMLGenerator().generate(_dataset()).content
    parsed = pyyaml.safe_load(content)

    assert parsed["exposures"] == []


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def test_validate_accepts_valid_dbt_target_metadata():
    dataset = _dataset(
        dbt_schema="PUBLIC", dbt_tags=["tableau", "sap"],
        dbt_datasource_name="Segment Master", dbt_datasource_project="Public",
    )
    validate_table(dataset)  # should not raise


def test_validate_rejects_blank_dbt_schema():
    dataset = _dataset(dbt_schema="   ")
    with pytest.raises(ValueError, match="dbt_schema, if set, cannot be blank"):
        validate_table(dataset)


def test_validate_rejects_blank_dbt_datasource_name():
    dataset = _dataset(dbt_datasource_name="   ")
    with pytest.raises(ValueError, match="dbt_datasource_name, if set, cannot be blank"):
        validate_table(dataset)


def test_validate_rejects_blank_dbt_datasource_project():
    dataset = _dataset(dbt_datasource_project="   ")
    with pytest.raises(ValueError, match="dbt_datasource_project, if set, cannot be blank"):
        validate_table(dataset)


def test_validate_rejects_blank_dbt_tags_entry():
    dataset = _dataset(dbt_tags=["tableau", "  "])
    with pytest.raises(ValueError, match="dbt_tags entries cannot be blank"):
        validate_table(dataset)
