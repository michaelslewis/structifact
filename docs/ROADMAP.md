# ROADMAP.md

# Structifact Roadmap

**Project:** Structifact
**Subtitle:** Schema-Driven Data Engineering Framework

---

# Purpose

This roadmap describes the planned evolution of Structifact.

It is organized around capability maturity rather than specific dates.

The goal is to evolve Structifact from a metadata interpretation framework into a broader metadata-driven data engineering platform while preserving the core principles:

* metadata as the source of truth
* declarative design
* explicit behavior
* modular architecture
* reliable engineering practices

The guiding progression is:

1. Strengthen metadata foundations.
2. Establish a stable internal model.
3. Improve validation and developer experience.
4. Generate increasingly useful artifacts.
5. Expand toward quality, lineage, integrations, and intelligent assistance.

---

# Current State

## Established Foundation

Structifact has established its initial architectural foundation.

Current capabilities include:

---

## Metadata Layer

Implemented:

* YAML-based metadata definitions
* dataset definitions
* field definitions
* type information
* metadata parsing

The metadata model is evolving toward a stronger v1 contract based around:

```text
DatasetSpec
    |
    +-- FieldSpec
    |
    +-- ConstraintSpec
```

---

## Adapter Architecture

Implemented adapters include:

* YAML
* CSV
* Excel

The adapter architecture provides a foundation for future input formats.

---

## Intermediate Representation

Structifact contains an internal representation layer separating:

* input formats
* framework logic
* generated outputs

The next evolution of the IR introduces:

* DatasetSpec as the canonical dataset model
* FieldSpec for intrinsic field properties
* ConstraintSpec for relational and business rules

---

## Validation Foundation

Current validation provides:

* metadata validation
* schema checks
* supported type validation
* framework correctness checks

Future work will expand validation into a first-class capability.

---

## Generator Framework

Current generators produce:

* SQL output
* dbt-compatible YAML output

The generator architecture provides a foundation for additional artifact types.

---

## Development Infrastructure

Established:

* Python package structure
* CLI foundation
* automated tests
* repository organization
* engineering documentation

---

# Phase 1 — Strengthen the Metadata Model

## Goal

Create a stable and extensible metadata foundation.

This phase establishes the contracts that future Structifact capabilities will depend on.

---

# Planned Work

## DatasetSpec Introduction

Introduce DatasetSpec as the canonical IR concept.

Goals:

* move away from table-specific terminology
* represent logical datasets
* support future dataset categories
* establish a stable framework boundary

Migration approach:

1. Introduce DatasetSpec.
2. Preserve TableSpec compatibility temporarily.
3. Update internal consumers.
4. Remove deprecated concepts only after migration is complete.

---

## FieldSpec Refinement

Define FieldSpec around intrinsic field characteristics.

Supported concepts:

* name
* type
* description
* nullable
* type parameters

Avoid expanding FieldSpec into a collection of unrelated flags.

---

## ConstraintSpec Foundation

Introduce a separate constraint model.

Initial direction:

```text
ConstraintSpec

type:
    primary_key
    unique
    foreign_key
    check

fields:
    related fields
```

The initial implementation should establish the structure without prematurely building a complete rule engine.

---

# Phase 2 — Expand Validation Framework

## Goal

Make metadata validation a core Structifact capability.

---

## Planned Work

Improve validation to support:

* richer schema checks
* constraint validation
* better error messages
* validation reporting
* clearer CLI output

Example future workflow:

```bash
structifact validate customers.yml
```

Output:

```text
✓ Loaded metadata
✓ Parsed 5 fields
✓ Valid schema
✓ No constraint violations
```

---

# Phase 3 — CLI User Experience

## Goal

Make Structifact immediately usable and demonstrate the architecture.

---

## Decision

CLI basics are intentionally moved earlier than originally planned.

The CLI is not only a convenience feature.

It is the primary user-facing boundary between:

* metadata
* framework behavior
* generated results

---

## Planned Commands

