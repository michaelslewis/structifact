# DECISION_HISTORY.md

# Structifact Decision History

**Project:** Structifact
**Subtitle:** Schema-Driven Data Engineering Framework

---

# Purpose

This document captures the reasoning behind important Structifact architectural and product decisions.

The goal is to preserve not only:

* what decisions were made
* but why those decisions were made

Architecture evolves over time. Without documenting the reasoning behind decisions, future development can unintentionally reverse important design principles.

This document serves as a record of the engineering thinking that guides Structifact.

---

# Decision: Build Structifact as a Metadata-Driven Framework

## Decision

Structifact is built around the principle that metadata should define dataset structure, rules, and generated behavior.

Users should describe datasets through declarative definitions rather than repeatedly writing procedural implementation code.

---

## Why

Data engineering systems often accumulate:

* duplicated ingestion logic
* inconsistent validation
* repeated schema definitions
* undocumented assumptions
* difficult-to-maintain pipelines

A metadata-driven approach allows common patterns to be centralized.

Instead of every dataset requiring custom code, Structifact interprets metadata and generates consistent artifacts.

---

## Resulting Principle

> Define structure once. Generate reliable systems from it.

This remains the foundation of Structifact.

---

# Decision: Use Declarative Metadata as the Source of Truth

## Decision

Structifact uses YAML metadata definitions as the primary interface for describing datasets.

---

## Why

Dataset structure contains information that should be defined explicitly:

* field names
* data types
* descriptions
* constraints
* relationships
* validation expectations

These concepts should not be duplicated throughout application code.

The framework should consume metadata and apply consistent behavior.

---

## Resulting Principle

Metadata should become the authoritative description of dataset intent.

---

# Decision: Introduce a Stable Internal Representation Layer

## Decision

Structifact uses an Intermediate Representation (IR) layer between metadata inputs and generated outputs.

---

## Why

Direct translation creates unnecessary coupling.

Without an IR:

```text
YAML
 |
 v
SQL
```

Every input format becomes coupled to every output format.

With an IR:

```text
YAML
 |
 v
Parser
 |
 v
IR
 |
 +--> SQL Generator
 |
 +--> dbt YAML Generator
```

The IR provides a stable architectural boundary.

---

## Benefits

The IR enables future capabilities including:

* additional adapters
* additional generators
* validation frameworks
* documentation generation
* lineage analysis
* AI-assisted metadata workflows

---

# Decision: Evolve TableSpec into DatasetSpec

## Decision

DatasetSpec becomes the canonical IR concept.

TableSpec should no longer represent the primary abstraction.

---

## Why

The term "table" is too implementation-specific.

Future Structifact capabilities may represent:

* relational tables
* source datasets
* event streams
* analytical models
* generated datasets

The broader concept is a dataset, not necessarily a database table.

---

## Migration Strategy

This evolution should be incremental.

The preferred approach:

1. Introduce DatasetSpec.
2. Preserve TableSpec compatibility temporarily.
3. Update adapters and generators gradually.
4. Remove TableSpec only after migration is complete.

The goal is architectural improvement without unnecessary repository disruption.

---

## Resulting Principle

The IR should represent logical data concepts rather than specific storage implementations.

---

# Decision: Keep FieldSpec Focused on Intrinsic Field Properties

## Decision

FieldSpec should represent characteristics that belong directly to a field.

Examples:

* name
* type
* description
* nullable
* type parameters

---

## Why

FieldSpec should not become a growing collection of unrelated flags.

A model such as:

```python
FieldSpec(
    name="customer_id",
    type="integer",
    primary_key=True,
    unique=True,
    regex="...",
    min_value=0
)
```

becomes difficult to maintain as requirements expand.

---

## Resulting Principle

Fields describe what a field is.

Separate metadata objects describe what rules apply to fields.

---

# Decision: Introduce ConstraintSpec as a Separate Concept

## Decision

Constraints should be modeled separately from FieldSpec.

Example future representation:

```text
ConstraintSpec

type:
    primary_key
    unique
    foreign_key
    check

fields:
    customer_id
```

---

## Why

Database and business rules are not intrinsic field properties.

Examples:

A primary key:

```text
customer_id
```

describes a relationship between a field and a dataset.

A foreign key:

```text
orders.customer_id
references
customers.customer_id
```

describes a relationship between datasets.

These concepts naturally belong outside FieldSpec.

---

## Tradeoff

### Option A — Field Attributes

Example:

