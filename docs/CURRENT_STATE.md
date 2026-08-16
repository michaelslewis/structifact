# CURRENT_STATE.md

# Structifact Current State

**Project:** Structifact
**Subtitle:** Schema-Driven Data Engineering Framework
**Repository:** github.com/michaelslewis/structifact
**Domain:** structifact.com

---

# Purpose

This document describes the current state of Structifact.

It serves as the reference point for continued development by documenting:

* what has been implemented
* current repository structure
* existing architectural foundations
* completed milestones
* known limitations
* immediate next steps

This document intentionally separates current reality from future vision. See `ROADMAP.md` for planned work and `FUTURE_WORK.md` for longer-term exploratory ideas.

---

# Current Project Status

Structifact has moved well past the initial framework-foundation stage. The core pipeline — adapters, IR, validation, and generation — is implemented, tested (427 tests passing, CI-enforced on Python 3.11/3.12), and has been exercised against real, non-trivial examples, not just the golden path.

Beyond the original schema-definition/generation pipeline, Structifact now also:

* infers draft schemas from raw data and from freeform requirements documents (with optional LLM assistance)
* validates real data rows against a dataset's declared rules — not just the metadata's own well-formedness
* checks foreign-key relationships across two datasets' real data
* declares and validates dependencies between datasets, and derives a safe
  execution order (with cycle detection) across a collection of them
* answers impact-analysis queries — what depends on a given dataset, directly or transitively — on top of that same dependency graph

The framework is not a production data platform and isn't intended to become one in the near term. The current objective remains a strong, trustworthy architectural foundation, now with several genuinely complete capability areas rather than only foundational scaffolding.

---

# Completed Work

## Project Foundation

* Repository created and organized; Python package structure established; `pyproject.toml` packaging.
* GitHub Actions CI running the full test suite on every push/PR against `main` (Python 3.11 and 3.12).
* `AGENTS.md` at repo root — working rules for AI assistants, including known project-specific traps.
* `examples/customers/` — golden-path example (input → validate → generate, both YAML and CSV input shown).
* Project domain registered: `structifact.com` (not deployed; deliberately deferred — see `ROADMAP.md`).
* Versioned releases: v0.3.0 tagged and published as a real GitHub Release.

---

# Current Repository Structure

```text
structifact/                        (repo root)
│
├── examples/
│   ├── customers/                  golden-path example
│   │   ├── customers.yml
│   │   ├── README.md
│   │   └── generated/               (output of `structifact generate`;
│   │                                 no input CSV — validate/generate
│   │                                 only, no validate-data walkthrough
│   │                                 here — see data_quality_demo/ for that)
│   ├── workorder_demo/             synthetic work-order example
│   │   (REQUIREMENTS_workorder.md, work_order_source.sql/yml,
│   │    work_order_catalog.csv, work_order_source.discovered.yml)
│   ├── data_quality_demo/          Phase 6 example
│   │   (orders_data.yml/csv, dq_customers.yml/csv)
│   └── dependency_demo/            Phase 7 remainder example
│       (customers/transactions/customer_summary/daily_report chain,
│        cyclic_broken/ deliberately-broken variant)
│
├── structifact/
│   ├── cli.py                      validate / generate / discover /
│   │                               validate-data / deps / impact / execute
│   ├── __main__.py
│   ├── ir.py                       DatasetSpec / FieldSpec / ConstraintSpec /
│   │                               SourceRef / JoinSpec / DedupRule
│   ├── types.py
│   ├── utils.py
│   ├── validation.py
│   ├── quality.py                  Phase 6: real-data checking (new subsystem,
│   │                               not a Generator)
│   ├── dependencies.py             Phase 7 remainder: cross-dataset dependency
│   │                               graph, cycle detection, execution ordering;
│   │                               Phase 9 v1: impact analysis (impacted_by)
│   ├── executors/                  Phase 8: execute generated DDL against a
│   │                               real database (DuckDB — first slice)
│   ├── discover.py                 schema/requirements inference
│   ├── llm.py                      provider-agnostic LLM client
│   │
│   ├── adapters/
│   │   ├── registry.py
│   │   ├── csv.py
│   │   ├── excel.py
│   │   └── yaml.py
│   │
│   └── generators/
│       ├── registry.py
│       ├── base.py
│       ├── sql.py
│       ├── dbt_yaml.py
│       ├── catalog.py
│       ├── catalog_extended.py
│       ├── docs.py
│       └── model.py                Phase 7: SELECT-based transformation model
│
├── tests/                          (37 files, 427 tests)
├── docs/                           this document and its siblings
├── pyproject.toml
├── README.md
└── LICENSE
```

