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

# Recently Completed

The following items were previously described below as planned work.
They are now implemented, tested, and covered by CI:

* **Type-aware SQL generation** (Phase 4) — the SQL generator maps
  normalized types to real SQL types (`INTEGER`, `TIMESTAMP`,
  `DECIMAL(precision,scale)`, etc.) instead of emitting `TEXT` for
  every column.
* **`structifact validate` command** (Phase 2 / Phase 3) — loads
  metadata, validates schema and constraints, reports the documented
  checkmark output.
* **CSV/Excel adapters normalize types** the same way the YAML adapter
  does, via `types.parse_type()`.
* **Continuous integration** — the test suite runs automatically via
  GitHub Actions on every push and pull request against `main`
  (Python 3.11 and 3.12; 322 tests as of this writing).
* **A golden-path example** (`examples/customers/`) shows the full
  input → output flow end to end for a new reader.
* **`structifact discover`** (Phase 10, deterministic half) — infers
  a draft schema from raw CSV sample data (types, nullability, a
  conservative "possible key" hint), including handling for common
  real-world messiness (null placeholders like `NULL`/`N/A`,
  leading-zero identifiers, and hints for currency/date-formatting
  issues). Writes a clearly-labeled draft for human review; never
  auto-validated or auto-generated from.
* **`structifact discover --ai`** (Phase 10, LLM-assisted field
  descriptions) — optional, off by default, zero cost/network unless
  explicitly invoked. A provider-agnostic `LLMClient` interface
  (`structifact/llm.py`) shows a cost estimate and requires explicit
  confirmation (or `-y`) before any real request; declining makes
  genuinely zero API calls. Bring-your-own-key via `ANTHROPIC_API_KEY`
  (never hardcoded); `AnthropicLLMClient` implements `LLMClient`
  without locking the interface to one provider; `FakeLLMClient`
  lets the test suite exercise this logic with no real network/API
  key. AI-suggested descriptions are clearly marked distinct from
  deterministic ones in the draft output.
* **`structifact discover --requirements <file> --ai`** (Phase 10,
  LLM-assisted requirements-document extraction) — extracts a draft
  field list from a raw requirements document (`.md`/`.txt`) of
  arbitrary shape: multi-column tables, plain prose, terse bullet
  lists, or a mix, often with freeform notes outside any table. No
  deterministic half is possible for this input type, so the path
  requires `--ai` explicitly and does nothing without it. Fields
  whose value is derived from other fields (a "Logic" column, inline
  math, or logic described in prose) are flagged `computed: true`
  with the raw logic preserved as text rather than translated to SQL
  automatically. Anything structurally unplaceable — join keys/
  relationships between tables, cross-field business rules,
  deprioritization or confirmation-status notes — is surfaced in an
  `unresolved_notes` list rather than silently dropped.
* **Field `role` classification** — `FieldSpec.role` (dimension |
  measure) is populated by the YAML adapter, and `validation.py`
  checks it's a supported value when present.
* **Catalog generation** — two generators: `CatalogCSVGenerator`
  (name/description/role/type/length, run by default alongside SQL/
  dbt) and `ExtendedCatalogCSVGenerator` (a richer column set
  matching a specific downstream tool's format, including a
  configurable `changed_by` and a real generation timestamp —
  deliberately **not** run by default).
* **`DocsGenerator`** (Phase 5 — Documentation Generation) — renders
  human-readable Markdown from a dataset's actual metadata (name,
  type with length/precision-scale, raw declared type, role,
  nullable, accepted_values, description, computed-field details, and
  constraints), per field and dataset-level. Never fabricates a value
  a field doesn't have. Opt-in (`generate -g docs`), not run by
  default.
* **Computed-field support in the IR** (Phase 7, first step) —
  `FieldSpec` gained `computed`, `expression`, and `depends_on`.
  `expression` is assumed-valid SQL meant to be inlined as-is by a
  generator — deliberately NOT the same thing as the freeform
  business-logic text `discover --requirements --ai` extracts (e.g.
  "if order_type in ('RET','CRM') then -1 else 1" is pseudocode, not
  valid SQL as written). Promoting a discovery draft's raw logic into
  a real `expression` is a human decision, not automatic. All three
  adapters parse it; validation checks well-formedness only.
* **Generator selection** — `structifact generate` accepts
  `-g/--generators` to explicitly choose which generators run.
* **`ConstraintSpec` foreign_key/check** (Phase 1, closing the
  previously-tracked gap) — `ConstraintSpec` gained `target_table`/
  `target_column` (foreign_key, single-column only — composite FK
  deliberately deferred) and `expression` (check). `validation.py`
  checks well-formedness (foreign_key requires exactly one column
  plus non-blank target_table/target_column; check requires a
  non-blank expression). `SQLGenerator` now emits `FOREIGN KEY (...)
  REFERENCES ...` and `CHECK (...)` DDL. A real bug was found and
  fixed in the process: `yaml.py`'s constraint parsing had never
  actually read `target_table`/`target_column`/`expression` from a
  YAML file (only `type`/`columns`) — meaning this feature, though
  correct in the IR/validation/generator layer and fully covered by
  unit tests, was silently unusable via any real YAML file until the
  fix. Found by running the real CLI against a real file during
  Phase 6 v3 verification, not by the existing test suite. See
  `DECISION_HISTORY.md`.
