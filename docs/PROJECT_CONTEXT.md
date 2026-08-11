# Structifact Project Context

## Project Identity

**Project:** Structifact
**Subtitle:** Schema-Driven Data Engineering Framework

**Repository:** github.com/michaelslewis/structifact
**Domain:** structifact.com

Structifact is a metadata-driven data engineering framework exploring how declarative definitions can be transformed into reliable, repeatable, and maintainable engineering workflows — and, as of more recent work, into real checks against actual data, not just generated artifacts.

The project is being developed as both:

1. A serious engineering exploration of metadata-driven data systems.
2. A professional portfolio project demonstrating modern software and data engineering practices.

The registration of `structifact.com` reflects the long-term intention for Structifact to become a recognizable standalone engineering project. The domain is deliberately not deployed yet — see "Current Development Phase" below for why.

---

# Project Vision

Structifact explores a fundamental question:

> How can metadata become the foundation for building reliable data engineering workflows?

Many data pipelines evolve into collections of custom scripts where each dataset requires handwritten ingestion logic, duplicated validation rules, repeated transformation code, and manually maintained documentation. This creates systems that become difficult to understand and maintain.

Structifact explores an alternative:

* define structure once through metadata
* interpret metadata through a reusable framework
* generate consistent artifacts from it
* validate the metadata's own well-formedness
* — and now, check whether real data actually conforms to what the metadata declares

That last point is a meaningful expansion of the original vision, not just an implementation detail: for most of this project's life, "validation" meant checking that a YAML file was internally consistent. Structifact now also checks real CSV data rows against a schema's declared rules — including relationships between two separate datasets. See "Current Repository State" below.

---

# Core Concept

The central idea behind Structifact remains:

> Define structure once. Generate reliable systems from it.

Metadata describes datasets, fields, types, constraints, and — as of recent work — how a dataset is built from one or more underlying sources, and what a real row of that dataset's data is required to look like.

---

# Current Repository State

Structifact has moved well past initial framework scaffolding. The core pipeline (adapters → IR → validation → generators) is fully implemented and tested, and two further capability areas are now complete alongside it: schema/requirements discovery (deterministic and AI-assisted) and real-data quality checking.

```text
structifact/
│
├── examples/
│   ├── customers/            golden-path example
│   ├── enterprise_demo/      synthetic wholesale-order example
│   ├── workorder_demo/       synthetic work-order example (multi-role joins, dedup)
│   └── data_quality_demo/    Phase 6 example (orders + a referenced customers dataset)
│
├── structifact/
│   ├── cli.py                 validate / generate / discover / validate-data
│   ├── ir.py                  DatasetSpec / FieldSpec / ConstraintSpec /
│   │                          SourceRef / JoinSpec / DedupRule
│   ├── validation.py          metadata well-formedness + relationship checks
│   ├── quality.py             real-data checking against that metadata
│   ├── discover.py            schema/requirements inference
│   ├── llm.py                 provider-agnostic LLM client
│   ├── types.py
│   │
│   ├── adapters/               yaml.py (canonical) / csv.py / excel.py
│   └── generators/             sql.py / dbt_yaml.py / catalog.py /
│                               catalog_extended.py / docs.py / model.py
│
├── tests/                      279 tests
├── docs/
└── pyproject.toml
```

---

# Currently Implemented Capabilities

## Metadata Handling

A dataset's metadata can now express far more than the original name/fields/types shape: field-level role classification, an accepted-value domain, computed/derived fields with their own expression, value-level rules (range, regex pattern), which source (of possibly several) a field actually comes from, and dataset-level relationships to other sources — including the same physical table joined in multiple times under different roles, each with its own filter and a priority-based deduplication rule.

## Adapter Architecture

YAML (canonical), CSV, and Excel — all three kept at parity on field-level attributes, including the newer value-level rules.

## Intermediate Representation

```text
Input Metadata
       |
       v
    Adapter
       |
       v
Intermediate Representation
       |
       +------------+
       |            |
       v            v
 Validation    Generators
```

The IR remains the central architectural decision preventing the framework from becoming tightly coupled to specific formats or outputs. It has grown substantially since the project's early stages — see `ARCHITECTURE.md` for the full current shape.

## Validation Framework

Validates the IR's own well-formedness: schema structure, constraint relationships, and (a newer addition) genuinely checkable rule *content* — a declared regex pattern must actually compile, a declared min/max range must be internally consistent, a declared relationship between sources must actually resolve. This remains distinct from checking real data, which is `quality.py`'s job.

## Data Quality Framework

A dataset's declared rules can now be checked against real CSV data — required fields, uniqueness, an accepted-values domain, numeric ranges, regex patterns, and (checking across two datasets at once) whether a foreign-key relationship's values actually exist in the referenced dataset's real data. This is implemented as its own subsystem (`quality.py`), not bolted onto the existing `Generator` framework, since checking real data needs two inputs (a schema and a data file) where every generator only ever needed one.

