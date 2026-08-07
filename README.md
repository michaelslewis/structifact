# Structifact

[![Tests](https://github.com/michaelslewis/Structifact/actions/workflows/tests.yml/badge.svg)](https://github.com/michaelslewis/Structifact/actions/workflows/tests.yml)

**Schema-Driven Data Engineering Framework**

> Define dataset structure once. Generate reliable engineering artifacts from it.

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
and future artifact types — from that one definition?

```yaml
dataset:
  name: customers
  description: Customer master data

fields:
  - name: customer_id
    type: integer
    description: Unique customer identifier

  - name: created_at
    type: timestamp
    description: Record creation timestamp

constraints:
  - type: primary_key
    columns:
      - customer_id
```

One file. Everything downstream — the schema, the documentation
metadata, the validation — derives from it instead of being
maintained by hand in parallel.

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
    customer_id INTEGER,
    created_at TIMESTAMP
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

One definition, two consistent, independently-correct artifacts, no
duplicated column descriptions to keep in sync by hand. See
[`examples/customers/`](examples/customers/) for the full walkthrough,
including CSV as an alternative input format.

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
      (DatasetSpec / FieldSpec / ConstraintSpec)
              |
      +-------+-------+
      |               |
      v               v
  Validation      Generators
                       |
                       v
              Generated Artifacts
              (SQL, dbt YAML, ...)
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
  a shared type system
* An Intermediate Representation (`DatasetSpec` / `FieldSpec` /
  `ConstraintSpec`) as the stable internal model, including optional
  per-field `role` classification (`dimension` / `measure`)
* Schema and constraint validation, with clear error reporting —
  including per-field `accepted_values` well-formedness checks and
  rejecting more than one `primary_key` constraint per dataset
* Type-aware SQL generation (`INTEGER`, `TIMESTAMP`,
  `DECIMAL(precision,scale)`, etc. — not a blanket text type)
* dbt-compatible YAML metadata generation
* Catalog CSV generation — a minimal default generator, plus a
  second, richer format available via `-g catalog_extended` for
  downstream tools that expect a specific column set
* `structifact discover` — infers a draft schema from raw CSV sample
  data (types, nullability, key/format hints), for human review
  before it becomes real metadata
* A `validate`, `generate`, and `discover` CLI, with `-g/--generators`
  to select which generators run
* Continuous integration running the full test suite on every push

## Technology Stack

**Currently used:** Python, YAML, SQL, Git, pytest.

**Under consideration for future work, not yet dependencies:**
DuckDB, Apache Parquet, dbt, Snowflake, Prefect, and other warehouse
or orchestration integrations.

---

## Repository Structure

```text
Structifact/
│
├── examples/
│   ├── customers/        golden-path example (start here)
│   └── ...                additional input examples
│
├── structifact/
│   ├── adapters/          input format integrations
│   ├── generators/         artifact generation logic
│   ├── ir.py               DatasetSpec / FieldSpec / ConstraintSpec
│   ├── validation.py
│   └── cli.py
│
├── tests/                  automated test suite
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
* [`docs/EXAMPLES.md`](docs/EXAMPLES.md) — additional usage examples

---

## Project Status

Structifact is under active development as both an engineering
exploration of metadata-driven data systems and a portfolio project
demonstrating modern software and data engineering practices. The
core pipeline — adapters, IR, validation, and generation — is
implemented, tested, and covered by CI. See `docs/ROADMAP.md` for
what's next.

> Define structure once. Generate reliable systems from it.