* **`SELECT`-based transformation-model generator** (`ModelGenerator`,
  Phase 7 second step) — emits a real, executable `SELECT` for a
  dataset's computed fields, distinct from `SQLGenerator`'s
  schema-only DDL. `Generator.generate()` may now return `None` to
  mean "nothing to generate for this dataset" (this generator returns
  `None` for a dataset with no computed fields and no sources/joins);
  `cli.py`'s `generate` loop was updated to skip writing in that
  case. Added `DatasetSpec.source_table` (falls back to the dataset's
  own name when unset). Opt-in (`-g model`).
* **Sources/joins/dedup IR** (Phase 7, "Two Further Gaps" closed) —
  `SourceRef`, `JoinSpec`, `DedupRule`, plus `FieldSpec.source`/
  `source_column` and `DatasetSpec.sources`/`joins`. A dataset can now
  be assembled from more than one source, including the same physical
  table joined in multiple times under different roles (e.g. a shared
  partner table joined separately for requested-by/billed-to/site-
  contact), each with its own filter and a priority-based
  deduplication rule (`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY
  ...) = 1`, matching the reference SQL this was scoped against).
  `ModelGenerator` now qualifies every column reference by its source
  alias — a deliberate output change from its earlier unqualified
  form. `validation.py` checks the metadata *relationships* (unique
  source names, joins/fields resolve to declared sources, dedup rules
  non-empty, supported join types) without parsing the raw SQL
  fragments (`filter`/`on`/`order_by`), matching the existing
  `expression` trust model.
* **Data Quality Framework** (Phase 6, all three planned increments —
  see the dedicated Phase 6 section below for full detail) — a new
  `structifact validate-data` command and `structifact/quality.py`
  subsystem check real CSV data against a schema's already-declared
  rules: required fields, uniqueness, accepted values (v1); numeric
  range and regex pattern (v2); and foreign-key/relationship
  validation against a second dataset's real data via `--ref` (v3).
  Not a `Generator` — a deliberately separate subsystem, since
  checking real data needs two inputs (schema + data) where every
  generator only ever needed one. Structured `QualityIssue`/
  `QualityResult` output, formatted into human-readable text entirely
  in `cli.py`, never inside the checking logic itself.
* **Dataset dependency tracking** (Phase 7, closing the previously
  "genuinely unstarted" remainder) — `DatasetSpec` gained `depends_on`
  (a plain `List[str]`, distinct from the existing `FieldSpec.depends_on`,
  which refers to fields within the same dataset). Per-dataset
  validation catches blank/duplicate/self-referencing entries; a new
  `structifact/dependencies.py` subsystem — following the same
  precedent as `quality.py`, since resolving a collection of datasets
  is a genuinely different question from validating one — handles
  duplicate dataset names, unresolved dependency references, and
  cycle detection (a hard error naming the full cycle), and derives a
  deterministic execution order across a collection of datasets.
  Dependency *ordering* is semantically guaranteed; the relative order
  of two mutually-independent datasets is not, though output is still
  deterministic run-to-run. Exposed via a new `structifact deps`
  command. Declaration/ordering only — deliberately does NOT resolve
  cross-dataset values or generate SQL for how one dataset obtains
  another's data; see `FUTURE_WORK.md` for that still-future problem
  and the real example (`workorder_demo`) that motivates it. New
  `examples/dependency_demo/` (a four-dataset chain
  plus a deliberately-broken cyclic variant) as the acceptance
  fixtures. See `DECISION_HISTORY.md` for the scoping process,
  including a real test-fixture bug caught by running the tests, not
  by the tests themselves.
* **DuckDB Executor, first slice of Phase 8** — a new `Executor`
  interface (`structifact/executors/`), following the same registry
  pattern as adapters/generators, lets Structifact actually execute
  its own generated DDL against a real database rather than only ever
  producing SQL text. `DuckDBExecutor` is the first (and currently
  only) real implementation — local, no credentials — proving the
  interface works before a credentialed engine (Postgres, Snowflake)
  is attempted. New `structifact execute` command, with `--data` and
  `--drop-if-exists`. Deliberately does not yet execute
  `ModelGenerator`'s transformation SQL, and has no transaction/
  pooling/retry handling — see `FUTURE_WORK.md`'s "Before a 1.0
  Release" section. See the dedicated Phase 8 section below for full
  detail.
* **Documentation refresh** — this document and its siblings
  (`CURRENT_STATE.md`, `CURRENT_IMPLEMENTATION.md`,
  `PROJECT_CONTEXT.md`, `EXAMPLES.md`, `DECISION_HISTORY.md`,
  `DESIGN_PRINCIPLES.md`, `ARCHITECTURE.md`, `README.md`) were
  substantially out of date relative to the codebase (several
  predated all of the work described above) and were rewritten
  against the actual current implementation rather than left
  drifting further.

