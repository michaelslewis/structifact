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

Structifact is a Python-based metadata-driven framework that converts declarative dataset definitions into validated internal representations and generated engineering artifacts.

The current implementation focuses on:

* YAML-based metadata definitions
* Input adapters
* Metadata parsing
* Internal representation
* Type normalization
* Validation foundations
* Artifact generation
* Automated testing

The core design principle is:

> Define structure once. Generate reliable systems from it.

---

# Repository Structure

Current repository organization:

```text
Structifact/

├── examples/
│   ├── customers.csv
│   ├── customers.yml
│   └── types.yml
│
├── output/
│   ├── customers.sql
│   ├── transactions.sql
│   ├── customers.yml
│   └── transactions.yml
│
├── structifact/
│   ├── cli.py
│   ├── parser.py
│   ├── ir.py
│   ├── types.py
│   ├── utils.py
│   ├── validation.py
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
│       └── dbt_yaml.py
│
├── tests/
│   ├── test_types.py
│   ├── test_validation.py
│   ├── test_generators.py
│   ├── test_csv_adapter.py
│   └── test_yaml_adapter.py
│
└── pyproject.toml
```

---

# Core Components

## Metadata Layer

Structifact currently uses YAML metadata files as the primary metadata input format.

Current metadata definitions describe:

* dataset names
* field names
* data types
* field descriptions
* schema information

The metadata layer provides the declarative contract consumed by the framework.

The target v1 metadata model introduces:

* datasets as the primary concept
* fields as schema elements
* constraints as separate metadata objects

The migration toward this model is designed to preserve compatibility with existing metadata definitions.

---

# Adapters

Location:

```text
structifact/adapters/
```

Adapters provide a consistent interface for loading external metadata and source information.

Current adapters:

* YAML
* CSV
* Excel

---

## YAML Adapter

Location:

```text
structifact/adapters/yaml.py
```

Implemented capabilities:

* load YAML metadata definitions
* parse field definitions
* normalize field types
* construct internal representation objects

The YAML adapter is currently the primary metadata ingestion path.

---

## CSV Adapter

Location:

```text
structifact/adapters/csv.py
```

Implemented capabilities:

* read CSV-based source datasets
* extract dataset structure information
* support schema-driven workflows

---

## Excel Adapter

Location:

```text
structifact/adapters/excel.py
```

Framework support exists for Excel-based input handling.

The adapter architecture allows additional metadata sources to be introduced without changing core framework behavior.

---

# Internal Representation

Location:

```text
structifact/ir.py
```

Structifact uses an internal representation layer between external metadata formats and framework operations.

The IR exists to separate:

* input formats
* metadata interpretation
* validation
* generation

The approved v1 direction evolves the IR around:

```text
DatasetSpec
    |
    +-- FieldSpec
    |
    +-- ConstraintSpec
```

---

## DatasetSpec

DatasetSpec is the canonical internal representation concept.

Responsibilities:

* represent a logical dataset definition
* contain dataset-level metadata
* contain fields
* contain constraints

DatasetSpec replaces the idea of a table-specific internal model as the long-term abstraction.

---

## FieldSpec

FieldSpec represents intrinsic field characteristics.

Current and planned responsibilities include:

* field name
* normalized type
* raw source type
* description
* nullable information
* type parameters such as length, precision, and scale

FieldSpec intentionally avoids becoming a container for every possible business rule.

---

## ConstraintSpec

ConstraintSpec represents dataset-level or relational rules.

Examples include:

* primary keys
* uniqueness rules
* foreign key relationships
* check constraints

Constraints remain separate from FieldSpec to avoid uncontrolled growth of field attributes.

---

# Type System

Location:

```text
structifact/types.py
```

The type system provides common type normalization behavior.

Current capabilities include:

* mapping source database types into normalized types
* parsing type parameters
* extracting length
* extracting precision and scale

Examples:

```text
VARCHAR(50)
        |
        v
type: string
length: 50
```

```text
DECIMAL(10,2)
        |
        v
type: decimal
precision: 10
scale: 2
```

The type system provides a foundation for future schema compatibility and validation features.

---

# Validation Framework

Location:

```text
structifact/validation.py
```

Structifact currently includes a validation foundation.

Current capabilities include:

* required dataset checks
* required field checks
* duplicate field detection
* supported type validation

The current validation system operates against the internal representation.

Future expansion will introduce a more complete validation framework including:

* constraint validation
* data quality rules
* validation reporting
* compatibility checks