Note: `structifact/parser.py`, referenced in earlier drafts of this document, was removed early on as dead code — adapters construct IR objects directly; there is no separate parsing stage.

---

# Implemented Components

## Metadata Layer

Datasets are defined declaratively via YAML (canonical), CSV, or Excel — all three normalize through the shared type system (`structifact/types.py`) rather than each implementing their own type-mapping.

A dataset definition can now express, well beyond the original name/fields/types:

* per-field `role` (dimension/measure), `accepted_values`, `nullable`
* computed/derived fields (`computed`, `expression`, `depends_on`)
* value-level data-quality rules (`min_value`, `max_value`, `pattern`)
* cross-source field attribution (`source`, `source_column`) for datasets that join in other sources
* dataset-level `source_table`, `sources` (`SourceRef`), and `joins` (`JoinSpec`) — a dataset can be built from more than one physical source, including the same physical table joined in multiple times under different roles, each with its own filter and a priority-based dedup rule (`DedupRule`)
* dataset-level `depends_on` — a dataset can declare that it depends on other Structifact-defined datasets (distinct from `FieldSpec.depends_on`, which refers to fields within the same dataset)
* constraints: `primary_key`, `unique`, `foreign_key` (with `target_table`/`target_column`), `check` (with `expression`)

---

## Adapter Architecture

Implemented adapters: YAML (primary/canonical), CSV, Excel — all three at parity on every `FieldSpec` attribute, including the Phase 6 v2 additions (`min_value`/`max_value`/`pattern`). Dataset-level `depends_on` is currently YAML-only, matching how `constraints`/`sources`/`joins` are also YAML-only.

---

## Intermediate Representation

`structifact/ir.py` holds `DatasetSpec` / `FieldSpec` / `ConstraintSpec`, plus the sources/joins additions (`SourceRef`, `JoinSpec`, `DedupRule`) and `DatasetSpec.depends_on`. This is now a substantially larger IR than the original "table + fields" model — see `ARCHITECTURE.md` for the full shape and the reasoning behind each addition.

---

## Validation Framework

`structifact/validation.py` validates a dataset's *metadata* — schema well-formedness, constraint relationships, and (new) genuinely checkable rule content: a `pattern` must compile as valid regex, `min_value` must not exceed `max_value`, range/pattern rules must apply to a compatible field type, `sources`/`joins`/`foreign_key` relationships must resolve to something real within the dataset's own metadata, and `depends_on` entries must be non-blank, non-duplicated, and not self-referencing.

This is distinct from — and a prerequisite for — the newer `quality.py` subsystem, which checks real *data* against that already-validated metadata, and from `dependencies.py` (below), which checks a *collection* of datasets against each other.

---

## Data Quality Framework (Phase 6)