The phase sections below are left largely as originally written for
planning context, but should not be read as "not yet done" for the
specific items called out above. Phases are organized by capability
maturity, not a strict execution order.

---

# Current State

## Established Foundation

Structifact's architectural foundation, described in earlier drafts
of this document as a set of goals, is now a set of completed,
tested capabilities. See "Recently Completed" above and
`docs/CURRENT_STATE.md` / `docs/CURRENT_IMPLEMENTATION.md` for the
authoritative current snapshot.

---

# Phase 1 — Strengthen the Metadata Model

## Goal

Create a stable and extensible metadata foundation.

## Status

**Done.** `DatasetSpec` is the canonical IR concept (`TableSpec`
remains a plain alias). `FieldSpec` covers intrinsic field
characteristics without having grown into an unmanageable flag
collection — see `DECISION_HISTORY.md` for how that line was held
even as real value-level rules (Phase 6 v2) were added.

## ConstraintSpec Foundation

**Status: fully done.** `primary_key`, `unique`, `foreign_key`, and
`check` are all validated and emitted in generated SQL — see
"Recently Completed" above. `foreign_key` supports single-column
references only; composite FK remains deliberately deferred until a
real example needs it.

---

# Phase 2 — Expand Validation Framework

## Goal

Make metadata validation a core Structifact capability.

## Status

**Done**, and expanded well beyond the original scope. Validation now
covers not just schema/constraint structure but genuinely checkable
*rule content* — a `pattern` must compile as valid regex, `min_value`
must not exceed `max_value`, sources/joins relationships must
resolve. See `docs/ARCHITECTURE.md`'s Validation Framework section.

---

# Phase 3 — CLI User Experience

## Goal

Make Structifact immediately usable and demonstrate the architecture.

## Status

**Done.** Five commands now exist: `validate`, `generate`, `discover`,
`validate-data`, and `deps` — each added only once the underlying
capability existed to expose.

```bash
structifact validate customers.yml
structifact generate customers.yml
structifact discover data.csv
structifact validate-data schema.yml data.csv
structifact deps schema_a.yml schema_b.yml
```

## Success Criteria

A reviewer should be able to clone the repository and understand the
framework through simple commands. This has been demonstrated
directly, including in `docs/EXAMPLES.md`, which shows every command
above run against real files in the repo.

---

# Phase 4 — Metadata-Driven Generation Improvements

## Goal

Increase the value generated from metadata.

## Status

**Done**, except one explicitly-optional item. Normalized types,
nullable behavior, and all four constraint types (`primary_key`/
`unique`/`foreign_key`/`check`) are emitted in generated SQL.
Configurable templates remain unstarted and genuinely optional —
nothing currently depends on them.

---

# Phase 5 — Documentation Generation

## Goal

Make metadata useful for human understanding.

## Status

**Done, first version.** `DocsGenerator` (see "Recently Completed"
above) renders dataset- and field-level Markdown documentation,
including computed-field details. Not yet covered: cross-dataset
views, relationship/lineage documentation (Phase 9 territory).

---

# Phase 6 — Data Quality Framework

## Goal

Make data reliability a first-class capability.

## Status

**Done — v1, v2, and v3, matching the original planned scope below.**
Built in three separately-verified increments, each grounded in a
real synthetic example (`examples/data_quality_demo/`) with the exact
expected report output agreed before implementation:

* **v1** — required fields, uniqueness, accepted values. Reused
  existing metadata (`nullable`, `primary_key`/`unique`,
  `accepted_values`) rather than inventing new IR concepts — the
  only genuinely new capability was reading real data rows at all,
  which Structifact had never done before this.
* **v2** — range (`min_value`/`max_value`, inclusive, `Decimal`-
  based) and pattern (regex, fullmatch semantics) validation. Unlike
  most raw-fragment fields elsewhere in the IR, these ARE validated
  at metadata-validation time, since a regex's compilability and a
  range's ordering are both genuinely checkable without data.
* **v3** — foreign-key/relationship validation against a second
  dataset's real data, via `--ref alias=schema.yml:data.csv`.
  Schema-aware (the referenced schema is loaded and validated, its
  declared name must match the `--ref` alias, `target_column` must
  be a real declared field — never inferred from a bare CSV header).
  A missing/misconfigured `--ref` is a hard configuration error,
  never a silent "no issues found." Existence/membership only — a
  duplicate value on the *target* side is that dataset's own
  uniqueness concern, not this check's.

Per the project's own YAGNI discipline (and explicit advice received
during scoping), Phase 6 is considered a complete milestone at this
point, matching its originally planned rule concepts below — not a
foundation for an automatically-continuing v4/v5/etc. Future
data-quality work should come from a concrete, real need, the same
way v1/v2/v3 each did, not from expanding scope for its own sake.

