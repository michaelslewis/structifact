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

## Why

Data engineering systems often accumulate duplicated ingestion logic, inconsistent validation, repeated schema definitions, undocumented assumptions, and difficult-to-maintain pipelines. A metadata-driven approach allows common patterns to be centralized. Instead of every dataset requiring custom code, Structifact interprets metadata and generates consistent artifacts.

## Resulting Principle

> Define structure once. Generate reliable systems from it.

This remains the foundation of Structifact, and has held up across every subsequent addition — computed fields, sources/joins, and the data quality framework are all still expressed as metadata, not custom code.

---

# Decision: Use Declarative Metadata as the Source of Truth

## Decision

Structifact uses YAML metadata definitions as the primary interface for describing datasets (CSV and Excel as fully-supported alternate formats, kept at parity).

## Why

Dataset structure contains information that should be defined explicitly — field names, types, descriptions, constraints, relationships, and (as of later work) value-level rules and cross-source relationships. These concepts should not be duplicated throughout application code.

## Resulting Principle

Metadata should become the authoritative description of dataset intent. This was tested directly by the data quality framework: rather than writing a Python function to check that `discount_pct` stays between 0 and 1, the rule is `min_value: 0` / `max_value: 1` in the same metadata file as everything else.

---

# Decision: Introduce a Stable Internal Representation Layer

## Decision

Structifact uses an Intermediate Representation (IR) layer between metadata inputs and generated outputs.

## Why

Direct translation creates unnecessary coupling — without an IR, every input format becomes coupled to every output format. With an IR, adapters and generators can each evolve independently against one stable shared model.

## Benefits, Realized

This was originally written as a list of hoped-for future benefits. All of the following have since actually happened without requiring changes to the IR's basic shape: additional adapters (CSV, Excel joined YAML at parity), additional generators (six now exist), a validation framework, a documentation generator, and AI-assisted metadata workflows. The IR did have to grow substantially to support some of these (see the ConstraintSpec and SourceRef/JoinSpec/DedupRule decisions below) — but it grew by addition, not by rearchitecting.

---

# Decision: Evolve TableSpec into DatasetSpec

## Decision

DatasetSpec is the canonical IR concept. TableSpec remains only as a plain alias (`TableSpec = DatasetSpec`), not a separate class.

## Why

"Table" is too implementation-specific. Structifact datasets can now represent more than a single relational table — a dataset can be assembled from multiple joined sources (see the sources/joins decision below), which would have been an awkward fit for a "table"-centric model.

## Resulting Principle

The IR represents logical data concepts rather than specific storage implementations. This held up well: nothing in the sources/joins work required reintroducing table-specific assumptions.

---

# Decision: Keep FieldSpec Focused on Intrinsic Field Properties

## Decision

FieldSpec represents characteristics that belong directly to a field — not every possible rule or flag that might apply to it.

## Why

A model that keeps adding arbitrary flags (`primary_key=True`, `regex="..."`, `min_value=0`, ...) becomes difficult to maintain and reason about.

## Resulting Principle, and How It Actually Held Up

This principle was tested repeatedly as real work accumulated, and the line was drawn consistently: `FieldSpec` grew to include `role`, `accepted_values`, `computed`/`expression`/`depends_on`, `source`/`source_column`, and `min_value`/`max_value`/`pattern` — but every one of these describes something genuinely intrinsic to *that field* (what it is, what values it may hold, where it comes from). Anything describing a *relationship* between fields or datasets — primary keys, uniqueness, foreign keys, checks — went to `ConstraintSpec` instead, exactly as originally intended. Cross-source joins went to their own new concepts (`SourceRef`/`JoinSpec`) rather than being crammed into `FieldSpec`, for the same reason.

---

# Decision: Introduce ConstraintSpec as a Separate Concept

## Decision

Constraints are modeled separately from FieldSpec.

## Why

Database and business rules — a primary key, a foreign key referencing another dataset — describe a relationship, not an intrinsic property of one field.

## Decision, Confirmed

The initial implementation introduced only the structure necessary for future growth, deliberately avoiding a full rule engine up front. This was the right call: `ConstraintSpec` started with just `type`/`columns`, then grew `target_table`/`target_column` (for `foreign_key`) and `expression` (for `check`) only once a real need existed — and even then, `foreign_key` was deliberately scoped to single-column only, with composite FK explicitly deferred until a real example needs it. That gap stayed genuinely useful for a while, too: `foreign_key`/`check` were accepted as valid constraint *types* by validation well before `ConstraintSpec` could carry what either actually needed to be useful — and separately, a real bug was found and fixed where the YAML adapter accepted these fields in principle but never actually parsed them from a file (see below).

---

# Decision: Prioritize Validation Before Advanced Generation

## Decision

