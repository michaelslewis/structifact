Structifact Architecture
Overview

Structifact is a metadata-driven data engineering framework designed to convert declarative dataset definitions into validated internal models and reusable engineering artifacts.

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

The architecture separates:

how metadata enters the system
how datasets are represented internally
how rules are applied
how artifacts are generated

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
relationships
validation rules
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

Generated outputs should remain human-readable.

Structifact should automate repetitive engineering work without hiding engineering decisions. This is also why `structifact discover` — the deterministic schema-inference command — always writes a clearly-labeled draft for human review rather than treating any inferred value as real metadata, and why catalog generators never fabricate values (like a `pii` flag or `changed_by` name) that the IR has no actual way of knowing.

Reliability Before Cleverness

Structifact prioritizes predictable behavior over complex automation.

Preferred characteristics:

deterministic results
clear errors
inspectable outputs
simple abstractions
maintainable implementations

A smaller reliable framework is preferred over a larger framework with opaque behavior.

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
Validation
      |
      v
Generators
      |
      v
Output Artifacts

Components should collaborate through stable interfaces rather than depending on implementation details.

Architecture Components
Adapter Layer

Location:

structifact/adapters/

The adapter layer handles external metadata formats. Each adapter is responsible for loading a source format and constructing IR objects (`DatasetSpec` / `FieldSpec` / `ConstraintSpec`) directly — there is no separate parsing stage between an adapter and the IR.

Responsibilities:

loading source definitions
converting external formats into DatasetSpec/FieldSpec/ConstraintSpec objects
isolating format-specific behavior

Current adapters:

YAML (`structifact/adapters/yaml.py`) — the primary format; supports the canonical `dataset:` contract, the legacy `table:` format, per-field `role` (`dimension` | `measure`), and constraints
CSV (`structifact/adapters/csv.py`)
Excel (`structifact/adapters/excel.py`)

All three adapters normalize raw type strings through the shared type system (`structifact/types.py`) rather than each implementing their own type-mapping logic.

Future adapters may include:

JSON
database metadata sources
cloud storage formats
API-based metadata sources

Adapters should not contain business rules or generation logic.

Intermediate Representation (IR)

Location:

structifact/ir.py

The IR is the central abstraction in Structifact.

The purpose of the IR is to provide a stable internal model between external inputs and generated outputs.

The canonical v1 IR concepts are:

DatasetSpec
    |
    +-- FieldSpec[]
    |
    +-- ConstraintSpec[]

The IR separates:

external metadata formats
framework processing
generated artifacts

This allows adapters and generators to evolve independently.

## Semantic Model vs Artifact Model

Structifact maintains a deliberate separation between semantic concepts and generated artifacts.

The semantic model describes meaning:

DatasetSpec
FieldSpec
ConstraintSpec

The artifact model describes implementation outputs:

SQL
dbt metadata
catalog CSVs
documentation
lineage artifacts

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

A dataset represents a logical data object that Structifact can validate and generate artifacts from.

Conceptually:

DatasetSpec

name
description
metadata
fields[]
constraints[]

Responsibilities:

represent dataset identity
contain field definitions
contain dataset-level rules
provide the primary object passed through validation and generation workflows
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

However, dataset classification is intentionally not part of the v1 implementation.

The IR should leave room for this extension without introducing behavior prematurely.

FieldSpec

FieldSpec represents intrinsic characteristics of a dataset field.

A field describes what a column is.

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
metadata

Responsibilities:

represent field identity
represent data type information
represent field-level metadata
support validation and generation

`role` (`dimension` | `measure`) is optional — fields without a role are still valid. When present, it's validated against the supported set (`structifact/validation.py`) and consumed by the catalog generators to classify columns in generated catalog output. It is not derived or inferred; a field's role is only ever what the metadata explicitly states.

`accepted_values` (a list of strings) is likewise optional. Validation only checks that the declaration itself is well-formed — non-empty, no duplicate entries — since Structifact validates metadata definitions, not real data rows; there is currently no data-ingestion path to check actual values against this list. Note this deviates from the original plan below, which envisioned accepted values as a *constraint* rather than a field property — implementation ended up treating it as intrinsic to the field instead. That's worth revisiting if it causes friction, rather than silently left as an unexplained inconsistency.