## Generators

Six generators now exist: SQL DDL, dbt-style YAML, two catalog formats (a minimal default and a richer opt-in variant), Markdown documentation, and — the newest — a generator that emits real, executable `SELECT` SQL for a dataset's computed fields and joined-in sources, distinct from the SQL generator's schema-only DDL.

## Discovery

Beyond the original "infer types from a CSV sample" capability, Structifact can now extract a draft schema from a freeform requirements document (tables, prose, or a mix) with optional LLM assistance — always opt-in, always cost-estimated and confirmed before any real request, always producing a draft for human review rather than anything auto-applied.

## CLI

Four commands: `validate`, `generate`, `discover`, and `validate-data` — the last of these new, exposing the data quality framework.

---

# Current Development Phase

Structifact has moved past the original two-phase framing ("architectural foundation" then "framework expansion") into a phase better described as **capability completion**: several major areas (generation, discovery, data quality) are now genuinely complete first versions, not scaffolding. The project continues to follow the same discipline that got it here — ground each new capability in a real example, agree a minimal contract before writing code, then implement with tests verified end-to-end — rather than expanding scope for its own sake. Phase 6 (Data Quality Framework), for instance, was deliberately built in three small, separately-verified increments (required/uniqueness/accepted-values, then range/pattern, then cross-dataset relationships) rather than attempted all at once, and was declared complete once it matched its original planned scope rather than continuing to grow indefinitely.

---

# What Structifact Is Not Currently

Still true, and still worth stating plainly: Structifact is not a full ETL execution engine, a production orchestration platform, a warehouse platform, a replacement for dbt (it generates dbt-shaped YAML; it doesn't run dbt), an AI pipeline generator, or a dashboard application. Also not yet built: a GUI, a hosted product at structifact.com, or a documentation *site* (only per-dataset generated Markdown). These are possible future directions, deliberately deferred — see `FUTURE_WORK.md`.

---

# Long-Term Vision

Unchanged in spirit: a complete metadata-driven analytics engineering framework, where quality, documentation, and (eventually) lineage and platform integrations all derive from the same metadata contract rather than being maintained separately by hand. What's different from earlier versions of this document is that "data quality" is no longer purely aspirational — the first real version of it now exists and works end to end, described above. What remains aspirational: cross-dataset dependency graphs and execution ordering (Phase 7's remainder), lineage, and any platform/warehouse execution layer.

---

# AI-Assisted Vision — Current vs. Future

The originally-envisioned workflow:

```text
User provides unknown data file
            |
            v
AI-assisted inspection
            |
            v
Suggested schema and metadata
            |
            v
User reviews or modifies suggestions
            |
            v
Structifact generates workflows and artifacts
```

is now real for two input shapes: raw CSV sample data, and freeform requirements documents. Both remain strictly opt-in, cost-estimated, confirmed before any request, and produce a draft for human review — never auto-applied. AI assistance is bring-your-own-key (an `ANTHROPIC_API_KEY` environment variable, never hardcoded into the project) and built behind a provider-agnostic client interface, not locked to one vendor by design. Declining a cost-estimate confirmation makes zero API calls — verified in tests, not just documented. What remains future work: column classification beyond dimension/measure, validation-rule *recommendations* (as opposed to the deterministic rule-checking that already exists), and AI-assisted documentation (the existing `DocsGenerator` is fully deterministic).

The architectural principle is unchanged: AI assists the metadata-driven framework; it does not replace it. The deterministic Structifact core remains fully functional with zero AI involvement.

---

# Engineering Principles

Unchanged from earlier versions of this document, and now with a real track record behind each one:

## Metadata First

Metadata remains the source of truth — now including the newer rule types (range, pattern, cross-source relationships), not just the original name/type/description shape.

## Declarative Over Imperative

Users describe intent; the framework determines implementation. This extended naturally to data-quality checking: a person declares `min_value: 0` / `max_value: 1`, not a Python function that checks it.

## Explicit Over Magical

Generated artifacts and quality reports both stay inspectable. A `validate-data` run never silently skips a check it was actually supposed to perform — a missing or misconfigured `--ref` for a declared foreign-key relationship is a loud, explicit configuration error, never a quietly-incomplete "no issues found."

## Reliability Before Complexity

Every new IR concept this project has added went through the same real-example-first, paper-contract-before-code discipline — see `DECISION_HISTORY.md` for specific instances.

## Documentation as Engineering

This document itself is an example: kept out of sync for a period, then deliberately refreshed against the actual shipped state rather than left stale indefinitely.

---

# Current Success Criteria

Unchanged: Structifact succeeds if it helps engineers define datasets clearly, reduce repetitive pipeline development, improve data reliability, generate consistent artifacts, and maintain analytics workflows more effectively — not by replacing engineering judgment, but by increasing engineering leverage.

---

# Guiding Statement

> Define structure once. Generate reliable systems from it.
