Structifact Architecture

Overview

Structifact is a metadata-driven data engineering framework designed to convert declarative dataset definitions into validated internal models, reusable engineering artifacts, and — as of more recent work — real checks against actual data.

The central architectural pattern is:

Input Metadata
       |
       v
Adapters
       |
       v
Intermediate Representation (IR)
       |
       +----------------+
       |                |
       v                v
 Validation        Generators
                        |
                        v
               Generated Artifacts

A second, separate pattern checks real data against that same IR:

Metadata + Real Data
       |
       v
Data Quality Engine (structifact/quality.py)
       |
       v
Structured Quality Result
       |
       v
CLI Report Formatting

A third, separate pattern resolves how multiple datasets relate to each other:

Multiple Schemas (each independently valid)
       |
       v
Dependency Resolution Engine (structifact/dependencies.py)
       |
       v
Deterministic Execution Order (or a dependency error)

The architecture separates:

how metadata enters the system
how datasets are represented internally
how rules are applied to metadata
how artifacts are generated
how real data is checked against metadata
how multiple datasets relate to and depend on each other

This separation allows Structifact to evolve without tightly coupling individual components.

The core architectural principle is:

Define structure once. Generate reliable systems from it.

Core Architectural Principles
Metadata First

Metadata is the source of truth for Structifact.

Dataset definitions should capture structural information once and allow the framework to derive behavior from that definition.

Metadata concepts include:

datasets
fields
data types
descriptions
constraints
relationships (including cross-dataset foreign keys, a dataset's own upstream sources/joins, and a dataset's dependencies on other Structifact-defined datasets)
validation rules (including value-level rules — range, pattern)
generation inputs

Structifact should avoid requiring the same information to be manually recreated across multiple systems.

Declarative Over Imperative

Users describe the desired structure and intent.

Example:

dataset:
  name: customers

fields:
  - name: customer_id
    type: integer

The framework determines how that metadata should be interpreted.

This approach provides:

consistency
repeatability
easier maintenance
reduced duplication

Explicit Over Magic

Automation should remain understandable.

A user should be able to determine:

what metadata was interpreted
what artifacts were generated
why validation succeeded or failed
where generated behavior originated
why a data-quality check passed or failed, and against what rule
why a dependency resolution succeeded, failed, or reported a cycle

Generated outputs should remain human-readable.

Structifact should automate repetitive engineering work without hiding engineering decisions. This is also why `structifact discover` — the schema-inference command — always writes a clearly-labeled draft for human review rather than treating any inferred value as real metadata, why catalog generators never fabricate values (like a `pii` flag or `changed_by` name) that the IR has no actual way of knowing, why `structifact validate-data` treats a missing or misconfigured `--ref` for a declared foreign-key relationship as a loud configuration error rather than a silently-skipped check, and why `structifact deps` reports the complete cycle in its error message (`dataset_a -> dataset_b -> dataset_c -> dataset_a`) rather than a bare "circular dependency exists" — a quiet or vague failure would be exactly the kind of hidden behavior this principle exists to prevent.

Reliability Before Cleverness

Structifact prioritizes predictable behavior over complex automation.

Preferred characteristics:

deterministic results
clear errors
inspectable outputs
simple abstractions
maintainable implementations

A smaller reliable framework is preferred over a larger framework with opaque behavior. This is why `structifact/quality.py`'s range-checking deliberately does not attempt to interpret a value that fails to parse as a number — that's treated as a distinct, not-yet-built type-validation concern, not folded silently into range logic that wasn't designed for it. The same instinct shaped `structifact/dependencies.py`: execution order is deterministic (stable given the same input), but the framework deliberately does NOT claim the relative order of two mutually-independent datasets is semantically meaningful — overclaiming precision here would be its own kind of unreliability.

Separation of Concerns

Each component has a specific responsibility.

The architecture maintains clear boundaries:

Input Formats
      |
      v
Adapters
      |
      v
Intermediate Representation
      |
      v
Validation (metadata well-formedness)
      |
      v
Generators          Data Quality Engine     Dependency Resolution Engine
      |                     |                          |
      v                     v                          v
Output Artifacts    Quality Report              Execution Order
                  (against real data)         (across a collection)

Components should collaborate through stable interfaces rather than depending on implementation details.

Architecture Components
Adapter Layer

Location:

structifact/adapters/

The adapter layer handles external metadata formats. Each adapter is responsible for loading a source format and constructing IR objects (`DatasetSpec` / `FieldSpec` / `ConstraintSpec`, plus `SourceRef`/`JoinSpec` where applicable) directly — there is no separate parsing stage between an adapter and the IR.