```python
FieldSpec(
    name="customer_id",
    primary_key=True
)
```

Advantages:

* simple
* easy to understand
* approachable

Disadvantages:

* does not scale well
* creates attribute growth
* becomes harder to represent relationships

---

### Option B — Constraint Objects

Example:

```python
ConstraintSpec(
    type="primary_key",
    fields=["customer_id"]
)
```

Advantages:

* extensible
* represents relational concepts naturally
* supports future constraint types

Disadvantages:

* introduces additional abstraction

---

## Decision

Use ConstraintSpec as the long-term model.

However, the initial implementation should introduce only the structure necessary for future growth and avoid building a full rule engine prematurely.

---

# Decision: Prioritize Validation Before Advanced Generation

## Decision

Validation improvements should precede significant generator expansion.

---

## Why

The value of metadata depends on trust.

Before generating more artifacts, Structifact must ensure:

* metadata is correct
* schemas are consistent
* constraints are understandable
* failures are clear

Reliable metadata enables reliable generation.

---

# Decision: Move CLI Basics Earlier in Development

## Decision

Basic CLI workflows should be implemented after IR and validation improvements, before deeper generator expansion.

Preferred sequence:

1. IR improvements
2. Validation framework
3. CLI basics
4. Generator improvements
5. Documentation generation

---

## Why

Structifact is both:

1. An engineering framework.
2. A portfolio demonstration project.

The CLI is the boundary where users experience the architecture.

A workflow such as:

```bash
structifact validate examples/customers.yml
```

providing:

```text
✓ Loaded metadata
✓ Parsed fields
✓ Valid schema
✓ No constraint violations
```

makes the framework tangible.

---

## Tradeoff

### CLI Before Generators

Advantages:

* faster feedback loop
* easier demonstration
* encourages user-focused workflows

Disadvantages:

* CLI behavior may evolve while internals stabilize

---

### Generators Before CLI

Advantages:

* focuses first on core artifact capability

Disadvantages:

* architecture is less visible
* harder for reviewers to interact with

---

## Decision

Prioritize CLI after the foundational IR and validation work.

---

# Decision: Keep AI-Assisted Metadata Discovery as Future Architecture

## Decision

AI assistance is a long-term exploration area and should not influence current core implementation.

---

## Why

The deterministic metadata model must remain authoritative.

AI should help engineers discover and create metadata, not replace the metadata contract.

---

## Future Concept

The intended architecture:

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
Human Approval
        |
        v
Structifact IR
        |
        v
Validation + Generation
```

---

## Example Future Workflow

Given:

```text
customers.csv
```

A future discovery system might suggest:

```text
customer_id:
    likely unique identifier

email:
    nullable=false candidate

created_date:
    timestamp candidate

email column:
    97% match email pattern
```

The engineer reviews and approves the proposed metadata.

The approved Structifact metadata remains the source of truth.

---

# Decision: Separate Framework Core from Future Execution Layers

## Decision

Structifact should define metadata and artifacts, while execution systems remain separate.

---

## Why

The framework should answer:

> What should exist?

Execution systems should answer:

> When and where should it run?

Future integrations may include:

* Prefect
* Airflow
* Dagster
* warehouse platforms

but these should not become dependencies of the core framework.

---

# Decision: Documentation Is Part of Engineering Quality

## Decision

Documentation is treated as a first-class engineering artifact.

---

## Why

A mature framework requires contributors to understand:

* architecture
* decisions
* current capabilities
* limitations
* future direction

Documentation prevents accidental architectural drift.

---

# Decision: Build Incrementally

## Decision

Structifact development should proceed through incremental milestones.

---

## Why

Frameworks can become overly complex before proving their core value.

The preferred progression:

1. Establish metadata foundations.
2. Strengthen the IR.
3. Build validation capabilities.
4. Provide usable CLI workflows.
5. Improve generated artifacts.
6. Expand toward quality, lineage, and integrations.

---

# Decision: Design for Portfolio-Quality Engineering

## Decision

Structifact should demonstrate professional engineering practices.

---

## Why

The project represents more than generated files.

It demonstrates:

* architecture
* abstraction design
* Python engineering
* testing discipline
* documentation practices
* data engineering concepts

The repository should resemble a mature engineering project.

---

# Guiding Principle

Every future decision should be evaluated against:

> Does this make metadata more useful, workflows more reliable, and engineering effort more repeatable?

If not, the additional complexity may not justify the feature.
