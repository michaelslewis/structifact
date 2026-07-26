# DESIGN_PRINCIPLES.md

# Structifact Design Principles

**Project:** Structifact
**Subtitle:** Schema-Driven Data Engineering Framework

---

# Purpose

This document describes the engineering principles that guide Structifact development.

These principles exist to ensure that as Structifact evolves, new capabilities strengthen the framework rather than turning it into a collection of disconnected automation features.

Structifact is intended to be:

* metadata-driven
* declarative
* modular
* transparent
* reliable
* extensible

The goal is to build a coherent framework based on strong software engineering practices applied to data engineering problems.

---

# 1. Metadata Is the Source of Truth

Metadata should define dataset structure and intent whenever possible.

Structifact should avoid requiring engineers to repeatedly define the same information in multiple places.

Examples of information that should originate from metadata:

* dataset definitions
* field definitions
* data types
* descriptions
* constraints
* relationships
* validation expectations
* generated artifacts

The framework should derive behavior from metadata rather than relying on duplicated configuration.

---

# 2. Declarative Over Imperative

Users should describe what they want rather than manually implementing every workflow step.

Example:

```yaml
dataset:
  name: customers

fields:
  - name: customer_id
    type: integer
```

The framework determines how that definition becomes:

* validated metadata
* generated artifacts
* future documentation
* future integrations

Declarative systems provide:

* consistency
* repeatability
* reduced duplication
* easier maintenance

---

# 3. Dataset Concepts Over Implementation Concepts

Structifact should model logical data concepts rather than prematurely coupling itself to a specific storage technology.

The primary internal concept is:

```text
DatasetSpec
```

rather than:

```text
TableSpec
```

because future datasets may represent:

* database tables
* source files
* analytical models
* event streams
* generated datasets

The framework should describe what data represents before deciding where it is stored.

---

# 4. Internal Representation Is a First-Class Boundary

The Intermediate Representation (IR) is one of Structifact's most important architectural concepts.

The architecture should follow:

```text
Input Metadata
        |
        v
     Adapter
        |
        v
      Parser
        |
        v
        IR
        |
        +-------------+
        |             |
        v             v
  Validation     Generators
```

The IR provides separation between:

* external formats
* internal meaning
* generated outputs

A stable IR enables future capabilities without tightly coupling components.

---

# 5. Fields Describe Structure, Constraints Describe Rules

Field definitions and business rules should remain separate.

A field should describe intrinsic characteristics:

* name
* type
* description
* nullable
* type parameters

A constraint should describe rules involving fields or datasets.

Examples:

```text
Primary Key

customer_id
```

```text
Foreign Key

orders.customer_id
references
customers.customer_id
```

This prevents FieldSpec from becoming an ever-growing collection of unrelated flags.

---

# 6. Explicit Over Magic

Automation should never become mysterious.

Users should understand:

* what Structifact generated
* why it generated it
* where information came from
* how to modify behavior

Generated artifacts should remain readable and inspectable.

Examples:

Good:

```sql
CREATE TABLE customers (
    customer_id INTEGER
);
```

Less desirable:

* opaque generated code
* hidden runtime behavior
* difficult-to-debug transformations

Structifact should automate repetitive work without hiding engineering decisions.

---

# 7. Reliability Before Cleverness

Structifact should prioritize predictable behavior over impressive but fragile automation.

Preferred characteristics:

* deterministic outputs
* clear failures
* understandable workflows
* maintainable abstractions

A simpler system engineers trust is better than a sophisticated system engineers cannot debug.

---

# 8. Separation of Responsibilities

Each component should have a clearly defined purpose.

Adapters handle:

* external input formats

Parsers handle:

* interpretation of metadata

IR objects handle:

* framework-level concepts

Validation handles:

* enforcing metadata rules

Generators handle:

* producing artifacts

Execution systems, when introduced, should handle:

* running workflows

