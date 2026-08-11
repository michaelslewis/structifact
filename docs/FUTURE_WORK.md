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

A note on how this document has been kept: several sections below described work that has since actually shipped (AI-assisted discovery, documentation generation, the first Transformation Framework step, and a real Data Quality Framework going well beyond what was originally sketched here). Those sections have been trimmed or removed rather than left describing already-completed work as "future." See ROADMAP.md's "Recently Completed" section for the authoritative current list of what's done.

AI-Assisted Metadata Discovery

Status: substantially implemented. See ROADMAP.md for the current, detailed status — raw-CSV schema inference, AI-assisted field descriptions, and AI-assisted requirements-document extraction are all real, shipped, opt-in, cost-estimated, and always produce a draft for human review rather than anything auto-applied. The architectural boundary this section originally described — AI produces suggestions, Structifact metadata remains the source of truth — was upheld throughout.

What remains genuinely future here:

column classification beyond dimension/measure
validation-rule *recommendations* (as opposed to the deterministic rule-checking that already exists in quality.py)
interactive/IDE-integrated metadata authoring assistance (see the IDE Integration section below, which folds this in)
AI-assisted documentation (DocsGenerator is fully deterministic today)

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

This remains fully unstarted and genuinely future — nothing in the current IR or CLI touches schema comparison across versions.

Data Contracts

A possible future extension is support for explicit data contracts.

A contract could define:

expected schema
ownership
quality expectations
compatibility requirements
service-level expectations

This would extend Structifact from metadata generation toward broader data reliability practices. Worth noting: the Data Quality Framework (quality.py, see ROADMAP.md) already covers a meaningful slice of "quality expectations" — required fields, ranges, patterns, accepted values, and cross-dataset relationships are all real, checkable rules now. A formal "data contract" concept, if pursued, would likely sit on top of what already exists rather than replace it — packaging an existing dataset's rules plus ownership/SLA metadata into one reviewable unit, not reinventing rule-checking from scratch.

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

The existing IR architecture provides a foundation for this — DatasetSpec now has real, structural knowledge of a dataset's sources (SourceRef/JoinSpec) and, separately, of foreign-key relationships between datasets (ConstraintSpec's target_table/target_column, now actually meaningful since Phase 6 v3 resolves and checks them against real data). Neither of those was designed as a lineage feature, but both are exactly the kind of structural information a future lineage capability would need — worth revisiting this section once there's a concrete lineage use case, rather than designing it in the abstract now.

Plugin Architecture

As Structifact grows, a plugin architecture may become valuable.

Possible extension points: input adapters (JSON, database schemas, API definitions, cloud storage metadata), generators (lineage, warehouse-specific models, testing frameworks), validation providers (custom business rules, external validation engines, organization-specific standards).

A plugin architecture should only be introduced when existing extension patterns become insufficient. The current adapter and generator registries remain the preferred mechanism, and have proven sufficient for every extension so far — six generators and three adapters have all fit the existing registry pattern without needing anything more elaborate.

IDE Integration: VS Code Extension (and Potentially Other Editors)

A concrete idea, not yet started: package some of Structifact's capability as an editor extension — starting with VS Code, since that's the primary development environment — rather than (or alongside) a hosted web GUI.

Potential capabilities, roughly in order of how self-contained each would be to build:

syntax highlighting for the metadata YAML dialect
inline validation — surface `structifact validate`'s errors as editor squiggles/diagnostics as the file is edited, not just on a manual CLI run
command-palette actions to run `validate` / `generate` / `validate-data` against the open file without leaving the editor
a webview panel previewing generated output (SQL, the transformation model, a quality report) without a separate terminal step

The appeal, relative to the structifact.com/GUI idea below: meaningfully lower lift (no hosting, no auth, no backend service — it runs against the same local CLI that already exists), dogfoodable in the course of normal Structifact development itself (which would likely surface real UX gaps faster than a web GUI would), and arguably a stronger, more concrete portfolio artifact — a published extension is something a reviewer can install and try in under a minute, versus a hosted site that requires deploying and maintaining infrastructure.

If VS Code integration proves valuable, the same underlying capability (mostly just shelling out to the existing CLI and parsing its output) could reasonably extend to other editors later — JetBrains IDEs, Vim/Neovim via LSP, etc. — but that's explicitly a "later, if it makes sense" extension of the idea, not part of an initial scope.

