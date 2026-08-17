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

This principle was tested repeatedly as real work accumulated, and the line was drawn consistently: `FieldSpec` grew to include `role`, `accepted_values`, `computed`/`expression`/`depends_on`, `source`/`source_column`, and `min_value`/`max_value`/`pattern` — but every one of these describes something genuinely intrinsic to *that field* (what it is, what values it may hold, where it comes from). Anything describing a *relationship* between fields or datasets — primary keys, uniqueness, foreign keys, checks — went to `ConstraintSpec` instead, exactly as originally intended. Cross-source joins went to their own new concepts (`SourceRef`/`JoinSpec`) rather than being crammed into `FieldSpec`, for the same reason. Dataset-to-dataset dependencies (`DatasetSpec.depends_on` — see the dedicated decision below) followed this same line: a relationship between two datasets went on `DatasetSpec`, not into `FieldSpec`, even though the name `depends_on` is reused from the field-level concept.

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

This distinction became important as the project matured, and is worth recording explicitly: `validation.py`'s job is checking that the *metadata itself* is well-formed (a regex compiles, a constraint references a real field, bounds aren't reversed). It was never designed to check real data rows, and for most of the project's life didn't need to. When the need for real data-row checking arrived (see the Data Quality Framework decision below), that became a deliberately separate subsystem rather than an extension of `validation.py` — a different question ("is this data valid?" vs. "is this schema well-formed?") got a different answer, not the existing one stretched to cover both. The same pattern repeated again for dataset dependency tracking: resolving a *collection* of datasets against each other (duplicate names, unresolved references, cycles) is a third distinct question, and got its own module (`dependencies.py`) rather than further stretching `validation.py`.

---

# Decision: Move CLI Basics Earlier in Development

## Decision

Basic CLI workflows should be implemented after IR and validation improvements, before deeper generator expansion.

## Why

Structifact is both an engineering framework and a portfolio demonstration project. The CLI is the boundary where users experience the architecture.

## How the CLI Actually Grew

Started with `validate` and `generate`. Grew to five commands: `discover` (schema/requirements inference), `validate-data` (the data quality framework), and `deps` (dataset dependency resolution) were each added only once the underlying capability existed to expose — the CLI itself was never the bottleneck or the thing driving new capability; it followed each capability's completion.

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

The originally-planned progression (metadata foundations → IR → validation → CLI → generators → quality/lineage/integrations) roughly happened, but the more important discipline that emerged in practice wasn't in the original plan: **every non-trivial IR addition started from a real, concrete example, not an abstract design.** Computed fields were scoped against a real (synthetic but realistic) requirements document before any code was written. The sources/joins/dedup design was scoped against `examples/workorder_demo`'s actual reference SQL. Each Phase 6 data-quality increment was scoped against a real CSV with deliberately-planted violations, with the exact expected report output agreed *before* implementation. Dataset dependency tracking (see the dedicated decision below) followed the same pattern, and additionally demonstrated what happens when two real examples exist but turn out to be the *same* shape — see that decision for how the project responded rather than assuming a second example automatically justified a new abstraction. This "prove the contract on paper against something real, then implement" pattern is now the de facto standard for any IR-level change to this project.

---

# Decision: Design for Portfolio-Quality Engineering

## Decision

Structifact should demonstrate professional engineering practices.

## Why

The project represents more than generated files — it demonstrates architecture, abstraction design, Python engineering, testing discipline, documentation practices, and data engineering concepts.

## Status

Unchanged. The project's test suite (307 tests as of this writing, CI-enforced on two Python versions) and the real-example-first design discipline described above are both concrete evidence this held up in practice, not just in intention.

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

# Decision: Scoping Cross-Dataset Dependency Tracking — Evidence Over Imagination

## What Happened

Two real (synthetic) examples — `examples/enterprise_demo` and `examples/workorder_demo` — both surfaced the same cross-dataset pattern: a dataset needing a value resolved from another dataset via a join with conditional-fallback logic (an FX exchange rate lookup). The immediate temptation was to design IR support for resolving that value — a `resolved_fx_rate`-style computed field referencing another dataset.

That temptation was deliberately resisted. Instead: `ROADMAP.md` and `FUTURE_WORK.md` were inspected directly to determine what "cross-dataset dependency tracking" actually meant when originally scoped, rather than letting the compelling example define the milestone. The documents were clear — the original scope was dependency *declaration*, graphs, and execution ordering (`depends_on: [...]`), explicitly distinct from *resolving* a dependency's value.

## Why This Is Worth Recording

Two real examples showing the same pattern is genuine evidence that the pattern recurs — but it is not, by itself, evidence that solving it belongs in the current milestone. Those are different questions. The FX-resolution problem, once actually decomposed, turned out to require several distinct future capabilities (cross-dataset field references, lookup/fallback semantics, cross-dataset SQL generation) — effectively a second major subsystem, not an extension of one field. Scoping strictly to what the roadmap actually specified, and explicitly documenting the FX examples as motivating evidence for separate future work rather than folding them in, kept this milestone the size it should have been.

**Correction (found during the Phase 9-era 1.0 readiness audit):** `git log` shows `examples/enterprise_demo` was never actually committed to this repository, at any point — it existed only as a described-but-uncreated example across several docs (this entry included), not as a real checked-in file the way `examples/workorder_demo` genuinely is. The reasoning above still holds — the scoping decision itself, and the discipline of treating compelling motivating evidence as distinct from milestone scope, was correct — but only one of the two "real examples" cited was ever actually real. All other docs referencing `enterprise_demo` have been corrected to cite `workorder_demo` alone; this entry is left as originally written, with this note added, since rewriting a decision record after the fact would defeat its purpose.

