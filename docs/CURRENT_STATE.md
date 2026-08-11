# CURRENT_STATE.md

# Structifact Current State

**Project:** Structifact
**Subtitle:** Schema-Driven Data Engineering Framework
**Repository:** github.com/michaelslewis/structifact
**Domain:** structifact.com

---

# Purpose

This document describes the current state of Structifact.

It serves as the reference point for continued development by documenting:

* what has been implemented
* current repository structure
* existing architectural foundations
* completed milestones
* known limitations
* immediate next steps

This document intentionally separates current reality from future vision. See `ROADMAP.md` for planned work and `FUTURE_WORK.md` for longer-term exploratory ideas.

---

# Current Project Status

Structifact has moved well past the initial framework-foundation stage. The core pipeline — adapters, IR, validation, and generation — is implemented, tested (279 tests passing, CI-enforced on Python 3.11/3.12), and has been exercised against real, non-trivial examples, not just the golden path.

Beyond the original schema-definition/generation pipeline, Structifact now also:

* infers draft schemas from raw data and from freeform requirements documents (with optional LLM assistance)
* validates real data rows against a dataset's declared rules — not just the metadata's own well-formedness
* checks foreign-key relationships across two datasets' real data

The framework is not a production data platform and isn't intended to become one in the near term. The current objective remains a strong, trustworthy architectural foundation, now with several genuinely complete capability areas rather than only foundational scaffolding.

---

# Completed Work

## Project Foundation

* Repository created and organized; Python package structure established; `pyproject.toml` packaging.
* GitHub Actions CI running the full test suite on every push/PR against `main` (Python 3.11 and 3.12).
* `AGENTS.md` at repo root — working rules for AI assistants, including known project-specific traps.
* `examples/customers/` — golden-path example (input → validate → generate, both YAML and CSV input shown).
* Project domain registered: `structifact.com` (not deployed; deliberately deferred — see `ROADMAP.md`).
* Versioned releases: v0.3.0 tagged and published as a real GitHub Release.

---

# Current Repository Structure

```text
structifact/                        (repo root)
│
├── examples/
│   ├── customers/                  golden-path example
│   │   ├── customers.yml
│   │   ├── customers.csv
│   │   └── generated/
│   ├── enterprise_demo/            synthetic wholesale-order example
│   │   (REQUIREMENTS.md, wholesale_order_source.sql/yml,
│   │    int_fx_rate_lookup.sql/yml, catalog.csv)
│   ├── workorder_demo/             synthetic work-order example
│   │   (REQUIREMENTS_workorder.md, work_order_source.sql/yml,
│   │    work_order_catalog.csv, work_order_source.discovered.yml)
│   └── data_quality_demo/          Phase 6 example
│       (orders_data.yml/csv, dq_customers.yml/csv)
│
├── structifact/
│   ├── cli.py                      validate / generate / discover / validate-data
│   ├── __main__.py
│   ├── ir.py                       DatasetSpec / FieldSpec / ConstraintSpec /
│   │                               SourceRef / JoinSpec / DedupRule
│   ├── types.py
│   ├── utils.py
│   ├── validation.py
│   ├── quality.py                  Phase 6: real-data checking (new subsystem,
│   │                               not a Generator)
│   ├── discover.py                 schema/requirements inference
│   ├── llm.py                      provider-agnostic LLM client
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
│       └── model.py                Phase 7 first step: SELECT-based
│                                   transformation model
│
├── tests/                          (32 files, 279 tests)
├── docs/                           this document and its siblings
├── pyproject.toml
├── README.md
└── LICENSE
```

Note: `structifact/parser.py`, referenced in earlier drafts of this document, was removed early on as dead code — adapters construct IR objects directly; there is no separate parsing stage.

---

# Implemented Components

## Metadata Layer

Datasets are defined declaratively via YAML (canonical), CSV, or Excel — all three normalize through the shared type system (`structifact/types.py`) rather than each implementing their own type-mapping.

A dataset definition can now express, well beyond the original name/fields/types:

* per-field `role` (dimension/measure), `accepted_values`, `nullable`
* computed/derived fields (`computed`, `expression`, `depends_on`)
* value-level data-quality rules (`min_value`, `max_value`, `pattern`)
* cross-source field attribution (`source`, `source_column`) for datasets that join in other sources
* dataset-level `source_table`, `sources` (`SourceRef`), and `joins` (`JoinSpec`) — a dataset can be built from more than one physical source, including the same physical table joined in multiple times under different roles, each with its own filter and a priority-based dedup rule (`DedupRule`)
* constraints: `primary_key`, `unique`, `foreign_key` (with `target_table`/`target_column`), `check` (with `expression`)

---

## Adapter Architecture

Implemented adapters: YAML (primary/canonical), CSV, Excel — all three at parity on every `FieldSpec` attribute, including the Phase 6 v2 additions (`min_value`/`max_value`/`pattern`).

---

## Intermediate Representation

`structifact/ir.py` holds `DatasetSpec` / `FieldSpec` / `ConstraintSpec`, plus the sources/joins additions (`SourceRef`, `JoinSpec`, `DedupRule`). This is now a substantially larger IR than the original "table + fields" model — see `ARCHITECTURE.md` for the full shape and the reasoning behind each addition.

---

## Validation Framework

`structifact/validation.py` validates a dataset's *metadata* — schema well-formedness, constraint relationships, and (new) genuinely checkable rule content: a `pattern` must compile as valid regex, `min_value` must not exceed `max_value`, range/pattern rules must apply to a compatible field type, and `sources`/`joins`/`foreign_key` relationships must resolve to something real within the dataset's own metadata.

This is distinct from — and a prerequisite for — the newer `quality.py` subsystem, which checks real *data* against that already-validated metadata.

---

## Data Quality Framework (Phase 6 — new since the last full rewrite of this document)

