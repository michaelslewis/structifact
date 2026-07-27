# Golden Path Example

This folder shows the complete Structifact workflow end to end, from a
single metadata definition to generated, production-ready artifacts.

## The input

`customers.yml` — a declarative dataset definition:

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

## Validate it

```bash
structifact validate examples/customers/customers.yml
```

```text
✓ Loaded metadata
✓ Parsed 2 fields
✓ Valid schema
✓ No constraint violations
```

## Generate artifacts from it

```bash
structifact generate examples/customers/customers.yml -o examples/customers/generated
```

This produces everything in `generated/`:

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

## The point

One metadata definition, written once, produces a validated schema
plus two independent, consistent artifacts — no hand-written SQL, no
duplicated column descriptions between the database and the dbt
layer.

Structifact also supports CSV and Excel as input formats in addition
to YAML — see `examples/customers.csv` for an equivalent definition
in CSV form.