Validation improvements should precede significant generator expansion.

## Why

The value of metadata depends on trust — reliable metadata enables reliable generation.

## Extended Later: Validation Only Covers Metadata, Not Data

This distinction became important as the project matured, and is worth recording explicitly: `validation.py`'s job is checking that the *metadata itself* is well-formed (a regex compiles, a constraint references a real field, bounds aren't reversed). It was never designed to check real data rows, and for most of the project's life didn't need to. When the need for real data-row checking arrived (see the Data Quality Framework decision below), that became a deliberately separate subsystem rather than an extension of `validation.py` — a different question ("is this data valid?" vs. "is this schema well-formed?") got a different answer, not the existing one stretched to cover both.

---

# Decision: Move CLI Basics Earlier in Development

## Decision

Basic CLI workflows should be implemented after IR and validation improvements, before deeper generator expansion.

## Why

Structifact is both an engineering framework and a portfolio demonstration project. The CLI is the boundary where users experience the architecture.

## How the CLI Actually Grew

Started with `validate` and `generate`. Grew to four commands: `discover` (schema/requirements inference) and `validate-data` (the data quality framework) were each added only once the underlying capability existed to expose — the CLI itself was never the bottleneck or the thing driving new capability; it followed each capability's completion.

---

# Decision: Keep AI-Assisted Metadata Discovery as Future Architecture — Now Shipped

## Original Decision

AI assistance is a long-term exploration area and should not influence current core implementation. The deterministic metadata model must remain authoritative; AI should help engineers discover and create metadata, not replace the metadata contract.

## What Actually Got Built, and How the Original Boundary Was Upheld