`structifact/quality.py` is a genuinely new subsystem, not a `Generator` (a `Generator` takes one input — a schema — and returns one artifact; checking real data needs a schema *and* a data file, so it doesn't fit that contract). Exposed via a new CLI command, `structifact validate-data`.

Implemented, in three shipped increments:

* **v1** — required fields (reusing `nullable: false`), uniqueness (reusing `primary_key`/`unique` constraints), accepted values (reusing `accepted_values`) — checked against real CSV data rows for the first time. A missing value is an empty CSV field; uniqueness/accepted-values checks skip missing values (required-field validation owns that case, avoiding double-reporting).
* **v2** — range (`min_value`/`max_value`, inclusive bounds, stored as `Decimal` not `float` to avoid precision artifacts) and pattern (regex, full-match semantics) validation. A present-but-unparseable numeric value is deliberately *not* reported as a range violation — that's a distinct, not-yet-built type-validation concern, kept as its own code path rather than silently folded in.
* **v3** — foreign-key/relationship validation against a second dataset's real data, via `--ref alias=schema.yml:data.csv`. Schema-aware: the referenced schema is itself loaded and validated, its declared dataset name must match the `--ref` alias, and `target_column` must be a real declared field — never inferred from a bare CSV header. A missing or misconfigured `--ref` is a hard configuration error, never silently reported as "no issues found." Existence/membership only — a duplicate value on the *target* side is the target dataset's own uniqueness concern, not this check's.

All three report structured `QualityIssue`/`QualityResult` data; human-readable formatting lives entirely in `cli.py`, so a future `--format json` (not yet built) wouldn't require touching the checking logic.

---

## Discover / AI-Assisted Discovery

`structifact discover` infers a draft schema from raw CSV sample data — deterministic, no AI, always writes a clearly-labeled draft for human review. `--ai` adds optional LLM-assisted field descriptions (off by default, cost-estimated, confirmed before any request; declining makes zero API calls). `discover --requirements <file> --ai` extracts a draft schema from a freeform requirements document (multi-column tables, prose, terse bullets, or a mix) — always requires `--ai`, since there's no deterministic way to parse freeform text.

AI assistance is entirely optional and bring-your-own-key: `structifact/llm.py` defines a provider-agnostic `LLMClient` interface (not locked to one vendor), with `AnthropicLLMClient` reading an `ANTHROPIC_API_KEY` environment variable — never a hardcoded key — and a `FakeLLMClient` used in tests so the test suite needs no real network access or API key. Every non-AI Structifact command works with zero setup and zero network access.

---

## Generator Framework

`structifact/generators/` — `SQLGenerator` (type-aware DDL, now including `FOREIGN KEY`/`CHECK` constraint emission), `DBTYAMLGenerator`, two catalog generators (minimal, run by default; extended, opt-in), `DocsGenerator` (Markdown, opt-in), and `ModelGenerator` (Phase 7 first step — emits a real, executable `SELECT` for a dataset's computed fields and joined-in sources, qualifying every column reference by its source; distinct from `SQLGenerator`, which only ever emits schema DDL).

`Generator.generate()` may now return `None` to mean "nothing to generate for this dataset" (e.g. `ModelGenerator` on a dataset with no computed fields and no joins) — the CLI's `generate` loop skips writing when that happens, rather than every generator being required to always produce an artifact.

---

## CLI

`structifact/cli.py` — four commands: `validate`, `generate` (`-g/--generators`), `discover` (`--ai`, `--requirements`, `-y`), and `validate-data` (`--ref`, repeatable).

---

# Current Technology Stack

**Implemented:** Python, YAML, SQL, Git, pytest, GitHub Actions. Optional: `pandas`/`openpyxl` (Excel adapter), Anthropic API (opt-in LLM assistance).

**Under consideration for future work, not yet dependencies:** DuckDB, Apache Parquet, dbt (as an execution engine — Structifact currently *generates* dbt-shaped YAML, it doesn't run dbt), Snowflake, Prefect, and other warehouse/orchestration integrations.

---

# Current Limitations

Structifact still does not provide:

* production ingestion pipelines or cloud/warehouse execution
* orchestration
* automated lineage generation or a documentation *site* (only per-dataset Markdown via `DocsGenerator`)
* a GUI or hosted product (structifact.com remains unregistered-but-undeployed by design)
* a plugin architecture (the existing adapter/generator registries are still the extension mechanism)
* data-type validation (verifying a "decimal" column's values are actually numeric at all) — deliberately deferred; range/pattern checking in `quality.py` skips values that fail to parse rather than flagging them
* composite (multi-column) foreign keys, joins, or dedup rules beyond what's already scoped — the IR intentionally supports only the shapes real examples have needed so far

These are documented, deliberate scope boundaries, not oversights — see `ROADMAP.md`/`FUTURE_WORK.md` for what's actually planned next versus what's exploratory.

---

# Immediate Development Focus

Phase 6 (Data Quality Framework) is now complete end to end (v1/v2/v3), matching its original scope in `ROADMAP.md`. Per the project's own YAGNI discipline, the next step is *not* an automatic Phase 6 v4 — future data-quality work should come from a real, concrete need, the same way v1/v2/v3 each did.

Open threads:

* **Transformation Framework, remainder of Phase 7** — dependency graphs and execution ordering across *datasets* remain unstarted (the "one computed field" and "sources/joins within one dataset" pieces are both done).
* Longer-term, deliberately deferred: VS Code extension, structifact.com deployment/GUI (see `FUTURE_WORK.md`).

---

# Current Development Philosophy

Unchanged from earlier versions of this document: the priority is a trustworthy architecture over feature quantity. What has changed is that this philosophy now has a real track record behind it — every non-trivial IR addition this project has made (computed fields, FK/check constraints, sources/joins, each Phase 6 increment) went through the same sequence: a real example first, a minimal paper contract, review, then implementation with tests verified end-to-end before being considered done. See `DECISION_HISTORY.md` for specific instances of this.

---

# Summary

Structifact currently represents a working metadata-driven framework: adapters normalize three input formats into a shared IR; validation checks that IR's own well-formedness; generators produce SQL, dbt-shaped YAML, catalogs, docs, and (for datasets with computed fields or joins) real executable transformation SQL; `discover` can bootstrap a draft schema from raw data or a freeform requirements document, optionally AI-assisted; and `validate-data` checks real data rows — including across two related datasets — against everything the schema declares.

The project has moved from "architectural design" through "deeper implementation" into what's now a genuinely complete first version of several major capability areas, not just scaffolding for them.
