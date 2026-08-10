FUTURE_WORK.md
Structifact Future Work

Project: Structifact
Subtitle: Schema-Driven Data Engineering Framework

Purpose

This document captures longer-term ideas, experiments, and architectural possibilities for Structifact.

Unlike ROADMAP.md, which represents planned development direction, this document contains exploratory concepts that may or may not become implemented capabilities.

These ideas should not influence the simplicity of the current implementation unless they provide clear architectural value.

Future development should continue prioritizing:

stable metadata contracts
reliable internal representations
deterministic validation
transparent generation
strong engineering foundations

The guiding principle remains:

Build the foundation that makes future capabilities possible.

AI-Assisted Metadata Discovery

One of the most compelling long-term possibilities for Structifact is assisting engineers with understanding unfamiliar datasets.

The goal is not:

AI replaces metadata engineering.

The goal is:

AI reduces the effort required to create and maintain high-quality metadata while keeping engineers in control.

Current Status

As of the current implementation (see ROADMAP.md, Phase 10), the
workflow described below is realized for two input types: raw CSV
sample data (`structifact discover --ai`) and freeform requirements
documents of arbitrary shape (`structifact discover --requirements
--ai`). The architectural boundary this section describes — AI
produces suggestions, Structifact metadata remains the source of
truth — was upheld in both: neither path auto-validates or
auto-generates from AI output, both always write a draft file for
human review, and both are opt-in, cost-estimated, and confirmed
before any real request is made. The scenario below (a plain
`customers.csv`) reflects the earlier, simpler input shape; the
requirements-document path additionally handles derived/computed
fields and freeform relational/business-rule notes, which this
scenario doesn't illustrate.

Potential Future Workflow

A future AI-assisted workflow could look like:

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

The important architectural boundary:

AI produces suggestions.

Structifact metadata remains the source of truth.

Example Future Scenario

A user provides:

customers.csv

Structifact could eventually analyze the dataset and suggest:

Detected:

customer_id
- likely identifier
- values appear unique

email
- 97% match email pattern
- nullable candidate

created_date
- timestamp candidate

country_code
- repeated categorical values

The system could then propose:

dataset:
  name: customers

fields:

  - name: customer_id
    type: integer

  - name: email
    type: string

  - name: created_date
    type: timestamp

An engineer reviews and modifies the proposal before acceptance.

Architectural Requirements for AI Integration

Any AI-assisted capability should preserve:

Human Approval

AI suggestions should never silently become production metadata.

Explainability

Recommendations should include reasoning.

Examples:

Suggested type: timestamp

Reason:
97% of values matched ISO datetime pattern.
Deterministic Core

Structifact should remain fully functional without AI services.

The architecture should continue to work as:

Explicit Metadata
        |
        v
Structifact IR
        |
        v
Validation
        |
        v
Generation

AI should be an optional assistance layer around this workflow.

Metadata Authoring Assistance

A future goal could be reducing the friction of creating metadata definitions.

Possible capabilities:

schema suggestions
YAML generation assistance
interactive metadata creation
IDE integration
metadata completion
validation feedback during authoring

Possible future commands:

structifact discover customers.csv

structifact suggest-schema customers.csv

structifact explain customers.yml

These should improve developer experience without changing the underlying metadata model.

Schema Evolution Management

As datasets change over time, Structifact could eventually assist with schema evolution.

Potential capabilities:

schema comparison
compatibility analysis
migration recommendations
breaking-change detection
metadata versioning

Example:

Current:

customers v1

customer_id
email
created_date

New:

customers v2

customer_id
email
phone
created_date

Structifact could identify:

added fields
removed fields
incompatible changes
downstream impact
Data Contracts

A possible future extension is support for explicit data contracts.

A contract could define:

expected schema
ownership
quality expectations
compatibility requirements
service-level expectations

This would extend Structifact from metadata generation toward broader data reliability practices.

However, contract management should only be introduced after the core metadata model and validation framework are mature.

Lineage and Dependency Intelligence

A mature Structifact system could understand relationships between datasets and generated artifacts.

Potential capabilities:

dataset dependency graphs
source-to-output lineage
impact analysis
change recommendations

Example:

customers.csv
       |
       v
customers dataset
       |
       v
customer_summary model
       |
       v
dashboard dataset

The existing IR architecture provides a potential foundation for these capabilities.

Documentation and Knowledge Generation

Future generators could produce documentation artifacts from metadata.

Current Status

This has been prioritized as near-term work (see ROADMAP.md, Phase
5), ahead of several other items in this document, given the concrete
value of a `structifact docs` command for demonstrating the framework
— it requires no new inference or data ingestion, only rendering
metadata Structifact already holds.

Possible outputs:

dataset documentation
schema references
column dictionaries
ownership documentation
metadata catalogs

Example:

customers.md

Dataset:
Customer master information

Fields:

customer_id
Unique customer identifier

email
Customer email address

The generated documentation should remain human-readable and inspectable.

Plugin Architecture

As Structifact grows, a plugin architecture may become valuable.

Possible extension points:

Input Adapters

Examples:

JSON
database schemas
API definitions
cloud storage metadata
Generators

Examples:

documentation
lineage
warehouse-specific models
testing frameworks
Validation Providers

Examples:

custom business rules
external validation engines
organization-specific standards

A plugin architecture should only be introduced when existing extension patterns become insufficient.

The current adapter and generator registries should remain the preferred mechanism until then.

Web Interface Exploration

A future interface could provide visibility into Structifact projects.

Potential capabilities:

Metadata Browser

Explore:

datasets
fields
descriptions
constraints
relationships
Lineage Visualization

Display:

Source
 |
 v
Dataset
 |
 v
Generated Artifact
 |
 v
Downstream Consumer
Validation Dashboard

Display:

validation results
quality trends
failed checks
metadata history

The web interface should remain separate from the core framework.

Structifact should remain usable as:

a Python library
a command-line tool
an automation component
Data Catalog Integration

Structifact metadata could eventually integrate with broader governance systems.

Potential integrations:

data catalogs
governance platforms
business glossaries
documentation systems

The core metadata model should remain platform-independent.

Warehouse and Platform Integrations

Future exploration may include:

Snowflake
BigQuery
Databricks
PostgreSQL
DuckDB
cloud object storage

These should be implemented through adapters or generators rather than embedded into the core framework.

The architectural principle:

Structifact defines intent.

Platform-specific components implement execution details.

Transformation Framework

A future direction could extend Structifact from schema definition toward declarative transformations.

Current Status

This gap is no longer purely abstract. Real scoping work — a
synthetic requirements-document example and the now-implemented
`discover --requirements --ai` (see ROADMAP.md, Phase 10) — surfaced
a concrete, recurring case the IR cannot represent: a field computed
from other fields via a conditional expression, and datasets that
depend on other datasets via a join. `discover --requirements --ai`
currently flags such fields as `computed: true` and preserves the raw
logic as text rather than attempting to generate SQL for it. A
deliberately small first step — just enough IR support to represent a
single computed field, not the full framework below — is now planned
as near-term work (see ROADMAP.md, Phase 7), since it is the one
remaining piece that blocks turning a raw requirements document into
real, generated SQL/YAML/catalog output rather than a draft with
logic flagged for manual implementation.

A second, harder synthetic example (`examples/workorder_demo`,
modeled on real complexity from an actual SAP-shaped requirements
sheet) surfaced two further gaps this framework will eventually need
to address, neither yet designed (see ROADMAP.md, Phase 7, "Two
Further Gaps Found"):

* the same source table referenced multiple times under different
  roles within one dataset's generation logic (e.g. a shared partner
  table joined separately for requested-by/billed-to/site-contact) —
  the IR currently has no way to represent source-level joins at all,
  only a dataset's output columns
* priority-based row deduplication (picking one "current" row per key
  via a tiebreak rule) — a row-selection concern, meaningfully
  different in kind from a computed field's value-transformation
  `expression`

Potential capabilities:

transformation definitions
dataset dependencies
model generation
dependency ordering

Example:

model:
  name: customer_summary

depends_on:
  - customers
  - transactions

This should only occur after the metadata and IR foundations are mature.

Streaming and Event Data

Although current development focuses on structured datasets, future exploration could include event-driven systems.

Potential areas:

event schemas
streaming contracts
schema registry integration
real-time validation

Possible technologies:

Kafka
Spark Structured Streaming
cloud streaming platforms

This should not influence the current batch-oriented metadata model until there is a clear need.

Enterprise Capabilities

If Structifact evolves into a production platform, future capabilities could include:

approval workflows
audit history
environment management
access controls
governance policies
deployment workflows

These are long-term possibilities and not current development priorities.

Open Source and Community Direction

Structifact is designed with open-source engineering practices in mind.

Possible future efforts:

public documentation site
expanded examples
contributor documentation
plugin ecosystem
community extensions

The registered domain:

structifact.com

provides future flexibility for:

documentation
demonstrations
project resources

It does not imply a current hosted product or commercial offering.

Educational Value

Structifact may also serve as an educational example of:

metadata-driven architecture
data engineering design
Python package development
validation frameworks
testing practices
software architecture

Potential educational materials:

architecture walkthroughs
tutorials
example projects
implementation guides
Guiding Principle

Future expansion should continue following the central philosophy:

Increase engineering leverage without sacrificing transparency, reliability, or control.

The purpose of future capabilities is not automation for its own sake.

The purpose is to help engineers build better data systems with less repetitive work and greater confidence.