Responsibilities:

loading source definitions
converting external formats into IR objects
isolating format-specific behavior

Current adapters:

YAML (`structifact/adapters/yaml.py`) — the primary/canonical format; supports the canonical `dataset:` contract, the legacy `table:` format, per-field `role`, value-level rules (`min_value`/`max_value`/`pattern`), cross-source attribution (`source`/`source_column`), dataset-level `sources`/`joins`/`depends_on`, and constraints including `foreign_key`'s `target_table`/`target_column` and `check`'s `expression`
CSV (`structifact/adapters/csv.py`) — a field-grid format; does not represent dataset-level `constraints`/`sources`/`joins`/`depends_on`, since a flat one-row-per-field CSV has no natural place for them
Excel (`structifact/adapters/excel.py`) — same field-grid shape as CSV, via `pandas`; normalizes pandas' blank-cell `NaN` representation to `None`

All three adapters normalize raw type strings through the shared type system (`structifact/types.py`) rather than each implementing their own type-mapping logic, and are kept at parity on field-level attributes (CSV/Excel do not yet support dataset-level `sources`/`joins`/`constraints`/`depends_on`, which remain YAML-only).

Future adapters may include: JSON, database metadata sources, cloud storage formats, API-based metadata sources.

Adapters should not contain business rules or generation logic.

Intermediate Representation (IR)

Location:

structifact/ir.py

The IR is the central abstraction in Structifact.

The purpose of the IR is to provide a stable internal model between external inputs and generated outputs.

The current IR concepts are:

DatasetSpec
    |
    +-- FieldSpec[]
    |
    +-- ConstraintSpec[]
    |
    +-- source_table
    +-- sources: SourceRef[]
    +-- joins: JoinSpec[]
    +-- depends_on: str[]

The IR separates:

external metadata formats
framework processing
generated artifacts
real-data checking
cross-dataset dependency relationships

This allows adapters, generators, the data quality engine, and the dependency resolution engine to evolve independently.

## Semantic Model vs Artifact Model

Structifact maintains a deliberate separation between semantic concepts and generated artifacts.

The semantic model describes meaning:

DatasetSpec
FieldSpec
ConstraintSpec
SourceRef / JoinSpec / DedupRule

The artifact model describes implementation outputs:

SQL (schema DDL, and separately, transformation-model SELECT SQL)
dbt metadata
catalog CSVs
documentation
lineage artifacts (future)

The data quality model describes a third thing — neither semantic definition nor generated artifact, but a *check* against real data:

QualityIssue / QualityResult

The dependency resolution model describes a fourth thing — not a property of any single dataset, but a *relationship* across a collection of them:

execution order (a list of dataset names)
a dependency-resolution error (unresolved reference, duplicate name, or a named cycle)

The IR should represent intent rather than implementation details.

For example:

```yaml
constraints:
  - type: primary_key
    columns:
      - customer_id
```

DatasetSpec

DatasetSpec is the canonical representation of a dataset definition.

A dataset represents a logical data object that Structifact can validate, generate artifacts from, check real data against, and relate to other datasets.

Conceptually:

DatasetSpec

name
description
metadata
fields[]
constraints[]
source_table
sources[]
joins[]
depends_on[]

Responsibilities:

represent dataset identity
contain field definitions
contain dataset-level rules
contain (optionally) the sources this dataset is assembled from, and the joins connecting them
contain (optionally) the names of other Structifact-defined datasets this one depends on
provide the primary object passed through validation, generation, quality-checking, and dependency-resolution workflows

Dataset Classification

Future versions may introduce dataset classification through a concept such as:

dataset:
  name: customers
  kind: table

Potential future dataset kinds:

table
event
source
model
snapshot

However, dataset classification is intentionally not part of the current implementation.

The IR should leave room for this extension without introducing behavior prematurely.

FieldSpec

FieldSpec represents intrinsic characteristics of a dataset field.

A field describes what a column is, and (now) what values it's allowed to hold.

Conceptually:

FieldSpec

name
type
description
nullable
role
accepted_values
length
precision
scale
computed / expression / depends_on
source / source_column
min_value / max_value
pattern
metadata

Responsibilities:

represent field identity
represent data type information
represent field-level metadata
represent value-level rules (Phase 6 v2)
represent cross-source attribution, for datasets assembled from multiple sources
support validation, generation, and data-quality checking

