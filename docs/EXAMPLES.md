# EXAMPLES.md

# Structifact Examples

## Purpose

This document demonstrates how Structifact is actually used today.

Earlier versions of this document showed a mix of real and aspirational workflows without clearly distinguishing them (a `structifact build` command, a `structifact docs` command, and others that were never built). This version shows only commands and output that exist in the current codebase. Where a workflow doesn't exist yet, it's described in `ROADMAP.md` or `FUTURE_WORK.md` instead — not here.

Structifact is designed around the principle:

> Define structure once. Generate reliable systems from it.

---

# Example 1 — Defining a Dataset Schema

`examples/customers/customers.yml`:

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

This is the actual golden-path example shipped in the repo — every subsequent example in this document either builds on it or shows a different real one.

## The Same Schema as CSV or Excel

YAML is canonical, but the same schema can be written as a CSV or Excel spec file instead — one row per field, column headers giving each field's attributes. `examples/customers.csv` is the exact CSV equivalent of the YAML above:

```csv
column_name,type,description
customer_id,string,Unique customer identifier
created_at,timestamp,Account creation time
```

The full set of columns the CSV and Excel adapters recognize — `column_name` and `type` are required, everything else is optional and may be left blank:

| Column | Meaning | Format |
|---|---|---|
| `column_name` | Field name | required |
| `type` | e.g. `integer`, `varchar(50)`, `decimal(9,2)` | required |
| `description` | Field description | plain text |
| `role` | `dimension` or `measure` | plain text |
| `accepted_values` | Allowed values | `;`-separated, e.g. `Free;Pro;Enterprise` |
| `nullable` | Whether the field allows blanks | `true`/`false`/`yes`/`no`/`1`/`0`; defaults to `true` |
| `computed` | Whether the value is derived, not sourced directly | same boolean format; defaults to `false` |
| `expression` | SQL expression, if `computed` is true | plain text |
| `depends_on` | Other field names this one is computed from | `;`-separated |
| `min_value` / `max_value` | Inclusive numeric bounds | plain number |
| `pattern` | Regex the value must fully match | plain text |

An Excel spec file (`.xlsx`) uses the exact same column headers, as the first row of one sheet — the Excel adapter reads it with `pandas.read_excel`, same shape as the CSV above, just in workbook form. Requires the `excel` extra (`pip install -e ".[excel]"`).

**This is a different thing from a raw Excel or Word requirements document** someone wrote by hand to describe a dataset — prose, a loose table, notes — rather than one already shaped as `column_name`/`type` rows. For that, see Example 9 below (`structifact discover --ai`) rather than trying to feed it to `validate`/`generate` directly.

Not available in CSV/Excel, YAML-only: per-field `source`/`source_column` (cross-source attribution) and `label`, plus everything at the dataset level beyond a bare name/description — `constraints`, `source_table`/`sources`/`joins`, and `depends_on`.

---

# Example 2 — Validating a Schema

```bash
$ structifact validate examples/customers/customers.yml
✓ Loaded metadata
✓ Parsed 2 fields
✓ Valid schema
✓ No constraint violations
```

This checks the *metadata's* own well-formedness — field names, supported types, constraint structure. It does not touch any data file. See Example 6 for checking real data.

---

# Example 3 — Generating Artifacts

```bash
$ structifact generate examples/customers/customers.yml -o examples/customers/generated
```

Produces, by default (SQL, dbt YAML, and the minimal catalog — see `-g` below for the full list):

`generated/customers.sql`:

```sql
CREATE TABLE customers (
    customer_id INTEGER,
    created_at TIMESTAMP
);
```

`generated/customers.yml` (dbt-style metadata):

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

To run a specific generator (or set of generators) instead of the default set:

```bash
$ structifact generate examples/customers/customers.yml -g docs,catalog_extended
```

