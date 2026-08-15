# Structifact

[![Tests](https://github.com/michaelslewis/Structifact/actions/workflows/tests.yml/badge.svg)](https://github.com/michaelslewis/Structifact/actions/workflows/tests.yml)

**Schema-Driven Data Engineering Framework**

> Define dataset structure once. Generate reliable engineering artifacts from it — and check that real data actually conforms to it.

---

## The Problem

Data teams routinely define the same dataset structure in multiple
disconnected places: a SQL `CREATE TABLE` statement, a dbt YAML file,
maybe a wiki page or a data dictionary, sometimes hand-written
validation code. Each copy is maintained separately, so they drift —
a column gets renamed in the database but not in the docs, a
constraint exists in one place and not another, and nobody is fully
sure which version is authoritative.

## The Solution

Structifact asks a different question: what if you defined a
dataset's structure and intent exactly once, in a single declarative
metadata file, and generated everything else — SQL, dbt metadata,
documentation, and even real executable transformation SQL — from
that one definition? And what if that same definition could also
check whether your actual data conforms to it, and how it relates to
other datasets you've defined the same way?

```yaml
dataset:
  name: customers
  description: Customer master data

fields:
  - name: customer_id
    type: integer
    description: Unique customer identifier
    nullable: false

  - name: created_at
    type: timestamp
    description: Record creation timestamp

constraints:
  - type: primary_key
    columns:
      - customer_id
```

One file. Everything downstream — the schema, the documentation
metadata, the validation, a data-quality report against real data,
and its place in a larger dependency graph — derives from it instead
of being maintained by hand in parallel.

## See It In Action

Validate a definition before anything is generated from it:

```bash
$ structifact validate examples/customers/customers.yml
✓ Loaded metadata
✓ Parsed 2 fields
✓ Valid schema
✓ No constraint violations
```

Generate real artifacts from the same definition:

```bash
$ structifact generate examples/customers/customers.yml -o examples/customers/generated
```

**`generated/customers.sql`**

```sql
CREATE TABLE customers (
    customer_id INTEGER NOT NULL,
    created_at TIMESTAMP,
    PRIMARY KEY (customer_id)
);
```

**`generated/customers.yml`** (dbt-style metadata)

```yaml
version: 2
models:
- name: customers
  columns:
  - name: customer_id
    description: Unique customer identifier
  - name: created_at
    description: Record creation timestamp
```

Check whether real data actually conforms to the same definition — including a foreign-key relationship checked against a second dataset's real data:

```bash
$ structifact validate-data examples/data_quality_demo/orders_data.yml examples/data_quality_demo/orders_data.csv \
    --ref dq_customers=examples/data_quality_demo/dq_customers.yml:examples/data_quality_demo/dq_customers.csv
✓ Loaded schema: orders_data
✓ Loaded data: 15 rows

✗ 11 issue(s) found

Required-field violations:
  - order_id is blank at data row 4
  - customer_id is blank at data row 15
  - quantity is blank at data row 7

Uniqueness violations:
  - order_id 'ORD-1002' appears in data rows 2 and 5
...
Foreign-key violations:
  - customer_id 'CUST-004' at data rows 5 and 14 not found in dq_customers.customer_id
...
```

Resolve how multiple datasets depend on each other into a safe processing order — and ask the reverse question, what depends on this one:

```bash
$ structifact deps examples/dependency_demo/customers.yml examples/dependency_demo/transactions.yml examples/dependency_demo/customer_summary.yml examples/dependency_demo/daily_report.yml
✓ Loaded 4 dataset(s)

--- EXECUTION ORDER ---

1. customers
2. transactions
3. customer_summary
4. daily_report

$ structifact impact customers examples/dependency_demo/customers.yml examples/dependency_demo/transactions.yml examples/dependency_demo/customer_summary.yml examples/dependency_demo/daily_report.yml
✓ Loaded 4 dataset(s)

--- IMPACTED BY 'customers' ---

1. customer_summary
2. daily_report
```

Execute that same definition against a real database — DuckDB (no setup) or PostgreSQL — and, for datasets with computed fields or joined-in sources, materialize the transformation into a real table:

```bash
$ structifact execute examples/customers/customers.yml --engine duckdb
✓ Loaded schema: customers
✓ Connected: duckdb (in-memory)
✓ Executed DDL: CREATE TABLE customers (...)

Table 'customers' created successfully.
```

(Omit `--connection` for a throwaway in-memory database, as above, or pass a file path — e.g. `--connection customers.duckdb` — to persist it.)

One definition, several independently-correct outcomes — generated
artifacts, real-data validation, dependency resolution, and real
database execution — all from the same source, with no duplicated
column descriptions or rules to keep in sync by hand. See
[`examples/customers/`](examples/customers/) for the generation
walkthrough, [`examples/data_quality_demo/`](examples/data_quality_demo/)
for the data-quality walkthrough (including checking a foreign-key
relationship against a second dataset), and
[`examples/dependency_demo/`](examples/dependency_demo/) for the
dependency-resolution walkthrough (including a deliberately-broken
cyclic example).

---

## How It Works

```text
Input Metadata (YAML / CSV / Excel)
              |
              v
          Adapters
              |
              v
   Intermediate Representation
      (DatasetSpec / FieldSpec / ConstraintSpec,
       + SourceRef / JoinSpec / DedupRule for
       multi-source datasets,
       + depends_on for cross-dataset relationships)
              |
      +-------+-------+
      |               |
      v               v
  Validation      Generators
  (metadata           |
   well-formedness)   v
                Generated Artifacts
                (SQL, dbt YAML, catalog,
                 docs, transformation SQL)
```

A separate flow checks real data against that same metadata:

```text
Metadata (validated as above)  +  Real Data (CSV)
              |
              v
      structifact validate-data
              |
              v
       Data-Quality Report
```

A third flow resolves how multiple datasets relate to each other —
`structifact deps` for a safe execution order, `structifact impact`
for the reverse question:

```text
Multiple Metadata Files (each validated as above)
              |
              v
    structifact deps / impact
              |
              v
   Execution Order, or Impacted Datasets
   (or a dependency error)
```

A fourth flow actually runs generated SQL against a real database —
creating the schema, and, for datasets with computed fields or
joined-in sources, materializing the transformation into a real table:

```text
Generated Artifacts (SQL DDL, transformation SELECT)
              |
              v
        structifact execute
     (--data / --materialize)
              |
              v
   Real Table, Created and Populated
   (DuckDB or PostgreSQL — atomic:
    a failure leaves the database
    exactly as it was before)
```

The Intermediate Representation (IR) is the architectural core: every
input format is normalized into the same `DatasetSpec` model before
anything downstream touches it, so adapters and generators can evolve
independently without becoming tangled together. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/DECISION_HISTORY.md`](docs/DECISION_HISTORY.md) for the
reasoning behind these choices.

---

## Current Capabilities

* YAML, CSV, and Excel input adapters, all normalizing types through
  a shared type system, kept at parity on every field-level attribute
* An Intermediate Representation (`DatasetSpec` / `FieldSpec` /
  `ConstraintSpec`) as the stable internal model, including optional
  per-field `role` classification, computed/derived fields, and
  (for datasets assembled from more than one source) `SourceRef` /
  `JoinSpec` / `DedupRule` — including the same physical table joined
  in multiple times under different roles, each independently
  filtered and deduplicated
* Schema and constraint validation, with clear error reporting —
  including `foreign_key`/`check` constraints, regex-pattern
  compilability, and range-bound consistency, on top of the original
  well-formedness checks
* Type-aware SQL generation (`INTEGER`, `TIMESTAMP`,
  `DECIMAL(precision,scale)`, `FOREIGN KEY`, `CHECK`, etc.)
* A separate transformation-model generator that emits real,
  executable `SELECT` SQL (not just DDL) for a dataset's computed
  fields and joined-in sources
* dbt-compatible YAML metadata generation
* Catalog CSV generation — a minimal default generator, plus a
  richer format available via `-g catalog_extended`
* Markdown documentation generation (`-g docs`)
* `structifact discover` — infers a draft schema from raw CSV sample
  data, or (with `--requirements --ai`) from a freeform requirements
  document — for human review before it becomes real metadata.
  AI assistance is entirely optional, bring-your-own-key
  (`ANTHROPIC_API_KEY`), cost-estimated and confirmed before any
  request, and every non-AI command works with zero setup
* **`structifact validate-data`** — checks real CSV data against a
  schema's declared rules: required fields, uniqueness, accepted
  values, numeric ranges, regex patterns, and foreign-key
  relationships against a second dataset's real data (`--ref`)
* **`structifact deps`** — declares and resolves dependencies between
  Structifact-defined datasets into a safe execution order, with cycle
  detection (a hard error naming the full cycle) and clear errors for
  unresolved references or duplicate dataset names
* **`structifact impact`** — the reverse question: given a dataset,
  which others depend on it, directly or transitively, in a valid
  order for regenerating them — built on the same dependency graph
  as `deps`
* **`structifact execute`** — runs a dataset's generated DDL against
  a real database engine (DuckDB, no credentials needed; PostgreSQL,
  via a `--connection` DSN), optionally loading real `--data` or
  `--materialize`-ing its transformation model (the computed-field/
  sources-joins SELECT, written into a real typed target table) — all
  atomic, so a failure partway through leaves the database exactly as
  it was before the invocation, not half-populated
* A seven-command CLI (`validate`, `generate`, `discover`,
  `validate-data`, `deps`, `impact`, `execute`)
* Continuous integration running the full test suite (~400 tests,
  including real PostgreSQL integration tests via a service
  container) on every push, across Python 3.11 and 3.12

## Technology Stack

**Currently used:** Python, YAML, SQL, Git, pytest, GitHub Actions,
DuckDB (embedded, no setup), `psycopg2`/PostgreSQL (real integration
tests run against an actual server, both locally and in CI). Optional:
`pandas`/`openpyxl` (Excel input), the Anthropic API (opt-in
AI-assisted discovery only).

**Under consideration for future work, not yet dependencies:**
Snowflake, Apache Parquet, dbt (as an execution engine — Structifact
generates dbt-shaped YAML; it doesn't run dbt itself), Prefect, and
other warehouse or orchestration integrations.

---

## Repository Structure

```text
Structifact/
│
├── examples/
│   ├── customers/          golden-path example (start here)
│   ├── workorder_demo/     multi-role joins + dedup scoping material
│   │                        (a real requirements doc; its only spec
│   │                        file is an unvalidated AI draft, not
│   │                        meant to run)
│   ├── data_quality_demo/  validate-data example, incl. a
│   │                        foreign-key reference dataset
│   └── dependency_demo/    deps/impact example, incl. a deliberately
│                            cyclic variant
│
├── structifact/
│   ├── adapters/            input format integrations
│   ├── generators/          artifact generation logic, incl. the
│   │                         SELECT-based transformation model
│   ├── executors/            real database execution (DuckDB,
│   │                         PostgreSQL) — DDL, atomic transactions,
│   │                         retry, materialization
│   ├── ir.py                 DatasetSpec / FieldSpec / ConstraintSpec /
│   │                         SourceRef / JoinSpec / DedupRule
│   ├── validation.py         metadata well-formedness
│   ├── quality.py            real-data checking (validate-data)
│   ├── dependencies.py       dependency resolution (deps / impact)
│   ├── discover.py           schema/requirements inference
│   ├── llm.py                 provider-agnostic AI client
│   └── cli.py
│
├── tests/                  automated test suite (~400 tests)
├── docs/                   architecture and design documentation
├── AGENTS.md                working rules for AI assistants in this repo
└── pyproject.toml
```

## Documentation

* [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) — overall vision and current state
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system architecture and component design
* [`docs/DECISION_HISTORY.md`](docs/DECISION_HISTORY.md) — key architectural decisions and rationale
* [`docs/DESIGN_PRINCIPLES.md`](docs/DESIGN_PRINCIPLES.md) — core engineering philosophy
* [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — snapshot of what's actually implemented
* [`docs/ROADMAP.md`](docs/ROADMAP.md) — planned development, with completed work marked as such
* [`docs/FUTURE_WORK.md`](docs/FUTURE_WORK.md) — longer-term exploratory ideas
* [`docs/EXAMPLES.md`](docs/EXAMPLES.md) — additional usage examples, including the full `validate-data` and `deps` walkthroughs

---

## Project Status

Structifact is under active development as both an engineering
exploration of metadata-driven data systems and a portfolio project
demonstrating modern software and data engineering practices. The
core pipeline — adapters, IR, validation, and generation — is
implemented, tested, and covered by CI, alongside a complete
real-data quality framework (required fields through cross-dataset
foreign-key checking), cross-dataset dependency resolution and impact
analysis (execution ordering with cycle detection, and the reverse
question), AI-assisted schema/requirements discovery, and real
execution against DuckDB and PostgreSQL — DDL creation, atomic
multi-step writes, retry on a real transient database error, and
materializing a dataset's transformation model into a real table. See
`docs/ROADMAP.md` for what's next; `docs/FUTURE_WORK.md`'s "Before a
1.0 Release" section tracks what's deliberately still open (a
Snowflake executor, connection pooling).

> Define structure once. Generate reliable systems from it.