Two real capabilities now exist: `discover --ai` (LLM-assisted field descriptions on top of deterministic CSV inference) and `discover --requirements --ai` (extracting a draft schema from a freeform requirements document, with no deterministic alternative — freeform text genuinely can't be parsed without a language model). Both were built to the exact boundary the original decision specified, not a looser version of it:

* **AI never becomes the source of truth.** Both paths only ever write a draft file, clearly labeled as unverified; neither auto-validates or auto-generates from AI output.
* **Explainable and reviewable.** The draft distinguishes AI-suggested content from deterministically-inferred content.
* **Optional, and genuinely zero-cost unless invoked.** `--ai` is off by default. A cost estimate is shown and confirmation required (or `-y` to skip the prompt) before any real API request. Declining makes zero API calls — this was verified in tests, not just asserted in documentation.
* **Deterministic core remains fully functional without it.** Every command works with zero AI involvement except `discover --requirements`, which has no non-AI path by its nature (there's no deterministic way to parse arbitrary prose) — that's a property of the input, not a broken promise about the architecture.
* **Bring-your-own-key, provider-agnostic by design.** `structifact/llm.py` defines an `LLMClient` interface, not an Anthropic-specific one; `AnthropicLLMClient` reads `ANTHROPIC_API_KEY` from the environment and never hardcodes a key; a `FakeLLMClient` lets the test suite exercise this logic with no real network access or API key at all.

This is a good example of a "future architecture" section that, once actually built, didn't need to compromise on any of its original constraints — worth remembering as a point of confidence for future speculative sections in `FUTURE_WORK.md`.

---

# Decision: Separate Framework Core from Future Execution Layers

## Decision

Structifact should define metadata and artifacts, while execution systems remain separate.

## Why

The framework should answer "what should exist," not "when and where should it run." Future integrations (Prefect, Airflow, Dagster, warehouse platforms) should not become core dependencies.

## Status

Unchanged and untested by real work yet — no execution/orchestration integration has been built. This remains a live boundary to hold, not yet a decision that's been stress-tested the way several others in this document have.

---

# Decision: Documentation Is Part of Engineering Quality

## Decision

Documentation is treated as a first-class engineering artifact.

## Why

A mature framework requires contributors to understand architecture, decisions, current capabilities, limitations, and future direction. Documentation prevents accidental architectural drift.

## A Real Test of This Principle

This principle was genuinely tested, not just stated: several of these documents (this one included) drifted noticeably out of date relative to the actual codebase for a period — describing `structifact/parser.py` as if it still existed well after it was removed, and describing entire shipped capabilities (AI discovery, the data quality framework) as still-future. The response, consistent with the principle, was a deliberate full-documentation refresh rather than leaving the drift in place. The lesson worth keeping: documentation quality isn't self-maintaining just because it's valued in principle; it needs an actual refresh pass scheduled in, the same way code needs tests run.

---

# Decision: Build Incrementally

## Decision

Structifact development should proceed through incremental milestones.

## Why

Frameworks can become overly complex before proving their core value.

## How This Actually Played Out — the Real-Example-First Discipline

The originally-planned progression (metadata foundations → IR → validation → CLI → generators → quality/lineage/integrations) roughly happened, but the more important discipline that emerged in practice wasn't in the original plan: **every non-trivial IR addition started from a real, concrete example, not an abstract design.** Computed fields were scoped against a real (synthetic but realistic) requirements document before any code was written. The sources/joins/dedup design was scoped against `examples/workorder_demo`'s actual reference SQL. Each Phase 6 data-quality increment was scoped against a real CSV with deliberately-planted violations, with the exact expected report output agreed *before* implementation. This "prove the contract on paper against something real, then implement" pattern is now the de facto standard for any IR-level change to this project, and is worth explicitly preserving as future work is scoped — see `ROADMAP.md`/`FUTURE_WORK.md` for items still awaiting this treatment (e.g. cross-dataset dependency tracking).

---

# Decision: Design for Portfolio-Quality Engineering

## Decision

Structifact should demonstrate professional engineering practices.

## Why

The project represents more than generated files — it demonstrates architecture, abstraction design, Python engineering, testing discipline, documentation practices, and data engineering concepts.

## Status

Unchanged. The project's test suite (279 tests as of this writing, CI-enforced on two Python versions) and the real-example-first design discipline described above are both concrete evidence this held up in practice, not just in intention.

---

# Decision: The Data Quality Framework Is a Separate Subsystem, Not a Generator

## Decision

Real-data checking (`structifact/quality.py`, exposed via `structifact validate-data`) is implemented as its own subsystem — not shoehorned into the existing `Generator` interface, and not an extension of `validation.py`.

## Why

Every existing `Generator` takes exactly one input (a `DatasetSpec`) and returns one `Artifact`. Checking real data needs two inputs — a schema *and* a data file — which doesn't fit that contract at all. Separately, `validation.py` checks metadata well-formedness; checking real data rows against that metadata is a genuinely different question with a genuinely different answer, not a bigger version of the same check (see the "Prioritize Validation Before Advanced Generation" decision above, extended).

## Supporting Decisions, Made Along the Way

* `check_data()`/`resolve_references()` return structured `QualityIssue`/`QualityResult` data and never call `print()` — all human-readable formatting lives in `cli.py`. This keeps the door open for a future `--format json` (not yet built) without touching the checking logic at all.
* A missing value is owned by exactly one check (`required`) — every other check (`uniqueness`, `accepted_values`, `range`, `pattern`, `foreign_key`) explicitly skips missing values rather than risk double-reporting the same underlying problem under two different rule names.
* A present-but-unparseable numeric value is deliberately *not* reported as a range violation. This isn't an oversight — type validation (confirming a "decimal" field's values are actually numeric at all) is a distinct, real, and still-unbuilt rule; folding it silently into range-checking would have blurred that boundary. `_try_parse_decimal` is kept as its own function specifically so a future type-validation rule has a clean seam to attach to.
* Foreign-key checking is existence/membership only. A duplicate value on the *target* side of a relationship is the target dataset's own `primary_key`/`unique` concern, not something `foreign_key` checking re-litigates.
* A missing or misconfigured `--ref` for a declared `foreign_key` constraint is a hard, loud configuration error raised before any checking runs — never a silently-skipped check that could produce a false "no issues found."
* Range/min/max values are stored as `Decimal`, not `float`, specifically converted via `Decimal(str(v))` rather than `Decimal(v)` directly — the latter would preserve a YAML-parsed float's exact (and often ugly) binary representation rather than the clean value a person actually typed.

---

# Decision: A Real Bug, Found by Actually Running the System End to End

## What Happened

While verifying the Phase 6 v3 (foreign-key validation) work by actually running the real CLI against real files — not just trusting the unit test suite — a genuine, previously-unknown bug surfaced: `yaml.py`'s constraint parsing had never read `target_table`, `target_column`, or `expression` from a YAML file, only `type` and `columns`. This meant the `foreign_key`/`check` constraint feature, while fully correct in `ir.py`/`validation.py`/`sql.py` and passing every one of its own unit tests, had been silently unusable via any actual YAML metadata file since it shipped — every test that exercised it had constructed `ConstraintSpec` directly in Python, never round-tripped through the YAML adapter.

## Why This Is Worth Recording as a Decision, Not Just a Bug Fix

The lesson is about process, not just the specific bug: a passing test suite proved the IR/validation/generator logic was correct, but said nothing about whether a real user's YAML file could actually reach that logic. The fix — and the practice worth keeping — was running the real CLI against a real file as the last verification step before considering any feature genuinely done, not just running its unit tests. This gap had existed, undetected, since the constraint feature first shipped.

---

# Guiding Principle

Every future decision should be evaluated against:

> Does this make metadata more useful, workflows more reliable, and engineering effort more repeatable?

If not, the additional complexity may not justify the feature.