Currently available generator names: `sql`, `dbt_yaml`, `catalog` (all three run by default), plus `catalog_extended`, `docs`, and `model` (all opt-in — see Example 5 and Example 4 for why `model` and `docs` aren't run automatically).

---

# Example 4 — A Dataset with Computed Fields and a Real Transformation Model

Structifact can represent a field whose value is derived from other fields, and — unlike the SQL generator, which only ever produces schema DDL — actually emit an executable `SELECT` for it.

```yaml
dataset:
  name: orders

fields:
  - name: qty
    type: integer
  - name: unit_price
    type: decimal
    precision: 9
    scale: 2
  - name: gross_amount
    type: decimal
    precision: 15
    scale: 2
    computed: true
    expression: "qty * unit_price"
```

```bash
$ structifact generate orders.yml -g model
```

produces `orders_model.sql`:

```sql
select
    orders.qty as qty,
    orders.unit_price as unit_price,
    qty * unit_price as gross_amount
from orders;
```

`structifact generate orders.yml` (the default set, no `-g`) does **not** include `model` — `SQLGenerator`'s output for the same dataset instead documents the computed field as a comment, since `SQLGenerator` produces `CREATE TABLE` DDL, not a transformation query:

```sql
CREATE TABLE orders (
    qty INTEGER,
    unit_price DECIMAL(9,2),
    -- computed: gross_amount = qty * unit_price
    gross_amount DECIMAL(15,2)
);
```

---

# Example 5 — A Dataset Built From Multiple Sources (Joins + Dedup)

A dataset can join in other sources — including the same physical table more than once, under different roles, each independently filtered and deduplicated. This is real, shipped functionality, not a future concept; see `examples/workorder_demo/` for the full-scale version this pattern was modeled on.

```yaml
dataset:
  name: work_order_source

sources:
  - name: partner_requested_by
    table: partner_role
    filter: "role_code = 'REQ'"
    dedup:
      partition_by: [wo_id]
      order_by:
        - "is_current desc"
        - "updated_at desc"

joins:
  - source: partner_requested_by
    on: "work_order_source.wo_id = partner_requested_by.wo_id"

fields:
  - name: wo_id
    type: string
  - name: requested_by_name
    type: string
    source: partner_requested_by
    source_column: contact_name
```

```bash
$ structifact generate work_order_source.yml -g model
```

produces:

```sql
with

partner_requested_by as (
    select *
    from (
        select *,
            row_number() over (
                partition by wo_id
                order by is_current desc, updated_at desc
            ) as rn
        from partner_role
        where role_code = 'REQ'
    ) t
    where rn = 1
),

final as (

    select
        work_order_source.wo_id as wo_id,
        partner_requested_by.contact_name as requested_by_name

    from work_order_source
    left join partner_requested_by
        on work_order_source.wo_id = partner_requested_by.wo_id

)

select * from final;
```

---

# Example 6 — Checking Real Data Against a Schema

This is the core Phase 6 workflow: given a schema and an actual CSV of data, check whether the data conforms to what the schema declares.

`examples/data_quality_demo/orders_data.yml` declares (among other rules) that `order_id` is required and must match `^ORD-[0-9]+$`, `order_type` must be one of `STD`/`RET`/`CRM`, and `discount_pct` must be between 0 and 1.

```bash
$ structifact validate-data examples/data_quality_demo/orders_data.yml examples/data_quality_demo/orders_data.csv
✓ Loaded schema: orders_data
✓ Loaded data: 15 rows

✗ 7 issue(s) found

Required-field violations:
  - order_id is blank at data row 4
  - customer_id is blank at data row 15
  - quantity is blank at data row 7

Uniqueness violations:
  - order_id 'ORD-1002' appears in data rows 2 and 5

accepted_values violations:
  - order_type 'XYZ' at data row 6 not in the accepted set

Range violations:
  - discount_pct '1.50' at data row 8 out of range

Pattern violations:
  - order_id 'BADID' at data row 13 does not match the expected pattern
```

A dataset with no rules violated reports:

```bash
$ structifact validate-data orders_data.yml clean_data.csv
✓ Loaded schema: orders_data
✓ Loaded data: 2 rows

✓ No data-quality issues found
```

---

# Example 7 — Checking a Foreign-Key Relationship Against Real Data

`orders_data.yml` also declares a `foreign_key` constraint: `customer_id` should reference `dq_customers.customer_id`. Checking that requires a second dataset's schema and data, supplied via `--ref`:

```bash
$ structifact validate-data examples/data_quality_demo/orders_data.yml examples/data_quality_demo/orders_data.csv \
    --ref dq_customers=examples/data_quality_demo/dq_customers.yml:examples/data_quality_demo/dq_customers.csv
```

adds a new section to the same report:

```text
Foreign-key violations:
  - customer_id 'CUST-004' at data rows 5 and 14 not found in dq_customers.customer_id
  - customer_id 'CUST-006' at data row 9 not found in dq_customers.customer_id
  - customer_id 'CUST-008' at data row 12 not found in dq_customers.customer_id
  - customer_id 'CUST-009' at data row 13 not found in dq_customers.customer_id
```

Running the same command *without* `--ref`, when the schema declares a `foreign_key` constraint, is a hard configuration error — not a silent "no issues found":

```bash
$ structifact validate-data examples/data_quality_demo/orders_data.yml examples/data_quality_demo/orders_data.csv
✓ Loaded schema: orders_data

Foreign-key configuration error:

Foreign-key constraint on 'customer_id' targets dataset 'dq_customers', but no reference data was supplied for it. Pass --ref dq_customers=<schema.yml>:<data.csv>.
```

---

# Example 8 — Bootstrapping a Schema from Raw Data

When no metadata exists yet, `structifact discover` infers a draft schema from a raw CSV sample:

```bash
$ structifact discover raw_customers.csv
✓ Read 500 row(s)
✓ Sampled 100 row(s)
✓ Inferred 6 column(s)
✓ Wrote draft metadata to raw_customers.discovered.yml
```

The draft is clearly labeled as unverified and is never automatically validated or generated from — a human reviews and fixes it, then runs `structifact validate` on it like any other metadata file. Adding `--ai` (off by default, cost-estimated, requires confirmation) asks an LLM to suggest field descriptions for the same draft.

Any `--ai` usage requires an `ANTHROPIC_API_KEY` environment variable — Structifact never ships or hardcodes a key — and the `ai` extra installed (`pip install -e ".[ai]"`; it's optional so plain `discover` and every non-AI command work without it). Without a key set, `--ai` fails with a clear error rather than a confusing downstream failure; every other command, including plain `discover` with no `--ai`, works with zero setup and zero network access. Declining the cost-estimate confirmation prompt (or omitting `--ai` entirely) makes genuinely zero API calls.

---

# Example 9 — Bootstrapping a Schema from a Requirements Document

For a freeform requirements document (a table-based spec, prose, bullet points, or a mix — see `examples/workorder_demo/REQUIREMENTS_workorder.md` for a real, complex example), there's no deterministic parsing path — `--ai` is required. There's no separate `--requirements` flag either: a `.md`/`.txt`/`.xlsx` file passed to `discover` is routed to this path automatically, based on its extension:

```bash
$ structifact discover REQUIREMENTS_workorder.md --ai

AI-assisted requirements-document extraction requested.
Estimate: ~2,400 input tokens, ~1,800 output tokens (~$0.02)
Proceed with this request? [y/N] y

✓ Wrote draft metadata to work_order_source.discovered.yml
```

Fields whose value is described as derived from others are flagged `computed: true` with the raw described logic preserved as text (not auto-translated into a real `expression` — that remains a human decision). Anything the extraction can identify but can't structurally place — join keys, cross-field business rules, deprioritization notes — goes into an `unresolved_notes` list in the draft rather than being silently dropped.

A raw `.xlsx` requirements document works the same way — `structifact discover REQUIREMENTS.xlsx --ai` — and is read directly, no manual conversion to Markdown needed first: every sheet's grid is dumped as plain text, in workbook order, into the same extraction prompt shown above. This has no awareness of cell *formatting*: a real workbook that uses, say, a grey fill to mark a field as a join-key/filter-only column rather than a real output field — a real, load-bearing signal observed in an actual requirements workbook — is invisible to this extraction; only what's literally typed into a cell comes through (see `DECISION_HISTORY.md` for that real case, and `FUTURE_WORK.md` for the currently-deferred formatting-aware extraction idea). Reading `.xlsx` requires the `excel` extra in addition to `ai`.

---

# Example 10 — Resolving Dataset Dependencies

Datasets can declare a dependency on other Structifact-defined datasets, not just on raw source tables:

```yaml
dataset:
  name: customer_summary

depends_on:
  - customers
  - transactions

fields:
  - name: customer_id
    type: string
  - name: total_amount
    type: decimal
    precision: 15
    scale: 2
```

Given a collection of related dataset files, `structifact deps` resolves them into a safe processing order:

```bash
$ structifact deps examples/dependency_demo/customers.yml examples/dependency_demo/transactions.yml examples/dependency_demo/customer_summary.yml examples/dependency_demo/daily_report.yml
✓ Loaded 4 dataset(s)

--- EXECUTION ORDER ---

1. customers
2. transactions
3. customer_summary
4. daily_report
```

A circular dependency is a hard error, naming the full cycle:

```bash
$ structifact deps examples/dependency_demo/cyclic_broken/dataset_a.yml examples/dependency_demo/cyclic_broken/dataset_b.yml examples/dependency_demo/cyclic_broken/dataset_c.yml
✓ Loaded 3 dataset(s)

Dependency resolution failed:

Circular dependency detected: dataset_a -> dataset_b -> dataset_c -> dataset_a
```

This is declaration and ordering only — `deps` doesn't know or generate anything about *how* `customer_summary` actually obtains data from `customers`/`transactions`. See `FUTURE_WORK.md` for the related, still-future cross-dataset value-resolution problem.

---

# Example 11 — Impact Analysis: What Depends On This Dataset?

`structifact impact` answers the reverse question to `deps`: given a dataset, which others depend on it, directly or transitively — built on the same dependency graph, so it stays grounded in the same interpretation of `depends_on` rather than reimplementing traversal.

```bash
$ structifact impact customers examples/dependency_demo/customers.yml examples/dependency_demo/transactions.yml examples/dependency_demo/customer_summary.yml examples/dependency_demo/daily_report.yml
✓ Loaded 4 dataset(s)

--- IMPACTED BY 'customers' ---

1. customer_summary
2. daily_report
```

The result isn't an arbitrary set — it's ordered as a valid regeneration sequence, since every entry really is downstream of `customers`. A dataset nothing depends on reports that explicitly rather than silently:

```bash
$ structifact impact daily_report examples/dependency_demo/customers.yml examples/dependency_demo/transactions.yml examples/dependency_demo/customer_summary.yml examples/dependency_demo/daily_report.yml
✓ Loaded 4 dataset(s)

--- IMPACTED BY 'daily_report' ---

(no datasets depend on 'daily_report')
```

---

# Example 12 — Executing Against a Real Database, and Materializing a Transformation

`structifact execute` runs a dataset's generated DDL against a real database engine — DuckDB (no credentials needed) or PostgreSQL (via `--connection`):

```bash
$ structifact execute examples/customers/customers.yml --engine duckdb
✓ Loaded schema: customers
✓ Connected: duckdb (in-memory)
✓ Executed DDL: CREATE TABLE customers (...)

Table 'customers' created successfully.
```

For a dataset with computed fields or joined-in sources (like `orders` from Example 4), `--materialize` populates the table by actually running the transformation model's SELECT — a real `INSERT INTO ... SELECT`, not just generating the SQL text — instead of loading raw `--data`. This assumes the upstream table(s) the model reads from (`source_table`, here `raw_orders`) already exist and are populated in the target database; `structifact execute` doesn't create or populate them, only the dataset being executed:

```bash
$ structifact execute orders.yml --engine duckdb --connection orders.duckdb --materialize
✓ Loaded schema: orders
✓ Connected: duckdb (orders.duckdb)
✓ Executed DDL: CREATE TABLE orders (...)
✓ Executed model INSERT: INSERT INTO orders (...)
✓ Verification query: 2 rows in orders

Table 'orders' created and materialized successfully.
```

Every write is atomic — the DROP (if `--drop-if-exists`), CREATE, and load/materialize steps share a single transaction, so a failure partway through (a duplicate-key row, a real constraint violation) leaves the database exactly as it was before the invocation, not half-populated. Re-running against an existing table fails loudly unless `--drop-if-exists` is passed — never a silent overwrite.

`--materialize` and `--data` are mutually exclusive, and a dataset with neither computed fields nor sources/joins declared has nothing to materialize — both are checked before ever connecting to the database:

```bash
$ structifact execute examples/customers/customers.yml --engine duckdb --materialize
✓ Loaded schema: customers

'customers' has no computed fields or sources/joins declared — nothing to materialize.
```

---

# Current Implementation Examples

The current repository demonstrates all of the above, live, in its own example folders:

* `examples/customers/` — the golden-path example (Examples 1–3, 12)
* `examples/workorder_demo/` — a real requirements document exercising multi-role joins and dedup (source material for Example 9); its only spec-shaped file is an AI-extracted draft, explicitly not meant to run — Examples 4–5 above use a small self-contained dataset instead
* `examples/data_quality_demo/` — the Phase 6 data-quality example, including a second referenced dataset for foreign-key checking (Examples 6–7)
* `examples/dependency_demo/` — dataset dependency chain (fan-in + multi-level) plus a deliberately-broken cyclic variant (Examples 10–11)

---

# Example Philosophy

Examples in this document should continue to show real, runnable commands against real files in the repository — not aspirational syntax for commands that don't exist. When a new capability ships, its example belongs here, replacing or extending the relevant section, rather than accumulating in a separate "future workflow" section that never gets reconciled with reality.
