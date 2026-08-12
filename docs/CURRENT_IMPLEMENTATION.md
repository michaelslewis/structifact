# CURRENT_IMPLEMENTATION.md

# Structifact Current Implementation

**Project:** Structifact
**Subtitle:** Schema-Driven Data Engineering Framework

---

# Purpose

This document describes the functionality currently implemented in the Structifact repository.

It intentionally reflects the current state of the codebase only.

Future architectural goals, planned capabilities, and exploratory ideas are documented separately in:

* `ROADMAP.md`
* `FUTURE_WORK.md`

This document should remain the technical source of truth for implemented behavior.

---

# Implementation Overview

Structifact is a Python-based metadata-driven framework that converts declarative dataset definitions into a validated internal representation, then into generated engineering artifacts and, separately, into real data-quality checks against actual data.

The current implementation covers:

* three input adapters (YAML, CSV, Excel), all normalizing through a shared type system
* an internal representation (`DatasetSpec` / `FieldSpec` / `ConstraintSpec`, plus `SourceRef` / `JoinSpec` / `DedupRule` for multi-source datasets, and `DatasetSpec.depends_on` for cross-dataset dependencies)
* metadata validation (schema well-formedness, constraint relationships, checkable rule content)
* six generators (SQL, dbt YAML, two catalog variants, docs, a SELECT-based transformation model)
* deterministic and AI-assisted schema/requirements discovery
* real-data quality checking, including cross-dataset foreign-key validation
* collection-level dependency resolution across multiple datasets — cycle
  detection and deterministic execution ordering
* a five-command CLI
* 307 automated tests, CI-enforced on every push

The core design principle remains:

> Define structure once. Generate reliable systems from it.

---

# Repository Structure

```text
structifact/                        (repo root)
│
├── examples/
│   ├── customers/
│   ├── enterprise_demo/
│   ├── workorder_demo/
│   ├── data_quality_demo/
│   └── dependency_demo/
│
├── structifact/
│   ├── cli.py
│   ├── __main__.py
│   ├── ir.py
│   ├── types.py
│   ├── utils.py
│   ├── validation.py
│   ├── quality.py
│   ├── dependencies.py
│   ├── discover.py
│   ├── llm.py
│   │
│   ├── adapters/
│   │   ├── registry.py
│   │   ├── csv.py
│   │   ├── excel.py
│   │   └── yaml.py
│   │
│   └── generators/
│       ├── registry.py
│       ├── base.py
│       ├── sql.py
│       ├── dbt_yaml.py
│       ├── catalog.py
│       ├── catalog_extended.py
│       ├── docs.py
│       └── model.py
│
├── tests/
├── docs/
└── pyproject.toml
```

`structifact/parser.py` no longer exists — it was removed as dead code early in the project's history. Adapters build IR objects directly; there is no separate parsing stage between an adapter and the IR.

---

# Core Components

## Metadata Layer

YAML is the canonical format (supporting both the current `dataset:` contract and a legacy `table:` form for backward compatibility); CSV and Excel are fully-supported alternate input formats, kept at parity with YAML on every `FieldSpec` attribute.

---

# Adapters

Location: `structifact/adapters/`

## YAML Adapter (`yaml.py`)

