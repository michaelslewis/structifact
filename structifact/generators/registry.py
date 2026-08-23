from .sql import SQLGenerator
from .dbt_yaml import DBTYAMLGenerator
from .dbt_yaml_extended import DBTExtendedYAMLGenerator
from .catalog import CatalogCSVGenerator
from .catalog_extended import ExtendedCatalogCSVGenerator
from .docs import DocsGenerator
from .model import ModelGenerator
from .mermaid_erd import MermaidERDGenerator
from .json_schema import JSONSchemaGenerator

# Run by default on every `structifact generate` — no configuration
# required, output shape is the same for every user.
GENERATORS = [
    SQLGenerator(),
    DBTYAMLGenerator(),
    CatalogCSVGenerator(),
]

# Available, but NOT run by default. These depend on assumptions
# Structifact can't make for every user (e.g. a specific downstream
# tool's exact expected column set, or org-specific config like
# changed_by), or are new enough that they shouldn't silently change
# existing default output. Opt in explicitly:
# `structifact generate -g <name>`.
#
# ModelGenerator (Phase 7 — Transformation Framework) is opt-in for
# the same "new enough, shouldn't silently change default output"
# reason as DocsGenerator was — it's also the first generator whose
# generate() can return None (see base.py), so it's a good idea to
# let it settle here before it's ever a default.
#
# MermaidERDGenerator (structifact.com build plan, Phase 0a) and
# JSONSchemaGenerator (Phase 0b, same plan) are opt-in for the same
# "new enough, shouldn't silently change default output" reason as
# DocsGenerator and ModelGenerator above.
OPTIONAL_GENERATORS = [
    ExtendedCatalogCSVGenerator(),
    DBTExtendedYAMLGenerator(),
    DocsGenerator(),
    ModelGenerator(),
    MermaidERDGenerator(),
    JSONSchemaGenerator(),
]

ALL_GENERATORS = GENERATORS + OPTIONAL_GENERATORS
