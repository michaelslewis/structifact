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

## Before a 1.0 Release

Items deliberately scoped out of earlier phases for good reason (avoiding
premature complexity, no real credentialed environment to test against yet)
but that should be revisited before Structifact is called 1.0, since a 1.0
implies the core promise — "generate reliable systems from metadata" — holds
up beyond the narrowest proven case:

* **Real Snowflake Executor implementation** (Phase 8B) — the Executor
  interface is designed to support this without a redesign. DuckDB and,
  as of Phase 8A, PostgreSQL are both real, tested implementations
  (PostgreSQL verified with real integration tests against an actual
  server, CI-enforced via a `postgres:16` service container — see
  ROADMAP.md); Snowflake remains unimplemented. No longer just an
  abstract gap: see "Legacy Migration and Reconciliation" below for a
  concrete real-world need now motivating it. To be validated against
  a personal free-trial Snowflake account, matching how PostgreSQL was
  validated against a real, personally-run server rather than any
  employer's instance — never a work account or work data.
* **Retry logic** (Phase 8C-v2) — now done. `structifact/executors/base.py`
  gained `retry_transaction(executor, fn, retry_on, max_attempts)`, a
  module-level function (not a new `Executor` method — retrying means
  re-running the caller's code, which a context manager can't do to its
  own body), built on `transaction()` (Phase 8C-v1) with zero changes
  to any `Executor` implementation. Scoped against a real, empirically-
  reproduced transient failure — PostgreSQL's `serialization_failure`
  (SQLSTATE `40001`) from two genuinely concurrent `SERIALIZABLE`
  transactions, verified interactively before any code was written —
  rather than a hypothetical retry taxonomy. See ROADMAP.md for the
  full contract (what `fn` must guarantee, exact attempt-counting
  semantics) and test plan. No CLI exposure yet — no real caller with
  concurrent writers exists today.
* **Connection pooling** (Phase 8C-v3) remains deliberately deferred —
  no usage pattern anywhere in the codebase motivates it (confirmed by
  inspection: exactly one `Executor` instance is ever constructed, per
  CLI invocation).
