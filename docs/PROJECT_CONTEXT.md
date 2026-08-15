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

The registration of `structifact.com` reflects the long-term intention for Structifact to become a recognizable standalone engineering project. The domain is deliberately not deployed yet — see `FUTURE_WORK.md`'s "Open Source and Community Direction" section for why.

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
* check whether real data actually conforms to what the metadata declares
* — and now, understand how multiple datasets relate to and depend on each other

That last point is a meaningful expansion of the original vision, not just an implementation detail: for most of this project's life, a dataset's metadata described only itself. Structifact now also lets a dataset declare a dependency on another Structifact-defined dataset, and resolves a whole collection of related datasets into a safe processing order. See `CURRENT_STATE.md` for the current implementation snapshot.

---

# Core Concept

The central idea behind Structifact remains:

> Define structure once. Generate reliable systems from it.

Metadata describes datasets, fields, types, constraints, how a dataset is built from one or more underlying sources, what a real row of that dataset's data is required to look like, and — as of the most recent work — what other datasets it depends on.

---

# Current Implementation

This document deliberately does not maintain its own snapshot of what's implemented, the repository structure, or capability lists — that duplicated `CURRENT_STATE.md` and reliably drifted out of sync with it (see `DECISION_HISTORY.md` for the specific instance that prompted removing it). **See [`CURRENT_STATE.md`](CURRENT_STATE.md) for the authoritative, actively-maintained description of what's actually implemented, the current repository structure, completed milestones, and known limitations.** This document's job is the one below: why Structifact exists, not what it currently does.

---

# What Structifact Is Not Currently

Still true, and still worth stating plainly: Structifact is not a full ETL execution engine, a production orchestration platform, a warehouse platform, a replacement for dbt (it generates dbt-shaped YAML; it doesn't run dbt), an AI pipeline generator, or a dashboard application. Also not yet built: a GUI, a hosted product at structifact.com, or a documentation *site* (only per-dataset generated Markdown). Also still future: cross-dataset value resolution (a dataset actually consuming another's computed value, not just knowing it must run after it). These are possible future directions, deliberately deferred — see `FUTURE_WORK.md`.

---

# Long-Term Vision

Unchanged in spirit: a complete metadata-driven analytics engineering framework, where quality, documentation, dependency awareness, and (eventually) lineage and platform integrations all derive from the same metadata contract rather than being maintained separately by hand. What's different from earlier versions of this document is that "data quality" and "dataset dependency tracking" are no longer purely aspirational — real versions of both now exist and work end to end, described above. What remains aspirational: cross-dataset *value resolution* (dependency graphs and execution ordering themselves are now real), lineage, and any platform/warehouse execution layer.

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

Metadata remains the source of truth — now including the newer rule types (range, pattern, cross-source relationships, dataset-level dependencies), not just the original name/type/description shape.

## Declarative Over Imperative

Users describe intent; the framework determines implementation. This extended naturally to data-quality checking: a person declares `min_value: 0` / `max_value: 1`, not a Python function that checks it. Dependency tracking is no different: a person declares `depends_on: [customers, transactions]`, not a script that determines processing order by hand.

## Explicit Over Magical

Generated artifacts and quality reports both stay inspectable. A `validate-data` run never silently skips a check it was actually supposed to perform — a missing or misconfigured `--ref` for a declared foreign-key relationship is a loud, explicit configuration error, never a quietly-incomplete "no issues found." `structifact deps` follows the same principle: a circular dependency is a loud error naming the complete cycle, never a silent or partial result.

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
