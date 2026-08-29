# Experiment B notes: order revenue by resolved customer status

## What I built

Three chained Structifact `DatasetSpec` YAML files rather than one:

1. `order_status_and_revenue_candidates.yml` — primary source `orders`,
   `LEFT JOIN`s in `customer_status_history` (`csh`) on
   `csh.customer_id = orders.customer_id and csh.effective_date <=
   orders.order_date` (a non-equi/"as of" join, expressed as a raw
   `on:` string), and separately `LEFT JOIN`s `order_lines` (`lines`)
   pre-aggregated via `AggregateRule` (`group_by: [order_id]`,
   `aggregates: {revenue: sum(quantity * unit_price)}`). Produces a
   **fan-out**: one row per order per status candidate whose
   `effective_date` qualifies (0, 1, or several).
2. `order_status_resolved.yml` — collapses stage 1 down to exactly
   one row per order via `DedupRule` (`partition_by: [order_id]`,
   `order_by: [effective_date desc]`). This is the per-order output
   requirement.
3. `order_status_revenue_summary.yml` — groups stage 2 by `status`
   via another `AggregateRule` (`sum(revenue)`, `count(*)`). This is
   the summary requirement.

`depends_on:` on datasets 2 and 3 documents the pipeline order
(declaration only, per its own docstring — it doesn't drive
execution).

## Why not one dataset

`DedupRule`'s `ROW_NUMBER()` CTE (see `model.py::_source_cte`) is
built **only from the source's own columns, before any join
happens** — it has no visibility into the primary table at all. So a
`SourceRef` for `customer_status_history` with a dedup rule can only
express "the single latest status ever for this customer" (partition
by `customer_id`, order by `effective_date desc`), never "latest
status **as of this particular order's date**" — the actual
requirement, and the reason REQUIREMENTS.md explicitly warns against
the "current status applied retroactively" bug. There is no way,
within one `ModelGenerator` dataset, to rank join candidates using a
column from the *other* side of the join. That forced the two-stage
split: stage 1 produces the (possibly multi-row) fan-out of everything
that *could* apply as of the order date, using the inequality `on:`
condition to do the date filtering; stage 2 is a completely separate
dataset whose only job is to run `DedupRule` against stage 1's
*already-materialized* output, where `order_id`-grouped ranking finally
makes sense because effective_date and order_date have already been
reconciled into one row's worth of context per candidate.

## The `source_table == sources[0].name` trick

Datasets 2 and 3 need to apply `DedupRule`/`AggregateRule` to an
upstream table with **no new join** — just "read this table, then
collapse it." But `DedupRule`/`AggregateRule` can only be attached to
a `SourceRef` under `sources:`, and `ModelGenerator`'s final `SELECT`
always reads `FROM {primary}` (`source_table` or the dataset name).
There's no first-class "just dedup/aggregate the primary source, no
join" concept in the IR.

The trick I used: set `source_table:` to the *same string* as the
sole `SourceRef.name` (e.g. `source_table: candidates`, with
`sources: [{name: candidates, table: order_status_and_revenue_candidates,
dedup: {...}}]`) and leave `joins: []` empty. `ModelGenerator` then
emits `with candidates as (...dedup CTE...), final as (select ...
from candidates ...)` — the bare `FROM candidates` resolves to the CTE
by name, no `JOIN` line needed (`join_lines` is just an empty list,
which stringifies to `""` harmlessly). It works and produces exactly
the SQL I wanted, but I only found it by reading `model.py`'s actual
string-building code line by line — nothing in `ir.py`'s docstrings
or `validate` present this as an intended, documented pattern. It
reads more like exploiting an implementation detail than using a
supported feature, even though `validation.py` raises no objection to
it (I checked: no rule requires every declared `source` to appear in
`joins`, and no rule forbids `source_table` colliding with a
`SourceRef.name`).

## Other friction

