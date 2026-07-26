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
Metadata Parser
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

Structifact should automate repetitive engineering work without hiding engineering decisions.

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
Metadata Parser
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

The adapter layer handles external metadata formats.

Responsibilities:

loading source definitions
converting external formats into framework inputs
isolating format-specific behavior

Current adapter examples:

YAML
CSV
Excel

Future adapters may include:

JSON
database metadata sources
cloud storage formats
API-based metadata sources

Adapters should not contain business rules or generation logic.

Metadata Parser

Location:

structifact/parser.py

The parser converts adapter output into Structifact's internal representation.

Responsibilities:

interpreting metadata definitions
creating IR objects
normalizing metadata structures
preparing definitions for validation and generation

The parser should remain independent from specific output formats.

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
documentation
lineage artifacts

The IR should represent intent rather than implementation details.

For example:

```yaml
constraints:
  - type: primary_key
    columns:
      - customer_id

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
length
precision
scale
metadata

Responsibilities:

represent field identity
represent data type information
represent field-level metadata
support validation and generation

FieldSpec should remain focused on characteristics inherent to the field itself.

Field Characteristics vs Constraints

Structifact intentionally separates field properties from rules.

Field properties:

name
type
nullable
description

Constraints:

primary key
unique
foreign key
accepted values
validation rules

This avoids allowing FieldSpec to grow into an unmanageable collection of flags.

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

This preserves working functionality while improving the long-term architecture.

Type System

Location:

structifact/types.py

The type system defines Structifact's understanding of data types.

Responsibilities:

normalizing external type names
mapping source types into framework types
preserving type metadata
supporting validation and generation

Examples:

VARCHAR  -> string

INTEGER  -> integer

DECIMAL  -> decimal

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

Current and near-term responsibilities:

dataset validation
field validation
supported type checks
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

Current examples:

SQL generation
dbt-compatible YAML generation

Future generators may include:

documentation
lineage metadata
warehouse-specific artifacts
configuration files

Generators should consume IR objects rather than directly reading YAML or other source formats.

Registry Pattern

Adapters and generators use registry concepts.

Examples:

structifact/adapters/registry.py

structifact/generators/registry.py

Registries provide extensibility points for supported components.

This allows future additions without modifying the framework core.

Command Line Interface

Locations:

structifact/cli.py

structifact/__main__.py

The CLI is the primary user interaction boundary.

The CLI is intentionally prioritized early because it serves two purposes:

A practical developer workflow.
A demonstration of the framework architecture.

Near-term workflows:

structifact validate examples/customers.yml

Example output:

✓ Loaded metadata
✓ Parsed 5 fields
✓ Valid schema
✓ No constraint violations

Future workflows:

structifact generate examples/customers.yml

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
Testing Architecture

Testing is a core design requirement.

Current test areas include:

tests/

test_types.py

test_validation.py

test_generators.py

test_csv_adapter.py

test_yaml_adapter.py

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

AI is considered a future assistance layer around the deterministic Structifact core.

The future workflow:

Unknown Dataset
        |
        v
AI-Assisted Discovery
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

Potential capabilities:

schema suggestions
type detection
constraint recommendations
metadata generation
documentation assistance

AI should create suggestions, not replace the metadata contract.

The approved metadata model remains authoritative.

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
              Metadata Parser
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