Components should collaborate through clear interfaces rather than hidden dependencies.

---

# 9. Extensibility Through Stable Interfaces

Future capabilities should be added through well-defined extension points.

Examples:

Adapters:

```text
CSV Adapter
Excel Adapter
Future JSON Adapter
Future Database Adapter
```

Generators:

```text
SQL Generator
dbt YAML Generator
Future Documentation Generator
Future Lineage Generator
```

The framework should support growth without requiring changes to unrelated components.

---

# 10. Avoid Premature Complexity

Structifact should evolve incrementally.

Potential future capabilities include:

* warehouse integrations
* orchestration
* lineage
* data quality frameworks
* AI assistance
* web interfaces

However, these should only be introduced when the underlying architecture can support them naturally.

The framework should establish strong foundations before expanding functionality.

---

# 11. Reproducibility and Determinism

Given:

* the same metadata
* the same input data
* the same framework version

Structifact should produce predictable results.

Reproducibility enables:

* testing
* debugging
* CI/CD workflows
* auditing
* confidence in generated artifacts

---

# 12. Validation Is a Core Capability

Validation is not an optional enhancement.

Metadata-driven systems depend on trust in their definitions.

Validation should provide:

* understandable errors
* actionable feedback
* predictable behavior
* confidence before generation

Future validation capabilities should build upon the same metadata foundation.

---

# 13. Human-Readable Outputs

Generated artifacts should be understandable without requiring Structifact itself.

Examples:

Good:

```sql
CREATE TABLE customers (
    customer_id INTEGER,
    email VARCHAR(255)
);
```

Less desirable:

* opaque generated code
* unnecessary abstraction layers
* unreadable output formats

Generated systems should remain approachable to engineers.

---

# 14. CLI as the User Boundary

The command-line interface is an important part of Structifact's design.

The CLI should make the architecture tangible.

A user should eventually be able to run:

```bash
structifact validate customers.yml
```

and receive:

```text
✓ Loaded metadata
✓ Parsed fields
✓ Valid schema
✓ No constraint violations
```

The CLI is not merely convenience.

It is the primary interaction boundary for demonstrating framework capabilities.

---

# 15. AI Should Assist, Not Replace Engineering Judgment

AI assistance is a future exploration area for Structifact.

Potential applications:

* dataset discovery
* schema suggestions
* metadata generation
* validation recommendations
* documentation assistance

However, AI-generated suggestions must remain:

* reviewable
* explainable
* optional
* controlled by engineers

The approved metadata contract remains the source of truth.

The intended future pattern:

```text
Unknown Dataset
        |
        v
AI-Assisted Discovery
        |
        v
Suggested Metadata
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

# 16. Documentation Is Part of the System

Documentation is an engineering artifact.

Important decisions should be captured through:

* architecture documentation
* decision history
* implementation documentation
* roadmap documentation
* examples

A future contributor should understand the project without reverse engineering every implementation detail.

---

# 17. Portfolio-Quality Engineering Standards

Structifact is both:

1. A framework exploration.
2. A demonstration of engineering capability.

The project should demonstrate:

* clean architecture
* thoughtful tradeoffs
* maintainable Python code
* meaningful tests
* professional documentation
* realistic engineering decisions

The repository should resemble a mature engineering project.

---

# 18. Build Foundations Before Features

The guiding principle for Structifact development:

> Build the foundation that makes future features easy.

Strong foundations include:

* stable metadata models
* clear internal representations
* modular architecture
* reliable validation
* predictable generation

Features should be added because they strengthen the framework, not simply because they are possible.

---

# Summary

Structifact is guided by a simple philosophy:

> Define structure once. Generate reliable systems from it.

Every design decision should reinforce:

* metadata over duplication
* clarity over complexity
* reliability over cleverness
* transparency over magic
* explicit contracts over hidden behavior
* engineering discipline over shortcuts

These principles provide the foundation for future growth while preserving the original vision of Structifact.
