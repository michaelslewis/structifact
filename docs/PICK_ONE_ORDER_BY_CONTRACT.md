# Paper Contract: `JoinSpec.pick_one_order_by`

**Status: DRAFT — for review only. No code, schema, or test changes have
been made. This document proposes a capability; it does not approve one.**

## Background

`DedupRule` collapses a joined-in `SourceRef` to one row per key by ranking
rows with `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` inside
`_source_cte()` ([structifact/generators/model.py:13-78](../structifact/generators/model.py#L13-L78)) — *before* that
source is joined to anything. Its `ORDER BY` can therefore only reference
columns physically present on the source's own table
(`source.table`'s columns via its `select *`). It has no visibility into
the primary source or any other joined source, because at the point
`_source_cte()` runs, no join has happened yet.

This is a real limitation, independently reproduced twice:

- **`examples/value_experiment/`** — resolving a customer's status *as of
  an order's own date* (`customer_status_history.effective_date <=
  orders.order_date`) could not be expressed with `DedupRule` at all,
  because the ranking needs `orders.order_date`, a primary-source column.
  The workaround was a three-stage dataset split
  (`order_status_and_revenue_candidates` → `order_status_resolved` →
  `order_status_revenue_summary`), including an undocumented trick
  (setting `source_table` to a source's own name so the *next* dataset's
  bare `FROM` resolves to that source's CTE). See
  `examples/value_experiment/experiment_b_notes.md` and
  `docs/FUTURE_WORK.md`.
- **`examples/coverage_round1/requirements_docs/hard_insurance_claims.*`**
  — `discover --requirements --ai` hit the identical wall and, with no
  guardrail stopping it, silently produced a **wrong** dataset: it folded
  the as-of condition into `JoinSpec.on` as a bare inequality
  (`policy_status.effective_date <= CLAIM_HDR.claim_date`) with no
  corresponding row-reduction. `structifact validate` passed. Executed
  against real synthetic data in DuckDB, a claim whose policy had two
  qualifying `POLICY_STATUS_HISTORY` rows came back as **two output
  rows** — one correct, one a stale duplicate, with `total_paid_amount`
  and `net_exposure` duplicated onto the phantom row too. Logged in
  `docs/FUTURE_WORK.md`, not yet scoped.

Meanwhile, `JoinSpec.on` already runs in the *final* join scope — it's
inlined into `from {primary}\n{join keyword} {j.source}\n on {j.on}`
([model.py:221-225](../structifact/generators/model.py#L221-L225)) — so it can already reference the
primary source and any source joined earlier in `dataset.joins`. The
candidate `pick_one_order_by` moves ranking into that same scope, via a
correlated `LEFT JOIN LATERAL`, so it can rank using exactly the columns
`on` can already see.

This document specifies what `pick_one_order_by` would mean, *without*
implementing it.

---

## 1. Semantics

`JoinSpec` gains one new optional field:

```python
pick_one_order_by: Optional[List[str]] = None
```

**Naming (resolved):** the name is `pick_one_order_by`, with no aliases.
It deliberately does not read as a plain ordering hint (e.g. `order_by`
alone would suggest sorting output rows, not changing how many of them
exist) — `pick_one_` up front signals that this is a cardinality-changing
operation, not cosmetic ordering: it selects exactly one qualifying row
according to the ordering that follows, out of however many `on` alone
would have matched. This was an open question in the prior draft of this
contract; it is now closed.

**When absent (`None`, the default):** `JoinSpec` behaves exactly as it
does today. No change to generated SQL, no change to validation, no
change to any existing dataset. This is not a special case to preserve —
it is the entire existing code path, untouched.

**When present:** the meaning is —

> Apply `JoinSpec.on` to find every row of `source` that qualifies for a
> given row of the join's left-hand side (the primary source, or the
> accumulated result of primary + earlier joins). If more than one row
> qualifies, order the qualifying rows by the `pick_one_order_by`
> expressions (first entry = highest priority, exactly like
> `DedupRule.order_by`) and keep only the first. The result is exactly
> one row of `source` per left-hand row, or zero.

- `JoinSpec.on` is **unchanged in meaning** — it still, and *only*,
  defines which rows qualify (the match condition). `pick_one_order_by`
  never adds or removes qualifying rows; it only orders and truncates
  among rows `on` already accepted.
- **Zero qualifying rows:** identical to today's behavior for the same
  `type`. For `type: left`, the left-hand row is preserved with every
  `source`-qualified column `NULL` (the candidate's `ON true` after a
  `LEFT JOIN LATERAL` that returns no rows already does this — no
  special-case logic needed). For `type: inner`, the left-hand row is
  dropped, matching plain inner-join semantics today.
- **Multiple qualifying rows:** exactly one is selected, per the
  ordering. This is the entire point of the feature — it is what turns
  `hard_insurance_claims`'s silent 2-row fan-out into a single,
  intentional row.
- **Trust model:** `pick_one_order_by` entries are raw SQL fragments,
  under the *exact same trust model as `DedupRule.order_by`* — not
  parsed, not semantically interpreted, only checked for
  presence/non-blankness (see §10). A string like `"effective_date
  desc"` is inlined into an `ORDER BY` clause as-is.

## 2. Scope / Visibility

**`JoinSpec.on`** (unchanged): may reference the primary source's table
alias, and any source named in a `JoinSpec` declared *earlier* in
`dataset.joins` — this is unchanged, pre-existing behavior, a direct
consequence of `on` being inlined into a `FROM ... JOIN ...` clause where
SQL join scope is left-to-right (see [model.py:221-225](../structifact/generators/model.py#L221-L225)). It may
reference any column physically present in the correlated source's own
CTE (i.e., anything `select *` from `source.table` exposes), not merely
columns mapped to a declared `FieldSpec` — Structifact does not parse
`on` and never has.

**`pick_one_order_by`**, under the candidate `LEFT JOIN LATERAL`
representation, sits *inside* the correlated subquery's `WHERE`/`ORDER
BY`, which SQL evaluates with exactly the same left-to-right visibility
as `on` does today:

```sql
from CLAIM_HDR
left join lateral (
    select *
    from policy_status
    where CLAIM_HDR.policy_id = policy_status.policy_id   -- from `on`
      and policy_status.effective_date <= CLAIM_HDR.claim_date  -- from `on`
    order by policy_status.effective_date desc              -- from pick_one_order_by
    limit 1
) as policy_status on true
```

So: **`pick_one_order_by` may reference exactly the same set of columns
`on` may reference for that same `JoinSpec`** — the primary source, any
source joined earlier in `dataset.joins`, and `source` itself. This is a
deliberate design choice, not an accident of the LATERAL mechanism: since
both live on the same `JoinSpec` and both execute in the same
correlated-subquery scope, there is no reason to give them different
visibility, and doing so would be a second thing to document and test for
no benefit.

**Documented ordering/visibility limitation (real, not artificial):**
because SQL `FROM`/`JOIN` visibility is strictly left-to-right, a
`JoinSpec`'s `on` and `pick_one_order_by` can **only** see sources
declared *before* it in `dataset.joins` — never one declared after. A
dataset author who needs join B's pick-one ordering to depend on join A's
result must declare A before B. This is the same constraint that already
governs `on` today; `pick_one_order_by` inherits it unchanged (see §5 for
how this plays out across multiple pick-one joins, and §3 of the "Multiple
pick-one joins" evidence below).

## 3. Determinism / Ties

**What happens if every qualifying row ties on every `pick_one_order_by`
expression?** The `ORDER BY ... LIMIT 1` inside the LATERAL subquery
still returns exactly one row — SQL engines do not raise an error for an
underspecified `ORDER BY`, they pick *some* row, and which one is not
guaranteed by the SQL standard (in practice, usually stable and tied to
physical/scan order, but not something Structifact should promise).

**Recommendation: do not invent a hidden tie-breaker, and do not reject
the configuration at validation time. Document that ties are the
caller's responsibility, exactly as `DedupRule` already does today.**

Reasoning:

- **Consistency with `DedupRule`.** `DedupRule`'s own docstring
  ([ir.py:160-184](../structifact/ir.py#L160-L184)) already says "ties broken by subsequent entries"
  and is silent on what happens if *every* entry ties — that case is
  already unspecified, existing, shipped behavior. Giving
  `pick_one_order_by` a stricter contract than the mechanism it's
  modeled on would be inconsistent for no real gain, and would invite the
  question of why `DedupRule` doesn't get the same treatment (a question
  this contract is explicitly not scoped to answer — "Do NOT redesign
  DedupRule").
- **Rejecting the configuration isn't something `validate` can actually
  do.** Whether a tie *will* occur is a property of real data, not of the
  metadata — and per `docs/DESIGN_PRINCIPLES.md` principle 12,
  "validation" in Structifact means checking the metadata's
  well-formedness; checking real data is a structurally different,
  deliberately separate capability (`quality.py`). A static check could
  only reject `pick_one_order_by` for being empty (see §10) — it cannot
  know, from schema alone, whether two rows will ever tie.
- **This matches design principle 6 (Explicit over Magic) and 7
  (Reliability Before Cleverness):** the honest, transparent answer is
  "Structifact will pick one row, deterministically per this ORDER BY,
  and if your ORDER BY doesn't fully discriminate, which one is
  underdetermined — make it discriminate if that matters to you." That is
  explicit and honest; synthesizing a hidden tiebreaker (e.g.
  silently appending a row-hash or physical row id) would be exactly the
  kind of implicit magic principle 6 exists to prevent, and would also
  make output depend on engine-internal row order in a way nothing
  documents.

**Documentation requirement (not a validation rule):** the field's
docstring must say, in the same place `DedupRule.order_by`'s docstring
does, that a `pick_one_order_by` which does not fully discriminate
between qualifying rows produces an engine-determined, not
Structifact-determined, selection — the caller should add enough
ordering keys (e.g. a tiebreaker column, or a stable id) to fully
discriminate if determinism matters to them.

## 4. Join Types

Current `SUPPORTED_JOIN_TYPES = {"left", "inner"}`
([validation.py:26-29](../structifact/validation.py#L26-L29)) — these are the *only* two `JoinSpec.type`
values the IR supports today; there is no third type to consider.

- **`left`**: `pick_one_order_by` composes cleanly. `LEFT JOIN LATERAL
  (...) ON true` preserves every left-hand row, with `NULL`s for
  `source`'s columns when zero rows qualify — identical semantics to
  today's plain `left join {source} on {on}` for the zero/one-match
  cases, and now well-defined (exactly one row, per the ordering) for the
  multiple-match case that is silently broken today.
- **`inner`**: also composes cleanly. An inner-flavored lateral join
  (`JOIN LATERAL (...) ON true`, or equivalently `CROSS JOIN LATERAL`
  followed by the correlated `WHERE`/`LIMIT 1` inside — both DuckDB and
  PostgreSQL accept `JOIN LATERAL ... ON true` as inner-lateral syntax)
  drops the left-hand row entirely when zero rows qualify, matching
  today's `inner join {source} on {on}` behavior for the zero-match case,
  and again resolves today's undefined multiple-match case to exactly one
  row.

**No `JoinSpec.type` value needs to be excluded from supporting
`pick_one_order_by`** — both existing types map onto a well-defined
LATERAL form. Should a third join type ever be added to
`SUPPORTED_JOIN_TYPES` in the future, this contract does not pre-approve
`pick_one_order_by` for it; that would need its own review at the time,
since `LATERAL`'s interaction with e.g. a hypothetical `full`/`right`
join is a different, unexamined question.

## 5. Multiple Pick-One Joins

Consider:

```yaml
joins:
  - source: A
    "on": "primary.k = A.k"
    pick_one_order_by: ["A.rank desc"]
  - source: B
    "on": "primary.k = B.k and B.a_id = A.id"   # references A
    pick_one_order_by: ["B.rank desc"]           # could also reference A or primary
```

**This composes naturally, with the same left-to-right constraint
already established in §2.** Under the candidate LATERAL representation,
each `JoinSpec` becomes one `LEFT JOIN LATERAL (...) AS <source> ON true`
clause, appended to the `FROM` in `dataset.joins` order — structurally
identical to how plain joins chain today
([model.py:221-225](../structifact/generators/model.py#L221-L225)). A later join's LATERAL subquery is a normal
FROM-item as far as SQL scoping is concerned, so it can correlate to
*any* alias introduced earlier in the same `FROM` clause — including the
resolved, single-row output of an earlier pick-one join. There is nothing
special about a pick-one join's output that would block a later join
(pick-one or plain) from referencing its columns; once join A has
resolved to one row per primary row, its columns are just ordinary
correlated columns to anything after it, exactly like a plain join's
columns are today.

**The one real constraint is the one already documented in §2:**
declaration order in `dataset.joins` is the visibility order. Join B
cannot reference join C's columns if C is declared after B — this holds
whether B and/or C use `pick_one_order_by` or not, and is not a new
constraint this feature introduces; it is the existing `on`-scope rule,
just now also governing `pick_one_order_by`.

No new IR field or ordering directive is proposed here — `dataset.joins`
already is an ordered `List[JoinSpec]`, and that order already carries
this meaning today.

## 6. Existing `DedupRule` and `AggregateRule`

**IR placement (resolved): `pick_one_order_by` belongs on `JoinSpec`,
not on `SourceRef` and not as a new IR concept.** The ranking this
feature performs is inherently relative to one particular join
condition, not to the source in isolation: `JoinSpec.on` is what defines
the set of candidate rows in the first place, and `pick_one_order_by`
only chooses among the candidates `on` already produced — it has no
meaning independent of an `on` condition to narrow rows down from. The
columns it needs to rank by are visible precisely because they're in
that join's own scope (§2: primary source, sources joined earlier,
and `source` itself) — not because of anything intrinsic to `source` on
its own. `SourceRef.dedup` and `SourceRef.aggregate`, by contrast, solve
a genuinely different, pre-join, source-level problem — "reduce this
source to one row per key, on its own terms, before it is joined to
anything" — which is exactly why they live on `SourceRef` rather than on
whatever `JoinSpec` happens to reference that source. Putting
`pick_one_order_by` anywhere but `JoinSpec` (e.g. on `SourceRef`, or as a
new standalone IR concept) would either duplicate `on`'s match condition
a second time somewhere else, or leave the ranking with no join
condition to be relative to. This was an open question in the prior
draft of this contract; it is now closed in favor of
`JoinSpec.pick_one_order_by`, as used throughout this document.

**Relationship to `DedupRule`:** `SourceRef.dedup` and
`JoinSpec.pick_one_order_by` are two different mechanisms operating at
two different SQL scopes on (potentially) the same joined `SourceRef`:

- `DedupRule` collapses `source.table` to one row per `partition_by` key
  **inside `_source_cte()`, before any join** — using only that source's
  own columns, independent of how (or whether) it ends up joined to
  anything. It answers: "for this source, on its own terms, which row
  wins within a group?"
- `pick_one_order_by` collapses the *join match* to one row per left-hand
  row, **in the final join scope, using the already-deduped/aggregated
  source CTE as its `FROM`** — using columns visible in that final scope
  (§2). It answers: "given this specific primary row, which of the
  (already-deduped) qualifying rows wins?"

**Relationship to `AggregateRule`:** `AggregateRule` collapses
`source.table` to one row per `group_by` key set, **also inside
`_source_cte()`, before any join** ([model.py:34-50](../structifact/generators/model.py#L34-L50)) — via a `GROUP BY`
over `source.aggregate.group_by`, using only that source's own table and
its own raw-SQL `aggregates` expressions. Exactly like `DedupRule`, it
has no visibility into the primary source or anything joined later; it
operates purely pre-join, on the source's own terms — the same scope,
just a different collapse mechanism (`GROUP BY` rather than
`ROW_NUMBER()`). `validation.py` already enforces that a `SourceRef` may
have at most one of `dedup`/`aggregate` set, never both
([validation.py:286-293](../structifact/validation.py#L286-L293)). `pick_one_order_by` doesn't compete with that
rule — it isn't a third pre-join mechanism; it's a join-scope mechanism,
orthogonal to whichever (if either) pre-join mechanism the source itself
uses.

**This design leaves every existing `DedupRule` and `AggregateRule`
semantic completely unchanged.** `pick_one_order_by` does not touch
`_source_cte()` or `SourceRef` at all — it is purely a `JoinSpec`-level
addition. A source with `dedup` or `aggregate` set and referenced by a
`JoinSpec` with no `pick_one_order_by` generates byte-identical SQL to
today.

**Using `pick_one_order_by` together with `SourceRef.dedup` on the same
joined `SourceRef` — valid and meaningful, not redundant, not
rejected.** They operate over different grouping keys in the general
case:

- `DedupRule.partition_by` groups by *the source's own* key(s) —
  independent of any particular join.
- `pick_one_order_by` effectively groups by *the join match* — which
  primary row's `on` condition a given source row satisfies.

These are the same grouping only when `DedupRule.partition_by` already
happens to equal the `on` match key exactly — in which case
`pick_one_order_by` becomes functionally redundant (the source CTE is
already ≤1 row per match) but still harmless: the LATERAL subquery simply
finds 0 or 1 candidate rows and the `ORDER BY ... LIMIT 1` is a no-op.
`hard_insurance_claims`'s `claimant`/`adjuster`/`beneficiary` sources are
exactly this redundant-but-harmless case if `pick_one_order_by` were
added to their joins too: `dedup.partition_by: [claim_id]` already
matches the join's `on` key, so it's already ≤1 row per match. Whether
this redundancy actually holds depends on an alignment between two
independently-declared raw-SQL fragments (`dedup.partition_by` and
`on`'s match key) that Structifact cannot verify — it is a coincidence
of how the dataset happens to be authored, not something the IR
guarantees.

**Using `pick_one_order_by` together with `SourceRef.aggregate` on the
same joined `SourceRef` — also valid, not rejected, but the case is
meaningfully stronger than the `dedup` case above: almost always a true
no-op, not merely "usually redundant."** An aggregated source's CTE is
*already, by construction*, exactly one row per `group_by` key — that is
what `GROUP BY` guarantees as a matter of relational algebra, not a
data-dependent coincidence the way `dedup.partition_by` happening to
equal the join's match key is. Whenever a `JoinSpec.on` condition
matches an aggregated source on (a subset of, or exactly) its own
`group_by` columns — which is the standard shape for this pattern,
matching `AggregateRule`'s own real-world motivation (its `ir.py`
docstring describes a source "pre-aggregated... before the join," and
`examples/value_experiment/order_status_and_revenue_candidates.yml`'s
`lines` source, aggregated by `order_id` and joined on
`lines.order_id = orders.order_id`, is exactly this shape) — the LATERAL
subquery's correlated `WHERE` can never see more than one candidate row
to begin with. `pick_one_order_by`'s `ORDER BY ... LIMIT 1` in that case
has structurally nothing to choose between: not "unlikely to matter,"
but mathematically guaranteed not to matter, given `on` matches on the
group key. As with the `dedup` case, Structifact cannot statically
*confirm* that `on`'s match key equals (or is a subset of) `group_by` —
both remain unparsed raw SQL — which is why this is stated as *almost
always* a true no-op rather than a provable one: a `JoinSpec.on` that
deliberately matches an aggregated source on some column outside its
`group_by` (unusual, and not the pattern any real example uses, but not
IR-prohibited) would be the one shape where `pick_one_order_by` retains
genuine selective power even against an aggregated source.

**No new validation rule is proposed for either interaction.**
Structifact cannot statically determine whether `dedup.partition_by` or
`aggregate.group_by` coincide with a `JoinSpec.on`'s match key — all are
raw, unparsed SQL text (`filter`/`on`/`order_by`/`partition_by`/
`group_by`/`aggregates` are all under the same "not parsed, not
validated beyond presence" trust model, per `ir.py`'s existing
docstrings) — so there is no metadata-only check that could tell
"redundant"/"no-op" from "necessary" apart, for either `dedup` or
`aggregate`. Per the same reasoning as §3, inventing a heuristic here
would be guessing at semantics Structifact deliberately does not parse.
Existing `AggregateRule` semantics are unchanged by any of this — this
section only documents how `pick_one_order_by` relates to it, not a
change to how `AggregateRule` itself behaves.

## 7. Backward Compatibility

**An existing `JoinSpec` with no `pick_one_order_by` (the default,
`None`) MUST generate exactly the same SQL structure as it does today —
byte-for-byte, not merely "equivalent."** The candidate design achieves
this trivially by construction: `pick_one_order_by is None` is proposed
as the branch condition for keeping today's `f"    {keyword}
{j.source}\n        on {j.on}"` code path in `model.py` untouched; the
`LEFT JOIN LATERAL` form is only emitted when `pick_one_order_by` is
present. This is a contract requirement on the eventual implementation,
not something this document can verify by itself — it belongs in §11's
required tests.

**`examples/workorder_demo`'s multi-role joins and existing `DedupRule`
tests must be unaffected**, because:
- `workorder_demo`'s `PARTNER_ROLE` joins never set `pick_one_order_by`
  under this proposal (it is opt-in), so they take the unchanged code
  path.
- `_source_cte()` is untouched by this proposal entirely (§6) — every
  existing `DedupRule`/`AggregateRule` test exercises code this contract
  does not modify.

## 8. Portability

The candidate representation is `LEFT JOIN LATERAL (subquery) AS alias
ON true` (and, per §4, `JOIN LATERAL ... ON true` for `inner`). Checked
against this repository's two real, tested execution paths
([structifact/executors/duckdb.py](../structifact/executors/duckdb.py),
[structifact/executors/postgres.py](../structifact/executors/postgres.py), both exercised by real
integration tests in `tests/test_executors.py` — DuckDB unconditionally,
PostgreSQL behind `requires_postgres`, a CI-service-gated skip):

- **DuckDB:** `pyproject.toml` pins `duckdb>=0.10`
  ([pyproject.toml:25-26,42](../pyproject.toml#L25-L26)); the active `.venv` resolves to `duckdb==1.5.5`.
  DuckDB has supported `LATERAL` joins (including the explicit `LEFT
  JOIN LATERAL ... ON true` form) since well before 0.10, so the pinned
  minimum and the actually-installed version both cover the candidate
  syntax.
- **PostgreSQL:** `LATERAL` is a long-standing, ANSI-SQL-adjacent feature
  (since PostgreSQL 9.3), universally available on any PostgreSQL version
  this project could plausibly target — `PostgresExecutor` places no
  version floor on the server itself (`connect()` only requires a DSN,
  [postgres.py:36-46](../structifact/executors/postgres.py#L36-L46)), so no separate version concern exists there.

**This has not been empirically executed in this repository as part of
this investigation** — no `LATERAL` SQL has actually been run against
either engine for this feature; the above is based on documented engine
support, not a verified test run. §11 requires both engines to actually
execute a `pick_one_order_by`-generated query (DuckDB unconditionally,
PostgreSQL behind the existing `requires_postgres` gate) before this
feature can be considered complete — that is where portability gets
verified, not here.

**No portability blocker was found.** Nothing here contradicts the
candidate design; no alternative SQL representation is proposed.

**Performance consideration (informational only — not a portability
finding, and not a reason to redesign the SQL representation here).**
The candidate `LEFT JOIN LATERAL` form evaluates its subquery once per
outer (left-hand) row — a correlated-subquery execution shape — which is
a structurally different execution profile from `DedupRule`'s existing
mechanism, a single set-based `ROW_NUMBER() OVER (PARTITION BY ...)`
pass over the whole source before any join happens. Whether that
difference is material in practice (row counts, available indexes, each
engine's own query-planner handling of `LATERAL`) is unknown from this
investigation:

- DuckDB/PostgreSQL *supporting* the LATERAL form (§8 above) and
  *executing it correctly* are separate questions from how it
  *performs* at realistic data volumes — correctness does not imply
  comparable performance to the pre-join, set-based path.
- No comparative benchmark between the candidate `LATERAL` form and any
  alternative representation has been performed as part of this
  investigation.
- Performance characterization is deliberately deferred until an actual
  implementation exists and can be run against representative data
  volumes — only then would there be real evidence of whether this is
  material enough to warrant a different SQL representation. This
  document does not propose one now.

## 9. Mapping to the Two Real Reproductions

### A. `examples/value_experiment/`

Today's workaround is a three-file pipeline:
`order_status_and_revenue_candidates.yml` (fans out every
`customer_status_history` row satisfying `csh.effective_date <=
orders.order_date` via a plain `left join` with no dedup — the file's own
comment explains why: `DedupRule` "has no visibility into
orders.order_date") → `order_status_resolved.yml` (a *second dataset*,
whose only job is applying `DedupRule(partition_by: [order_id],
order_by: [effective_date desc])` to the first dataset's materialized
output, using the undocumented `source_table: candidates` trick to make
`FROM` resolve to the sole source's own CTE) → a third summary dataset.

Under this contract, stages 1 and 2 collapse into **one** `JoinSpec` on
one dataset:

```yaml
source_table: orders

sources:
  - name: csh
    table: customer_status_history
  - name: lines
    table: order_lines
    aggregate:
      group_by: [order_id]
      aggregates:
        revenue: sum(quantity * unit_price)

joins:
  - source: csh
    "on": "csh.customer_id = orders.customer_id and csh.effective_date <= orders.order_date"
    type: left
    pick_one_order_by: ["csh.effective_date desc"]
  - source: lines
    "on": "lines.order_id = orders.order_id"
    type: left
```

This is a direct, one-for-one translation: `on` is unchanged from stage
1's join (it already correctly scoped to `orders.order_date`, per §2 —
this was never the broken part); `pick_one_order_by` replaces the need
for stage 2's entire second file, its `depends_on` declaration, and the
`source_table` workaround. `O032` (the order predating the customer's
earliest status) still resolves to `NULL` status — zero qualifying rows,
`left` type, per §1 — with no special handling needed, matching the
existing, already-correct ground-truth behavior.

### B. `examples/coverage_round1/requirements_docs/hard_insurance_claims.*`

`hard_insurance_claims.discovered.yml`'s `policy_status` join is exactly
the shape this contract exists to fix:

```yaml
sources:
  - name: "policy_status"
    table: "POLICY_STATUS_HISTORY"
    # no dedup — nothing here reduces multiple qualifying rows to one

joins:
  - source: "policy_status"
    "on": "CLAIM_HDR.policy_id = policy_status.policy_id and policy_status.effective_date <= CLAIM_HDR.claim_date"
    # no pick_one — this is the entire bug
```

Confirmed (`docs/FUTURE_WORK.md`, executed against real synthetic data in
DuckDB): a claim whose policy has two `POLICY_STATUS_HISTORY` rows both
satisfying the inequality produces **two output rows** for that one
claim, with `total_paid_amount`/`net_exposure` duplicated onto the
phantom row. Under this contract, the fix is one line added to the
existing join:

```yaml
joins:
  - source: "policy_status"
    "on": "CLAIM_HDR.policy_id = policy_status.policy_id and policy_status.effective_date <= CLAIM_HDR.claim_date"
    pick_one_order_by: ["policy_status.effective_date desc"]
```

`on` is unchanged (it was already correctly scoped — the requirements
doc's own Section 3 note, "most recent POLICY_STATUS_HISTORY row where
effective_date <= claim_date," was always expressible as an `on`
condition; what was missing was a way to pick exactly one). With
`pick_one_order_by` present, the generated `LEFT JOIN LATERAL` finds both
qualifying rows for the affected claim, orders them by
`effective_date desc`, and keeps exactly the correct, current one — the
row-fan-out (and the resulting silent duplication of
`total_paid_amount`/`net_exposure`) is structurally impossible, not just
avoided by careful authoring. This also directly addresses the second
half of the `hard_insurance_claims.discovered.yml`'s own
`unresolved_notes`: "this dedup/priority rule is not fully expressible in
the 'on' condition alone and may require window function logic" —
`pick_one_order_by` is exactly that missing expressiveness, made
declarative instead of requiring hand-written window-function SQL.

## 10. Validation

Proposed structural checks in `validation.py`, alongside the existing
sources/joins block ([validation.py:339-357](../structifact/validation.py#L339-L357)) — matching the granularity
and style of the existing `DedupRule`/`AggregateRule`/`JoinSpec` checks
already there:

- **Type check:** `pick_one_order_by`, if not `None`, must be a `list`
  (mirrors how `dedup.order_by` and `dedup.partition_by` are implicitly
  typed as `List[str]` in `ir.py` — a non-list value, e.g. a bare string,
  is a metadata authoring error the same class as any other IR type
  mismatch).
- **Non-empty:** an empty list (`pick_one_order_by: []`) should be
  rejected, mirroring exactly `dedup`'s existing "empty order_by" check
  ([validation.py:305-309](../structifact/validation.py#L305-L309)) — an empty ordering can't rank anything,
  so it's not a valid "present but degenerate" state, same reasoning
  already applied to `DedupRule.order_by`.
- **Entries non-blank:** each entry should be a non-blank string, same
  check already applied to other raw-SQL-fragment lists in this file
  (e.g. `aggregate.aggregates` values, [validation.py:326-333](../structifact/validation.py#L326-L333)).

**What is deliberately NOT proposed as a validation rule:**
- No rejection of `pick_one_order_by` combined with `SourceRef.dedup` on
  the same source (§6 — not redundant in general, and Structifact cannot
  tell redundant from necessary without parsing raw SQL it deliberately
  doesn't parse).
- No rejection based on `JoinSpec.type` (§4 — both existing types
  support it).
- No tie-detection or "sufficiently discriminating" check (§3 —
  data-dependent, out of scope for metadata-only validation, same
  boundary `docs/DESIGN_PRINCIPLES.md` principle 12 already draws).
- No cross-check of `pick_one_order_by`'s expressions against declared
  `FieldSpec`s or `on`'s referenced columns — same trust-model boundary
  as `on`, `filter`, `dedup.order_by`, and `aggregate.aggregates` all
  already have today.

## 11. Test Requirements

Before implementation can be considered complete, at minimum:

1. **Existing `JoinSpec` behavior unchanged** — a dataset with joins that
   do *not* set `pick_one_order_by` produces byte-identical generated SQL
   before/after this feature exists (extend
   `tests/test_model_sources_joins.py` and
   `tests/test_model_execution_sources_joins.py`, which already assert
   exact-SQL-fragment and real-execution behavior for the no-`pick_one`
   case).
2. **Basic pick-one join** — a minimal dataset with one `pick_one_order_by`
   join generates the expected `LEFT JOIN LATERAL` SQL structure
   (fragment-level assertion, matching the style of
   `test_minimal_example_produces_approved_sql_contract`).
3. **Zero qualifying rows** — executed (DuckDB) against real rows where
   no candidate satisfies `on`; assert the `left`-type row is preserved
   with `NULL`s, and (separately) that the `inner`-type row is dropped.
4. **Multiple qualifying rows** — executed (DuckDB) against real rows
   where more than one candidate satisfies `on`; assert exactly one
   output row for that key (this is the direct regression test for the
   `hard_insurance_claims` bug class).
5. **Ordering selects the expected row** — same multi-candidate fixture
   as #4, but asserting the *specific* surviving row's values match what
   `pick_one_order_by`'s stated priority should select (not just "one
   row," but "the right one").
6. **Both real reproductions**, each executed end-to-end and diffed
   against known-correct expected output:
   - `examples/value_experiment/`: re-run with the collapsed
     two-file-to-one-file shape from §9A; assert byte-for-byte agreement
     with `expected_result_per_order.csv`, including `O032`'s `NULL`
     status.
   - `examples/coverage_round1/.../hard_insurance_claims`: re-run with
     `pick_one_order_by` added to the `policy_status` join per §9B;
     assert the previously-duplicated claim now produces exactly one
     output row with the correct (most-recent-qualifying)
     `policy_status_as_of_claim`.
7. **DuckDB execution** — all of the above that involve real execution
   run against DuckDB unconditionally, matching existing
   `test_model_execution_sources_joins.py` convention.
8. **PostgreSQL execution** — the same real-execution cases re-run against
   PostgreSQL, gated behind the existing `requires_postgres`
   skip-marker/CI-service pattern already used in `tests/test_executors.py`
   and `test_model_execution_sources_joins.py`'s
   `test_postgres_executes_sources_joins_model_with_correct_values`.
9. **Multiple pick-one joins compose** — a dataset with two
   `pick_one_order_by` joins where the second's `on` and/or
   `pick_one_order_by` references a column produced by the first
   (per §5); executed against real data, asserting correct row selection
   at both stages.
10. **`workorder_demo` / `DedupRule` regression** — the existing
    `examples/workorder_demo` reference SQL comparison and every existing
    `DedupRule`-related test in `tests/test_model_sources_joins.py` /
    `tests/test_model_execution_sources_joins.py` continue to pass
    unmodified (§7 — confirms `_source_cte()` truly wasn't touched).
11. **Validation tests** for each rule in §10: non-list value, empty
    list, blank entry — each rejected with a specific message, mirroring
    the existing `test_dedup_with_empty_order_by_fails_validation`-style
    tests already in `tests/test_model_sources_joins.py`.

## 12. Open Questions

Two previously-open questions from this list — naming, and whether this
belongs on `JoinSpec` versus a different IR concept — are now resolved
(see the "Naming (resolved)" note in §1 and the "IR placement (resolved)"
note in §6) and have been removed from this list accordingly. The
following remain genuinely unresolved — none of these have enough
repository evidence to decide, and none were decided by fiat above:

1. **Does the `LEFT JOIN LATERAL ... ON true` form actually round-trip
   correctly through `ModelGenerator.generate_insert()`'s
   read-relation-collision check** ([model.py:257-281](../structifact/generators/model.py#L257-L281))? That check
   inspects `source.table` for every declared source; a LATERAL subquery
   introduces no new relation name, so it's *probably* unaffected, but
   this was not traced end-to-end and should be confirmed once real code
   exists.
2. **Should `pick_one_order_by`'s presence change whether `ModelGenerator`
   is willing to run at all** (the `has_sources`/`has_computed`/etc.
   gate at [model.py:154-163](../structifact/generators/model.py#L154-L163))? Almost certainly no special case is
   needed (`has_sources` already covers "any `joins` declared"), but
   worth a deliberate check rather than an assumption once implementing.
3. **Should there be any check that `pick_one_order_by` is only set when
   `on` is actually capable of matching more than one row** — i.e. some
   lint-level nudge (not a hard rejection, per §10) suggesting
   `pick_one_order_by` might be unnecessary if e.g. `on` is a pure
   equality on what looks like a unique key? This document deliberately
   did not propose this (Structifact doesn't parse `on`, so any such
   check would be a heuristic guessing at semantics, not a real
   validation), but it's worth a human judgment call on whether even a
   soft, best-effort nudge is worth the false-positive risk.
4. **Should this feature also cover the case where the *primary source
   itself* is the one needing "pick one qualifying row as of a
   condition"** — i.e. an as-of selection against the primary source
   before any join, analogous to `DatasetSpec.source_filter` but
   ranking-based instead of filter-based? Nothing in the two real
   reproductions needs this (both fixes are joined-source-side), so it is
   explicitly out of scope for this contract, but noting it in case a
   third real example surfaces the need later.