* **Materializing ModelGenerator's transformation SQL into a real target
  table** (Phase 8D v3) — now done. `ModelGenerator.generate_insert()`
  wraps its SELECT in a typed `INSERT INTO <target> (<columns>) <select>`,
  chosen over `CREATE TABLE ... AS SELECT` so the target's types/
  constraints stay authored by Structifact's metadata rather than
  inferred by the engine — confirmed empirically, not just argued in
  the abstract, before implementation. Reuses `Executor.execute_ddl()`
  as-is; no new Executor method. A real, load-bearing constraint
  surfaced during investigation: materializing into a table sharing a
  name with any relation the model reads from is a self-referential
  collision (the common case, since `source_table` defaults to the
  dataset's own name) — rejected with a clear error, scoped as a
  materialization-specific precondition rather than a general
  `DatasetSpec` validation rule. Verified on both engines, asserting
  persisted table contents (not just query-time results), including
  that a failed materialization is atomic (no target table left behind
  at all) and that the target's declared constraints are genuinely
  enforced, not engine-inferred. See ROADMAP.md's Phase 8 section for
  the full contract.
* **CLI exposure for materialization** (Phase 8D v4) — now done.
  `structifact execute` gained `--materialize`, mutually exclusive
  with `--data`, failing fast (before connecting) when materialization
  is impossible for the dataset. Wired into the same `transaction()`
  scope and verification-query reporting `--data` already used — no
  new CLI architecture. Deliberately still excluded: a `--retry` flag
  (no real concurrent-writer caller) and a standalone read-only preview
  mode (`generate -g model` already covers "see the SQL text";
  materialization's own verification query already shows the
  persisted result). Building this slice's real fixtures also
  surfaced and fixed a genuine bug: `yaml.py` had never parsed
  `source_table`/`sources`/`joins`/field-level `source`/`source_column`
  from a real YAML file — see `DECISION_HISTORY.md` for the full
  writeup (the same class of bug as the Phase 1 constraint-parsing
  gap). See ROADMAP.md's Phase 8 section for the full contract.
* **`docs/ARCHITECTURE.md`'s execution-pattern documentation** — found
  during the 1.0 readiness audit: the document has zero mentions of
  `Executor`, `execute`, or materialization anywhere across its full
  length, despite Phase 8 adding an entire fourth architectural
  pattern alongside generation/quality/dependency-resolution. This is
  a real content gap, not a stale-wording fix — a properly-scoped
  future task in its own right rather than something to fold into a
  documentation-consolidation pass. Specific, bounded scope for when
  this is picked up: document the `Executor` abstraction and the
  database-execution boundary, the `transaction()`/atomicity contract,
  `retry_transaction()`, materialization (`generate_insert()` and the
  typed-INSERT-over-CTAS decision), and the DuckDB/PostgreSQL executor
  implementations — as a fourth pattern alongside the three already
  documented, not a rewrite of the other three.

A note on how this document has been kept: several sections below described work that has since actually shipped (AI-assisted discovery, documentation generation, the first Transformation Framework step, and a real Data Quality Framework going well beyond what was originally sketched here). Those sections have been trimmed or removed rather than left describing already-completed work as "future." See ROADMAP.md's "Recently Completed" section for the authoritative current list of what's done.

Legacy Migration and Reconciliation (New Direction — Real-World Trigger)

Observing how legacy-ETL-to-warehouse migrations actually go in practice reframed part of Structifact's ambition (see DECISION_HISTORY.md's "Real-World Validation" entries for the datasets that motivated this, and PROJECT_CONTEXT.md for this project's independence from any employer). Retiring an aging ETL/BI stack in favor of a modern warehouse is slow for a reason that surprises people: the bottleneck isn't writing the new SQL, it's *proving* the new data source produces results the business already trusts. That verification step is where weeks turn into months. It's a common shape of pain across the industry — any organization retiring a legacy ETL tool eventually hits it — and nothing about it is specific to one company or one stack.

Three new fronts, in priority order, each meant to be validated only against personal or synthetic infrastructure — never real company data or systems, the same discipline this project has held to from the start:

* **Reconciliation — v1 done, treated as an experiment.** Given two datasets meant to represent the same logical output (an old system's and a new one's), `structifact reconcile` (Phase 12, `structifact/reconciliation.py`) reports row-population coverage (rows only on one side, by key, via a required explicit old<->new field mapping) and aggregate equivalence on declared measures, restricted to the matched population. Built and verified against a synthetic acceptance fixture (`examples/reconciliation_demo/`) — see `docs/ROADMAP.md`'s Phase 12 section and `docs/DECISION_HISTORY.md` for the full scoping account, including a real correction to the paper contract (aggregating over the matched population, not the full old/new populations) made before any code was written. Explicitly NOT yet done: column-level comparison on matched rows (v2), and any tolerance/normalization policy (numeric epsilon, date-format equivalence) — see below. **The higher-priority next step is not v2** — it's testing v1 against a real, sanitized legacy-migration example (never real employer data or systems) to see whether it actually catches the kinds of mistakes that motivated it, before investing further. That experiment's outcome should decide whether reconciliation continues, not the roadmap.
* **Snowflake Executor** — see "Before a 1.0 Release" above; an already-acknowledged, designed-for gap, now with a concrete real motivating need rather than an abstract one.
* **Tableau workbook introspection** — a new `discover`-style input reading a `.twb`/`.twbx` file (plain XML) to infer the fields, joins, and calculated-field logic an existing report actually depends on — potentially replacing days of manual requirements-gathering with something closer to what `discover --requirements --ai` already does for a written document. Genuinely unstarted; before any design, needs an exploration pass against a real workbook (Tableau's own public sample workbooks, e.g. Superstore, or the Tableau Public gallery — never a real company workbook) to see what's actually parseable, per this project's real-example-first discipline.

Reconciliation v2 (deliberately not yet scoped, pending the real-migration experiment above): full column-level comparison on matched rows, telling you *which* field disagrees on a matched row rather than only inferring a discrepancy exists via an aggregate mismatch — would have directly caught the kind of change v1's own synthetic example plants (a single field's value changing on an otherwise-matched row), which v1 can currently only detect indirectly, through an aggregate that happens to net non-zero. A dedicated tolerance/normalization policy (numeric epsilon, date-format equivalence, case-insensitive string comparison) is a separate, also-deferred question — real migrations hit this constantly, but no real example has yet forced a specific policy choice.

Two smaller, related ideas surfaced in the same conversation, worth recording even though neither is close to being worked on:

* **Configurable generation** — e.g. a per-alias naming convention, or which output artifacts (SQL/YAML/CSV/others) a given project actually wants, as a project-level config file rather than something fixed. Separable from, and much smaller than, the structifact.com/GUI question below (see "Web Interface Exploration" and "IDE Integration" further down) — worth a real design pass once there's enough real usage to know what actually needs to be configurable, not designed from guessing now.
* **Who this is actually for, beyond one person's own employer** — the working thesis is that "define once, generate consistently, and prove the new thing matches the old thing" generalizes to any legacy-ETL retirement, not just a Data-Services-to-Snowflake one. That's untested against any example outside the author's own situation, and deserves real thought (concrete personas, the adjacent tool/consulting landscape, what's actually differentiated) before being assumed true.

