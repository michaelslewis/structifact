# Structifact

**Schema-Driven Data Engineering Framework**

Structifact is an experimental metadata-driven data engineering framework that explores how declarative dataset definitions can be used to build reliable, repeatable, and maintainable data artifacts.

The core idea is simple:

> Define dataset structure and intent once through metadata, then generate consistent engineering artifacts from that definition.

Rather than creating isolated scripts for every dataset, Structifact explores how metadata can become the foundation for schema validation, documentation, artifact generation, and future analytics engineering workflows.

---

# Project Vision

Modern data platforms often evolve into collections of custom pipelines with duplicated logic, inconsistent validation, and difficult maintenance.

Structifact explores an alternative approach:

* Metadata defines dataset structure and expectations.
* Framework components interpret that metadata.
* Internal representations normalize different input formats.
* Repeatable engineering artifacts are generated automatically.
* Validation and quality checks become part of the workflow.

The long-term vision is to provide a reusable framework where onboarding a new dataset requires primarily metadata configuration rather than large amounts of custom pipeline code.

---

# Current Capabilities

Structifact is currently focused on establishing the core framework architecture.

The current implementation includes:

* YAML-based dataset metadata definitions
* Internal representation (IR) layer using `DatasetSpec`
* YAML metadata compatibility handling
* Metadata parsing and validation
* Pluggable adapter architecture
* CSV input support
* Excel input support
* SQL generation foundation
* dbt-style YAML generation foundation
* Automated validation tests

The current repository demonstrates the foundational architecture required for future metadata-driven data engineering workflows.

---

# Example Workflow

A typical Structifact workflow begins with a dataset definition:

```yaml
dataset:
  name: customers
  description: Customer master data

fields:
  - name: customer_id
    type: integer
    description: Unique customer identifier

  - name: created_at
    type: timestamp
    description: Record creation timestamp

constraints:
  - type: primary_key
    columns:
      - customer_id
```

The YAML metadata is normalized into Structifact's internal representation:

```
YAML Metadata Contract
          |
          v
     YAML Adapter
          |
          v
     DatasetSpec IR
          |
     +----+----+
     |         |
     v         v
Validation  Generators
```

Structifact can then use this definition to generate consistent artifacts such as:

* SQL artifacts
* dbt-style metadata artifacts
* future documentation and validation artifacts

The goal is to move repetitive engineering decisions into reusable framework behavior.

---

# YAML Contract Compatibility

The current canonical metadata format uses:

```yaml
dataset:
  name: customers
```

Legacy metadata definitions supported:

```yaml
table: customers
```

The legacy format remains supported for compatibility, but new metadata definitions should use the `dataset:` format.

---

# Architecture Principles

Structifact is built around several core principles:

## Metadata First

Metadata should be the source of truth.

Whenever possible, schemas, validation rules, documentation, lineage, and generated artifacts should derive from a shared definition rather than being maintained separately.

---

## Declarative Over Imperative

Users should describe:

* what data represents
* what fields exist
* what constraints and metadata rules apply
* what outputs are expected

The framework should determine:

* how metadata is interpreted
* how validation is performed
* how artifacts are generated

---

## Explicit Over Magical

Automation should improve productivity without hiding behavior.

Generated output should remain understandable and inspectable.

Engineers should be able to review:

* generated SQL
* generated metadata artifacts
* validation results
* dataset definitions

---

## Reliability Before Complexity

Structifact prioritizes:

* predictable behavior
* clear architecture
* testability
* maintainability

over unnecessary abstraction.

---

# Technology Stack

## Current Technologies

The current implementation uses:

* Python
* YAML
* SQL
* Git
* pytest

Input formats currently explored include:

* CSV
* Excel
* YAML metadata

---

## Future Technologies Under Consideration

Future development may explore integrations with technologies such as:

* DuckDB
* Apache Parquet
* dbt
* Snowflake
* Prefect
* cloud storage platforms
* additional warehouse technologies

These are future directions rather than current dependencies.

---

# Repository Structure

The repository is organized around a modular framework design:

```
Structifact/
│
├── examples/
│   └── Example metadata and input files
│
├── structifact/
│   ├── adapters/
│   │   └── Input format integrations
│   │
│   ├── generators/
│   │   └── Artifact generation logic
│   │
│   ├── parser.py
│   ├── validation.py
│   ├── types.py
│   └── ir.py
│
├── tests/
│   └── Automated framework tests
│
└── pyproject.toml
```

---

# Future Direction

Structifact is designed to evolve toward a broader metadata-driven analytics engineering framework.

Potential future capabilities include:

## Metadata Validation

* constraint validation
* schema compatibility checks
* generated validation suites
* data quality reporting

---

## Richer Artifact Generation

Future generators may support:

* richer SQL schema generation
* dbt test generation
* documentation artifacts
* warehouse-specific outputs

---

## Transformation Framework

Potential future capabilities:

* metadata-driven transformations
* dependency management
* generated SQL workflows
* reusable transformation patterns

---

## Documentation and Lineage

Potential future capabilities:

* automatic dataset documentation
* column-level metadata
* lineage generation
* dependency visualization

---

## Orchestration Integration

Potential integrations:

* Prefect
* Dagster
* Airflow

Structifact should define what needs to happen, while orchestration systems determine when and where workflows execute.

---

## AI-Assisted Data Engineering

A long-term exploration area is AI-assisted workflow generation.

Potential capabilities include:

* analyzing unfamiliar input files
* detecting likely schemas
* suggesting metadata definitions
* recommending transformations
* assisting with documentation
* helping users generate analytics workflows

AI should enhance engineering decisions rather than replace the underlying deterministic framework.

---

# Portfolio Purpose

Structifact serves as both:

1. An engineering exploration of metadata-driven data systems.
2. A portfolio project demonstrating modern software and data engineering practices.

The project demonstrates experience with:

* Python development
* SQL-based systems
* schema design
* validation frameworks
* software architecture
* modular engineering
* documentation practices
* analytics engineering concepts

The goal is not simply to build another ETL script.

The goal is to explore how engineering discipline can make data systems more reliable, understandable, and scalable.

---

# Documentation

Additional project documentation:

* `PROJECT_CONTEXT.md` — Overall project vision and current state
* `ARCHITECTURE.md` — System architecture and component design
* `DECISION_HISTORY.md` — Important architectural decisions and rationale
* `ROADMAP.md` — Planned development milestones
* `FUTURE_WORK.md` — Ideas and possible future directions
* `EXAMPLES.md` — Practical usage examples
* `CURRENT_STATE.md` — Snapshot of current implementation status
* `DESIGN_PRINCIPLES.md` — Core engineering philosophy
* `CURRENT_IMPLEMENTATION.md` — Detailed implementation documentation

---

# Project Status

Structifact is actively under development.

The current focus is evolving from architectural foundations toward metadata-aware validation and artifact generation.

The guiding principle remains:

> Define structure once. Generate reliable systems from it.