- **`structifact generate` (no `-g`) doesn't show the transformation
  at all.** The default generator set only emits a `CREATE TABLE`
  DDL statement (plus a normalized YAML echo and a catalog CSV) —
  none of `sources`/`joins`/`DedupRule`/`AggregateRule` show up
  anywhere in that output. `ModelGenerator` (`-g model`) is explicitly
  "not run by default" per its own docstring, specifically so it
  doesn't silently add output for existing users — reasonable design
  intent, but as a first-time user solving a transformation problem,
  it would be easy to run plain `generate`, see only a DDL statement
  with no `SELECT` anywhere, and conclude the join/dedup metadata
  wasn't doing anything. I only knew to reach for `-g model` because
  the task told me to.
- **No orchestration across the 3-file pipeline.** `structifact
  generate`/`execute` operate on exactly one YAML file at a time.
  Nothing chains "generate stage 1's model → materialize it → feed it
  as stage 2's source" automatically; I had to write my own DuckDB
  script that ran each stage's generated SQL as `CREATE TABLE ... AS
  <select>` in dependency order by hand. `structifact deps` exists to
  compute a safe order across files, but I didn't end up needing it —
  I already knew the order from designing the pipeline.
- **The `"on":` quoting gotcha** (documented in `ir.py`'s own
  docstring — PyYAML 1.1 parses a bare `on:` key as boolean `True`)
  is real and I made sure to quote it from the start; would have been
  a very confusing failure otherwise.
- No temporal/"as of" join primitive exists — the inequality condition
  is just a hand-written raw SQL string in `on:`, same trust model as
  everything else in the IR (unparsed, unvalidated). Fine for this
  size of task, but nothing would have caught a typo like `<` vs `<=`
  until I ran it against real data and checked the numbers by hand.

## Iterations

`structifact validate` passed on **all three files on the first
try** — zero iteration. `structifact generate -g model` likewise
produced correct SQL on the **first try** for all three, matching
what I'd sketched by hand before writing the YAML. The real iteration
cost was upstream of any Structifact command: working out, on paper,
that a single dataset couldn't express the as-of join, and designing
the 2-stage split plus the `source_table`-trick workaround for stages
2/3, all before writing a line of YAML.

## Execution

Ran the generated `-g model` SQL directly against DuckDB
(`duckdb` Python package, in-memory) rather than through `structifact
execute` (which wants to create its own DDL-defined table and
load/materialize into it — heavier than needed here). No FROM-clause
rewriting of the generated SQL was actually necessary: I loaded the
four CSVs into DuckDB tables named exactly `orders`,
`customer_status_history`, `order_lines` (matching `source_table`/
`SourceRef.table` in the YAML), then ran each stage's generated SQL as
`CREATE TABLE <name> AS <generated select>` in order, materializing
`order_status_and_revenue_candidates` and `order_status_resolved` as
real tables so the next stage's `sources[].table` reference resolved.
Worth being honest that this "just worked" partly because I got to
choose the DuckDB table names on both sides to match the YAML.

Results: 39 orders in, 39 candidate-fan-out rows collapsed correctly
back to 39 resolved rows (verified — the dedup didn't drop or
duplicate any order). One order (`O032`, customer `C12`, dated
2024-05-01) has no qualifying status candidate — `C12`'s only history
row is `2024-06-01, trial`, after the order date — so it correctly
resolves to a null status per the "don't guess" requirement, and
shows up as its own `NULL`-status bucket (`89.5` revenue, 1 order) in
the summary rather than being dropped or misattributed.

## Reconciliation — a genuine fit, not forced

I wrote a fully independent, pure-Python (no SQL, no Structifact)
recomputation of the same per-order status-as-of-date + revenue
logic (`independent_check.py`, not saved under this directory —
scratch only), producing `experiment_b_reconciliation_old_data.csv`.
I then ran `structifact reconcile` with
`experiment_b_reconciliation_old_schema.yml` (the independent
computation, treated as the "old" system) against
`order_status_resolved.yml`/`experiment_b_per_order.csv` (the
Structifact-generated "new" system), using
`experiment_b_reconciliation_mapping.yml` to map `order_id`/`status`/
`revenue` on both sides (had to add `role: measure` to
`order_status_resolved.yml`'s `revenue` field — `reconcile_data` only
aggregates fields the *new* schema marks as a measure).

Result: **zero issues** — 39/39 rows matched on both sides, and the
`revenue` aggregate over the matched population was exactly equal
(`+0` diff). This felt like a legitimate use of `reconcile`, not a
forced one: it's exactly the "old system vs. replacement, do the
numbers agree" scenario the tool is built for, and it gave a real
independent confirmation that the join/dedup logic resolved
correctly — I hadn't spot-checked every row by hand.

## Effort vs. hand-written SQL

The SQL this requirement needs is genuinely simple by hand: a `LEFT
JOIN` with an inequality condition, a `ROW_NUMBER() OVER (PARTITION
BY order_id ORDER BY effective_date DESC)` filtered to `= 1`, a join
to a pre-aggregated `order_lines` sum, and a trailing `GROUP BY
status`. An experienced analyst could write and test that directly
against DuckDB — as one query or two, no metadata files — in well
under 15 minutes, especially since the "gotcha" (don't use today's
status) is the kind of thing you'd naturally get right just by
writing the `WHERE effective_date <= order_date` clause instead of
querying "current" status.

The Structifact path took meaningfully longer, and almost none of
that time was spent on validate/generate iteration (both were
first-try clean). It went into: reading `ir.py`/`model.py` closely
enough to discover that `DedupRule` can't see the primary table's
columns (the core reason a single dataset wasn't possible), designing
the 2–3 stage pipeline and the `source_table == sources[0].name`
trick to express "just dedup this, no new join" within the IR's
actual constraints, writing ~150 lines across three YAML files plus a
reconciliation mapping, and hand-orchestrating three sequential
DuckDB `CREATE TABLE AS` statements myself since nothing in
Structifact chains multi-file pipelines. For a genuine one-off report
this size, hand SQL would clearly have been faster. The case for
Structifact here would rest on reuse/governance value (a declared,
validated, catalog-able definition of "resolve status as of a date"
that other datasets could `depends_on` and that generates its own
DDL/catalog/dbt artifacts alongside the transform) rather than
speed-to-first-answer.

## Features used

`DatasetSpec` (`source_table`, `source_filter` not used here,
`depends_on`), `SourceRef` (`table`, `filter` not used,
`dedup`/`aggregate`), `JoinSpec` (`on` with a non-equi condition,
`type: left`), `DedupRule`, `AggregateRule`, `FieldSpec`
(`source`/`source_column`, `role: measure`), `ConstraintSpec`
(`primary_key`, `unique`), `ModelGenerator` (`-g model`), and
`structifact reconcile` / `reconciliation.py`.

## Files

- `order_status_and_revenue_candidates.yml`,
  `order_status_resolved.yml`, `order_status_revenue_summary.yml` —
  the three DatasetSpecs.
- `experiment_b_validate_output.txt` — `structifact validate` output
  for all three (all passed first try).
- `experiment_b_generated.sql` — the three `-g model` generated SQL
  artifacts, concatenated, exact generated content.
- `experiment_b_per_order.csv` — per-order resolved status + revenue
  (39 rows).
- `experiment_b_summary.csv` — revenue summary by resolved status (6
  rows, including one `NULL`-status bucket for the undeterminable
  order).
- `experiment_b_reconciliation_old_schema.yml`,
  `experiment_b_reconciliation_old_data.csv`,
  `experiment_b_reconciliation_mapping.yml`,
  `experiment_b_reconciliation_output.txt` — the independent
  cross-check and its result (zero issues).
