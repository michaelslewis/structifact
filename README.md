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
check whether your actual data conforms to it?

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
metadata, the validation, and (if you point it at real data) a
data-quality report — derives from it instead of being maintained by
hand in parallel.

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

Check whether real data actually conforms to the same definition:

```bash
$ structifact validate-data examples/data_quality_demo/orders_data.yml examples/data_quality_demo/orders_data.csv
✓ Loaded schema: orders_data
✓ Loaded data: 15 rows

✗ 7 issue(s) found

Required-field violations:
  - order_id is blank at data row 4
  - customer_id is blank at data row 15
  - quantity is blank at data row 7
...
```

One definition, several independently-correct outcomes — generated
artifacts and real-data validation both — with no duplicated column
descriptions or rules to keep in sync by hand. See
[`examples/customers/`](examples/customers/) for the generation
walkthrough and [`examples/data_quality_demo/`](examples/data_quality_demo/)
for the data-quality walkthrough, including checking a foreign-key
relationship against a second dataset.

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
       multi-source datasets)
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
* A four-command CLI (`validate`, `generate`, `discover`,
  `validate-data`)
* Continuous integration running the full test suite (279 tests) on
  every push, across Python 3.11 and 3.12

## Technology Stack

**Currently used:** Python, YAML, SQL, Git, pytest, GitHub Actions.
Optional: `pandas`/`openpyxl` (Excel input), the Anthropic API
(opt-in AI-assisted discovery only).

**Under consideration for future work, not yet dependencies:**
DuckDB, Apache Parquet, dbt (as an execution engine — Structifact
generates dbt-shaped YAML; it doesn't run dbt itself), Snowflake,
Prefect, and other warehouse or orchestration integrations.

---

## Repository Structure

```text
Structifact/
│
├── examples/
│   ├── customers/          golden-path example (start here)
│   ├── enterprise_demo/    synthetic wholesale-order example
│   ├── workorder_demo/     multi-role joins + dedup example
│   └── data_quality_demo/  validate-data example, incl. a
│                            foreign-key reference dataset
│
├── structifact/
│   ├── adapters/            input format integrations
│   ├── generators/          artifact generation logic
│   ├── ir.py                 DatasetSpec / FieldSpec / ConstraintSpec /
│   │                         SourceRef / JoinSpec / DedupRule
│   ├── validation.py         metadata well-formedness
│   ├── quality.py            real-data checking (validate-data)
│   ├── discover.py           schema/requirements inference
│   ├── llm.py                 provider-agnostic AI client
│   └── cli.py
│
├── tests/                  automated test suite (279 tests)
├── docs/                   architecture and design documentation
├── AGENTS.md                working rules for AI assistants in this repo
└── pyproject.toml
```

## Documentation

* [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) — overall vision and current state
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system architecture and component design
* [`docs/DECISION_HISTORY.md`](docs/DECISION_HISTORY.md) — key architectural decisions and rationale
* [`docs/DESIGN_PRINCIPLES.md`](docs/DESIGN_PRINCIPLES.md) — core engineering philosophy
* [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) / [`docs/CURRENT_IMPLEMENTATION.md`](docs/CURRENT_IMPLEMENTATION.md) — snapshot of what's actually implemented
* [`docs/ROADMAP.md`](docs/ROADMAP.md) — planned development, with completed work marked as such
* [`docs/FUTURE_WORK.md`](docs/FUTURE_WORK.md) — longer-term exploratory ideas
* [`docs/EXAMPLES.md`](docs/EXAMPLES.md) — additional usage examples, including the full `validate-data` walkthrough

---

## Project Status

Structifact is under active development as both an engineering
exploration of metadata-driven data systems and a portfolio project
demonstrating modern software and data engineering practices. The
core pipeline — adapters, IR, validation, and generation — is
implemented, tested, and covered by CI, alongside a complete
real-data quality framework (required fields through cross-dataset
foreign-key checking) and AI-assisted schema/requirements discovery.
See `docs/ROADMAP.md` for what's next.

> Define structure once. Generate reliable systems from it.