The primary metadata ingestion path. Parses every `FieldSpec` attribute the IR supports — including `role`, `accepted_values`, `nullable`, computed-field fields (`computed`/`expression`/`depends_on`), Phase 6 v2 fields (`min_value`/`max_value`/`pattern`, converted via `Decimal(str(v))` rather than `Decimal(v)` directly, to avoid preserving a YAML-parsed float's exact binary representation instead of the clean value the user wrote), and cross-source attribution (`source`/`source_column`). Also parses dataset-level `source_table`, `sources`, `joins`, and `depends_on` (this last one a top-level key, sibling to `dataset:`/`fields:`/`constraints:` — same placement as `constraints`), and constraint-level `target_table`/`target_column`/`expression` (this last item was a real bug fix — see `DECISION_HISTORY.md`; earlier versions of `yaml.py` accepted these keys in `ConstraintSpec` but never actually read them from a YAML file).

## CSV Adapter (`csv.py`)

Reads a CSV-format field grid (one row per field: `column_name,type,description,...`) as an alternative to YAML. At parity with YAML on field-level attributes. Does not currently support dataset-level `constraints`, `sources`, `joins`, or `depends_on` — those remain YAML-only, since a flat one-row-per-field CSV format has no natural place to represent dataset-level relationships without a different structure.

## Excel Adapter (`excel.py`)

Same field-grid shape as the CSV adapter, read via `pandas`. Normalizes pandas' blank-cell representation (`NaN`, a float) to `None` before it can leak into the IR as the literal string `"nan"`. At parity with the CSV adapter on field-level attributes, including the Phase 6 v2 fields.

---

# Internal Representation

Location: `structifact/ir.py`

```text
DatasetSpec
    |
    +-- FieldSpec[]
    |     (name, type, nullable, role, accepted_values,
    |      computed/expression/depends_on,
    |      min_value/max_value/pattern,
    |      source/source_column)
    |
    +-- ConstraintSpec[]
    |     (primary_key, unique, foreign_key [target_table/target_column],
    |      check [expression])
    |
    +-- source_table
    +-- sources: SourceRef[]     (name, table, filter, dedup)
    +-- joins: JoinSpec[]        (source, on, type)
    +-- depends_on: str[]        (other dataset names — declaration only)
```

## DatasetSpec

Canonical dataset representation. `TableSpec` remains a plain alias (`TableSpec = DatasetSpec`), not a separate class.

## FieldSpec

Intrinsic field characteristics, deliberately kept from growing into an unbounded flag collection — see `DECISION_HISTORY.md` for the reasoning each time a new field was proposed. Current attributes: `name`, `type`, `raw_type`, `description`, `label`, `role`, `length`/`precision`/`scale`, `accepted_values`, `nullable`, `computed`/`expression`/`depends_on`, `source`/`source_column`, `min_value`/`max_value`/`pattern`.

## ConstraintSpec

Dataset-level rules, kept separate from `FieldSpec` for the same reason. `type` is one of `primary_key`/`unique`/`foreign_key`/`check`; `foreign_key` also carries `target_table`/`target_column` (single-column only — composite FK is out of scope until a real example needs it); `check` carries `expression` (raw SQL, assumed valid, never parsed).

## SourceRef / JoinSpec / DedupRule

Added for the sources/joins milestone (multi-source datasets, including the same physical table joined in multiple times under different roles). `SourceRef.name` (a logical alias for this joined-in instance) is deliberately distinct from `SourceRef.table` (the physical table) — that distinction is what lets one physical table be joined in several times under different roles, each with its own `filter` and `DedupRule`. `JoinSpec.on` is a single raw SQL condition (multiple join keys expressed with `AND` inside the one string, not a structured list). `DedupRule` represents priority-based row selection (`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) = 1`), not a uniqueness constraint.

## depends_on (Phase 7 remainder)

A plain `List[str]` on `DatasetSpec`, naming other Structifact-defined datasets this one depends on. Deliberately NOT a new dataclass — no real example has yet shown a need for dependency-level metadata beyond a name. Distinct from `FieldSpec.depends_on` (a computed field's dependency on other fields *within the same dataset*) — the two occupy different, unambiguous nesting positions in the YAML. Declaration only: says nothing about *how* this dataset obtains the other's data. See `structifact/dependencies.py` below for what operates on this field.

---

# Type System

Location: `structifact/types.py`

`parse_type`/`normalize_type` map raw source types (`VARCHAR(50)` → `string`, length `50`; `DECIMAL(10,2)` → `decimal`, precision `10`, scale `2`) into the normalized IR type system. `infer_type_from_values` (used by `discover`) infers a likely type from raw sample values with no declared type — deliberately conservative: a leading-zero numeric-looking value (e.g. a zip code) stays `string` rather than risk corrupting an identifier, and common null placeholders (`NULL`, `N/A`, `-`, etc.) are recognized, not just literal empty strings.

---

# Validation Framework

Location: `structifact/validation.py`

Validates the IR's own well-formedness — this operates on *metadata*, not real data (that's `quality.py`'s job, described below), and on a single dataset at a time (collection-level checks are `dependencies.py`'s job, also described below). Current checks include:

* dataset/field name presence, duplicate field names, supported types, supported roles
* `accepted_values` well-formedness (non-empty, no duplicates)
* computed-field well-formedness (`computed` requires `expression`; `depends_on` entries must reference real fields in the same dataset; no self-reference)
* `source_table` non-blank when set
* `sources`/`joins` relationship checks: unique `SourceRef.name` values, every `JoinSpec.source` resolves to a declared source, every `DedupRule` has non-empty `partition_by`/`order_by`, `JoinSpec.type` is a supported join type (currently `left`/`inner`)
* every `FieldSpec.source` (when set) resolves to a declared source
* dataset-level `depends_on` well-formedness: no blank entries, no duplicates, no self-reference (whether a referenced dataset actually exists is a collection-level question — see `dependencies.py`)
* constraint checks: at most one `primary_key` per dataset, columns reference real fields, `foreign_key` requires exactly one column plus non-blank `target_table`/`target_column`, `check` requires a non-blank `expression`
* Phase 6 v2 additions: `pattern` must compile as valid regex; `min_value` must not exceed `max_value`; `min_value`/`max_value` only apply to `integer`/`decimal` fields, `pattern` only to `string` fields

Raw SQL/regex fragments (`expression`, `JoinSpec.on`, `SourceRef.filter`, `DedupRule.order_by`) are never parsed or semantically validated — Structifact trusts them as-is, same as it always has. The one deliberate exception is `pattern`, which *is* checked (via `re.compile`) since — unlike a SQL fragment — a regex can be meaningfully validated without running anything.

---

# Data Quality Framework (Phase 6)

Location: `structifact/quality.py`

A separate subsystem from validation and generation — it checks real data, which no other part of Structifact does. Not a `Generator` (the `Generator` interface takes one input and returns one artifact; this needs a schema *and* a data file, and produces a structured result rather than a write-to-disk artifact).

## Core types

```python
QualityIssue(rule, field, rows, value=None)
QualityResult(dataset, rows_checked, issues) -> .is_valid
```

`rule` is one of `required` / `uniqueness` / `accepted_values` / `range` / `pattern` / `foreign_key`. Issues are always grouped by field (and offending value, where relevant) — never one issue per row.

## `check_data(table, rows, referenced_values=None)`

Runs every rule the schema declares against real, in-memory-loaded CSV rows (no streaming/chunking; a deliberate v1 scope decision). A missing value is exactly an empty CSV field. Ownership rule, applied consistently across every check: a missing value is *only* ever reported once, by `required` — `uniqueness`, `accepted_values`, `range`, `pattern`, and `foreign_key` all skip rows where the relevant value is missing, rather than double-reporting.

* **required** — `nullable: false`
* **uniqueness** — `primary_key`/`unique` constraints; groups all rows sharing a duplicate value into one issue
* **accepted_values** — reuses the existing metadata field
* **range** — `min_value`/`max_value`, inclusive. A value that's present but fails to parse as a number is *not* reported (see `_try_parse_decimal`, deliberately kept separate from the missing-value check so a future type-validation rule has a clean seam to attach to, rather than this being one blanket try/except)
* **pattern** — `re.fullmatch`, not `search` — the entire value must match
* **foreign_key** — pure existence/membership against `referenced_values` (precomputed by the caller); indifferent to duplication on the target side, which is the target dataset's own uniqueness concern

## `resolve_references(table, refs)`

Resolves a schema's `foreign_key` constraints against caller-supplied reference data (`refs: Dict[alias, (DatasetSpec, rows)]`), producing the `referenced_values` dict `check_data` needs. Schema-aware and deliberately strict — every failure here is a `ValueError` (a configuration/usage error), never a `QualityIssue`:

* the constraint's `target_table` must have a corresponding entry in `refs`
* the referenced schema's own declared `name` must match the `refs` key it was supplied under
* `target_column` must be a real field declared on the referenced schema — never inferred from what a CSV header happens to contain

## `load_data_rows(path)`

Plain `csv.DictReader` read — no type coercion, no inference. Deliberately distinct from `discover.py`'s sampler, which infers a schema *from* data; this reads data to check it against a schema that already exists.

All formatting of `QualityResult` into human-readable text lives in `cli.py`, not here — `check_data`/`resolve_references` never call `print()`.

---

# Dataset Dependency Tracking (Phase 7 remainder)

Location: `structifact/dependencies.py`

A separate subsystem from `validation.py`, following the same precedent as `quality.py`: it operates on a *collection* of `DatasetSpec`s, which is a genuinely different question from single-dataset well-formedness.

## `build_dependency_graph(datasets)`

Builds a `{name: [depends_on names]}` mapping. Raises `ValueError` (message lists every problem found, not just the first) if two datasets share a name, or if any `depends_on` entry doesn't resolve to a dataset in the collection.

## `execution_order(datasets)`

Returns a deterministic list of dataset names, ordered so every dataset appears after all of its dependencies. Uses a DFS-based topological sort, tie-broken by input order among datasets with no dependency relationship to each other — that relative order is NOT semantically guaranteed, only kept stable so output doesn't vary run-to-run. Raises `ValueError` (no partial order ever returned) on anything `build_dependency_graph` would raise, or on a circular dependency — the message names the complete cycle, e.g. `Circular dependency detected: dataset_a -> dataset_b -> dataset_c -> dataset_a`.

Per-dataset well-formedness (blank/duplicate/self-referencing `depends_on` entries) lives in `validation.py` instead, matching where every other per-dataset check lives — only collection-level concerns are in this module.

---

# Generators

Location: `structifact/generators/`

* **`sql.py`** — `CREATE TABLE` DDL. Type-aware (`INTEGER`/`TIMESTAMP`/`DECIMAL(p,s)`, not blanket `TEXT`). Emits `NOT NULL`, `PRIMARY KEY`, `UNIQUE`, and now `FOREIGN KEY`/`CHECK`. A computed field's `expression` is documented as a SQL comment, never emitted as executable/vendor-specific syntax.
* **`dbt_yaml.py`** — dbt-compatible YAML metadata.
* **`catalog.py`** — minimal catalog CSV (name/description/role/type/length); run by default.
* **`catalog_extended.py`** — richer catalog matching a specific downstream tool's column set; `pii`/`comments` always blank (never fabricated), `changed_by` configurable, `changed_on` a real timestamp. Opt-in only.
* **`docs.py`** (`DocsGenerator`) — per-dataset Markdown, rendering every metadata attribute a field actually has; never fabricates. Opt-in.
* **`model.py`** (`ModelGenerator`) — a real, executable `SELECT`, not DDL. For a dataset with `sources`/`joins`, builds the necessary CTEs (including `ROW_NUMBER()`-based dedup per `DedupRule`) and qualifies every column reference by its source. Returns `None` (not an `Artifact`) for a dataset with no computed fields and no sources/joins — nothing to transform. Opt-in.

`generators/registry.py` splits `GENERATORS` (run by default: SQL, dbt YAML, minimal catalog) from `OPTIONAL_GENERATORS` (opt-in via `-g`: extended catalog, docs, model) — the default set is reserved for output that needs no user-specific configuration.

---

# Discover / AI-Assisted Discovery

Location: `structifact/discover.py`, `structifact/llm.py`

* **`structifact discover <data.csv>`** — deterministic. Infers types, nullability, and a conservative "possible key" hint from raw sample rows. Handles common messiness: null placeholders (`NULL`/`N/A`/`-`), leading-zero identifiers kept as strings. Always writes a clearly-labeled draft; never auto-validates or auto-generates from it.
* **`--ai`** — adds LLM-assisted field descriptions. Off by default; shows a cost estimate and requires confirmation (or `-y`) before any real request; declining makes zero API calls (verified in tests).
* **`--requirements <file> --ai`** — extracts a draft schema from a freeform requirements document (tables, prose, bullets, or a mix). Always requires `--ai` (no deterministic path exists for freeform text). Fields whose value is derived from others are flagged `computed: true` with the raw logic preserved as text, not translated to SQL automatically. Anything structurally unplaceable (join keys, cross-field business rules, deprioritization notes) goes into an `unresolved_notes` list rather than being silently dropped.

`llm.py` provides a provider-agnostic `LLMClient` interface (not Anthropic-locked by design), a `FakeLLMClient` for tests, and `AnthropicLLMClient` (bring-your-own API key via `ANTHROPIC_API_KEY`, never hardcoded).

---

# Command Line Interface

Location: `structifact/cli.py`, `structifact/__main__.py`

Five commands:

```bash
structifact validate <spec.yml>
structifact generate <spec.yml> [-o output_dir] [-g generator_names]
structifact discover <data.csv|requirements.md> [--ai] [--requirements] [-y] [-n sample_size] [-o output]
structifact validate-data <spec.yml> <data.csv> [--ref alias=schema.yml:data.csv ...]
structifact deps <spec.yml> [<spec.yml> ...]
```

`validate-data`'s `--ref` flag is repeatable (multiple foreign-key targets can each get their own `--ref`). A missing `--ref` for a declared `foreign_key` constraint is a hard error, printed distinctly from the data-quality report — never silently skipped, never mixed into "issues found" output.

`deps` accepts one or more explicit dataset file paths (no directory/glob scanning in v1, matching every other command's explicit-path convention), loads and validates each individually, then resolves them as a collection — printing either a deterministic execution order or a dependency-resolution error (missing reference, duplicate dataset name, or circular dependency).

---

# Testing

Location: `tests/` — 307 tests across 34 files, covering the type system, all three adapters, IR construction, validation (metadata well-formedness and relationship checks), every generator, `discover`'s inference logic (deterministic and AI-assisted, with `FakeLLMClient`), `quality.py` (all three Phase 6 increments, including deliberately-not-flagged edge cases like unparseable numeric values and missing-value ownership), dataset dependency tracking (per-dataset validation, collection-level graph building, cycle detection, deterministic ordering, and CLI-level behavior), and CLI command behavior end to end.

CI runs the full suite via GitHub Actions on Python 3.11 and 3.12 on every push/PR against `main`.

---

# Current Workflow

Three independent flows now exist.

**Metadata → artifacts** (the original flow):

```text
Metadata (YAML/CSV/Excel)
        |
        v
     Adapter
        |
        v
Internal Representation
        |
        v
     Validation
        |
        v
     Generators
        |
        v
 Generated Artifacts (SQL, dbt YAML, catalog, docs, model SQL)
```

**Schema + real data → quality report** (Phase 6):

```text
Schema (validated as above)  +  Real data (CSV)  [+ referenced dataset(s), for FK checks]
                              |
                              v
                        quality.py
                              |
                              v
                       QualityResult
                              |
                              v
                     CLI report formatting
```

**Multiple schemas → execution order** (Phase 7 remainder):

```text
Multiple Schemas (each validated as above)
        |
        v
  dependencies.py
  (graph + cycle check)
        |
        v
Deterministic Execution Order
   (or a dependency error)
```

A fourth, separate flow exists for bootstrapping metadata that doesn't exist yet:

```text
Raw Data (CSV) or a Requirements Document
        |
        v
Deterministic Inference / AI-Assisted Extraction
        |
        v
Draft YAML (clearly labeled, not authoritative)
        |
        v
Human Review
        |
        v
(only then) enters the flows above
```

---

# Currently Supported Concepts

✓ Metadata-driven dataset definitions (YAML/CSV/Excel)
✓ Adapter-based architecture, all three formats at parity
✓ Internal representation, including multi-source datasets (joins, dedup)
✓ Type normalization and inference
✓ Metadata validation (well-formedness + relationship checks)
✓ Six generators (SQL, dbt YAML, 2 catalog variants, docs, transformation model)
✓ Deterministic and AI-assisted schema/requirements discovery
✓ Real-data quality checking (required, uniqueness, accepted values, range, pattern, foreign key)
✓ Cross-dataset dependency declaration, cycle detection, and execution ordering
✓ Five-command CLI
✓ 307 automated tests, CI-enforced

---

# Not Currently Implemented

* Data-type validation (confirming a "decimal" field's actual values parse as numbers at all) — deliberately deferred; see `quality.py`'s range check
* Composite (multi-column) foreign keys, or join/dedup shapes beyond what real examples have needed
* Cross-dataset value resolution — one dataset consuming another's computed/resolved value, e.g. an FX-rate lookup with conditional fallback (two real examples motivate this; deliberately kept out of Phase 7's dependency-tracking milestone — see `FUTURE_WORK.md`)
* Data warehouse execution (Snowflake/BigQuery/Databricks/PostgreSQL)
* Pipeline orchestration (Prefect/Airflow/Dagster)
* Data lineage (rendered graphs/visualization, impact analysis) — though `dependencies.py`'s dependency graph is now real structural groundwork this could build on
* A documentation *site* or metadata catalog beyond per-dataset Markdown
* A plugin architecture beyond the existing adapter/generator registries
* A GUI or hosted product at structifact.com

---

# Current Development Direction

With Phase 6 (Data Quality Framework) and Phase 7 (Transformation Framework, including its dependency-tracking remainder) both now complete end to end, the next real work is expected to come from wherever a concrete need surfaces next — consistent with how every phase so far actually got scoped (a real example first, not a plan written in the abstract). See `ROADMAP.md`'s "Recently Completed" section for the full, current list of what's shipped, and `FUTURE_WORK.md` for longer-term exploratory ideas not yet scoped into any phase.

---

# Implementation Philosophy

Unchanged: explicit abstractions, small composable components, stable interfaces, deterministic behavior, testability. What's different now is the track record — every significant IR addition (computed fields, FK/check constraints, sources/joins/dedup, each Phase 6 increment, dataset dependency tracking) went through the same real-example-first, paper-contract-before-code discipline, with cross-review and end-to-end verification before being called done. See `DECISION_HISTORY.md`.

> Define structure once. Generate reliable systems from it.