---

# Generators

Location:

```text
structifact/generators/
```

Generators convert internal representations into external artifacts.

Current generators include:

* SQL generator
* dbt YAML generator

---

## SQL Generator

Location:

```text
structifact/generators/sql.py
```

Implemented capability:

* generate SQL artifacts from metadata definitions

Example output:

```text
output/customers.sql
```

The SQL generator demonstrates the core Structifact workflow:

```text
Metadata Definition
        |
        v
        IR
        |
        v
 Generated Artifact
```

---

## dbt YAML Generator

Location:

```text
structifact/generators/dbt_yaml.py
```

Implemented capability:

* generate dbt-compatible YAML metadata structures

Current functionality focuses on metadata generation.

It does not currently generate complete dbt projects or execute dbt workflows.

---

# Command Line Interface

Locations:

```text
structifact/cli.py

structifact/__main__.py
```

Structifact currently contains CLI foundations.

Current purpose:

* provide framework entry points
* establish future command workflows

The next CLI milestone is to expose user-facing workflows such as:

```bash
structifact validate examples/customers.yml

structifact generate examples/customers.yml
```

The CLI is considered an important usability and portfolio boundary because it makes the framework behavior visible.

---

# Testing

Location:

```text
tests/
```

Structifact includes automated tests covering current framework behavior.

Current test areas:

---

## Type System

```text
test_types.py
```

Validates:

* type normalization
* type parsing behavior

---

## Validation

```text
test_validation.py
```

Validates:

* valid metadata handling
* invalid types
* duplicate fields
* missing required information

---

## Generators

```text
test_generators.py
```

Validates:

* generated artifact behavior

---

## Adapters

```text
test_csv_adapter.py

test_yaml_adapter.py
```

Validates:

* metadata loading
* source handling

---

# Current Workflow

The current conceptual workflow:

```text
Dataset Metadata (YAML)
            |
            v
        Adapter
            |
            v
          Parser
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
 Generated Engineering Artifacts
```

---

# Currently Supported Concepts

Structifact currently demonstrates:

✓ Metadata-driven dataset definitions
✓ Declarative YAML configuration
✓ Adapter-based architecture
✓ Internal representation layer
✓ Type normalization
✓ Validation foundation
✓ SQL generation
✓ dbt YAML generation
✓ Automated testing
✓ CLI foundation

---

# Not Currently Implemented

The following are future capabilities and should not be considered current functionality.

---

## Advanced Constraints

Not currently implemented:

* primary key enforcement
* foreign key relationships
* uniqueness validation
* check constraints

The v1 architecture reserves ConstraintSpec for these capabilities.

---

## Data Quality Framework

Not currently implemented:

* profiling
* anomaly detection
* quality dashboards
* historical quality metrics

---

## Data Warehouse Execution

Not currently implemented:

* Snowflake execution
* BigQuery execution
* Databricks execution
* PostgreSQL execution

---

## Pipeline Orchestration

Not currently implemented:

* Prefect workflows
* Airflow DAG generation
* Dagster integration

---

## Data Lineage

Not currently implemented:

* lineage graphs
* dependency visualization
* impact analysis

---

## Documentation Generation

Not currently implemented:

* generated documentation sites
* metadata catalogs
* ownership documentation

---

## AI-Assisted Metadata Discovery

Not currently implemented.

Future AI-assisted capabilities may include:

* analyzing unknown datasets
* suggesting schemas
* identifying candidate keys
* recommending validation rules
* generating metadata drafts

The intended future workflow is:

```text
Unknown Dataset
        |
        v
AI-Assisted Discovery
        |
        v
Suggested Metadata Contract
        |
        v
Human Review
        |
        v
Structifact IR
        |
        v
Validation + Generation
```

AI should assist engineers, but approved metadata remains the source of truth.

---

# Current Development Direction

The next implementation priorities are:

1. Strengthen the internal representation model.
2. Expand validation into a first-class framework capability.
3. Introduce basic CLI workflows.
4. Improve generators using the stronger metadata model.
5. Expand examples and documentation.

The goal is to improve the framework foundation before adding larger platform capabilities.

---

# Implementation Philosophy

Current development favors:

* explicit abstractions
* small composable components
* stable interfaces
* deterministic behavior
* maintainable code
* testability

Structifact intentionally avoids premature complexity.

Future capabilities should only be introduced when they strengthen the central objective:

> Define structure once. Generate reliable systems from it.