`role` (`dimension` | `measure`) is optional — fields without a role are still valid. When present, it's validated against the supported set and consumed by the catalog generators to classify columns in generated catalog output. It is never derived or inferred.

`accepted_values` (a list of strings) is likewise optional. Validation checks the declaration itself is well-formed (non-empty, no duplicates) — separately, `structifact validate-data` checks a field's actual data values against this list (Phase 6 v1). This resolved the deviation noted in earlier drafts of this document, where `accepted_values` was treated as a field property rather than a constraint by implementation — now that real data-row checking exists, keeping it on `FieldSpec` (rather than moving it to `ConstraintSpec`) reads as the right call: it's a property of the field's valid domain, evaluated per-field, not a relationship between fields or datasets.

`computed`/`expression`/`depends_on` represent a field whose value is derived from other fields. `expression` is assumed-valid SQL, inlined as-is by `ModelGenerator` (see below) — deliberately not the same thing as freeform business-logic text `discover --requirements --ai` extracts, which may be pseudocode rather than valid SQL as written. This field-level `depends_on` — a field's dependency on other *fields within the same dataset* — is a different concept from `DatasetSpec.depends_on` (see below), a dataset's dependency on other *datasets*. The two occupy different, unambiguous nesting positions in the YAML (inside a `fields:` entry vs. top-level), so the shared name doesn't create real ambiguity in practice.

`source`/`source_column` (Phase 7 — sources/joins milestone) represent cross-source attribution: which of a dataset's `sources` (if any) a field actually comes from, and under what column name there. Both default to `None`, meaning "the dataset's own primary source, same-name column" — the existing single-source behavior, unaffected for any dataset that doesn't use `sources`/`joins`.

`min_value`/`max_value`/`pattern` (Phase 6 v2) represent value-level data-quality rules, checked against real data by `structifact/quality.py`. Stored as `Decimal` (not `float`) for `min_value`/`max_value` — adapters convert via `Decimal(str(v))` rather than `Decimal(v)` directly, since a direct conversion would preserve a YAML-parsed float's exact binary representation rather than the clean decimal value a person actually wrote. Unlike most raw-fragment fields elsewhere in the IR, `pattern` is genuinely validated at metadata-validation time (`re.compile`) — a regex either compiles or it doesn't, no data required — and `min_value`/`max_value` ordering and type-compatibility are checked the same way.

FieldSpec should remain focused on characteristics inherent to the field itself.

Field Characteristics vs Constraints vs Dataset-Level Relationships

Structifact intentionally separates field properties from rules, and separates both from relationships between whole datasets.

Field properties:

name
type
nullable
role
accepted_values
description
computed / expression / depends_on
source / source_column
min_value / max_value
pattern

Constraints (relationships involving fields, within or across datasets):

primary key
unique
foreign key
check

Dataset-level relationships (relationships between whole datasets, not individual fields):

depends_on

This avoids allowing FieldSpec to grow into an unmanageable collection of flags. The line has held through every addition so far — every field property above genuinely describes something intrinsic to that field (what it is, what it may hold, where it comes from); everything describing a *relationship* went to `ConstraintSpec`, the new `SourceRef`/`JoinSpec` concepts, or (for the newest case — one dataset depending on another) directly onto `DatasetSpec` as `depends_on`, rather than being folded into `FieldSpec`.

ConstraintSpec

ConstraintSpec represents relationships and rules applied to datasets.

Conceptually:

ConstraintSpec

type
columns
target_table   (foreign_key only)
target_column  (foreign_key only)
expression     (check only)

Examples:

primary_key
unique
foreign_key
check

Constraints are separate because many database and business rules do not describe a field itself.

Example:

constraints:

  - type: foreign_key
    columns:
      - customer_id
    target_table: dq_customers
    target_column: customer_id

**Status**: `primary_key`, `unique`, `foreign_key`, and `check` are all fully supported end-to-end — validated, and emitted in generated SQL (`FOREIGN KEY (...) REFERENCES ...`, `CHECK (...)`). `foreign_key` currently supports single-column references only (composite FK is deliberately deferred until a real example needs it); `target_table`/`target_column` are free-text at the metadata-validation level (Structifact doesn't cross-reference another dataset's schema during `validate`), but ARE resolved and checked against a real, loaded, validated schema during `structifact validate-data` (see the Data Quality Engine section below) — that's where `target_table`/`target_column` finally become fully meaningful, not just accepted syntax.

A dataset may have at most one `primary_key` constraint — validation rejects a second one rather than silently allowing an ambiguous schema.