Initial workflows:

```bash
structifact validate customers.yml

structifact generate customers.yml
```

Future commands:

```bash
structifact inspect customers.yml

structifact docs customers.yml

structifact lineage customers.yml
```

---

## Success Criteria

A reviewer should be able to clone the repository and understand the framework through simple commands.

---

# Phase 4 — Metadata-Driven Generation Improvements

## Goal

Increase the value generated from metadata.

---

## Planned Work

Improve SQL generation:

* use normalized types
* support nullable behavior
* support constraints
* improve formatting
* support configurable templates

Improve metadata generation:

* richer dbt YAML output
* improved generated documentation metadata

---

# Phase 5 — Documentation Generation

## Goal

Make metadata useful for human understanding.

---

## Planned Work

Generate:

* dataset documentation
* schema references
* column descriptions
* metadata summaries

Potential future workflow:

```text
Metadata
    |
    v
Documentation Generator
    |
    v
Human-readable Data Documentation
```

---

# Phase 6 — Data Quality Framework

## Goal

Make data reliability a first-class capability.

---

## Planned Work

Support metadata-defined validation rules.

Examples:

```yaml
fields:

  - name: customer_id
    type: integer
```

Future rule concepts:

* required fields
* uniqueness
* accepted values
* regex validation
* range validation
* relationships

---

## Validation Philosophy

Validation should remain:

* deterministic
* explainable
* metadata-driven

---

# Phase 7 — Transformation Framework

## Goal

Move from describing datasets toward describing data workflows.

---

## Planned Work

Support metadata describing:

* source datasets
* dependencies
* transformations
* output models

Example future concept:

```yaml
model:
  name: customer_summary

depends_on:
  - customers
  - transactions
```

---

## Dependency Management

Potential capabilities:

* dependency graphs
* execution ordering
* impact analysis

---

# Phase 8 — Execution and Platform Integrations

## Goal

Connect Structifact metadata with execution environments.

---

## Potential Integrations

Future exploration:

* DuckDB
* Apache Parquet
* dbt
* Snowflake
* BigQuery
* Databricks
* PostgreSQL

---

## Design Requirement

Execution systems should remain separate from metadata definition.

Structifact defines:

> What should exist.

Execution platforms define:

> How and where it runs.

---

# Phase 9 — Lineage and Observability

## Goal

Improve understanding of data systems.

---

## Potential Capabilities

Generate:

* source-to-output lineage
* dependency graphs
* impact analysis
* metadata relationships

---

# Phase 10 — AI-Assisted Data Engineering

## Goal

Explore AI as an engineering assistant.

AI is intentionally a long-term capability.

It should not influence the core metadata architecture.

---

## Future Concept

The intended workflow:

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

---

## Potential Capabilities

Future exploration:

* schema inference assistance
* column classification
* candidate key detection
* validation recommendations
* metadata generation
* transformation suggestions
* documentation assistance

---

## Design Requirement

AI should:

* suggest
* explain
* assist

AI should not:

* replace metadata contracts
* become the source of truth
* hide engineering decisions

---

# Phase 11 — Developer Experience

## Goal

Make Structifact easier to adopt and contribute to.

---

## Potential Improvements

* project initialization
* improved CLI workflows
* configuration management
* IDE support
* metadata templates
* richer examples
* contributor documentation

---

# Long-Term Vision

The long-term goal is a metadata-driven engineering framework where:

1. Engineers define structure and intent.
2. Structifact interprets metadata.
3. Validation ensures reliability.
4. Artifacts are generated consistently.
5. Quality and lineage become easier to manage.
6. Intelligent assistance reduces repetitive engineering effort.

---

# Success Criteria

Structifact succeeds if it enables engineers to:

* define datasets consistently
* reduce repetitive pipeline development
* improve data reliability
* understand system behavior
* generate maintainable artifacts
* create reusable engineering patterns

---

# Guiding Principle

> Define structure once. Generate reliable systems from it.