`structifact/quality.py` is a genuinely new subsystem, not a `Generator` (a `Generator` takes one input — a schema — and returns one artifact; checking real data needs a schema *and* a data file, so it doesn't fit that contract). Exposed via a new CLI command, `structifact validate-data`.

Implemented, in three shipped increments:

* **v1** — required fields (reusing `nullable: false`), uniqueness (reusing `primary_key`/`unique` constraints), accepted values (reusing `accepted_values`) — checked against real CSV data rows for the first time. A missing value is an empty CSV field; uniqueness/accepted-values checks skip missing values (required-field validation owns that case, avoiding double-reporting).
* **v2** — range (`min_value`/`max_value`, inclusive bounds, stored as `Decimal` not `float` to avoid precision artifacts) and pattern (regex, full-match semantics) validation. A present-but-unparseable numeric value is deliberately *not* reported as a range violation — that's a distinct, not-yet-built type-validation concern, kept as its own code path rather than silently folded in.
* **v3** — foreign-key/relationship validation against a second dataset's real data, via `--ref alias=schema.yml:data.csv`. Schema-aware: the referenced schema is itself loaded and validated, its declared dataset name must match the `--ref` alias, and `target_column` must be a real declared field — never inferred from a bare CSV header. A missing or misconfigured `--ref` is a hard configuration error, never silently reported as "no issues found." Existence/membership only — a duplicate value on the *target* side is the target dataset's own uniqueness concern, not this check's.

All three report structured `QualityIssue`/`QualityResult` data; human-readable formatting lives entirely in `cli.py`, so a future `--format json` (not yet built) wouldn't require touching the checking logic.

---

## Dataset Dependency Tracking (Phase 7 remainder — new since the last full rewrite of this document)

`structifact/dependencies.py` is a new subsystem, following the same precedent as `quality.py`: it operates on a *collection* of `DatasetSpec`s, which is a genuinely different question from single-dataset metadata validation, so it isn't shoehorned into `validation.py` or the `Generator` interface.

`DatasetSpec.depends_on` (a plain `List[str]`) declares that a dataset depends on other Structifact-defined datasets — distinct from the existing `FieldSpec.depends_on`, which refers to other fields within the same dataset. Per-dataset validation catches blank/duplicate/self-referencing entries; `structifact/dependencies.py` handles what requires seeing the whole collection: duplicate dataset names, dependencies that don't resolve to a provided dataset, and circular dependencies (a hard error naming the full cycle, e.g. `dataset_a -> dataset_b -> dataset_c -> dataset_a`). A valid collection resolves to a deterministic execution order — dependency ordering is semantically guaranteed; the relative order of two mutually-independent datasets is not, though it is still deterministic run-to-run.

Exposed via a new CLI command, `structifact deps <path> [<path> ...]`.

Declaration and ordering only — deliberately does *not* resolve cross-dataset values or generate SQL for how one dataset obtains another's data. A real synthetic example (`workorder_demo`) motivates that as a real future need (an FX-rate lookup pattern), but it's out of scope for this milestone — see `FUTURE_WORK.md`.

---

## Impact Analysis (Phase 9, v1 — new since the last full rewrite of this document)

`dependencies.py` gained one new function, `impacted_by(dataset_name, datasets) -> List[str]` — the reverse question to `execution_order()`: given a dataset name, which datasets depend on it, directly or transitively? Deliberately added to `dependencies.py` itself rather than a new module, since it's the same graph and the same collection-level validation needs as `build_dependency_graph()`/`execution_order()`, just traversed backward.

Built directly on the existing graph machinery rather than reimplementing traversal: `impacted_by()` calls `execution_order()` first (reusing its validation — duplicate dataset names, unresolved `depends_on` references, circular dependencies — and its ordering), then `build_dependency_graph()` for the reverse walk itself, so all three functions stay grounded in one canonical graph rather than gradually developing different interpretations of `depends_on`. The result is not an unordered set: it's the subsequence of `execution_order()`'s output restricted to the impacted set, which is a genuinely meaningful order (a valid regeneration sequence) precisely because every entry in it really is downstream of the queried dataset. A dataset name absent from the collection raises a distinct error, checked only once the collection itself is confirmed structurally sound — so a broken collection always reports its own structural problems first, never a possibly-misleading "not found."

Exposed via a new CLI command, `structifact impact <dataset_name> <path> [<path> ...]`, mirroring `deps`'s existing multi-file loading/validation/error-reporting exactly — no new CLI architecture introduced. Verified against the real `examples/dependency_demo/` chain end to end (not just in-memory `DatasetSpec`s), plus unit coverage of fan-out, diamond-shaped, and unrelated-dataset graph shapes.

---

## Execution (Phase 8 — new since the last full rewrite of this document)

`structifact/executors/` is a new package, following the same registry pattern as `adapters/`/`generators/`. It closes a real gap: nothing previously confirmed that Structifact's generated SQL was actually valid, executable SQL — `SQLGenerator` only ever produced text.

`Executor` (`executors/base.py`) defines the interface: `connect()`, `execute_ddl()`, `load_rows()`, `query()`, `transaction()`, `close()`. `DuckDBExecutor` (`executors/duckdb.py`) was the first real implementation — chosen deliberately because it needs no credentials or network access, so the interface itself got proven before a credentialed engine was attempted. `PostgresExecutor` (`executors/postgres.py`, Phase 8A) is the second, proving the same interface holds for a real, networked, credentialed engine via `psycopg2` — connects with `autocommit=True` so its standalone persistence semantics match DuckDB's existing behavior. Both third-party drivers are imported lazily, inside `connect()`, not at module load time — so `structifact`'s CLI works even when neither `duckdb` nor `psycopg2` is installed, and only the engine actually invoked needs its extra present. `executors/registry.py` maps an `--engine` name to its `Executor` class, exactly like `generators/registry.py` maps generator names.

`transaction()` (Phase 8C-v1) is a context manager, not a `begin()`/`commit()`/`rollback()` triplet — deliberately: Python's `with` guarantees exit runs exactly once, so a transaction can't be left half-open the way three independent public methods could be misused, and callers never learn how either engine implements transactions underneath. Scoped directly from a reproduced bug: `load_rows`'s internal batching committed rows individually on both engines, so a mid-batch failure left prior rows silently persisted even though the caller saw an exception. `execute_ddl()`/`load_rows()`/`query()` needed no changes at all to support it — both drivers already treat in-transaction vs. autocommitting transparently at the connection level, so calls outside `transaction()` keep their exact standalone behavior.

`retry_transaction()` (Phase 8C-v2, also in `executors/base.py`) adds retry on top of `transaction()` — a module-level function, not a new `Executor` method, since retrying means re-running the *caller's* code inside a fresh `transaction()` scope, and a context manager can't re-invoke its own `with`-block body. Zero changes to `Executor`, `DuckDBExecutor`, or `PostgresExecutor`. Scoped against a real, empirically-verified transient failure rather than a hypothetical: PostgreSQL's `serialization_failure` (SQLSTATE `40001`, `psycopg2.errors.SerializationFailure`), reproduced with two genuinely concurrent `SERIALIZABLE` transactions and confirmed interactively before any retry code was written. The callback (`fn`) passed to `retry_transaction` must represent the *complete* unit of work for one attempt and be safe to re-run from the beginning — retries re-execute `fn()` in its entirety, not just the failing statement, so `fn` may not perform irreversible effects outside the database. `max_attempts` counts total calls to `fn()`, including the first. Verified at two levels (`tests/test_executor_retry.py`): deterministic loop-mechanics tests against a real `DuckDBExecutor` with plain Python exceptions (exact attempt counts, which exception propagates when), and a real PostgreSQL integration test whose callback performs two separate writes — proving, via a call counter and the exact final committed values, that the whole callback re-executes on retry and the committed effect is exactly one complete application, not zero and not doubled. No CLI exposure — no real caller with concurrent writers exists yet, and in practice this is Postgres-specific for now, since DuckDB has no comparable concurrent-writer failure mode to retry against.

Exposed via a new CLI command, `structifact execute <spec.yml> --engine <name> [--connection <target>] [--data <csv>] [--drop-if-exists]`. `--connection` is a single opaque string, interpreted by whichever `Executor` is selected — a file path for `duckdb`, a DSN (`postgresql://user:pass@host:port/dbname`) for `postgres` — so the CLI itself never learns engine-specific connection concepts like host/port/user/password. Runs `SQLGenerator`'s DDL output against the real engine; with `--data`, also loads real CSV rows and runs a verification query. The DROP (if `--drop-if-exists`), CREATE, and row-load steps now run inside a single `transaction()` scope — atomic as a whole, so a failure partway through (e.g. a duplicate-key row) rolls back everything from that invocation, including the DROP, leaving the database exactly as it was beforehand rather than silently half-populated. The verification query runs after the transaction commits, proving durable persistence rather than merely in-transaction visibility. `--drop-if-exists` was added after a real run showed the honest default behavior — failing loudly if the target table already exists, rather than silently overwriting or appending — needs an explicit opt-in escape hatch for repeated runs. Real PostgreSQL integration tests (`tests/test_executors.py`, `tests/test_executor_transactions.py`) run against an actual `postgres:16` server — a GitHub Actions service container in CI, opt-in locally via `STRUCTIFACT_TEST_POSTGRES_DSN` — never mocked; they skip cleanly when no real server is configured.

`tests/test_model_execution.py` (Phase 8D, v1) proves `ModelGenerator`'s computed-field SELECT actually executes correctly against real data — a minimal single-computed-field fixture (no sources/joins), run via the existing `Executor.query()` on both DuckDB and PostgreSQL, asserting exact expected values (not just "the query didn't error"), plus a check that the generated SQL itself contains the expected expression/alias. Read-only verification only: the table it reads from is a raw upstream table Structifact doesn't generate DDL for (matching how `sources`/`joins` already treat upstream tables), distinct from `SQLGenerator`'s DDL for that same dataset's own resulting shape.

`tests/test_model_execution_sources_joins.py` (Phase 8D, v2) proves the materially bigger sources/joins/dedup CTE shape also executes correctly, still read-only, via the same `Executor.query()` — no new Executor method needed for this either. Split out from what was originally one "8D remainder" item, matching the discipline that each slice proves exactly one new thing. Reuses the `work_order_source`/`partner_role` fixture already unit-tested (SQL text only) in `tests/test_model_sources_joins.py`, with real data specifically designed to exercise three semantics with exact-value assertions: a `filter` that must exclude a wrong-role candidate that would otherwise look like a better dedup match, a dedup tie broken by the *secondary* sort key rather than the primary one, and a `left join` that must preserve an unmatched row as `NULL` rather than dropping it. Verified against both DuckDB and a real PostgreSQL server.

`ModelGenerator.generate_insert()` (Phase 8D, v3) closes the gap v1/v2 deliberately left open: it wraps `generate()`'s SELECT in a typed `INSERT INTO <target> (<columns>) <select>`, materializing the transformation into a real table created by `SQLGenerator`'s DDL, atomically (one `transaction()` scope, Phase 8C-v1) — proven on both engines via `tests/test_model_materialization.py`, asserting *persisted* table contents. Chosen over `CREATE TABLE ... AS SELECT` — confirmed empirically before implementation, not just argued — because CTAS lets the engine infer types and drops declared constraints, handing type/constraint authority away from Structifact's own metadata; a plain typed `INSERT` works cleanly since `SQLGenerator` and `ModelGenerator` already emit fields in identical order. Reuses `Executor.execute_ddl()` as-is; no new method. Investigation surfaced a real precondition before any code was written: `source_table` defaults to `dataset.name`, so materializing into a table sharing a name with any relation the model reads from is a self-referential collision — `generate_insert()` rejects this explicitly (checking the primary source *and* every joined source's table, not just `source_table`), scoped as a materialization-specific precondition rather than a general `DatasetSpec` validation rule, since a model reading from its own dataset name can be legitimate outside of materializing it. Tests also prove the target's declared `primary_key` is genuinely enforced (not engine-inferred) and that a failed materialization is atomic — a real constraint violation during the INSERT leaves no target table at all, not a partial one. No CLI exposure in this slice, matching 8D v1/v2's precedent.

