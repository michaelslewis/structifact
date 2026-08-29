# Expected shape — medium_subscription_billing.xlsx

Written BEFORE running `discover --requirements --ai` against this
document.

## Dataset
One dataset, name close to `subscription_billing_snapshot`.

## Fields
From SUBSCRIPTION (primary): `subscription_id`, `customer_id`,
`plan_code`, `start_date`, `status`, `snapshot_date` (all
dimension), plus two computed measures: `account_age_days` (date
math) and `monthly_price_usd` (references `resolved_fx_rate`, which
should ALSO appear as its own computed/derived field or at minimum
be captured in a note — see below).

From CUSTOMER (joined on `customer_id`): `customer_name`,
`region_code`, `billing_currency` — dimension fields with `source:
customer` (or equivalent alias) and no `source_column` needed (names
match).

From PLAN_CATALOG (joined on `plan_code`): `plan_name` (dimension),
`monthly_price_local` (measure) — `source: plan_catalog` (or
equivalent).

FX_RATE itself contributes no *output* field directly — it's a pure
lookup source. Expect a `sources` entry for it (e.g. `name: fx_rate,
table: FX_RATE`) with a `joins` entry, but no field with `source:
fx_rate` unless the AI decides to expose `rate_to_usd` directly (not
required by the document).

## Sources / joins
Expect `source_table` (something like `SUBSCRIPTION`) plus three
`sources` entries: `customer` (table `CUSTOMER`, joined on
`customer_id`), `plan_catalog` (table `PLAN_CATALOG`, joined on
`plan_code`), and a lookup source for `FX_RATE` joined on
`billing_currency = currency_code`. **No `dedup` expected on any of
these** — this document deliberately has no multi-row-per-key/
priority-selection language anywhere (unlike the FX lookup in
`examples/workorder_demo`, which does need dedup via effective-dating
— this document's FX_RATE is a plain one-row-per-currency table, no
history).

## Known-tricky part, expected to land in unresolved_notes
`resolved_fx_rate`'s conditional fallback ("if USD, skip the lookup
and use 1.0; if not USD and no match, leave null") is the same shape
as `ModelGenerator`'s documented, still-unsupported limitation: a
computed field referencing a joined-in field inside a conditional/
COALESCE-style expression (see `ir.py`'s `FieldSpec.source`/
`source_column` docstring and `model.py`'s `ModelGenerator`
docstring). Expect the AI to correctly identify the fallback logic
and place it in `unresolved_notes` (matching exactly what happened in
`examples/workorder_demo`'s FX-rate case) — this is a KNOWN, already-
logged gap if it appears here, not a new finding.

## Known-gap classification if generation/execution fails
If `structifact generate -g model` or execution fails specifically on
`monthly_price_usd`/`resolved_fx_rate`'s conditional logic, that
traces directly to the already-documented "computed field can't yet
reference a joined-in field inside a conditional" gap — expected, not
new. A failure anywhere else in this document (the plain
CUSTOMER/PLAN_CATALOG joins, `account_age_days`) would be a genuinely
new finding.