## Originally Planned Work (for reference — now realized as above)

Future rule concepts, as originally listed:

* required fields — done (v1)
* uniqueness — done (v1)
* accepted values — done (v1)
* regex validation — done (v2, as `pattern`)
* range validation — done (v2)
* relationships — done (v3, as `foreign_key` checking)

Every originally-planned rule concept in this phase is now
implemented.

## Validation Philosophy

Validation should remain deterministic, explainable, and
metadata-driven. This held up directly: `structifact validate-data`
produces the same report for the same schema and data every time, and
every reported issue traces to a specific, named metadata rule.

---

# Phase 7 — Transformation Framework

## Goal

Move from describing datasets toward describing data workflows.

## Status

**Done, matching the phase's originally planned scope.** Four things
are now real: a single computed field can be represented and emitted
as executable SQL (`ModelGenerator`); a dataset can be assembled from
multiple sources, including the same physical table joined in
multiple times under different roles, each independently filtered and
deduplicated (`SourceRef`/`JoinSpec`/`DedupRule`); and — closing what
was previously this phase's one remaining piece — a dataset can
declare dependencies on other Structifact-defined datasets, with the
resulting collection validated (unresolved references, cycles) and
resolved into a deterministic execution order (`DatasetSpec.depends_on`,
`structifact/dependencies.py`, `structifact deps`). See "Recently
Completed" above for full detail.

What was scoped as "dependency graphs, execution ordering" below is
now done. **Impact analysis** — understanding what else is affected
by a change to a given dataset — was named as a potential capability
below but was never actually part of this phase's core definition; it
remains future work, more naturally scoped under Phase 9 (Lineage and
Observability) once a real need for it surfaces.

Separately, and deliberately kept out of this phase: **cross-dataset
value resolution** — one dataset actually consuming another's
computed/resolved value (not just knowing it must run after it). A
real synthetic example (`workorder_demo`) motivates this via an
FX-rate-lookup pattern, which is real evidence it recurs, but it's a
substantially different and larger
problem (cross-dataset field references, lookup/fallback semantics,
cross-dataset SQL generation) — see `FUTURE_WORK.md` and
`DECISION_HISTORY.md` for the full reasoning on why this was kept
separate rather than folded into this milestone.

## Dependency Management (now done — see above)

Originally-listed potential capabilities: dependency graphs, execution
ordering, impact analysis. Dependency graphs and execution ordering
are now real (above); impact analysis was re-scoped to Phase 9, as
noted above.

---

# Phase 8 — Execution and Platform Integrations

## Goal

Connect Structifact metadata with execution environments.

## Status

**Two real engines done (8A); a computed-field SELECT proven to
execute correctly, read-only, for both the simple single-source case
(8D, v1) and the sources/joins/dedup CTE shape (8D, v2); execute's
write operations now atomic (8C-v1); a genuinely reproduced transient
database error now recoverable via retry (8C-v2); ModelGenerator's
output now materializes into a real target table on both engines
(8D, v3), and is reachable from `structifact execute --materialize`
(8D, v4). Snowflake and connection pooling remain (8B/8C-v3).** A new `Executor` interface
(`structifact/executors/`) lets Structifact actually run its own
generated DDL against a real database, not just produce SQL text —
closing a real gap (nothing previously confirmed generated SQL was
genuinely valid/executable). `DatasetSpec` → `SQLGenerator` →
`Executor.execute_ddl()` is now a real, tested, end-to-end path,
proven against two independent engines with no engine-specific logic
added to `SQLGenerator` or the CLI.

**DuckDB** (`DuckDBExecutor`, local file or in-memory, no credentials
needed) was implemented first specifically because it needed no
credentialed environment, letting the `Executor` interface itself get
proven before a credentialed engine was attempted.

**PostgreSQL** (`PostgresExecutor`, Phase 8A) is the second, proving
the same interface holds for a real, networked, credentialed engine
via `psycopg2`. Verified with real integration tests against an
actual PostgreSQL 16 server — never mocked — covering DDL correctness
(table/columns/types/primary key), row loading with the same raw,
uncoerced CSV-string values the existing `load_rows` contract already
passed to DuckDB, query shape, persistence across a close/reconnect
cycle, and a real constraint-violation error propagating uncaught.
CI runs these via a `postgres:16` GitHub Actions service container;
local runs are opt-in via `STRUCTIFACT_TEST_POSTGRES_DSN` and skip
cleanly when unset.

Two things changed at the interface/CLI boundary to make this
possible, both applied to DuckDB too for consistency: the CLI's
connection flag was renamed `--database` → `--connection` (a clean
pre-1.0 break, no alias — `--database` was DuckDB-specific
terminology to begin with and wasn't shown in any README/EXAMPLES
golden path), carrying a single opaque string the CLI never
interprets — each `Executor` decides what it means (a file path for
DuckDB, a DSN for Postgres). This keeps host/port/user/password
concepts entirely out of the generic CLI layer. Separately, both
`DuckDBExecutor` and `PostgresExecutor` now import their third-party
driver lazily, inside `connect()`, rather than at module load time —
fixing a real pre-existing bug where the whole `structifact` CLI
failed to import without `duckdb` installed (confirmed: CI had
actually been failing on `main` for several commits, including the
`v0.4.0` tag, for exactly this reason — also fixed alongside this
work).