`structifact execute --materialize` (Phase 8D, v4) is the CLI-exposure slice that follows: mutually exclusive with `--data` (checked before connecting), and fails fast — also before connecting — on either of `generate_insert()`'s own failure modes (nothing to materialize; the source/target collision from v3), so a dataset that can't be materialized never wastes a connection. Wired into the exact same `transaction()` scope DROP/CREATE already use, and the same post-commit verification-query block previously gated on `args.data` alone — no new CLI architecture, no new reporting path. `--materialize` changes nothing about DROP/CREATE's existing behavior: still fails loudly against an existing table without `--drop-if-exists`, still atomic on a real constraint violation, now confirmed through the actual CLI path (`tests/test_cli_execute_materialize.py`) rather than only at the `Executor` level. Deliberately still excluded: a `--retry` flag (no real caller of this command has a concurrent-writer need) and a standalone read-only preview mode (`generate -g model` already shows the SQL text; materialization's own verification query already shows the persisted result).

Building this slice's real fixtures surfaced a genuine, previously-invisible bug: `yaml.py`'s `load_yaml()` had never actually parsed `source_table`, `sources`, `joins`, or a field's `source`/`source_column` from a real YAML file, despite `validation.py`/`ModelGenerator` operating correctly on those exact attributes since Phase 7 — every sources/joins test across Phase 7 and 8D v1–v3 had constructed `DatasetSpec` directly in Python. Fixed in `yaml.py`, with regression tests in `tests/test_yaml_adapter.py` including a full YAML → `DatasetSpec` → `validate_table` → `ModelGenerator` pipeline test — the same class of bug, found the same way, as the Phase 1 constraint-parsing gap (see `DECISION_HISTORY.md`). A related finding is now documented directly on `JoinSpec` in `ir.py`: PyYAML's default resolver parses a bare `on:` key as the boolean `True`, so real YAML files must quote it (`"on":`).

