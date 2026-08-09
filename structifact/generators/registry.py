from .sql import SQLGenerator
from .dbt_yaml import DBTYAMLGenerator
from .catalog import CatalogCSVGenerator
from .catalog_extended import ExtendedCatalogCSVGenerator
from .docs import DocsGenerator

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
OPTIONAL_GENERATORS = [
    ExtendedCatalogCSVGenerator(),
    DocsGenerator(),
]

ALL_GENERATORS = GENERATORS + OPTIONAL_GENERATORS