`PostgresExecutor` connects with `autocommit=True`, explicitly
documented (see `Executor`'s base docstring) as deliberate Phase 8A
compatibility behavior matching DuckDB's existing implicit
persistence semantics — not real transaction management. That
distinction matters: PostgreSQL does not autocommit by default the
way DuckDB does, and a naive implementation would have silently
rolled back everything on connection close while still reporting
success. Explicit transaction management, atomic multi-operation
execution, rollback semantics, connection pooling, and retry logic
remain deferred — see below and `FUTURE_WORK.md`.

**8D, v1 (read-only verification) is also now done.** `tests/test_model_execution.py`
proves `ModelGenerator`'s computed-field `SELECT` actually runs against
real data on both real engines, not just that it looks like plausible
SQL text — a minimal, deliberately single-purpose fixture (one
dataset, one computed field, `expression: "quantity * unit_price"`,
no sources/joins/dedup), asserting exact expected values, not just
"the query didn't error." The generated SQL itself is asserted to
contain the expected expression/alias too, so a generator regression
and an Executor regression stay distinguishable. Uses `Executor.query()`
— already the right tool for this — no new Executor method was added.
The table the model reads from is deliberately a *raw* upstream table
(`order_id`/`quantity`/`unit_price` only): `ModelGenerator`'s SELECT
never reads a dataset's own computed-field column, only the raw inputs
it derives that value from — a different table than `SQLGenerator`'s
DDL would produce for that same dataset. Deliberately, explicitly
scoped out of this slice: materializing the SELECT's output into a
real target table (an `INSERT INTO ... SELECT`-style write path,
closer to `dbt run`), any CLI exposure, and the sources/joins/dedup
CTE shape (a materially bigger, still-unproven SQL construct at the
time) — all still open, not silently folded into "done."

**8D, v2 (sources/joins/dedup CTE, also read-only) is also now done.**
Split out from what was originally scoped as a single "8D remainder"
slice, matching this project's discipline of proving one new thing
per slice: 8D v1 proved a simple single-source SELECT executes
correctly; 8D v2 proves the materially bigger CTE shape (joined
sources, filters, `ROW_NUMBER()`-based dedup) does too, still
read-only, via the same `Executor.query()` — no new method, no CLI
change. `tests/test_model_execution_sources_joins.py` reuses the
`work_order_source`/`partner_role` shape already unit-tested (SQL-text
only) in `tests/test_model_sources_joins.py`, but with real data
deliberately designed to exercise three distinct semantics with
exact-value assertions rather than "the query didn't error": a
`filter` that must exclude a wrong-role candidate that would otherwise
look like a better dedup match; a dedup tie broken by the *secondary*
sort key, not just the primary one; and a `left join` that must
preserve a row with no match at all (`NULL`, not a dropped row).
Verified against both DuckDB and a real PostgreSQL server. Still
explicitly open: materializing either shape's output into a real
target table (8D v3) and any CLI exposure.

**8C-v1 (atomic execution) is also now done.** Scoped directly from a
reproduced, real bug rather than the roadmap's original three-item
list treated as equally-sized: `load_rows`'s internal batching was
found to commit rows individually on both DuckDB and PostgreSQL, so a
mid-batch failure (e.g. a duplicate primary key) left prior rows
silently persisted even though the CLI reported "Execution failed" —
a genuine correctness gap, not a hypothetical. `Executor` gained one
new public method, `transaction()` — a context manager, not the
`begin()`/`commit()`/`rollback()` triplet originally considered.
Deliberately one method rather than three: Python's `with` guarantees
exit runs exactly once, so a transaction can't be left half-open the
way three independent lifecycle calls could be misused, and callers
never need to know how DuckDB or PostgreSQL implements transactions
underneath. `execute_ddl()`/`load_rows()`/`query()` needed **no
changes at all** — both drivers already treat "inside a transaction
vs. autocommitting" transparently at the connection level, so
standalone calls outside `transaction()` keep their exact Phase 8A
behavior, asserted explicitly in tests, not just implied by the rest
of the suite still passing.

`cli.py`'s `execute()` now wraps its DROP (if `--drop-if-exists`) +
CREATE + row-load sequence in a single `transaction()` scope — atomic
as a whole, including the DROP itself. The post-load verification
query moved to *after* the transaction commits, so it proves durable
persistence rather than merely in-transaction visibility (matching
what "verification" was always meant to demonstrate). Verified with
real regression tests against both engines: the exact
`[1, 2, 1, 4]` batch now leaves zero rows after rollback; a fresh
target's `CREATE` rolls back too, leaving no table at all after a
failed load (not just an empty one); and — the centerpiece case — a
pre-existing table's original data survives a failed
`--drop-if-exists` reload intact, proving the DROP lives inside the
transaction rather than being applied destructively beforehand.
Manually confirmed end-to-end against a real PostgreSQL server too,
not just via pytest.

**8C-v2 (retry) is also now done.** Scoped directly against a real,
empirically-verified transient failure rather than a hypothetical
error taxonomy: PostgreSQL's `serialization_failure` (SQLSTATE
`40001`, raised as `psycopg2.errors.SerializationFailure`), reproduced
with two genuinely concurrent `SERIALIZABLE` transactions before any
retry code was written, confirming the exact exception type and
condition rather than assuming it. `structifact/executors/base.py`
gained one new module-level function, `retry_transaction(executor,
fn, retry_on, max_attempts)` — deliberately NOT a new `Executor`
method: retrying means re-running the *caller's* code, and a context
manager can't re-invoke its own `with`-block body, so `fn` is passed
in as a callable rather than becoming a new abstract method every
`Executor` subclass would need to implement. `Executor`,
`DuckDBExecutor`, and `PostgresExecutor` needed zero changes, the same
pattern 8C-v1 established for `execute_ddl()`/`load_rows()`/`query()`.