Deliberately still not started, and deliberately not pursued opportunistically alongside the above: structifact.com deployment and any GUI. The project's own standing discipline already defers this until the core engine has more maturity — see "Web Interface Exploration" and "IDE Integration" below — and that's more true now, not less, with a whole new capability area about to be added on top of the existing one.

AI-Assisted Metadata Discovery

Status: substantially implemented. See ROADMAP.md for the current, detailed status — raw-CSV schema inference, AI-assisted field descriptions, and AI-assisted requirements-document extraction are all real, shipped, opt-in, cost-estimated, and always produce a draft for human review rather than anything auto-applied. The architectural boundary this section originally described — AI produces suggestions, Structifact metadata remains the source of truth — was upheld throughout.

What remains genuinely future here:

column classification beyond dimension/measure
validation-rule *recommendations* (as opposed to the deterministic rule-checking that already exists in quality.py)
interactive/IDE-integrated metadata authoring assistance (see the IDE Integration section below, which folds this in)
AI-assisted documentation (DocsGenerator is fully deterministic today)
formatting-aware requirements extraction — `discover --ai` now reads a raw `.xlsx` requirements document directly (see ROADMAP.md, "Real-World Validation"), but only its literal cell text; it has no awareness of cell *formatting*. A real requirements workbook has already been observed using a grey fill to mark a candidate field as a join-key/filter-only column that should not appear in the output — a real, load-bearing signal a plain-text dump cannot represent, which caused several such fields to be silently included in an AI draft that the source document had excluded by color alone. Worth a real design pass (what formatting signals to surface, and how — a per-cell hint in the extraction prompt? in `unresolved_notes`?) once a second real example confirms the shape recurs, per this project's usual discipline — not designed abstractly from the one observed case

a real, evidenced extraction gap, distinct from the formatting-awareness item above, originally found retesting the third real-world requirements document (a SAP-shaped account-summary source) after `AggregateRule` shipped, since substantially reframed by a follow-up experiment. `discover --ai`'s first-pass draft omitted six real dimension fields (`struct_aggopen_srckey`/`versionkey`/`currcode`, `struct_aggdue_srckey`/`versionkey`/`currcode`) that are genuinely present, unambiguously, in the raw extracted requirements text — confirmed to be a clean extraction with no mechanical cause. Re-running the identical prompt against the identical document did NOT reproduce the same omission, but the second run had its own, different failure mode: it picked up the six previously-missing fields but lost the "this is an aggregate" semantic on six measures and incorrectly added sixteen raw/join-only columns the document's own dimension/measure marker column explicitly leaves blank.

**Follow-up experiment, and a partial fix.** Rather than wait for a second real document of this exact shape, a synthetic one was deliberately built to isolate the variable (see `DECISION_HISTORY.md`): four side-by-side folder-groups per row, a blank-vs-marked role column as the only exclusion signal, real fields sitting sparsely among mostly-blank rows — the same structural risk pattern, with a precisely known ground truth since the document was authored rather than found. Two independent runs against it produced *nearly identical* results to each other — contradicting a pure run-to-run-instability explanation — but both consistently included every blank-marker field anyway, with a confidently guessed role, even though the model's own `unresolved_notes` explicitly flagged "no explicit role... inferred" for those exact fields. That reframes the original finding: what looked like instability on the real document may be this same underlying weakness (no explicit "blank marker means exclude" instruction) manifesting inconsistently on a more complex document, not pure randomness.

