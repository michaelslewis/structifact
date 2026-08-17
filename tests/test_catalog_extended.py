import argparse
import csv
import io
import os
from datetime import datetime

import pytest

from structifact.adapters.yaml import load_yaml
from structifact.ir import DatasetSpec, FieldSpec
from structifact.generators.catalog_extended import ExtendedCatalogCSVGenerator
from structifact.generators.registry import GENERATORS, OPTIONAL_GENERATORS, ALL_GENERATORS


FIXED_TIME = datetime(2025, 6, 24, 11, 26, 49, 20908)


def _fixed_now():
    return FIXED_TIME


# --- ExtendedCatalogCSVGenerator ---

def test_extended_catalog_filename():
    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    gen = ExtendedCatalogCSVGenerator(changed_by="test_user", now_fn=_fixed_now)

    artifact = gen.generate(dataset)

    assert artifact.filename == "customers_catalog_extended.csv"


def test_extended_catalog_columns():
    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    gen = ExtendedCatalogCSVGenerator(changed_by="test_user", now_fn=_fixed_now)

    artifact = gen.generate(dataset)
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert set(rows[0].keys()) == {
        "name", "description", "role", "datatype", "fieldlength",
        "pii", "comments", "changed_by", "changed_on",
    }


def test_extended_catalog_changed_by_from_constructor():
    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    gen = ExtendedCatalogCSVGenerator(changed_by="alice", now_fn=_fixed_now)

    artifact = gen.generate(dataset)
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert all(r["changed_by"] == "alice" for r in rows)


def test_extended_catalog_changed_by_from_env_var(monkeypatch):
    monkeypatch.setenv("STRUCTIFACT_CHANGED_BY", "bob")

    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    gen = ExtendedCatalogCSVGenerator(now_fn=_fixed_now)  # no explicit changed_by

    artifact = gen.generate(dataset)
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert all(r["changed_by"] == "bob" for r in rows)


def test_extended_catalog_changed_by_blank_when_unspecified(monkeypatch):
    monkeypatch.delenv("STRUCTIFACT_CHANGED_BY", raising=False)

    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    gen = ExtendedCatalogCSVGenerator(now_fn=_fixed_now)

    artifact = gen.generate(dataset)
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert all(r["changed_by"] == "" for r in rows)


def test_extended_catalog_pii_always_blank():
    # Structifact's IR has no pii concept — must never be fabricated,
    # always blank
    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    gen = ExtendedCatalogCSVGenerator(now_fn=_fixed_now)

    artifact = gen.generate(dataset)
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert all(r["pii"] == "" for r in rows)


def test_extended_catalog_comments_blank_when_field_comment_unset():
    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    gen = ExtendedCatalogCSVGenerator(now_fn=_fixed_now)

    artifact = gen.generate(dataset)
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert all(r["comments"] == "" for r in rows)


def test_extended_catalog_comments_populated_from_field_comment():
    dataset = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="customer_id", type="string", comment="Cust ID")],
    )
    gen = ExtendedCatalogCSVGenerator(now_fn=_fixed_now)

    artifact = gen.generate(dataset)
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert rows[0]["comments"] == "Cust ID"


def test_extended_catalog_changed_on_format():
    dataset = load_yaml("tests/fixtures/customers_with_roles.yml")
    gen = ExtendedCatalogCSVGenerator(now_fn=_fixed_now)

    artifact = gen.generate(dataset)
    rows = list(csv.DictReader(io.StringIO(artifact.content)))

    assert rows[0]["changed_on"] == "2025-06-24 11:26:49.020908"


# --- registry: default vs optional ---

def test_extended_generator_not_in_default_set():
    assert "catalog_extended" not in {g.name for g in GENERATORS}


def test_extended_generator_is_available_but_optional():
    assert "catalog_extended" in {g.name for g in OPTIONAL_GENERATORS}
    assert "catalog_extended" in {g.name for g in ALL_GENERATORS}


# --- CLI: generator selection ---

def test_cli_default_generate_unchanged(tmp_path):
    from structifact.cli import generate as generate_cmd

    args = argparse.Namespace(
        spec="tests/fixtures/customers_with_roles.yml",
        output=str(tmp_path),
        generators=None,
    )
    generate_cmd(args)

    # default behavior: sql, dbt yaml, basic catalog — NOT extended
    assert (tmp_path / "customers.sql").exists()
    assert (tmp_path / "customers.yml").exists()
    assert (tmp_path / "customers_catalog.csv").exists()
    assert not (tmp_path / "customers_catalog_extended.csv").exists()


def test_cli_explicit_generator_selection(tmp_path):
    from structifact.cli import generate as generate_cmd

    args = argparse.Namespace(
        spec="tests/fixtures/customers_with_roles.yml",
        output=str(tmp_path),
        generators="catalog_extended",
    )
    generate_cmd(args)

    assert (tmp_path / "customers_catalog_extended.csv").exists()
    assert not (tmp_path / "customers.sql").exists()  # only what was asked for


def test_cli_model_generator_none_result_prints_explanation(tmp_path, capsys):
    """
    Found during the 1.0 readiness audit: ModelGenerator legitimately
    returns None for a dataset with no computed fields and no
    sources/joins (nothing to transform) -- but the CLI previously
    printed nothing at all when that happened, leaving an empty
    "GENERATED ARTIFACTS" section with no explanation. Not an error
    (exit code must stay unaffected), just previously silent.
    """
    from structifact.cli import generate as generate_cmd

    args = argparse.Namespace(
        spec="tests/fixtures/customers_with_roles.yml",
        output=str(tmp_path),
        generators="model",
    )
    result = generate_cmd(args)

    out = capsys.readouterr().out
    assert "model: nothing to generate for this dataset" in out
    assert result is True
    assert not (tmp_path / "customers_model.sql").exists()


def test_cli_unknown_generator_lists_available(tmp_path, capsys):
    from structifact.cli import generate as generate_cmd

    args = argparse.Namespace(
        spec="tests/fixtures/customers_with_roles.yml",
        output=str(tmp_path),
        generators="nonexistent",
    )
    generate_cmd(args)

    out = capsys.readouterr().out
    assert "Unknown generator" in out
    assert "catalog_extended" in out  # tells them what IS available
    assert not (tmp_path / "customers.sql").exists()  # nothing written
