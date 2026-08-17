from pathlib import Path

from structifact.adapters.yaml import load_yaml

def test_load_yaml_dataset_format_from_example():
    dataset = load_yaml("examples/customers.yml")

    assert dataset.name == "customers"

    assert len(dataset.fields) == 2

    assert dataset.fields[0].name == "customer_id"
    assert dataset.fields[0].type == "integer"

    assert dataset.fields[1].name == "created_at"
    assert dataset.fields[1].type == "timestamp"


def test_load_yaml_dataset_format_from_file(tmp_path):
    yaml_file = tmp_path / "customers.yml"

    yaml_file.write_text(
        """
dataset:
  name: customers
  description: Customer master data

fields:
  - name: customer_id
    type: integer
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.name == "customers"
    assert dataset.description == "Customer master data"

    assert len(dataset.fields) == 1
    assert dataset.fields[0].name == "customer_id"


def test_load_yaml_constraints(tmp_path):
    yaml_file = tmp_path / "customers.yml"

    yaml_file.write_text(
        """
dataset:
  name: customers

fields:
  - name: customer_id
    type: integer

constraints:
  - type: primary_key
    columns:
      - customer_id
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert len(dataset.constraints) == 1

    constraint = dataset.constraints[0]

    assert constraint.type == "primary_key"
    assert constraint.columns == ["customer_id"]

def test_load_yaml_legacy_table_format(tmp_path):
    yaml_file = tmp_path / "customers.yml"
    yaml_file.write_text(
        """
table: customers

fields:
  - name: customer_id
    type: integer
"""
    )

    dataset = load_yaml(yaml_file)

    assert dataset.name == "customers"


# ---------------------------------------------------------------------
# source_table / sources / joins / field-level source / source_column
#
# Regression coverage for a real bug found while implementing Phase
# 8D v4 (CLI exposure for materialization): validation.py and
# ModelGenerator have operated on DatasetSpec.source_table/.sources/
# .joins and FieldSpec.source/.source_column since Phase 7, but
# load_yaml() never actually parsed any of them from a real YAML file
# -- every existing sources/joins test constructed DatasetSpec
# directly in Python. The gap was invisible until this was the first
# time a real YAML file needed source_table to load correctly.
# ---------------------------------------------------------------------

def test_load_yaml_parses_source_table(tmp_path):
    yaml_file = tmp_path / "order_items.yml"
    yaml_file.write_text(
        """
dataset:
  name: order_items

source_table: raw_order_items

fields:
  - name: order_id
    type: integer
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.source_table == "raw_order_items"


def test_load_yaml_parses_source_filter(tmp_path):
    yaml_file = tmp_path / "profit_center.yml"
    yaml_file.write_text(
        """
dataset:
  name: profit_center

source_table: cepc
source_filter: "datbi = '9999-12-31'"

fields:
  - name: prctr
    type: string
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.source_filter == "datbi = '9999-12-31'"


def test_load_yaml_source_filter_absent_defaults_to_none(tmp_path):
    dataset = load_yaml("tests/fixtures/customers.yml")

    assert dataset.source_filter is None


def test_load_yaml_source_table_absent_defaults_to_none(tmp_path):
    dataset = load_yaml("tests/fixtures/customers.yml")

    assert dataset.source_table is None


def test_load_yaml_parses_dbt_target_metadata(tmp_path):
    yaml_file = tmp_path / "profit_center.yml"
    yaml_file.write_text(
        """
dataset:
  name: profit_center
  description: Model for Profit Centers.

dbt_schema: PUBLIC
dbt_tags: [tableau, sap]
dbt_datasource_name: Profit Center
dbt_datasource_project: Public
dbt_datasource_extract: true
dbt_data_catalog: true

fields:
  - name: struct_cepc_mandt
    type: string
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.dbt_schema == "PUBLIC"
    assert dataset.dbt_tags == ["tableau", "sap"]
    assert dataset.dbt_datasource_name == "Profit Center"
    assert dataset.dbt_datasource_project == "Public"
    assert dataset.dbt_datasource_extract is True
    assert dataset.dbt_data_catalog is True


def test_load_yaml_dbt_target_metadata_absent_defaults(tmp_path):
    dataset = load_yaml("tests/fixtures/customers.yml")

    assert dataset.dbt_schema is None
    assert dataset.dbt_tags == []
    assert dataset.dbt_datasource_name is None
    assert dataset.dbt_datasource_project is None
    assert dataset.dbt_datasource_extract is None
    assert dataset.dbt_data_catalog is None


def test_load_yaml_parses_sources_and_joins(tmp_path):
    yaml_file = tmp_path / "work_order_source.yml"
    yaml_file.write_text(
        """
dataset:
  name: work_order_source

source_table: raw_work_order_source

fields:
  - name: wo_id
    type: integer
  - name: requested_by_name
    type: string
    source: partner_requested_by
    source_column: contact_name

sources:
  - name: partner_requested_by
    table: partner_role
    filter: "role_code = 'REQ'"
    dedup:
      partition_by: [wo_id]
      order_by: ["is_current desc", "updated_at desc"]

joins:
  - source: partner_requested_by
    "on": "raw_work_order_source.wo_id = partner_requested_by.wo_id"
    type: left
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.source_table == "raw_work_order_source"

    assert dataset.fields[1].source == "partner_requested_by"
    assert dataset.fields[1].source_column == "contact_name"

    assert len(dataset.sources) == 1
    source = dataset.sources[0]
    assert source.name == "partner_requested_by"
    assert source.table == "partner_role"
    assert source.filter == "role_code = 'REQ'"
    assert source.dedup.partition_by == ["wo_id"]
    assert source.dedup.order_by == ["is_current desc", "updated_at desc"]

    assert len(dataset.joins) == 1
    join = dataset.joins[0]
    assert join.source == "partner_requested_by"
    assert join.on == "raw_work_order_source.wo_id = partner_requested_by.wo_id"
    assert join.type == "left"


def test_load_yaml_sources_join_type_defaults_to_left(tmp_path):
    yaml_file = tmp_path / "orders.yml"
    yaml_file.write_text(
        """
dataset:
  name: orders

fields:
  - name: order_id
    type: integer

sources:
  - name: customers
    table: cust_mst

joins:
  - source: customers
    "on": "orders.customer_id = customers.customer_id"
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.joins[0].type == "left"


def test_load_yaml_sources_joins_absent_default_to_empty_lists(tmp_path):
    dataset = load_yaml("tests/fixtures/customers.yml")

    assert dataset.sources == []
    assert dataset.joins == []


def test_load_yaml_parses_field_comment(tmp_path):
    yaml_file = tmp_path / "customers.yml"
    yaml_file.write_text(
        """
dataset:
  name: customers

fields:
  - name: customer_id
    type: integer
    description: Unique customer identifier
    comment: Cust ID
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.fields[0].description == "Unique customer identifier"
    assert dataset.fields[0].comment == "Cust ID"


def test_load_yaml_field_comment_defaults_to_none(tmp_path):
    dataset = load_yaml("examples/customers.yml")

    assert dataset.fields[0].comment is None


def test_load_yaml_parses_aggregate_rule(tmp_path):
    yaml_file = tmp_path / "customer_credit.yml"
    yaml_file.write_text(
        """
dataset:
  name: customer_credit

source_table: knkk

fields:
  - name: kunnr
    type: string
  - name: struct_bsid_sum_dmbtr
    type: decimal
    source: bsid
    source_column: struct_bsid_sum_dmbtr

sources:
  - name: bsid
    table: bsid
    aggregate:
      group_by: [kunnr, kkber]
      aggregates:
        struct_bsid_sum_dmbtr: "SUM(case when shkzg = 'S' then dmbtr when shkzg = 'H' then -dmbtr else 0 end)"

joins:
  - source: bsid
    "on": "knkk.kunnr = bsid.kunnr and knkk.kkber = bsid.kkber"
"""
    )

    dataset = load_yaml(str(yaml_file))

    source = dataset.sources[0]
    assert source.dedup is None
    assert source.aggregate.group_by == ["kunnr", "kkber"]
    assert source.aggregate.aggregates == {
        "struct_bsid_sum_dmbtr": (
            "SUM(case when shkzg = 'S' then dmbtr "
            "when shkzg = 'H' then -dmbtr else 0 end)"
        ),
    }


def test_load_yaml_source_without_aggregate_leaves_aggregate_none(tmp_path):
    yaml_file = tmp_path / "orders.yml"
    yaml_file.write_text(
        """
dataset:
  name: orders

fields:
  - name: order_id
    type: integer

sources:
  - name: customers
    table: cust_mst
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.sources[0].aggregate is None


def test_load_yaml_source_without_dedup_leaves_dedup_none(tmp_path):
    yaml_file = tmp_path / "orders.yml"
    yaml_file.write_text(
        """
dataset:
  name: orders

fields:
  - name: order_id
    type: integer

sources:
  - name: customers
    table: cust_mst
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.sources[0].dedup is None


def test_load_yaml_dependency_demo_end_to_end_via_real_pipeline():
    """
    Loads the real examples/workorder_demo-motivated sources/joins/
    dedup shape end to end -- YAML -> DatasetSpec -> validate_table ->
    ModelGenerator -- proving the fix works through the whole real
    pipeline, not just load_yaml() in isolation.
    """
    from structifact.validation import validate_table
    from structifact.generators.model import ModelGenerator

    import tempfile
    import os

    yaml_content = """
dataset:
  name: work_order_source

source_table: raw_work_order_source

fields:
  - name: wo_id
    type: integer
  - name: requested_by_name
    type: string
    source: partner_requested_by
    source_column: contact_name

sources:
  - name: partner_requested_by
    table: partner_role
    filter: "role_code = 'REQ'"
    dedup:
      partition_by: [wo_id]
      order_by: ["is_current desc", "updated_at desc"]

joins:
  - source: partner_requested_by
    "on": "raw_work_order_source.wo_id = partner_requested_by.wo_id"
"""

    fd, path = tempfile.mkstemp(suffix=".yml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(yaml_content)

        dataset = load_yaml(path)
        validate_table(dataset)  # should not raise

        artifact = ModelGenerator().generate(dataset)
        assert "from raw_work_order_source" in artifact.content
        assert "left join partner_requested_by" in artifact.content
    finally:
        os.remove(path)