FieldSpec should remain focused on characteristics inherent to the field itself.

Field Characteristics vs Constraints

Structifact intentionally separates field properties from rules.

Field properties:

name
type
nullable
role
accepted_values
description

Constraints:

primary key
unique
foreign key
validation rules

This avoids allowing FieldSpec to grow into an unmanageable collection of flags. Notably, FieldSpec still has no way to express a *derived* or *computed* field (a value calculated from other fields via an expression) — that remains unaddressed future work; see the Transformation Framework scoping notes in `ROADMAP.md`.

ConstraintSpec

ConstraintSpec represents relationships and rules applied to datasets.

Conceptually:

ConstraintSpec

type
fields
name
parameters

Examples:

primary_key

unique

foreign_key

check

Constraints are separate because many database and business rules do not describe a field itself.

Example:

constraints:

  - type: primary_key
    fields:
      - customer_id

This model provides future extensibility for:

multi-column constraints
relationships
validation rules
data contracts

A dataset may have at most one `primary_key` constraint — validation rejects a second one rather than silently allowing an ambiguous schema.

TableSpec Compatibility Strategy

Historically, Structifact used:

TableSpec

as the primary IR object.

The long-term model evolves toward:

DatasetSpec

because "table" is too implementation-specific for future possibilities.

Future datasets may represent:

relational tables
events
source definitions
analytical models

However, the migration should avoid unnecessary disruption.

The compatibility strategy is:

Introduce DatasetSpec as the canonical internal concept.
Preserve TableSpec temporarily as a compatibility alias or wrapper.
Migrate internal usage gradually.
Update documentation and examples to use DatasetSpec terminology.
Remove deprecated terminology only after the ecosystem has migrated.

This preserves working functionality while improving the long-term architecture. `TableSpec` remains a plain alias for `DatasetSpec` in `ir.py`; no separate class exists.

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

Validation Framework

Location:

structifact/validation.py

Validation operates against the IR.

The validation framework ensures metadata definitions are consistent and reliable.

Current responsibilities:

dataset validation
field validation
supported type checks
role checks (when a field specifies `role`, it must be `dimension` or `measure`)
constraint validation
meaningful error reporting

Future validation capabilities may include:

data quality checks
profiling
compatibility validation
generated test suites
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
Artifact

Current generators:

SQL generation (`sql.py`) — type-aware; maps normalized types to real SQL types (`INTEGER`, `TIMESTAMP`, `DECIMAL(precision,scale)`, etc.)
dbt-compatible YAML generation (`dbt_yaml.py`)
Catalog CSV generation (`catalog.py`) — a minimal catalog (name, description, role, type, length) using only what the IR actually knows; run by default
Extended catalog CSV generation (`catalog_extended.py`) — a richer catalog matching a specific downstream tool's expected column set. Fields the IR has no way to know (`pii`, `comments`) are always blank rather than guessed; `changed_by` is explicitly configurable (constructor argument or `STRUCTIFACT_CHANGED_BY` environment variable), blank if unset; `changed_on` is a real generation timestamp. **Not** run by default — see Registry Pattern below.

Future generators may include:

documentation
lineage metadata
warehouse-specific artifacts
configuration files

Generators should consume IR objects rather than directly reading YAML or other source formats.

Registry Pattern

Adapters and generators use registry concepts.

Locations:

structifact/adapters/registry.py
structifact/generators/registry.py

The generator registry distinguishes two sets:

`GENERATORS` — run by default on every `structifact generate`. Reserved for generators whose output shape requires no user-specific configuration (SQL, dbt YAML, the minimal catalog).
`OPTIONAL_GENERATORS` — available, but not run unless explicitly requested via `structifact generate -g <name>`. Reserved for generators that depend on assumptions Structifact cannot make for every user (currently just the extended catalog generator).

This split exists because Structifact cannot know what any given user's downstream tooling requires — adding a new org-specific output format means writing one more small generator and deciding which set it belongs in, not teaching the framework to guess.

Registries provide extensibility points for supported components. This allows future additions without modifying the framework core.