`fn` must represent the *complete* unit of work for one attempt and be
safe to re-run from the beginning — `retry_transaction` re-executes
`fn()` in its entirety inside a fresh `transaction()` scope on each
retry, not just the statement that failed, so `fn` may not perform
irreversible effects outside the database (an email, an external API
call). `max_attempts` counts total calls to `fn()`, including the
first — `max_attempts=3` means at most 3 calls, not 3 retries after an
initial attempt. A non-`retry_on` exception propagates immediately, on
any attempt; exhausting `max_attempts` propagates the *final*
attempt's exception. Verified at two levels: deterministic loop-
mechanics tests (`tests/test_executor_retry.py`, real `DuckDBExecutor`,
plain Python exceptions — proving exact attempt counts and which
exception propagates when) and a real PostgreSQL integration test
proving the actual claim under test — that the *entire* callback
re-executes, not just the failing statement. That test's callback
performs two separate writes; after a successful retry, the committed
state is asserted to reflect exactly one complete application of the
callback's effect (not zero — proving the failed attempt left no
partial writes; not two — proving the failed attempt's work wasn't
double-counted), and a call counter independently proves `fn` was
invoked exactly twice. No CLI exposure (e.g. a `--retry` flag) —
`structifact execute` is a single sequential invocation with no
concurrent writer today, so there's no real caller that would hit a
retryable failure yet; wiring it into the CLI now would build for a
hypothetical rather than a real need, the same discipline `transaction()`
itself followed before 8C-v1. In practice this is Postgres-specific for
now — DuckDB has no comparable concurrent-writer failure mode, so its
callers simply never encounter a `retry_on` match and get unchanged
single-attempt behavior.

**8D, v3 (materialization) is also now done.** Closes the gap 8D v1/v2
deliberately left open: `ModelGenerator` gained one new method,
`generate_insert(dataset)`, wrapping `generate()`'s SELECT in
`INSERT INTO <dataset.name> (<columns>) <select>`. Materializing means
running `SQLGenerator`'s DDL to create the target (typed and
constrained from Structifact's own declared metadata), then that
`INSERT ... SELECT`, inside a single `transaction()` scope (Phase
8C-v1) — the same atomic-as-a-whole pattern `cli.py`'s `execute()`
already uses for DROP/CREATE/load. Chosen deliberately over
`CREATE TABLE ... AS SELECT`: CTAS would let the engine infer column
types from the query result and drop every declared constraint unless
re-added afterward, handing type/constraint authority to the database
instead of Structifact's metadata — confirmed empirically before
implementation that a plain typed `INSERT INTO (<explicit columns>)
<select>` executes correctly on both engines with `SQLGenerator` and
`ModelGenerator` already emitting fields in identical order. Reuses
`Executor.execute_ddl()` as-is for the INSERT statement — no new
method, no rename; `execute_ddl()`'s actual contract was already "run
this SQL, don't return rows," and adding a second method with an
identical body just to fix the DDL-flavored name would be surface
area without solving a real problem.