`build_requirements_prompt()`'s role instruction now explicitly says a blank marker where sibling fields clearly have one should exclude the field, not prompt a guess. Verified against the same synthetic document: real, partial improvement — the model no longer guesses a role for these fields and now surfaces accurate reasoning in `note`/`unresolved_notes` (correctly identifying join-key duplicates by name across tables), but several such fields still appear in the `fields` list without a role, rather than being omitted from `fields` entirely as asked. Deliberately not iterated further in the same round — real progress was made and is worth keeping; chasing a fully clean result risks diminishing returns for marginal prompt-wording tweaks. A tighter instruction (or a stronger structural change, e.g. a required `excluded` boolean per candidate rather than relying on omission) remains open for whenever there's a real reason to revisit it.

a real, mechanical gap found scoping a fourth real example (`shipment_header`, ~500 fields, a materially larger document than any of the first three), now fixed — `discover --ai`'s response was cut off entirely by `AnthropicLLMClient`'s `_APPROX_OUTPUT_TOKEN_CAP`, and raising the cap alone wasn't a complete fix either: a diagnostic attempt at a higher cap was rejected by the Anthropic SDK itself before any request was sent (requests estimated to run past 10 minutes require streaming, which `complete()` didn't implement). `complete()` now uses the streaming API (with visible progress feedback), and the cap is raised to 64,000 with real headroom over the ~27,000 tokens this document actually needs. Verified against the real document that originally failed: it now completes without truncation.

Fixing that surfaced two further, genuinely new findings from the same document. Both got an explicit-instruction fix (matching the pattern that worked for YAML quoting and the blank-role-marker case), and both fixes were verified against the real document again — and neither worked:

* **`discover --ai` does not reliably apply a later section's override of an earlier-declared field's attributes on `claude-haiku-4-5` — confirmed to be at least partly a model-capability limit, not purely a prompt-wording problem, and deliberately not being pursued further right now.** `shipment_header`' requirements document defines fields once, then has a later "UPDATED FIELD NAMES, COMMENTS, AND FIELD DESCRIPTIONS" section giving a different `description` (and a `comment`) for specific already-named fields, while their role/type/length from the first section still apply. Three separate real runs against this pattern (full document, twice; a trimmed real excerpt isolating just one table) produced three genuinely different failure shapes on `claude-haiku-4-5` — silently keeping the original value, falsely claiming in `unresolved_notes` that the override had been applied, and creating a wrongly-named duplicate field — never a correct merge. The same trimmed excerpt run against `claude-sonnet-5` got it exactly right: correct name, the override's replacement description, the override's other value correctly placed in `comment`. That settles the open question from the earlier entries: this is at least partly a genuine model-capability threshold at `claude-haiku-4-5`'s tier, not something a clearer prompt alone would fix. See `DECISION_HISTORY.md` for the full three-run account, including a real cost-discipline failure during the diagnostic itself (escalating retries — a higher token cap, a stronger and more expensive model, a longer timeout — without checking in first) that became the occasion for a broader pause on this whole thread. Deliberately not pursued further for now — not because it's unsolvable (a stronger model demonstrably can), but because continuing to chase a complete fix for the fast/cheap model, on one large document's edge-case pattern, stopped being a good use of engineering time relative to this project's actual current priorities. If picked up again, the real design question is bigger than a prompt tweak: whether `discover --ai` should support selecting a different (costlier) model for harder documents, which is a real, user-facing feature decision, not a default to make unilaterally.
* **`build_requirements_prompt()`'s extraction schema didn't ask for `comment` at all — fixed, but unverified in isolation.** Added as an optional extraction field. Cannot yet be confirmed working on real data independently of the override-merge finding above, since in `shipment_header` specifically, every `comment` value only ever comes from the override section, which isn't being applied — so this fix's own correctness is currently untestable against this document until that's resolved. Unit-tested (`FakeLLMClient`) and confirmed to render correctly when present in a parsed response — the gap is specifically "does a real model produce one here," not "does Structifact handle one if given."
* **`unresolved_notes` can assert a completion that didn't happen — logged, not scoped.** The six-arm override-merge characterization (`DECISION_HISTORY.md`) reproduced this on demand for the first time: one of three `claude-haiku-4-5` runs against the full hard-mode synthetic document silently dropped every one of twelve `comment` overrides while its own `unresolved_notes` stated "all revisions have been applied to corresponding field entries above" — false, checked directly against the actual field output, not assumed. The real `shipment_header` document produced the identical pattern earlier ("all revisions have been applied to primary field entries," also false). `DESIGN_PRINCIPLES.md` #6 ("Explicit Over Magic") is why `validate-data` fails loudly on a missing `--ref` instead of silently reporting "no issues found" — `discover --ai` currently violates the same principle in a different subsystem, surfacing the model's own unverified success claim as if it were a checked fact. The remedy needs no AI work, since it's a Structifact-side trust problem, not an extraction-quality one: either strip completion/success claims out of `unresolved_notes` before rendering (treat the field as being for genuine open questions only, not self-assessment), or verify any such claim deterministically against the parsed draft before letting it reach the user. Not designed further here, per this project's standing discipline against scoping a fix under the momentum of the round that found it.

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