SourceRef / JoinSpec / DedupRule

Location: `structifact/ir.py` (Phase 7 — sources/joins milestone)

These three concepts let one dataset be assembled from more than one underlying source, including the same physical table referenced multiple times under different roles.

```text
SourceRef
    name             logical alias for this joined-in instance
    table            the physical table
    filter           optional raw SQL predicate scoping this instance
    dedup            optional DedupRule

JoinSpec
    source           a SourceRef.name
    on               raw SQL join condition
    type             left | inner

DedupRule
    partition_by     columns identifying a group
    order_by         priority order within the group; first entry wins
```

The `SourceRef.name` vs `.table` distinction is the reason this exists as three concepts rather than a simple table reference: `table` is the physical table; `name` is a logical alias for *this particular joined-in instance* of it. This is what lets the same physical table (e.g. a shared `partner_role` table) be joined into one dataset three separate times under three different roles (requested-by/billed-to/site-contact), each with its own `filter` and `dedup` rule — `name` is what `JoinSpec.source` and `FieldSpec.source` both refer to, never `table` directly.

`DedupRule` represents priority-based row selection, not a uniqueness constraint — given a group of rows sharing the same `partition_by` key(s), exactly one wins, chosen by `order_by` priority. Maps directly onto `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) = 1`, generated by `ModelGenerator` as its own CTE per source.

Like `expression` and `JoinSpec.on`, `SourceRef.filter` and `DedupRule.order_by` are raw SQL fragments — trusted as-is, not parsed or validated. What validation.py *does* check about `sources`/`joins`: `SourceRef.name` values are unique within a dataset, every `JoinSpec.source` resolves to a declared source, every `DedupRule` has non-empty `partition_by`/`order_by`, and `JoinSpec.type` is one of the currently-supported types (`left`/`inner`).

Important distinction: `sources`/`joins` describe how *one* dataset is physically assembled from underlying tables. `depends_on` (below) describes how *multiple Structifact-defined datasets* relate to each other. These look superficially similar (both are about "where does this dataset's data come from") but answer genuinely different questions — one is about raw table assembly within a dataset; the other is about ordering and relationships between whole datasets.

depends_on

Location: `structifact/ir.py` (Phase 7 remainder — dataset dependency tracking)

A plain `List[str]` on `DatasetSpec`, naming other Structifact-defined datasets this one depends on.

```text
DatasetSpec.depends_on: List[str]
```

Deliberately NOT a new dataclass (unlike `SourceRef`/`JoinSpec`/`DedupRule`) — no real example has yet shown a need for dependency-level metadata beyond a name; a bare list matches exactly what real examples and the original roadmap sketch both called for. Declaration only: says nothing about *how* this dataset obtains the other's data, only that the other must be processed first. See the Dependency Resolution Engine section below for what operates on this field.

TableSpec Compatibility Strategy

Historically, Structifact used:

TableSpec

as the primary IR object.

The long-term model evolved toward:

DatasetSpec

because "table" is too implementation-specific for future possibilities — a point since reinforced directly by the sources/joins work, where a single `DatasetSpec` can now represent output assembled from several underlying tables, not one.

`TableSpec` remains a plain alias for `DatasetSpec` in `ir.py`; no separate class exists.

Type System

Location:

structifact/types.py

The type system defines Structifact's understanding of data types.

Responsibilities:

normalizing external type names (`parse_type`, `normalize_type`)
inferring a likely type from raw sample values with no declared type (`infer_type_from_values`, used by `structifact discover`)
mapping source types into framework types
preserving type metadata
supporting validation and generation

Examples:

VARCHAR  -> string

INTEGER  -> integer

DECIMAL  -> decimal

`infer_type_from_values` is deliberately conservative: values that look numeric but have a leading zero (e.g. a zip code) are kept as `string` rather than risk silently corrupting an identifier, and common null placeholders (`NULL`, `N/A`, `-`, etc.) are recognized rather than only literal empty strings.

The type system should remain separate from the IR.

The type system answers:

What kind of data is this?

The IR answers:

What does this dataset look like?

Notably, the type system currently does NOT answer "is this real data value actually of this type" — `structifact/quality.py`'s range checking parses a real CSV value against `Decimal` for range comparison, but a value that fails to parse is simply not evaluated for range violations, rather than being reported as a type mismatch. Genuine data-type validation (confirming a "decimal" column's real values actually parse as numbers at all) remains unbuilt — see `ROADMAP.md`/`FUTURE_WORK.md`.