Command Line Interface

Locations:

structifact/cli.py
structifact/__main__.py

The CLI is the primary user interaction boundary.

The CLI is intentionally prioritized early because it serves two purposes:

A practical developer workflow.
A demonstration of the framework architecture.

Current commands:

structifact validate examples/customers.yml

Output:

✓ Loaded metadata
✓ Parsed 2 fields
✓ Valid schema
✓ No constraint violations

structifact generate examples/customers.yml [-o output_dir] [-g generator_names]

Runs the default generator set, or an explicitly selected subset via `-g` (comma-separated generator names). An unknown name lists what's available rather than failing silently.

structifact discover some_data.csv [-o output.yml] [-n sample_size]

Infers a draft schema from raw CSV sample data and writes it to a file for human review. Never validates or generates from the draft automatically — see Future Architectural Direction below.

Future workflows:

structifact docs examples/customers.yml

The CLI should expose framework capabilities without hiding underlying behavior.

Current Data Flow

A Structifact workflow follows:

1. Metadata Definition

Example:

dataset:
  name: customers

fields:
  - name: customer_id
    type: integer
2. Adapter Loading

Example:

customers.yml

      |

      v

YAML Adapter
3. IR Construction
Adapter

  |

  v

DatasetSpec

  |

  +-- FieldSpec

  +-- ConstraintSpec
4. Validation
DatasetSpec

      |

      v

Validation Framework
5. Generation
DatasetSpec

      |

      v

Generators

      |

      v

Engineering Artifacts

An additional, separate flow exists for schema discovery from raw data with no existing metadata:

Raw Sample Data (CSV)
        |
        v
Deterministic Inference (structifact/discover.py)
        |
        v
Draft YAML (clearly labeled, not authoritative)
        |
        v
Human Review
        |
        v
(only then) Adapter Loading, as in the flow above

Testing Architecture

Testing is a core design requirement.

Current test areas include type system behavior, adapter behavior (per format), IR construction, validation rules, each generator, `discover`'s inference logic, and CLI command behavior — see `tests/` for the current, evolving set of test files.

Future tests should continue validating:

IR behavior
metadata parsing
validation rules
generated artifacts
CLI workflows

A design that is difficult to test is considered a design problem.

Future Architectural Direction

The current architecture intentionally leaves room for future expansion.

AI-Assisted Metadata Discovery

The deterministic half of this is implemented: `structifact discover` infers a draft schema (types, nullability, key/format hints) from raw sample data using no AI, and writes it to a file for human review — it is never auto-validated or auto-generated from.

The LLM-assisted half remains future work:

Unknown Dataset
        |
        v
Deterministic Inference (implemented)
        |
        v
LLM-Assisted Discovery (not yet implemented)
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

Potential future capabilities:

richer schema suggestions than deterministic inference can produce
constraint recommendations
interpreting freeform notes attached to a field (e.g. business logic described in prose)
documentation assistance

AI should create suggestions, not replace the metadata contract. The approved metadata model remains authoritative. Structifact must remain fully functional without any AI-assisted feature.

Transformation Framework

Not yet implemented. Neither `FieldSpec` nor `ConstraintSpec` has any way to express a field whose value is computed from other fields via an expression (e.g. a conditional sign adjustment, a tiered commission calculation), nor does the IR have a concept of one dataset depending on another (e.g. a model referencing an intermediate lookup model). This is real new IR/validation/generator work, not an incremental addition — see the scoping notes in `ROADMAP.md` for a concrete example of the kind of complexity this would need to support.

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

Execution should remain separate from metadata interpretation.

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

Architectural Summary

The long-term Structifact architecture:

                 Metadata
                     |
                     v
              Adapter Layer
                     |
                     v
              DatasetSpec IR
                     |
          +----------+----------+
          |                     |
          v                     v
     Validation            Generators
                                  |
                                  v
                   Generated Engineering Artifacts

The architecture is designed to grow deliberately.

The priority is not adding features quickly.

The priority is creating a trustworthy metadata-driven engineering framework built on:

explicit contracts
stable abstractions
predictable behavior
human-readable outputs
Guiding Principle

Define structure once. Generate reliable systems from it.