## Supporting Decisions, Made Along the Way

* `DatasetSpec.depends_on` was kept as a plain `List[str]`, not a new `DependencySpec` type — no real example has yet shown a need for dependency-level metadata beyond a name, and `ROADMAP.md`'s own example uses a bare list.
* Dataset-level `depends_on` and the existing field-level `FieldSpec.depends_on` intentionally share a name — they occupy different, unambiguous nesting positions in the YAML (top-level vs. inside a `fields:` entry), consistent with "Keep FieldSpec Focused on Intrinsic Field Properties": a dataset-to-dataset relationship is not an intrinsic field property, and got its own concept rather than being folded into an existing one.
* Per-dataset well-formedness (blank/duplicate/self-reference entries) was kept in `validation.py`; collection-level concerns (duplicate dataset names, unresolved references, cycle detection) went to a new `structifact/dependencies.py` module — following the same precedent as `quality.py`: a question that requires more than one `DatasetSpec` is a genuinely different kind of check.
* A real bug was caught late, not by the test suite itself but by re-examining test output against its own stated intent: a cyclic test fixture's `depends_on` edges didn't actually encode the 3-node cycle its own comments claimed. The fix reinforced the project's existing "verify end to end, don't just trust green tests" practice — a passing suite had briefly hidden a genuinely wrong fixture.

---

# Decision: The Same Class of Bug, Found the Same Way, Twice

## What Happened

While implementing Phase 8D v4 (CLI exposure for materialization), the first-ever real YAML file to declare `source_table` (needed so the CLI's target table and the model's upstream read source could be genuinely distinct relations — see the Phase 8D v3 self-reference-collision finding in ROADMAP.md) failed to materialize correctly. Investigation found that `yaml.py`'s `load_yaml()` never parsed `source_table`, `sources`, `joins`, or a field's `source`/`source_column` from a YAML file at all — despite `validation.py` and `ModelGenerator` having operated correctly on those exact `DatasetSpec`/`FieldSpec` attributes since Phase 7. Every sources/joins test in the codebase, across three phase slices (7, 8D v1, 8D v2, 8D v3), had constructed `DatasetSpec` directly in Python, never once round-tripping through the YAML adapter — so the gap was invisible until this was the first time a real file needed it.

This is the identical shape of bug documented above ("A Real Bug, Found by Actually Running the System End to End"): an IR/generator/validation feature that was fully correct and fully unit-tested, silently unreachable from any real YAML file, because every test exercising it bypassed the adapter entirely.

A second, smaller finding surfaced in the same pass: PyYAML's default (YAML 1.1) resolver parses a bare `on:` key as the boolean `True`, not the string `"on"` — meaning `JoinSpec.on`'s real YAML key silently fails to bind unless quoted (`"on":`). Documented directly on `JoinSpec` in `ir.py` rather than worked around in the adapter, since this is an inherent YAML dialect quirk tied to the word "on" itself, not something Structifact should paper over.

## Why This Is Worth Recording