Investigation surfaced a real, load-bearing constraint before any code
was written: `source_table` defaults to the dataset's own `name` when
unset — exactly what 8D v1/v2's original fixtures did — so
materializing into a table named `dataset.name` while reading from a
relation of that same name is a self-referential collision (the raw
and enriched shapes can't coexist under one name). `generate_insert()`
rejects this with a clear error whenever `dataset.name` is among the
relations the generated SELECT reads from — the resolved primary
source *or any joined source's table*, not just `source_table` alone.
Deliberately scoped as a materialization-specific precondition inside
`generate_insert()`, not a general `DatasetSpec` validation rule — a
model reading from its own dataset name may be entirely legitimate
outside of materializing it (see 8D v1/v2, both read-only). Every
fixture here sets a genuinely distinct upstream relation name, the
same pattern any real ELT pipeline already uses.

Verified against adapted versions of 8D v1/v2's exact fixtures
(`tests/test_model_materialization.py`) on both DuckDB and PostgreSQL,
asserting *persisted* table contents, not query-time results:
computed-field transformation, source filtering, dedup ordering, and
LEFT JOIN NULL-preservation all still hold once written to a real
table. Two things proven beyond 8D v1/v2's read-only scope: the
target's declared `primary_key` constraint is actually enforced on the
materialized table (a raw duplicate insert against it fails for real —
proof the schema came from Structifact's metadata, not engine
inference), and a failed materialization is atomic — a genuine
primary-key violation during the INSERT leaves no target table at all
afterward, not a partially- or fully-populated one, since CREATE and
INSERT share one `transaction()` scope. No CLI exposure — matching
8D v1/v2 and 8C-v2's precedent, this is proven via `Executor` methods
directly in tests; `structifact execute --materialize` (or similar)
remains a distinct, later slice.

**8D, v4 (CLI exposure for materialization) is also now done.**
`structifact execute` gained `--materialize`: populates the table by
running `ModelGenerator.generate_insert()`'s INSERT instead of loading
raw `--data` — the two are mutually exclusive, checked before ever
connecting to a database, alongside `generate_insert()`'s own two
failure modes (nothing to materialize; the source/target collision
from 8D v3), so a dataset that can't be materialized fails fast with a
clear message rather than a wasted connection. Wired into the exact
same `transaction()` scope DROP/CREATE already use — `--materialize`
changes nothing about DROP/CREATE's existing behavior (still fails
loudly against an existing table without `--drop-if-exists`, still
atomic on a real constraint violation, now confirmed through the CLI
path itself, not just at the `Executor` level). Reuses the existing
post-commit verification-query block (previously gated on `args.data`
alone) rather than inventing a second reporting path. Does not create
or populate the upstream tables a model reads from — no cross-dataset
orchestration, an explicit, unchanged boundary. Deliberately still
excluded: a `--retry` flag (no real caller of this command has a
concurrent-writer need) and any standalone read-only "preview the
model's results" mode (`structifact generate -g model` already exposes
the raw SQL text; materialization's own verification query already
shows the persisted result — a distinct preview command would be new
surface area without a demonstrated need).

A real, previously-invisible bug surfaced while building this slice's
test fixtures: `yaml.py`'s `load_yaml()` had never actually parsed
`source_table`, `sources`, `joins`, or a field's `source`/
`source_column` from a YAML file, despite `validation.py` and
`ModelGenerator` operating correctly on those exact attributes since
Phase 7 — every sources/joins test across Phase 7 and 8D v1–v3 had
constructed `DatasetSpec` directly in Python, so the gap was invisible
until this was the first time a real YAML file needed `source_table`
to load. Fixed directly in `yaml.py`, with regression coverage in
`tests/test_yaml_adapter.py` including a full YAML → `DatasetSpec` →
`validate_table` → `ModelGenerator` pipeline test — the same class of
bug, found the same way, as the Phase 1 constraint-parsing gap (see
`DECISION_HISTORY.md`). A related, smaller finding from the same pass
is now documented directly on `JoinSpec` in `ir.py`: PyYAML's default
resolver parses a bare `on:` key as the boolean `True`, not the string
`"on"`, so real YAML files must quote it (`"on":`).

Deliberately, explicitly still NOT done — kept visible as separate
pieces rather than folded into "Postgres done," matching the
originally scoped 8A/8B/8C/8D breakdown:

* **8B — Snowflake** (or any further engine) implementation
* **8C-v3 — Connection pooling**: deliberately deferred — no usage
  pattern anywhere in the codebase motivates it yet (confirmed by
  inspection: exactly one `Executor` instance is ever constructed,
  in `cli.py`'s `execute()`, one per CLI invocation)

The DuckDB slice's scope was chosen deliberately rather than from an
external real-need example, an explicit, acknowledged exception to
this project's usual real-example-first discipline — justified
because DuckDB requires no setup and there was a genuine gap
(unverified generated SQL) worth closing regardless. The Postgres
slice returned to the normal discipline: scoped on paper against the
same `tests/fixtures/customers.yml` fixture and `SQLGenerator` output
already proven against DuckDB, with the connection-configuration
boundary and persistence-semantics questions investigated and
resolved *before* any implementation, not assumed.

## Design Requirement

Execution systems should remain separate from metadata definition.
Structifact defines what should exist; execution platforms define how
and where it runs. Held up directly: `Executor.execute_ddl()` runs
SQL `SQLGenerator` already produced — nothing about *what* SQL gets
generated changed to accommodate execution.

---

# Phase 9 — Lineage and Observability

## Goal

Improve understanding of data systems.

## Status

**v1 (impact analysis) done.** `structifact/dependencies.py` gained
`impacted_by(dataset_name, datasets) -> List[str]` — the reverse of
the forward graph `build_dependency_graph()` already built: given a
dataset name, returns every dataset that depends on it, directly or
transitively. Ordering is not arbitrary: the result is the
subsequence of `execution_order()`'s output restricted to the
impacted set, so it's a genuine regeneration order, not an arbitrary
one, since every returned entry actually is downstream of the queried
dataset.

Deliberately built on the existing graph machinery rather than
reimplementing traversal: `impacted_by()` calls `execution_order()`
for validation (duplicate names / unresolved references / cycles —
the same errors, same messages) and `build_dependency_graph()` for
the reverse walk itself, so `build_dependency_graph()`,
`execution_order()`, and `impacted_by()` all stay grounded in one
canonical graph rather than developing subtly different
interpretations of `depends_on` over time. A dataset name absent from
the collection is a distinct, explicit error ("Dataset 'X' was not
found in the provided collection.") — checked only after the
collection itself is confirmed structurally sound, so a broken
collection always reports its structural problems first. Exposed via
a new CLI command, `structifact impact <dataset_name> <path>
[<path> ...]`, mirroring `deps`'s existing multi-file loading/
validation/error-reporting exactly. Verified against the existing
`examples/dependency_demo/` chain (`customers`/`transactions` →
`customer_summary` → `daily_report`) end to end, not just against
in-memory `DatasetSpec`s — including the diamond-dependency shape
(one dataset feeding two, both feeding a fourth), where the result
must place the sink after both branches.

`DatasetSpec` had more real structural groundwork to build on when
this phase was picked up than when it was first written: genuine
structural knowledge of a dataset's sources (`SourceRef`/`JoinSpec`),
of foreign-key relationships between datasets (`ConstraintSpec`'s
`target_table`/`target_column`, resolved and checked against real
data by Phase 6 v3), and, most directly relevant here, of explicit
dataset-to-dataset dependencies (`DatasetSpec.depends_on`, validated
and resolved into a graph by Phase 7's `dependencies.py`) — the
dependency graph in particular was already close to lineage-ready as
a data structure, which is exactly why impact analysis was the
smallest real next slice.

Still unstarted: source-to-output lineage rendering and
dependency-graph visualization (see "Potential Capabilities" below) —
both bigger, less concretely scoped problems, deliberately left for a
real need to justify picking one, the same discipline that scoped
this slice.

## Potential Capabilities

Generate: source-to-output lineage, dependency-graph visualization,
metadata relationships. (Impact analysis — what depends on a given
dataset — is now done; see above.)

---

# Phase 10 — AI-Assisted Data Engineering

## Goal

Explore AI as an engineering assistant.

## Status

**Substantially done.** Raw-CSV schema inference (deterministic),
AI-assisted field descriptions for CSV input (`discover --ai`), and
AI-assisted requirements-document extraction (`discover --requirements
--ai`) are all implemented — see "Recently Completed" above for full
detail, including the bring-your-own-key/provider-agnostic/cost-
estimated/zero-calls-if-declined constraints, all verified in tests.

**Not yet built**: column classification beyond dimension/measure,
validation-*recommendations* (as distinct from the deterministic
rule-checking `quality.py` already does), transformation suggestions
(now unblocked in principle, since Phase 7's first steps are done —
still not built), and AI-assisted documentation beyond what
`DocsGenerator` already renders deterministically.

## Design Requirement

AI should suggest, explain, and assist. AI should not replace
metadata contracts, become the source of truth, or hide engineering
decisions. This has held up through everything built so far — see
`DECISION_HISTORY.md` for the specific accounting of how each
constraint was upheld.

---

# Phase 11 — Developer Experience

## Goal

Make Structifact easier to adopt and contribute to.

## Status

Unstarted as formal roadmap work, but one concrete idea is recorded
in `FUTURE_WORK.md`: a VS Code extension (syntax highlighting, inline
validation, command-palette actions running the existing CLI against
the open file), potentially extending to other editors later —
currently favored over a hosted web GUI as the more likely near-term
move in this space, given lower lift and a faster feedback loop, but
not yet started.

## Potential Improvements

project initialization, improved CLI workflows, configuration
management, IDE support, metadata templates, richer examples,
contributor documentation.

---

# Long-Term Vision

The long-term goal is a metadata-driven engineering framework where:

1. Engineers define structure and intent.
2. Structifact interprets metadata.
3. Validation ensures reliability.
4. Artifacts are generated consistently.
5. Real data is checked against the same declared rules.
6. Quality and lineage become easier to manage.
7. Intelligent assistance reduces repetitive engineering effort.

Items 1 through 5 are now real, not aspirational.

---

# Success Criteria

Structifact succeeds if it enables engineers to:

* define datasets consistently
* reduce repetitive pipeline development
* improve data reliability
* understand system behavior
* generate maintainable artifacts
* create reusable engineering patterns
* trust that real data actually conforms to what was declared

---

# Guiding Principle

> Define structure once. Generate reliable systems from it.