Deliberately, explicitly NOT built yet — see `FUTURE_WORK.md`'s "Before a 1.0 Release" section: a real Snowflake (or other) engine implementation, connection pooling (no usage pattern in the codebase motivates it — exactly one `Executor` instance is ever constructed, per CLI invocation), a `--retry` flag, and a standalone read-only model-preview command.

**`DatasetSpec.source_filter`** (post-1.0, "Real-World Validation" — see `ROADMAP.md`) is the first feature added purely from real use, not the roadmap: a real work ticket surfaced that the *primary* source had no way to carry its own filter, only a joined-in `SourceRef` could. Added as a plain trusted-raw-SQL string field, same shape as `source_table`. The real dataset also proved the generation logic can't treat it as a trailing `WHERE`: the primary and a joined-in source shared a column name, so a post-join `WHERE` would be genuinely ambiguous. `ModelGenerator` wraps the primary source in its own CTE, filtered before any join, whenever `source_filter` is set alongside `sources`/`joins` — matching how real hand-written SQL for this pattern is actually structured. Verified against real DuckDB and PostgreSQL data specifically designed to prove the ambiguity risk is avoided, not just asserted. See `DECISION_HISTORY.md` for the full account.

---

## Discover / AI-Assisted Discovery

`structifact discover` infers a draft schema from raw CSV sample data — deterministic, no AI, always writes a clearly-labeled draft for human review. `--ai` adds optional LLM-assisted field descriptions (off by default, cost-estimated, confirmed before any request; declining makes zero API calls). `discover --requirements <file> --ai` extracts a draft schema from a freeform requirements document (multi-column tables, prose, terse bullets, or a mix) — always requires `--ai`, since there's no deterministic way to parse freeform text.