The previous entry's stated practice — "run the real CLI against a real file as the last verification step before considering any feature genuinely done" — held for every feature it was actually applied to going forward (constraints, quality checks, dependency tracking, execution). It didn't retroactively protect a feature (Phase 7's sources/joins) that had already shipped and stayed unit-tested-only ever since, because nothing forced a real YAML file through that specific path until this slice's CLI test needed one. The fix (`yaml.py` now parses all four previously-missing fields, with regression tests in `tests/test_yaml_adapter.py` covering each one plus a full YAML → `DatasetSpec` → `validate_table` → `ModelGenerator` pipeline test) closes the gap the same way the constraint bug's fix did. The durable lesson is narrower and more actionable than "test end to end": a feature isn't actually proven end to end until *every* adapter/interface path a real user could take has been exercised at least once by something other than direct object construction — passing unit tests against directly-constructed IR objects proves the logic, not the wiring.

---

# Decision: A 1.0 Readiness Audit, and Retiring a Duplicate Document

## What Happened

A structured 1.0 readiness audit (Green/Yellow/Red across the entire public surface — IR, adapters, validation, dependencies, generation, execution, materialization, CLI, tests, docs) found that `README.md` and `docs/EXAMPLES.md` had both stopped being updated before Phase 8 started, while `ROADMAP.md`/`FUTURE_WORK.md`/`CURRENT_STATE.md`/this document had been updated every single phase since. The gap was concrete, not cosmetic: README's own flagship `validate-data` example no longer reproduced its documented output (the fixture gained a `foreign_key` constraint requiring `--ref` since the example was written), README described five CLI commands and omitted `execute`/`impact` entirely, and `examples/enterprise_demo` — cited as a real example across eight files, including this one — had never actually been committed to the repository at any point (confirmed via `git log`). Separately, the CLI never called `sys.exit()` anywhere, so a genuine validation or execution failure exited `0`, and a missing file produced a raw Python traceback in most commands.

The same audit pass, extended to a documentation-structure review, found `docs/CURRENT_IMPLEMENTATION.md` and `docs/CURRENT_STATE.md` had converged on an identical stated purpose ("describes the current state of Structifact" / "the technical source of truth for implemented behavior") with near-identical shape (repo structure diagram, capabilities list, workflow diagrams, "not currently implemented" list) — one actively maintained every phase, the other frozen at the same stale point as README. `docs/PROJECT_CONTEXT.md` was found to be a partial duplicate: its vision/identity/principles sections were unique, but its "Current Repository State"/"Currently Implemented Capabilities"/"Current Development Phase" sections covered the identical territory as `CURRENT_STATE.md`, at the same staleness.

## What Was Done

CLI exit codes and file-not-found handling were fixed (every command now returns a success/failure signal `main()` propagates into a real process exit code). README and `EXAMPLES.md` were corrected against the real, currently-running CLI — every command shown was re-run and its actual output used, not assumed. `enterprise_demo` references were corrected everywhere except this document's own earlier entry (left as originally written, with a correction note added, since rewriting a decision record after the fact would defeat its purpose). `docs/CURRENT_IMPLEMENTATION.md` was deleted outright — not merged, not deprecated-in-place — since it had no unique content once `CURRENT_STATE.md` was confirmed authoritative, and keeping both was exactly the "did we update both?" maintenance trap this project's own simplicity principle exists to avoid. `docs/PROJECT_CONTEXT.md` was trimmed, not deleted: its vision/identity/engineering-principles content was kept (genuinely unique, doesn't go stale the way an implementation snapshot does), and its redundant current-state sections were replaced with a single pointer to `CURRENT_STATE.md`.

## Why This Is Worth Recording

This is the same lesson as the two entries above, applied one level up: "verify end to end, don't just trust a green test suite" is about code; the equivalent discipline for documentation is "verify the documented workflow against the real CLI, don't just trust that a doc was accurate when it was written." Four of nine core docs had been rigorously kept current every phase; two (README, EXAMPLES.md) had not, for no principled reason — nobody decided to stop maintaining them, the per-phase docs habit just never covered them. The fix wasn't "write more documentation" — it was "delete the document that duplicated an already-authoritative one, and correct the two that made false claims a user could immediately disprove by running the command shown." One document doing one job, verified against reality, beats several documents doing the same job with different amounts of drift.

`docs/ARCHITECTURE.md` was found to have the same staleness (zero mentions of the entire Phase 8/9 execution layer across 927 lines) but was deliberately left unaddressed here — its content is genuinely unique (not a duplicate of anything), so fixing it means writing real new material (the `Executor` abstraction, atomic transactions, retry, materialization as a fourth architectural pattern), not a correction. That's a properly-scoped future task in its own right, not something to fold into a consolidation pass — see `FUTURE_WORK.md`.

---

# Decision: The First Real-World-Triggered Feature — `source_filter`

## What Happened

After the 1.0 readiness audit closed with an empty backlog, the agreed next step was to stop building from the roadmap and wait for real use to surface a real need. That happened almost immediately: a real work ticket (a SAP-shaped profit-center data source — one requirements xlsx, plus SQL/dbt-YAML/catalog already hand-built as ground truth, kept entirely outside the git repo in a scratchpad directory since it's real work data) was run through Structifact's actual pipeline as a genuinely adversarial test, not a demo built to look good.

The experiment was structured in layers, each isolating a different question:

1. **`discover --ai` against a naive xlsx→text conversion.** The requirements sheet used cell *color* (grey fill) to mark which candidate fields were join-keys/filter-only and shouldn't appear in the output — a real, load-bearing signal that a plain text dump of cell values has no way to carry, since `discover` has no spreadsheet-formatting awareness at all. Result: 19 flat fields, all candidates included, exactly as predicted — but everything textually present (types, lengths, descriptions, the join/filter logic surfaced honestly into `unresolved_notes` rather than guessed at) came out essentially perfectly.
2. **The same run, with the exclusion signal made explicit in the text.** Confirmed the extraction logic itself wasn't the limitation: given the same information in words instead of color, it correctly excluded exactly the right 5 fields and said why. The real gap was entirely in step 1's input preparation, not in `discover`'s reasoning.
3. **Hand-modeling the real IR** (`source_table`, `sources`, `joins`, `filter`) and diffing generated output against the hand-built reference SQL field-by-field. This surfaced two distinct things, not one: a real structural IR gap (below), and a self-inflicted modeling mistake (relying on `source_column`'s default-to-field-name behavior for primary-source fields that had been intentionally renamed away from their physical column name — the mechanism to avoid this already existed, it just wasn't obvious it was needed on the *primary* source specifically).
4. **Diffing every generated artifact against the full set of hand-built reference files**, not just the model SQL that had already been the focus. This is what actually found the `DBTYAMLGenerator` gap below — a question the model-SQL comparison alone would never have asked.

The real, structural finding: `DatasetSpec` had no way to express a filter on its *primary* source — `source_table` was a bare string, and only a joined-in `SourceRef` carried a `filter`. Naively "just add a trailing `WHERE`" would have been wrong, not merely inelegant: the real dataset's primary and joined-in sources shared a column name (a "valid to" date), so a `WHERE` applied after the join would have been genuinely ambiguous in any real engine, not a hypothetical risk.

## What Was Done

Added `source_filter: Optional[str] = None` to `DatasetSpec` — same trust model as `SourceRef.filter` and `source_table` (raw SQL, inlined as-is, validated only for non-blankness). Wired into `yaml.py` from the start this time (see the entry above for what happens when that step gets skipped). `ModelGenerator` wraps the primary source in its own CTE, filtered *before* any join, whenever `source_filter` is set alongside `sources`/`joins` — matching how the real hand-written reference SQL was itself structured, not an invented shape. A plain trailing `WHERE` remains correct (and is what's generated) for the simpler case of a filter with no joins at all, where the ambiguity risk doesn't exist.

Verified two ways: unit tests asserting the exact SQL shape in all four combinations (filter alone, filter+joins, and both `unchanged` regression cases), and a real DuckDB/PostgreSQL execution test using data specifically designed to prove the ambiguity risk is actually avoided — a shared column name, one active and one expired primary-source row, an independently-filtered joined-source row present for *both*, so a wrong implementation would either error or silently include the expired row. Final generated SQL, once correctly modeled, matched the real hand-built reference field-for-field, alias-for-alias, modulo dbt-specific syntax (`{{ source() }}`, inline comments) that isn't part of what Structifact generates.

Two more findings from the same exercise were fixed as documentation corrections, not code: `--requirements` was documented (and used as informal shorthand in several other docs) as if it were a real CLI flag — routing to requirements-document extraction has always been automatic, based on `.md`/`.txt` extension plus `--ai`. And the `anthropic` package has no setup step called out anywhere prominent despite being required for any `--ai` usage.

A fifth finding, from step 4: `DBTYAMLGenerator` was silently dropping information the IR already had — `FieldSpec.role` was never emitted at all, and there was no `source_field` showing which physical source/column a dbt column actually came from. Fixed by emitting both: `role` when set, and `source_field` built as `<source>.<source_column>` using the exact same resolution `ModelGenerator` already uses to qualify SELECT columns — reusing an existing, tested convention rather than inventing a second one. Deliberately did *not* try to reproduce the reference file's own `source_field` prefix (`struct.cepc.mandt`): nothing in the IR has a "struct" concept, and one field in the reference was internally inconsistent about it (a dot where the real column has an underscore) — evidence it was manually typed, not a rule to encode. The reference file's *dataset-level* dbt metadata (`config`/tags, `schema`, a dataset description, `datasource_name`/etc.) was deliberately left unmatched — none of it exists anywhere in `DatasetSpec`, and adding several new IR fields from one reference file is a different, bigger kind of change than exposing data the IR already validates. Logged in `FUTURE_WORK.md` as a `dbt_extended` candidate, the same pattern `catalog_extended` already established, pending a second real example.

## Why This Is Worth Recording

This is the outcome the whole "stop, audit, wait for a real trigger" sequence was built to produce, and it's worth noting that it produced exactly the *shape* of finding the project's discipline has always aimed for: small, real, evidence-backed, and immediately testable against actual ground truth — not a speculative capability added because it seemed plausible. The layered experiment design mattered as much as the fix: separating "did the AI extraction fail" from "was the input missing information" from "is there a real IR gap" from "did I make a modeling mistake" from "what does the *rest* of the output look like, not just the part already under scrutiny" turned one vague "the aliasing/filtering didn't quite work" impression into five distinct, individually-actionable findings, only two of which needed a code change at all. The line drawn between the two code changes matters as much as the changes themselves: `source_filter` was a genuine IR gap (a real capability had nowhere to go); `DBTYAMLGenerator`'s fix was exposing data the IR already had and had already validated. Adding *new* `DatasetSpec` fields for the dbt dataset-level metadata would have been a third category — designing IR surface from a single example — and got correctly deferred instead. That's the same discipline this project has applied to every prior IR addition, now demonstrated end to end starting from a real requirements document instead of a synthetic one.

---

# Decision: A Second Real Example — One Correction, One New Feature, One New Gap

## What Happened

The previous entry deliberately deferred adding dataset-level dbt metadata (`config.tags`, `schema`, a dataset `description`, `meta.datasource_name`/`datasource_project`/`datasource_extract`/`data_catalog`) to the IR, on the grounds that one reference file wasn't evidence a shape generalizes. A second, independent real work ticket (`internal_order_master` — single-source, no join, no filter, structurally different from the first) tested that directly: its hand-built dbt YAML had the *identical* dataset-level shape, with several values byte-for-byte identical across both real files (`schema: PUBLIC`, `datasource_project: Public`, `datasource_extract: true`, `data_catalog: true`), and `tags`/`datasource_name` both following the exact same mechanical derivation from the dataset's own name in both cases. That's the evidence the first entry said was missing.

The same second example also did two things the first pass couldn't have: it *disproved* an assumption, and it surfaced a gap the first dataset's shape never could have exposed.

The disproof: `DBTYAMLGenerator`'s `source_field` had been built as `<source>.<source_column>`, deliberately matching `ModelGenerator`'s own column-qualification logic — a principled choice, but untested against a second data point. The second reference file's `source_field` values (`biz.aufk.mandt`, etc.) turned out to follow a different, simpler rule: the field's own display name with underscores replaced by dots, with no reference to the physical source at all. Re-checking the first file against this rule confirmed it fit there too, including the one field that had looked like an inconsistency (`struct_cepc_verak_user` → `struct.cepc.verak.user`) — it wasn't inconsistent, it was the *display name* being split, and the "physical column" theory just happened to produce the same three-segment result for every other field in that file, so the difference was invisible until a second file with a similarly-named physical column existed to check against.

The new gap: `internal_order_master`'s SQL is a real, legitimate case that has no analog in the first dataset — a single source, every column renamed via `source_column`, but no filter, no join, and no computed field anywhere. `ModelGenerator`'s "is there anything to generate" check only tested for those three conditions, never for a plain rename, so this exact real shape silently returned `None` — and since `generate_insert()` builds on `generate()`, `execute --materialize` was silently unusable for it too.

## What Was Done

Added six `dbt_`-prefixed fields to `DatasetSpec` (`dbt_schema`, `dbt_tags`, `dbt_datasource_name`, `dbt_datasource_project`, `dbt_datasource_extract`, `dbt_data_catalog`; the dataset-level `description` reuses the field the IR already had) and a new opt-in `DBTExtendedYAMLGenerator` (`-g dbt_extended`), duplicating the small per-column loop from the plain generator (sharing one helper, `_source_field`) rather than wrapping it — the exact relationship `catalog_extended.py` already has to `catalog.py`. `dbt_tags` auto-appends the dataset's own name as the final tag; `dbt_datasource_name` defaults to a title-cased dataset name when unset — both because both real examples confirmed these derivations identically, so there's nothing to make the user retype. Every other field is omitted entirely from the output when unset; the fact that both real examples happened to share the same `schema`/`datasource_project`/`datasource_extract`/`data_catalog` values reflects one person's two datasets in one project, not a universal default every Structifact user would want.

`source_field` was corrected to the simpler, now-doubly-confirmed rule. `ModelGenerator` gained a fourth condition (`has_renaming`, alongside computed/sources/filter) to its "generate or return None" check. Both were verified against real DuckDB (and, for the model-execution case, PostgreSQL) data, and the full `internal_order_master` fixture was hand-modeled and run through `validate`/`generate` end to end — its model SQL, dbt YAML, dbt_extended YAML, and catalog CSV all now match the real hand-built reference files closely, the same standard applied to the first example.

One more real-world wrinkle, unrelated to Structifact: the reference SQL for this dataset had one more field (`biz_aufk_user6`) than the reference YAML and catalog CSV did, and the requirements document didn't mention it at all. Confirmed with the user this was stale — added to the SQL at some point and never propagated, or no longer needed and never removed — and excluded from the acceptance fixture accordingly. Not every discrepancy an adversarial real-world test turns up is a Structifact question.

## Why This Is Worth Recording

This is the payoff of insisting on a *second* real example before building the dataset-level dbt metadata, rather than accepting "it seems plausible" after the first: the second example didn't just confirm the deferred feature, it corrected something the first example had made look more confident than it actually was, and found a completely different gap the first dataset structurally couldn't have exposed (no dataset with only renaming, no filter, no join, had been tried yet). None of that would have surfaced from theorizing harder about the first file — it required a genuinely different real shape to check against. The general lesson: one real example proves a capability is needed; it does not prove the *exact shape* of the fix is right, and it especially can't prove a negative ("nothing else is missing") — only a second, differently-shaped real example can do that work.

---

# Decision: A Question, Not a Ticket — Onboarding Gaps and Native `.xlsx` Discovery

## What Happened

Every prior "Real-World Validation" entry above was triggered by a new work ticket. This one wasn't: asked directly how someone other than the project's own author would know how to install and use Structifact, the honest answer required actually inspecting the README and CLI rather than assuming they were fine — and they weren't, in two concrete ways. First, the README had no Installation section anywhere; a reader would reach the `structifact validate ...` command shown in "See It In Action" with no path to having that command available at all. Second, nothing documented the actual contract for a structured CSV/Excel input file — `examples/customers.csv` was referenced by name in the golden-path walkthrough, but the full set of columns the CSV/Excel adapters recognize (`role`, `accepted_values`, `min_value`/`max_value`, `pattern`, etc. — eleven optional columns beyond the two required ones) existed only as something a reader would have to go read `adapters/csv.py` to discover.

Investigating the second gap surfaced a real capability gap underneath the documentation one. A structured CSV/Excel spec file is a completely different thing from a raw Excel (or Word) requirements document — a spreadsheet someone wrote by hand to describe a dataset, not one already shaped as `column_name`/`type` rows — and both real work tickets in the prior two entries were exactly that second kind. Both required manually converting the source `.xlsx` to Markdown before `discover --ai` could read it, because `discover` had never accepted `.xlsx` as an extension at all — it only recognized `.md`/`.txt`. Nothing in the docs said this conversion step was necessary; a real user would have had no way to know why `structifact discover ticket.xlsx --ai` simply refused to run.

## What Was Done

Two documentation-only fixes: an Installation section (clone, venv, `pip install -e .`, and each optional extra individually) added to `README.md`; a full structured-input column reference (every column the CSV/Excel adapters recognize, what's required vs. optional, and an explicit note on what's YAML-only) added to `EXAMPLES.md`. While writing the column reference, checking it against the actual adapter code (not the prior claim that CSV/Excel were "at parity on every `FieldSpec` attribute") found that claim was itself slightly wrong — per-field `source`/`source_column` and `label` are YAML-only, never parsed by either `csv.py` or `excel.py`. Corrected in both `README.md` and `CURRENT_STATE.md`.

One real code change: `discover.extract_text_from_xlsx()` reads a raw `.xlsx` requirements document directly — every sheet's grid dumped as plain text (blank rows and entirely-blank sheets skipped), in workbook order — and `discover`/`discover_requirements` in `cli.py` now route a `.xlsx` `spec` argument the same way they already routed `.md`/`.txt`. A missing `excel` extra (`pandas`) surfaces as the same kind of clear, caught error as a missing `anthropic` package for `--ai`, not a raw traceback. Deliberately scoped to text only, not cell *formatting* — the earlier entry in this section ("The First Real-World-Triggered Feature") already documented a real case where a workbook's grey-fill exclusion signal was invisible to a naive text conversion; this fix makes the text conversion itself automatic, but does not attempt to close that separate, harder gap, which stays tracked in `FUTURE_WORK.md`.

Verified two ways: synthetic multi-sheet `openpyxl` fixtures in the automated test suite (`tests/test_discover_xlsx.py`) covering header/data rows, a blank row, an entirely blank sheet, a missing file, and CLI dispatch end to end with a `FakeLLMClient`; and, separately, re-running the new extraction against both real requirements workbooks already sitting in the scratchpad from the prior two entries — confirming it reproduces the same information the earlier *manual* Markdown conversion did, including the source document's own literal "Grey color = not included in table" instruction, which the AI still has no way to act on since it only ever sees that instruction as text, never as an actual color on a cell.

## Why This Is Worth Recording

The prior entries in this section all treated "real-world validation" as something that starts when a new work ticket arrives. This one shows the same discipline applies to a much more mundane trigger — a plain question about who else could use this and how — and that answering it honestly (by actually checking the README and the adapter code, not by asserting confidence) found real gaps exactly the same way a work ticket would have. It's also a second, independent confirmation of a pattern from earlier in this document (the Phase 1 constraint-parsing gap, and the Phase 8D `yaml.py` sources/joins gap): documentation and code both drift from what a fresh pair of eyes actually needs, and the fix is always to check, not to assume the existing docs already say it.

---

# Decision: Reconciliation v1 — A Paper-Contract Correction, Caught Before Any Code

## What Happened

Following this project's real-example-first discipline, reconciliation's exact paper contract — synthetic "old vs. new" data, an old<->new field mapping shape, and the literal expected report output — was drafted and agreed before any implementation, the same process every other IR-adjacent addition in this project has gone through (see "Build Incrementally" above).

The first draft of that contract planted three deliberate differences in the synthetic `orders_legacy`/`orders_new` example: one row dropped in the migration (`1004`), one row newly added (`1006`), and one row whose amount genuinely changed on an otherwise-matched key (`1005`: `60.00` → `65.00`). The proposed aggregate check summed the *full* old and new populations and reported the difference — which, worked out on paper before implementation, came to `-255.00`. That number is real, but not useful: it's overwhelmingly the dropped row's `$300` and the added row's `$40` netting against the `$5` value change, and a reader looking at `-255.00` has no way to tell a genuine migration defect (`1005`'s value drifted) from ordinary migration noise (rows legitimately added or removed) — the three are just summed together into one undifferentiated number.

The fix, caught on paper before any code existed: restrict the aggregate comparison to the **matched population only** — keys present on both sides. Reworking the same synthetic numbers over matched keys alone (`1001`, `1002`, `1003`, `1005`) gives old sum `485.50`, new sum `490.50`, diff `+5.00` — exactly and only the planted `1005` discrepancy, with the row-coverage check (already reporting `1004`/`1006` separately, by key) carrying the structural-noise signal instead.

## Why This Is Worth Recording

This is a second, independent confirmation of "Prioritize Validation Before Advanced Generation" and "Build Incrementally"'s real-example-first discipline: working the exact numbers on paper, before writing `reconcile_data()`, surfaced a genuine design flaw (a diagnostically confounded aggregate) that a green test suite would never have caught on its own — a test written against the *original* flawed contract would have "passed" while still shipping a report that couldn't do the one thing reconciliation exists for: distinguishing a real migration defect from harmless population drift. The fix wasn't a bigger feature (e.g. jumping straight to full column-level comparison) — it was a smaller, more precise scope for the exact same v1: aggregate over matched rows, and let row-population coverage — a check the contract already had — carry the structural-difference signal it was always better suited to carry. `ReconciliationResult`'s report deliberately keeps row-coverage and aggregate issues in visibly separate sections for the same reason, rather than one undifferentiated issue list.

The corrected contract also made explicit, and kept explicit in `reconcile_data()`'s docstring and the example's `README.md`, a scope boundary worth stating outright: v1 does not claim two datasets are semantically equivalent. It establishes row-population coverage, key correspondence, and aggregate equivalence on declared measures for the matched population — not that every individual field value is identical. That's the honest boundary a matched-population aggregate can actually support, and it's also exactly why a full column-level v2 remains open, real, and deliberately unscoped rather than folded into v1 to make the boundary look less real than it is.

Reconciliation itself is being treated explicitly as an experiment, not an automatically-continuing subsystem — see `ROADMAP.md`'s Phase 12 section. The next real validation step is running v1 against a real, sanitized legacy-migration example (never real employer data or systems, per this project's standing IP-separation discipline) to see whether it actually catches the kinds of mistakes that motivated building it, before any v2 work is scoped at all.

---

# Decision: A Third Real Example — A Full Match Within Scope, and a Real Gap Found Just Outside It

## What Happened

A third, independent real work ticket (a SAP-shaped customer-credit source — a requirements xlsx plus hand-built reference SQL/dbt-YAML/catalog-CSV, kept entirely outside the git repo per this project's IP-separation discipline) was run through the same adversarial process as the first two rounds. This one was structurally and materially bigger than either prior example: the reference SQL joined five sources (not one or two), two of them pre-aggregated before joining, one aggregated via a conditional sign-flip at the final select level, and it also joined in what turned out to be *another dbt model's own output* rather than a raw table.

`discover --ai` was run first, as always, and correctly scoped itself to only the ~44 fields the requirements document actually described — it did not attempt to fabricate or guess at the ~90 additional "customer master" fields that the real reference file also carried, because those come from a separate, already-existing model (`{{ ref('customer_master_general') }}`) the requirements document was never meant to describe in the first place. Confirmed directly: dumping the raw extracted xlsx text (not just trusting the AI's summary) showed the same ~44-field scope, with no join/table information for the missing fields anywhere in the source document. This is exactly the intended behavior — surfacing what's genuinely there, not inventing structure to fill a document's apparent gaps — and a good sign that Structifact's stated principle ("AI suggests, never fabricates") continues to hold under a harder real case, not just the two it had already been proven against.

Two things followed from hand-modeling the real IR and diffing every generated artifact against the real reference files, matching the same process the first two rounds used:

1. **A genuine capability boundary, found by trying to model the full dataset.** The reference SQL requires two aggregation shapes `SourceRef`/`JoinSpec`/`DedupRule` cannot express: a joined source pre-aggregated (`SUM(...) GROUP BY`) into its own CTE before the join, and a joined source aggregated via a conditional sign-flip with a `GROUP BY` spanning the *entire* final select — collapsing a one-to-many join at the end rather than before it. Confirmed by reading `ModelGenerator` directly (not assumed): its generated model is always a flat, ungrouped `SELECT` with `LEFT JOIN`s, so the existing `computed`/`expression` escape hatch cannot absorb either shape — a bare `SUM(...)` inside a raw expression would be invalid SQL once mixed with non-aggregated columns at the same select level. This is materially bigger than any prior real-world finding (source_filter, dbt_extended, source_field, has_renaming) — it touches core join/select-shape generation, not additive metadata — and was deliberately NOT scoped or implemented in the same session that found it. See `FUTURE_WORK.md`'s "Aggregated joined sources" for the full writeup. The decision to stop here rather than immediately design a fix was explicit and user-confirmed, matching this project's standing discipline of a dedicated paper-contract pass for anything this size (the same discipline `source_filter` and reconciliation v1 both got).
2. **A full, exact match for everything within scope.** The 35 fields that don't depend on the unsupported aggregation (the primary `knkk` source plus a simple 1:1 `knka` join) were hand-modeled and run through `generate -g model,dbt_extended,sql,catalog_extended`. Every field's role, description, and `source_field` matched the real reference exactly, and every dataset-level `dbt_extended` field (tags, schema, description, `datasource_name`/`datasource_project`/`datasource_extract`/`data_catalog`) matched exactly too — verified programmatically (a real diff script comparing every field, not eyeballing), not just spot-checked. This is the third consecutive real example where the existing sources/joins/dbt_extended machinery produced a byte-for-byte-equivalent result once correctly modeled, and the largest and most structurally varied of the three.

Two smaller things surfaced in the same pass, worth recording for what they are — and are NOT:

* **A self-caught modeling mistake, not a Structifact bug.** The hand-modeled fixture initially included the dataset's own name explicitly in `dbt_tags`, which — combined with `DBTExtendedYAMLGenerator`'s existing, correct, already-documented behavior of auto-appending the dataset's name as the final tag — produced a duplicate. Caught by comparing against the `internal_order_master` fixture's own `dbt_tags` (which correctly omits the dataset's own name), not by any code defect. Fixed in the fixture, not in Structifact.
* **A real, but not directly evidenced, secondary finding**: spot-checking `SQLGenerator`'s DDL output (not something either prior round's reference materials ever included, since none of the three real tickets came with hand-built `CREATE TABLE` DDL to compare against) showed it silently drops `FieldSpec.length` for string fields — always emitting bare `TEXT`, unlike `decimal`, where `precision`/`scale` genuinely are honored. Confirmed by reading `sql.py` directly: `_sql_type()` has no length-aware branch for `string` the way it does for `decimal`. Real and verifiable, but explicitly flagged as lower-confidence than the aggregation finding above — it wasn't caught by this project's real-example-comparison discipline (no real reference DDL exists to diff against in any of the three rounds), only by incidental thoroughness. Left as an open, undecided item rather than fixed reflexively.

**Follow-up:** fixed shortly after, once explicitly requested — `_sql_type()` gained a `string`-with-`length` branch emitting `VARCHAR(length)`, mirroring the existing `decimal`-with-`precision`/`scale` branch exactly (same gating: only when the value is actually set, otherwise the existing bare-type fallback is unchanged). Verified against the real Customer Credit fixture's DDL, not just the synthetic test suite. See `ROADMAP.md`'s "Recently Completed" list.

## Why This Is Worth Recording

This is the strongest evidence yet that the real-example-first discipline scales past the first two, smaller confirmations: a materially bigger, structurally different third example still produced a full field-for-field, dataset-metadata-for-dataset-metadata match everywhere the existing IR actually claims to cover, and cleanly surfaced exactly where that coverage actually ends — rather than either silently producing wrong SQL for the aggregation-dependent fields, or being unable to say anything useful about the rest of the dataset. The instinct to treat the aggregation gap as its own future paper-contract candidate, rather than sketch a quick fix in the same session, is a direct, live application of the same discipline recorded above for `source_filter` and reconciliation v1 — this document exists partly so that discipline doesn't have to be re-argued for every new finding, and this round shows it held under real pressure to just "add the feature" while already deep in a real, evidenced example.

---

# Decision: `AggregateRule` — One Mechanism for Two Real Aggregation Shapes

## What Happened

The third real-world-validation round's headline finding (see the entry above) was that `SourceRef`/`JoinSpec`/`DedupRule` had no way to express a joined source needing `SUM(...) GROUP BY` — deliberately left unscoped and unimplemented in that same round. Once explicitly asked to scope and build it, the real reference SQL's two aggregation-dependent joined sources were re-examined side by side: `s066`/`s067` were already written as pre-aggregated CTEs (`SUM(...) GROUP BY <keys>`, joined normally afterward), while `bsid` was joined raw and aggregated via a `GROUP BY` spanning the *entire final select* — a materially different-looking shape, collapsing a one-to-many join at the end rather than before it.

Working through the semantics on paper rather than assuming two mechanisms were needed: `bsid`'s final-level `GROUP BY` only "works" because `knkk` (the primary source) is already unique per `(kunnr, kkber)` — the same grain `bsid` would be aggregated to if it were pre-aggregated the way `s066`/`s067` already are. Once that's true, joining a pre-aggregated `bsid` (grouped by `kunnr, kkber`, with the same conditional sign-flip `SUM` as the aggregate expression) to `knkk` produces an identical result set to the reference SQL's join-then-final-`GROUP BY` approach — the two shapes are mathematically equivalent for this data, not just superficially similar. That meant the two "distinct" real requirements the previous entry described were actually one requirement observed twice, in two different but equivalent hand-written forms.

## What Was Done

Added `AggregateRule` to `ir.py` — structurally parallel to `DedupRule` (`SourceRef.dedup`/`SourceRef.aggregate`, mutually exclusive, checked in `validation.py`) rather than a new concept bolted onto `SourceRef` directly. `group_by: List[str]` names the columns the source is aggregated down to one row per; `aggregates: Dict[str, str]` maps an output column alias to a raw SQL aggregate expression — same trust model as `DedupRule.order_by`/`FieldSpec.expression`, inlined as-is, checked only for non-blankness. `ModelGenerator._source_cte()` gained a third branch (alongside plain-passthrough and `DedupRule`'s `ROW_NUMBER()` shape) rendering a `GROUP BY` CTE. Deliberately, this required **zero changes** to `ModelGenerator`'s own final-select generation — it stays a flat, ungrouped `SELECT` exactly as before; the aggregation happens entirely inside the pre-joined CTE, the same architectural boundary `DedupRule` already established (collapse-to-1:1 happens before the join, not after).

Verified against real DuckDB and PostgreSQL data specifically designed to prove two things beyond "the query didn't error": a conditional debit/credit sign-flip (`SUM(CASE WHEN shkzg = 'S' THEN dmbtr WHEN shkzg = 'H' THEN -dmbtr ELSE 0 END)`) collapses multiple real rows to the correct signed total, and a `LEFT JOIN` against the pre-aggregated CTE still preserves a key with zero matching rows as `NULL`, rather than the `GROUP BY` step silently excluding it (a real risk worth checking explicitly, since a `GROUP BY` naturally only ever produces groups for keys actually present in the raw data).

## Why This Is Worth Recording

The previous entry's discipline — stop, write the finding down, don't design a fix under the momentum of the round that found it — paid off directly here: taking the extra step of re-deriving the reference SQL's two shapes from first principles, once actually asked to scope a fix, revealed they weren't two problems at all. Implementing two separate mechanisms (a pre-aggregation CTE option, and a second, much bigger change letting `ModelGenerator`'s final select become a grouped query) would have been solving a problem that didn't actually exist — real evidence of a need is not automatically evidence of the *shape* the fix should take, the same lesson the second real example ("A Second Real Example — One Correction, One New Feature, One New Gap") already recorded from a different angle. The smaller, later-arriving design is also the more architecturally conservative one: it extends the existing `DedupRule` collapse-before-join boundary rather than introducing a second, competing way for `ModelGenerator` to shape its output.

## Closing the Loop: The Full Retest

With `AggregateRule` built, the full `customer_credit` dataset — all 50 real reference fields, not just the 35 that didn't need aggregation — was hand-modeled and re-run through the same comparison process. Every field's role/description/`source_field`, and every dataset-level `dbt_extended` field, matched the real reference exactly (verified programmatically, the same script used for the first pass). One real, self-caught data point along the way: the reference material marks `struct_s066_sum_oeikw`/`struct_s066_sum_aoeiw` as `role: dimension` despite being `SUM`-aggregated dollar amounts, while the structurally identical `struct_s067_sum_*` fields are marked `measure` — an inconsistency in the human-authored reference itself (the same class of finding as the earlier `skfor`/`casha`/`klimk` D/M markings), not a Structifact defect; the hand-model was corrected to match the reference exactly rather than "fixing" the reference's own inconsistency.

Beyond the field-metadata match, the generated model was executed end-to-end against synthetic data specifically designed to prove the computed fields derived from multiple pre-aggregated sources come out numerically correct, not just that the SQL runs: a customer with a debit and a credit `bsid` row (sign-flip aggregation), one `s066` row, and one `s067` row produced `struct_credit_exposure` and `struct_credit_limit_used_percent` values matching hand-calculated expectations exactly.

One new, real, but separately-scoped finding surfaced during the retest, unrelated to aggregation: comparing the full 50-field reference against the earlier `discover --ai` draft (44 fields) showed the AI extraction had silently omitted six real dimension columns (`struct_s066_ssour`/`vrsio`/`cmwae`, `struct_s067_ssour`/`vrsio`/`cmwae`) that are genuinely present, unambiguously, in the raw requirements xlsx text — not excluded by any visible logic the other omissions in this document's earlier entries had (grey-fill formatting, out-of-scope tables). This wasn't caught during the original round because that round's comparison focused on the 44-field draft's own internal consistency, not a field-count audit against the full reference. Logged as a real, evidenced `discover --ai` gap, not yet investigated or fixed — see `FUTURE_WORK.md`.

---

# Guiding Principle

Every future decision should be evaluated against:

> Does this make metadata more useful, workflows more reliable, and engineering effort more repeatable?

If not, the additional complexity may not justify the feature.