Validation Framework

Location:

structifact/validation.py

Validation operates against a single dataset's IR — checking metadata well-formedness, never real data (that's the Data Quality Engine, below) and never a whole collection of datasets against each other (that's the Dependency Resolution Engine, further below).

Current responsibilities:

dataset validation
field validation
supported type checks
role checks (when a field specifies `role`, it must be `dimension` or `measure`)
computed-field well-formedness (`computed` requires `expression`; `depends_on` entries must reference real fields in the same dataset; no self-reference)
value-level rule well-formedness (Phase 6 v2): `pattern` must compile as valid regex; `min_value` must not exceed `max_value`; `min_value`/`max_value` only apply to `integer`/`decimal` fields, `pattern` only to `string` fields
constraint validation, including `foreign_key` (exactly one column, non-blank `target_table`/`target_column`) and `check` (non-blank `expression`)
sources/joins relationship validation (Phase 7): unique source names, joins/fields resolve to declared sources, dedup rules are well-formed, join types are supported
dataset-level `depends_on` well-formedness (Phase 7 remainder): no blank entries, no duplicates, no self-reference — whether a referenced dataset actually *exists* is a collection-level question, deliberately left to the Dependency Resolution Engine, since answering it requires seeing more than one dataset at once
meaningful error reporting

Future validation capabilities may include:

data-type validation (see Type System, above)
schema compatibility / evolution checks
generated test suites

Data Quality Engine

Location:

structifact/quality.py

A genuinely separate subsystem from validation and generation — checking real data, which nothing else in Structifact does. Not a `Generator`: every `Generator` takes one input (a `DatasetSpec`) and returns one `Artifact`; checking real data needs a schema *and* a data file, and produces a structured result, not a written artifact.

Exposed via a CLI command, `structifact validate-data`.

```text
QualityIssue(rule, field, rows, value=None)
QualityResult(dataset, rows_checked, issues) -> .is_valid
```

`rule` is one of `required` / `uniqueness` / `accepted_values` / `range` / `pattern` / `foreign_key`. Issues are grouped by field (and offending value, where relevant) — never one issue per row.

`check_data(table, rows, referenced_values=None)` runs every rule a schema declares against real, in-memory-loaded CSV rows (no streaming; a deliberate scope decision). A consistent ownership rule governs every check: a missing value is reported exactly once, by `required` — every other check skips rows where the relevant value is missing, rather than double-reporting the same underlying problem.

`resolve_references(table, refs)` (Phase 6 v3) resolves a schema's `foreign_key` constraints against caller-supplied reference data, producing the `referenced_values` `check_data` needs. Schema-aware and deliberately strict: every failure here is a `ValueError` (a configuration/usage error, never a `QualityIssue`) — a missing `--ref`, a `--ref` alias that doesn't match the referenced schema's own declared name, or a `target_column` that isn't actually declared on the referenced schema, are all caught here rather than silently producing wrong or misleading results.

```text
Schema A (+ real data)         Schema B (+ real data), via --ref
        |                              |
        +--------------+---------------+
                        |
                        v
              resolve_references()
                        |
                        v
                  check_data()
                        |
                        v
                 QualityResult
                        |
                        v
              CLI report formatting
```

All formatting of `QualityResult` into human-readable text lives in `cli.py` — `check_data`/`resolve_references` never call `print()`, keeping the door open for a future `--format json` without touching the checking logic.

Dependency Resolution Engine

Location:

structifact/dependencies.py

A third genuinely separate subsystem, following the same precedent as the Data Quality Engine above: it operates on a *collection* of `DatasetSpec`s, which is a different question from either single-dataset validation or single-dataset-plus-data-file quality checking. Not a `Generator`, and not part of `validation.py`.

Exposed via a CLI command, `structifact deps`.

`build_dependency_graph(datasets)` builds a `{name: [depends_on names]}` mapping from a collection. Raises `ValueError`, listing every problem found (not just the first), if two datasets share a name, or if any `depends_on` entry doesn't resolve to a dataset in the collection.

`execution_order(datasets)` returns a deterministic list of dataset names, ordered so every dataset appears after all of its dependencies — using a DFS-based topological sort, tie-broken by input order among datasets with no dependency relationship to each other. That relative order is explicitly NOT claimed to be semantically meaningful, only kept stable so output doesn't vary run-to-run (see "Reliability Before Cleverness" above). Raises `ValueError` (never a partial order) on anything `build_dependency_graph` would raise, or on a circular dependency — the message names the complete cycle.

```text
Multiple Schemas (each independently valid)
        |
        v
  build_dependency_graph()
   (duplicate names, unresolved
    references -> ValueError)
        |
        v
     execution_order()
   (cycle detection -> ValueError;
    otherwise a deterministic order)
        |
        v
  CLI report formatting
```

Deliberately scoped to declaration and ordering only. Does NOT resolve what value a dependent dataset actually obtains from its dependency, and does NOT generate any SQL expressing that relationship — see "Transformation Framework — Remaining Scope" below for why that's explicitly separate, still-future work rather than part of this engine.

Generator Framework

Location:

structifact/generators/

Generators transform IR objects into engineering artifacts.

Current generator concepts:

DatasetSpec
      |
      v
Generator
      |
      v
Artifact  (or None — see below)

Current generators:

SQL generation (`sql.py`) — type-aware DDL; maps normalized types to real SQL types (`INTEGER`, `TIMESTAMP`, `DECIMAL(precision,scale)`, etc.), emits `NOT NULL`, `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`. A computed field's `expression` is documented as a SQL comment, never emitted as executable syntax — this generator produces schema DDL, not a transformation query.
dbt-compatible YAML generation (`dbt_yaml.py`)
Catalog CSV generation (`catalog.py`) — a minimal catalog (name, description, role, type, length) using only what the IR actually knows; run by default
Extended catalog CSV generation (`catalog_extended.py`) — a richer catalog matching a specific downstream tool's expected column set. Fields the IR has no way to know (`pii`, `comments`) are always blank rather than guessed; `changed_by` is explicitly configurable; `changed_on` is a real generation timestamp. Not run by default.
Documentation generation (`docs.py`, `DocsGenerator`) — per-dataset Markdown rendering every metadata attribute a field actually has; never fabricates. Not run by default.
Transformation-model generation (`model.py`, `ModelGenerator`, Phase 7 first step) — emits a real, executable `SELECT`, not DDL. For a dataset with `sources`/`joins`, builds the necessary CTEs (including `ROW_NUMBER()`-based dedup per `DedupRule`) and qualifies every column reference by its source alias. Returns `None` — not an `Artifact` — for a dataset with no computed fields and no sources/joins, since there's nothing to transform. Not run by default.

`Generator.generate()` may return `None` to mean "nothing to generate for this dataset" — a real, deliberate loosening of the original contract (documented in `generators/base.py`), which required `cli.py`'s `generate` loop to check for `None` and skip writing, rather than every generator being required to always produce output.

Future generators may include: lineage metadata, warehouse-specific artifacts, configuration files.

Generators should consume IR objects rather than directly reading YAML or other source formats.

Registry Pattern

Adapters and generators use registry concepts.

Locations:

structifact/adapters/registry.py
structifact/generators/registry.py

The generator registry distinguishes two sets:

`GENERATORS` — run by default on every `structifact generate`. Reserved for generators whose output shape requires no user-specific configuration (SQL, dbt YAML, the minimal catalog).
`OPTIONAL_GENERATORS` — available, but not run unless explicitly requested via `structifact generate -g <name>`. Reserved for generators that depend on assumptions Structifact cannot make for every user (the extended catalog generator, docs, and the transformation model — the last of these also because it's the newest, and shouldn't silently change existing default output for anyone).

This split exists because Structifact cannot know what any given user's downstream tooling requires — adding a new org-specific output format means writing one more small generator and deciding which set it belongs in, not teaching the framework to guess.

Registries provide extensibility points for supported components. This allows future additions without modifying the framework core. Six generators and three adapters have now been added through this pattern without needing anything more elaborate (see Plugin Architecture in `FUTURE_WORK.md` for the explicit decision to keep it this way until it proves insufficient).

Command Line Interface

Locations:

structifact/cli.py
structifact/__main__.py

The CLI is the primary user interaction boundary.

Current commands:

structifact validate examples/customers/customers.yml

Output:

✓ Loaded metadata
✓ Parsed 2 fields
✓ Valid schema
✓ No constraint violations

structifact generate examples/customers/customers.yml [-o output_dir] [-g generator_names]

Runs the default generator set, or an explicitly selected subset via `-g` (comma-separated generator names). An unknown name lists what's available rather than failing silently.

structifact discover some_data.csv [-o output.yml] [-n sample_size] [--ai] [-y]
structifact discover requirements.md --requirements --ai [-y]

Infers a draft schema from raw CSV sample data, or extracts one from a freeform requirements document (always requires `--ai` for the latter — no deterministic path exists for freeform text). Writes to a file for human review. Never validates or generates from the draft automatically. `--ai` is off by default, shows a cost estimate, and requires confirmation (or `-y`) before any real request.

structifact validate-data schema.yml data.csv [--ref alias=schema.yml:data.csv ...]

Checks real data against the schema's declared rules — see Data Quality Engine above. `--ref` is repeatable, for schemas with more than one `foreign_key` target. A missing `--ref` for a declared `foreign_key` constraint is a hard configuration error, printed distinctly from the data-quality report.

structifact deps schema_a.yml schema_b.yml [schema_c.yml ...]

Loads and validates each dataset file individually, then resolves them as a collection — see Dependency Resolution Engine above. Prints a deterministic execution order, or a dependency-resolution error (unresolved reference, duplicate dataset name, or a named circular dependency). Accepts explicit file paths only, matching every other command's convention — no directory/glob scanning in v1.

The CLI should expose framework capabilities without hiding underlying behavior.

Current Data Flow

A Structifact schema/generation workflow follows:

1. Metadata Definition
2. Adapter Loading
3. IR Construction (DatasetSpec + FieldSpec[] + ConstraintSpec[], and where applicable SourceRef[]/JoinSpec[]/depends_on)
4. Validation (metadata well-formedness)
5. Generation

```text
DatasetSpec
      |
      v
  Generators
      |
      v
Engineering Artifacts
```

A separate, parallel flow checks real data against an already-validated schema:

```text
DatasetSpec (validated)  +  Real Data (CSV)  [+ --ref dataset(s), for FK checks]
        |
        v
  Data Quality Engine
        |
        v
   QualityResult
        |
        v
  CLI Report Formatting
```

A third, separate flow resolves how multiple already-validated schemas relate to each other:

```text
Multiple DatasetSpecs (each validated as above)
        |
        v
  Dependency Resolution Engine
        |
        v
Deterministic Execution Order
  (or a dependency error)
        |
        v
  CLI Report Formatting
```

A fourth, separate flow exists for schema discovery from raw data or a requirements document with no existing metadata:

```text
Raw Sample Data (CSV) or a Requirements Document
        |
        v
Deterministic Inference / AI-Assisted Extraction (structifact/discover.py)
        |
        v
Draft YAML (clearly labeled, not authoritative)
        |
        v
Human Review
        |
        v
(only then) Adapter Loading, as in the flow above
```

Testing Architecture

Testing is a core design requirement.

Current test areas include type system behavior, adapter behavior (per format), IR construction, validation rules (both well-formedness and sources/joins/constraint/depends_on relationships), each generator, the data quality engine (`quality.py` — all three Phase 6 increments, including deliberately-not-flagged edge cases like unparseable numeric values), the dependency resolution engine (`dependencies.py` — per-dataset validation, collection-level graph building, cycle detection, deterministic ordering, and CLI-level behavior), `discover`'s inference logic (deterministic and AI-assisted, via `FakeLLMClient`), and CLI command behavior — 307 tests across `tests/` as of this writing, CI-enforced on Python 3.11 and 3.12.

A design that is difficult to test is considered a design problem.

One process lesson worth recording here: a passing unit test suite once proved the `foreign_key`/`check` constraint logic was correct in `ir.py`/`validation.py`/`sql.py`, while a real bug meant it was silently unusable via any actual YAML file — `yaml.py`'s constraint parsing never read `target_table`/`target_column`/`expression` from a file, only from directly-constructed `ConstraintSpec` objects in tests. The bug was only found by running the real CLI against a real file, not by the test suite. A related lesson surfaced again during dependency-tracking development: a cyclic test fixture's own comments claimed a specific 3-node cycle shape that its actual `depends_on` edges didn't encode — caught by re-examining test output against its own stated intent, not by the test passing or failing. See `DECISION_HISTORY.md` for both full accounts — the practical takeaway is that end-to-end verification against real files, and real scrutiny of what a test actually asserts, both remain part of "done," not optional once unit tests pass.

Future Architectural Direction

The current architecture intentionally leaves room for future expansion.

AI-Assisted Metadata Discovery

Both halves of this are now implemented. `structifact discover` infers a draft schema (types, nullability, key/format hints) from raw sample data using no AI. `discover --ai` and `discover --requirements --ai` add optional LLM-assisted suggestions (field descriptions, and full draft extraction from a freeform requirements document respectively) on top of that:

Unknown Dataset
        |
        v
Deterministic Inference (implemented)
        |
        v
LLM-Assisted Discovery (implemented — discover --ai, discover --requirements --ai)
        |
        v
Suggested Metadata Contract
        |
        v
Human Review and Approval
        |
        v
Structifact IR
        |
        v
Validation + Generation

`structifact/llm.py` provides a provider-agnostic `LLMClient` interface (not Anthropic-locked by design), a `FakeLLMClient` for tests (no real network/API key needed to run the suite), and `AnthropicLLMClient` (bring-your-own-key via `ANTHROPIC_API_KEY`, never hardcoded). Every AI request is cost-estimated and requires explicit confirmation (or `-y`) first; declining makes zero API calls, verified in tests, not just documented.

What remains future work: column classification beyond dimension/measure, validation-rule *recommendations* (as distinct from the deterministic rule-checking `quality.py` already does), and AI-assisted documentation (`DocsGenerator` is fully deterministic today).

AI should create suggestions, not replace the metadata contract. The approved metadata model remains authoritative. Structifact remains fully functional without any AI-assisted feature (with the sole, structural exception of `discover --requirements`, which has no non-AI path by the nature of freeform text — not a compromise on this principle).

Transformation Framework — Remaining Scope

Done, matching the phase's originally planned scope. A single computed field can be represented and actually emitted as executable SQL (`ModelGenerator`); a dataset can be assembled from multiple sources — including the same physical table joined in multiple times under different roles with priority-based deduplication (`SourceRef`/`JoinSpec`/`DedupRule`); and a dataset can declare dependencies on other Structifact-defined datasets, resolved into a deterministic execution order with cycle detection (`DatasetSpec.depends_on`, the Dependency Resolution Engine above).

What remains, deliberately kept separate from this milestone: cross-dataset *value resolution* — one dataset actually consuming another's computed/resolved value (not just knowing it must run after it), e.g. joining a lookup dataset with conditional-fallback logic. Two real synthetic examples (`examples/enterprise_demo`, `examples/workorder_demo`) both motivate this via an FX-rate-lookup pattern, which is real evidence it recurs — but consistent with how every other IR addition in this project has been scoped, it should wait for a decision to expand scope deliberately (or a differently-shaped example) rather than being folded in just because compelling evidence exists. See `ROADMAP.md`/`FUTURE_WORK.md`/`DECISION_HISTORY.md`.

Execution and Orchestration

Future versions may introduce execution capabilities.

Possible architecture:

Dataset Metadata
        |
        v
Structifact IR
        |
        v
Execution Layer
        |
        v
Data Pipeline

Execution should remain separate from metadata interpretation. Worth noting: the Dependency Resolution Engine's `execution_order()` produces an *ordering*, not execution itself — it tells a future execution layer what order to run things in, but doesn't run anything. That boundary is deliberate, matching this principle directly.

Potential integrations:

Prefect
Dagster
Airflow

Warehouse Integrations

Future extensions may support:

Snowflake
BigQuery
Databricks
PostgreSQL

These should be implemented through adapters and generators rather than changing the core model.

IDE Integration

A concrete idea, not yet started: a VS Code extension (syntax highlighting, inline validation diagnostics, command-palette actions running `validate`/`generate`/`validate-data`/`deps` against the open file(s)) — potentially extending to other editors later. See `FUTURE_WORK.md` for the full reasoning, including why this is currently favored over a hosted web GUI as the more likely near-term move, if either is picked up before the engine matures further.

Architectural Summary

The current Structifact architecture:

                 Metadata
                     |
                     v
              Adapter Layer
                     |
                     v
              DatasetSpec IR
       (+ SourceRef/JoinSpec for
          multi-source datasets,
          + depends_on for cross-
          dataset relationships)
                     |
          +----------+----------+
          |                     |
          v                     v
     Validation            Generators
   (metadata well-              |
    formedness)                 v
                   Generated Engineering Artifacts

A parallel path checks real data:

     DatasetSpec (validated) + Real Data
                     |
                     v
            Data Quality Engine
                     |
                     v
              Quality Report

A third parallel path resolves relationships across datasets:

     Multiple DatasetSpecs (validated)
                     |
                     v
        Dependency Resolution Engine
                     |
                     v
           Execution Order or Error

The architecture is designed to grow deliberately.

The priority is not adding features quickly.

The priority is creating a trustworthy metadata-driven engineering framework built on:

explicit contracts
stable abstractions
predictable behavior
human-readable outputs

Guiding Principle

Define structure once. Generate reliable systems from it.