Sequencing note: this idea and the structifact.com/GUI idea below are both explicitly deferred until the core engine has more maturity behind it (see ROADMAP.md's Immediate Development Focus / this document's Open Source and Community Direction section for the structifact.com framing). Between the two, the editor-extension idea is currently favored as very likely the better first move if/when this category of work is picked up — lower lift, faster feedback loop, stronger portfolio signal for the effort involved — but no commitment has been made to build either yet.

Web Interface Exploration

A future interface could provide visibility into Structifact projects.

Potential capabilities:

Metadata Browser — explore datasets, fields, descriptions, constraints, relationships
Lineage Visualization — display source → dataset → generated artifact → downstream consumer
Validation Dashboard — display validation results, quality trends, failed checks, metadata history (this would have real data to draw on now, given quality.py's structured QualityResult output — previously this section was purely hypothetical since there was no data-quality checking at all to visualize)

The web interface should remain separate from the core framework. Structifact should remain usable as a Python library, a command-line tool, and an automation component regardless of whether this is ever built.

See the IDE Integration section above for the current thinking on which of these two directions (editor extension vs. web interface) is the more likely near-term move, if either is picked up before the engine matures further.

Data Catalog Integration

Structifact metadata could eventually integrate with broader governance systems.

Potential integrations: data catalogs, governance platforms, business glossaries, documentation systems.

The core metadata model should remain platform-independent.

Warehouse and Platform Integrations

Future exploration may include: Snowflake, BigQuery, Databricks, PostgreSQL, DuckDB, cloud object storage.

These should be implemented through adapters or generators rather than embedded into the core framework.

The architectural principle: Structifact defines intent. Platform-specific components implement execution details.

Transformation Framework — Remaining Scope

Status: a meaningful first slice of this is now real — see ROADMAP.md for full detail. A single computed field can be represented and actually emitted as executable SQL (ModelGenerator), and a dataset can be built from multiple sources including the same physical table joined in multiple times under different roles with priority-based deduplication (SourceRef/JoinSpec/DedupRule).

What remains genuinely future, and was the original scope of this section: cross-*dataset* dependency tracking — one dataset's model depending on another dataset (not just one dataset joining in raw sources), with dependency graphs and execution ordering across that dependency chain. Example of the still-unbuilt shape:

model:
  name: customer_summary

depends_on:
  - customers
  - transactions

This is a different concern from the sources/joins work that's already done: sources/joins describe how *one* dataset is assembled from underlying tables; this describes how *multiple Structifact-defined datasets* relate to and depend on each other. Should only be scoped once there's a concrete example that needs it, matching how every other IR addition in this project has been grounded — not designed abstractly in advance.

Streaming and Event Data

Although current development focuses on structured, batch-oriented datasets, future exploration could include event-driven systems.

Potential areas: event schemas, streaming contracts, schema registry integration, real-time validation.

Possible technologies: Kafka, Spark Structured Streaming, cloud streaming platforms.

This should not influence the current batch-oriented metadata model until there is a clear need.

Enterprise Capabilities

If Structifact evolves into a production platform, future capabilities could include: approval workflows, audit history, environment management, access controls, governance policies, deployment workflows.

These are long-term possibilities and not current development priorities.

Open Source and Community Direction

Structifact is designed with open-source engineering practices in mind.

Possible future efforts: a public documentation site, expanded examples, contributor documentation, a plugin ecosystem, community extensions.

The registered domain, structifact.com, provides future flexibility for documentation, demonstrations, and project resources. It does not imply a current hosted product or commercial offering, and deployment is deliberately deferred — the current strategic framing (see PROJECT_CONTEXT.md / DECISION_HISTORY.md) treats Structifact primarily as a portfolio/credibility asset supporting consulting opportunities, not a product to launch, and holds off on a GUI or public-facing site until well past the current engine maturity. See the IDE Integration section above for the currently-favored alternative if/when this category of work is picked up.

Educational Value

Structifact may also serve as an educational example of: metadata-driven architecture, data engineering design, Python package development, validation frameworks, testing practices, software architecture.

Potential educational materials: architecture walkthroughs, tutorials, example projects, implementation guides.

Guiding Principle

Future expansion should continue following the central philosophy:

Increase engineering leverage without sacrificing transparency, reliability, or control.

The purpose of future capabilities is not automation for its own sake.

The purpose is to help engineers build better data systems with less repetitive work and greater confidence.