AI assistance is entirely optional and bring-your-own-key: `structifact/llm.py` defines a provider-agnostic `LLMClient` interface (not locked to one vendor), with `AnthropicLLMClient` reading an `ANTHROPIC_API_KEY` environment variable — never a hardcoded key — and a `FakeLLMClient` used in tests so the test suite needs no real network access or API key. Every non-AI Structifact command works with zero setup and zero network access.

---

## Generator Framework

`structifact/generators/` — `SQLGenerator` (type-aware DDL, now including `FOREIGN KEY`/`CHECK` constraint emission), `DBTYAMLGenerator`, two catalog generators (minimal, run by default; extended, opt-in), `DocsGenerator` (Markdown, opt-in), and `ModelGenerator` (Phase 7 first step — emits a real, executable `SELECT` for a dataset's computed fields and joined-in sources, qualifying every column reference by its source; distinct from `SQLGenerator`, which only ever emits schema DDL).

`Generator.generate()` may now return `None` to mean "nothing to generate for this dataset" (e.g. `ModelGenerator` on a dataset with no computed fields and no joins) — the CLI's `generate` loop skips writing when that happens, rather than every generator being required to always produce an artifact.

---

## CLI

`structifact/cli.py` — seven commands: `validate`, `generate` (`-g/--generators`), `discover` (`--ai`, `-y`; a `.md`/`.txt` `spec` argument routes automatically to requirements-document extraction — there's no separate `--requirements` flag), `validate-data` (`--ref`, repeatable), `deps` (resolves dependencies across multiple dataset files into a safe execution order), `impact` (Phase 9 v1 — reports every dataset that depends on a given dataset, directly or transitively), and `execute` (Phase 8 — runs generated DDL against a real database; `--engine`, `--connection`, `--data`, `--materialize`, `--drop-if-exists`).

---

# Current Technology Stack

**Implemented:** Python, YAML, SQL, Git, pytest, GitHub Actions. Optional: `pandas`/`openpyxl` (Excel adapter), Anthropic API (opt-in LLM assistance).

**Under consideration for future work, not yet dependencies:** DuckDB, Apache Parquet, dbt (as an execution engine — Structifact currently *generates* dbt-shaped YAML, it doesn't run dbt), Snowflake, Prefect, and other warehouse/orchestration integrations.

---

# Current Limitations

Structifact still does not provide:

* production ingestion pipelines or cloud/warehouse execution
* orchestration
* automated lineage generation or a documentation *site* (only per-dataset Markdown via `DocsGenerator`)
* a GUI or hosted product (structifact.com remains unregistered-but-undeployed by design)
* a plugin architecture (the existing adapter/generator registries are still the extension mechanism)
* data-type validation (verifying a "decimal" column's values are actually numeric at all) — deliberately deferred; range/pattern checking in `quality.py` skips values that fail to parse rather than flagging them
* composite (multi-column) foreign keys, joins, or dedup rules beyond what's already scoped — the IR intentionally supports only the shapes real examples have needed so far
* cross-dataset value resolution — one dataset consuming another's computed/resolved value (e.g. an FX-rate lookup with conditional fallback); dependency *declaration* and *ordering* are done, but not this
* real, credentialed execution against anything beyond DuckDB (Postgres, Snowflake, etc.) — the `Executor` interface is designed for it, but only DuckDB is actually implemented
* transaction management, connection pooling, or retry logic in the execution layer — a single connect/run/close per `structifact execute` invocation only
* executing `ModelGenerator`'s transformation SQL — only `SQLGenerator`'s schema DDL is currently executable

These are documented, deliberate scope boundaries, not oversights — see `ROADMAP.md`/`FUTURE_WORK.md` for what's actually planned next versus what's exploratory. The execution-layer items above are also tracked explicitly in `FUTURE_WORK.md`'s "Before a 1.0 Release" checklist.

---

# Immediate Development Focus

Phase 6 (Data Quality Framework) and Phase 7 (Transformation Framework, including its dependency-tracking remainder) are both now complete end to end, matching their original scope in `ROADMAP.md`. Phase 8 (Execution and Platform Integrations) has a first real slice done (DuckDB). Per the project's own YAGNI discipline, none of this automatically continues — future work in these areas should come from a real, concrete need, the same way each prior increment did. (Phase 8's DuckDB slice is a deliberate, acknowledged exception to that discipline — chosen for its own sake, specifically because it required no credentialed environment and closed a real gap: nothing previously confirmed Structifact's generated SQL was actually executable.)

Phase 9 (Lineage and Observability) now has a first real slice done: impact analysis (`impacted_by()`, above). Source-to-output lineage rendering and dependency-graph visualization remain open — both bigger, less concretely scoped, deliberately left for a real need to justify picking one.

Open threads:

* **Cross-dataset value resolution** (deliberately deferred out of Phase 7's dependency-tracking milestone) — a real synthetic example (`workorder_demo`) motivates this via an FX-rate-lookup pattern; should only be scoped once a differently-shaped example is available, per this project's real-example-first discipline.
* **8B — Snowflake Executor**, **8C-v3 — connection pooling** (see `FUTURE_WORK.md`'s "Before a 1.0 Release" checklist) — deliberately parked pending a real, concrete need.
* **Lineage view / dependency-graph visualization** (Phase 9 remainder) — bigger, less concretely scoped than impact analysis; worth revisiting once a real use case surfaces.
* Longer-term, deliberately deferred: VS Code extension, structifact.com deployment/GUI (see `FUTURE_WORK.md`).

---

# Current Development Philosophy

Unchanged from earlier versions of this document: the priority is a trustworthy architecture over feature quantity. What has changed is that this philosophy now has a real track record behind it — every non-trivial IR addition this project has made (computed fields, FK/check constraints, sources/joins, each Phase 6 increment, dataset dependency tracking) went through the same sequence: a real example first, a minimal paper contract, review, then implementation with tests verified end-to-end before being considered done. Phase 8's DuckDB slice is a notable, acknowledged departure from strict real-example-first sequencing (chosen deliberately rather than externally motivated) — but it kept every other part of the discipline: a minimal contract agreed before code, a real end-to-end run (not just passing unit tests) required before being called done, and a genuine bug (re-running against an existing table) found and fixed from that real run rather than from the test suite alone. See `DECISION_HISTORY.md` for specific instances of this.

---

# Summary

Structifact currently represents a working metadata-driven framework: adapters normalize three input formats into a shared IR; validation checks that IR's own well-formedness; generators produce SQL, dbt-shaped YAML, catalogs, docs, and (for datasets with computed fields or joins) real executable transformation SQL; `discover` can bootstrap a draft schema from raw data or a freeform requirements document, optionally AI-assisted; `validate-data` checks real data rows — including across two related datasets — against everything the schema declares; `deps` resolves and safely orders dependencies across a collection of related datasets; and `execute` runs generated SQL against a real database (DuckDB or PostgreSQL today), proving it actually works rather than just looking plausible.

The project has moved from "architectural design" through "deeper implementation" into what's now a genuinely complete first version of several major capability areas, not just scaffolding for them.