The existing IR architecture provides a foundation for this — DatasetSpec has real, structural knowledge of a dataset's sources (SourceRef/JoinSpec), of foreign-key relationships between datasets (ConstraintSpec's target_table/target_column, now actually meaningful since Phase 6 v3 resolves and checks them against real data), and, as of the Phase 7 remainder, an explicit, validated dependency graph between Structifact-defined datasets themselves (DatasetSpec.depends_on, structifact/dependencies.py). None of these three was designed as a lineage feature, but all are exactly the kind of structural information a future lineage capability would need — the dependency graph in particular was close to lineage-ready as a data structure, which is exactly why it was the graph impact analysis got built on top of.

Impact-analysis queries ("what depends on X?") are now real — Phase 9, v1: `impacted_by()` in `structifact/dependencies.py`, exposed via `structifact impact <dataset_name> <path> [<path> ...]`. It deliberately reuses `build_dependency_graph()`/`execution_order()` rather than reimplementing traversal, so it stays grounded in the same canonical graph rather than developing its own interpretation of `depends_on`. See ROADMAP.md's Phase 9 section for full detail.

What's still genuinely future: a rendered lineage *view* and dependency-graph visualization. Worth revisiting once there's a concrete use case for either, rather than designing them in the abstract now — the same discipline that let impact analysis wait until the dependency graph existed to build on.

Plugin Architecture

As Structifact grows, a plugin architecture may become valuable.

Possible extension points: input adapters (JSON, database schemas, API definitions, cloud storage metadata), generators (lineage, warehouse-specific models, testing frameworks), validation providers (custom business rules, external validation engines, organization-specific standards).

A plugin architecture should only be introduced when existing extension patterns become insufficient. The current adapter and generator registries remain the preferred mechanism, and have proven sufficient for every extension so far — every generator and adapter added has fit the existing registry pattern without needing anything more elaborate.

IDE Integration: VS Code Extension (and Potentially Other Editors)

A concrete idea, not yet started: package some of Structifact's capability as an editor extension — starting with VS Code, since that's the primary development environment — rather than (or alongside) a hosted web GUI.

Potential capabilities, roughly in order of how self-contained each would be to build:

syntax highlighting for the metadata YAML dialect
inline validation — surface `structifact validate`'s errors as editor squiggles/diagnostics as the file is edited, not just on a manual CLI run
command-palette actions to run `validate` / `generate` / `validate-data` / `deps` against the open file(s) without leaving the editor
a webview panel previewing generated output (SQL, the transformation model, a quality report, a dependency execution order) without a separate terminal step

The appeal, relative to the structifact.com/GUI idea below: meaningfully lower lift (no hosting, no auth, no backend service — it runs against the same local CLI that already exists), dogfoodable in the course of normal Structifact development itself (which would likely surface real UX gaps faster than a web GUI would), and arguably a stronger, more concrete portfolio artifact — a published extension is something a reviewer can install and try in under a minute, versus a hosted site that requires deploying and maintaining infrastructure.

If VS Code integration proves valuable, the same underlying capability (mostly just shelling out to the existing CLI and parsing its output) could reasonably extend to other editors later — JetBrains IDEs, Vim/Neovim via LSP, etc. — but that's explicitly a "later, if it makes sense" extension of the idea, not part of an initial scope.

Sequencing note: this idea and the structifact.com/GUI idea below are both explicitly deferred until the core engine has more maturity behind it (see ROADMAP.md's Immediate Development Focus / this document's Open Source and Community Direction section for the structifact.com framing). Between the two, the editor-extension idea is currently favored as very likely the better first move if/when this category of work is picked up — lower lift, faster feedback loop, stronger portfolio signal for the effort involved — but no commitment has been made to build either yet.

Web Interface Exploration

A future interface could provide visibility into Structifact projects.

Potential capabilities:

Metadata Browser — explore datasets, fields, descriptions, constraints, relationships, and dependencies
Lineage Visualization — display source → dataset → generated artifact → downstream consumer, and the dataset-to-dataset dependency graph now available from structifact/dependencies.py
Validation Dashboard — display validation results, quality trends, failed checks, metadata history (this would have real data to draw on now, given quality.py's structured QualityResult output — previously this section was purely hypothetical since there was no data-quality checking at all to visualize)

The web interface should remain separate from the core framework. Structifact should remain usable as a Python library, a command-line tool, and an automation component regardless of whether this is ever built.

See the IDE Integration section above for the current thinking on which of these two directions (editor extension vs. web interface) is the more likely near-term move, if either is picked up before the engine matures further.

Data Catalog Integration

Structifact metadata could eventually integrate with broader governance systems.

Potential integrations: data catalogs, governance platforms, business glossaries, documentation systems.

The core metadata model should remain platform-independent.

Warehouse and Platform Integrations

DuckDB and PostgreSQL are now real, tested Executor implementations (Phase 8A — see ROADMAP.md). Future exploration may still include: Snowflake, BigQuery, Databricks, cloud object storage.

These should be implemented through Executors (or adapters/generators, for non-warehouse targets) rather than embedded into the core framework.

The architectural principle: Structifact defines intent. Platform-specific components implement execution details.

Transformation Framework — Remaining Scope

Status: complete as originally scoped, now including a real-world-driven addition. A single computed field can be represented and emitted as executable SQL (ModelGenerator), a dataset can be built from multiple sources including the same physical table joined in multiple times under different roles with either priority-based deduplication or aggregation (SourceRef/JoinSpec/DedupRule/AggregateRule), and dataset-level dependencies can be declared, validated as a collection, and resolved into a deterministic execution order with cycle detection (DatasetSpec.depends_on, structifact/dependencies.py, the `structifact deps` command). See ROADMAP.md for full detail and DECISION_HISTORY.md for the scoping process.

**`AggregateRule`** (found via a real third-world-validation requirements document — a SAP-shaped account-summary source; see DECISION_HISTORY.md) is now built: the second, mutually exclusive way a `SourceRef` can collapse a joined source to one row per key before the join happens, alongside `DedupRule`. Where a first read of the real reference SQL suggested two materially different aggregation shapes were needed (a source pre-aggregated before its join, and a source aggregated via a `GROUP BY` spanning the entire final select), these were confirmed mathematically equivalent before implementation — one mechanism (a pre-aggregated `GROUP BY` CTE) covers both, without changing `ModelGenerator`'s own final-select shape at all. Verified against real DuckDB and PostgreSQL data.

What remains genuinely future: cross-dataset value resolution — one dataset consuming another's computed/resolved value (e.g. joining a lookup dataset with conditional-fallback logic and making the resolved value available to downstream computed fields). A real synthetic example (examples/workorder_demo) exercises this exact pattern via an FX-rate lookup, which is real evidence it recurs — but it was deliberately kept out of this milestone's scope, since dependency *declaration* and cross-dataset *value resolution* are different concerns (see DECISION_HISTORY.md). Should only be scoped once a differently-shaped example justifies the abstraction, matching how every other IR addition in this project has been grounded — not designed abstractly in advance.

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

The registered domain, structifact.com, provides future flexibility for documentation, demonstrations, and project resources. It does not imply a current hosted product or commercial offering, and deployment is deliberately deferred — the current strategic framing (see PROJECT_CONTEXT.md / DECISION_HISTORY.md) treats Structifact primarily as a portfolio/credibility asset supporting consulting opportunities, not a product to launch, and holds off on a GUI or public-facing site until well past current engine maturity. See the IDE Integration section above for the currently-favored alternative if/when this category of work is picked up.

Educational Value

Structifact may also serve as an educational example of: metadata-driven architecture, data engineering design, Python package development, validation frameworks, testing practices, software architecture.

Potential educational materials: architecture walkthroughs, tutorials, example projects, implementation guides.

Guiding Principle

Future expansion should continue following the central philosophy:

Increase engineering leverage without sacrificing transparency, reliability, or control.

The purpose of future capabilities is not automation for its own sake.

The purpose is to help engineers build better data systems with less repetitive work and greater confidence.
