# Coverage Round 1 — Report

Dogfooding/coverage work: new synthetic test materials at three
complexity tiers (Part 1, `discover --requirements --ai`, CLI-only)
and two complexities (Part 2, hand-authored YAML, site-testable),
run through real end-to-end tests — extraction, `validate`,
`generate`, and actual execution against synthetic data in DuckDB
(plus one PostgreSQL check). **No engine code was changed.** Every
failure below was investigated to the point of a precise, evidenced
description and then left alone, per this round's own scope.

Total live LLM spend: **~$0.021** (3 calls, `claude-haiku-4-5`,
confirmed with the user beforehand; worst-case estimate had been
~$0.97).

## Part 2 — hand-authored YAML specs (site-testable)

Both passed **fully, end-to-end, with correct results.**

### `yaml_specs/simple_product_inventory.yml`
One join (`PRODUCT_STOCK` → `WAREHOUSE`), one computed field
referencing only primary-source columns. `validate` clean, `generate`
(default) clean, `generate -g model` clean. Executed the generated
model SQL against synthetic data: **all 5 rows matched
`EXPECTED.md` exactly** (`total_value` computed correctly per row,
`warehouse_name`/`region` correctly joined in).

### `yaml_specs/complex_helpdesk_tickets.yml`
Same physical table (`CONTACT_ROLE`) joined twice under two roles
(`reporter`, `assignee`), each with a priority `dedup` rule
(`is_active desc, updated_at desc`) — the proven-good
`workorder_demo` pattern, fresh domain. `validate`/`generate -g
model` clean. Executed against synthetic data deliberately covering
both dedup branches (a row with `is_active='Y'` present, and a row
with no `'Y'` at all, forcing the `updated_at`-fallback branch):
**all 4 tickets' `reporter_name`/`assignee_name` resolved correctly**
on both branches.

One value in this spec's own `EXPECTED.md` needed **self-correcting**
after execution — not a Structifact finding: `resolution_hours`'s
expression, `date_diff('hour', opened_at, closed_at)`, is DuckDB's
integer hour-*boundary-crossing* count, not fractional elapsed hours.
T004 (12:00→18:30, 6.5 real hours) correctly returns `6`, not the
`6.50` I'd originally written down from naive subtraction. The
expression choice (and my own expected value) was the error;
`ModelGenerator` reproduced the expression exactly as written. Fixed
in the committed `EXPECTED.md`.

## Part 1 — requirements documents (CLI-only, `discover --requirements --ai`)

### SIMPLE — `simple_expense_claims.md`
Single table, no joins, 12 fields (10 base + 2 computed), matched
`expected_shape.md` closely: correct field set, correct types,
**no `sources`/`joins`/`source_table` hallucinated** (nothing in the
document describes more than one table, and the extraction correctly
reflected that). `structifact validate` passed clean.

`structifact generate -g model` and execution against synthetic data
failed exactly where expected: both computed fields'
`expression`s are the document's own prose, not SQL (e.g. `"if
approved_flag = 'Y', the reimbursable amount is the full claimed
amount_usd; otherwise it's 0"`), so DuckDB's parser rejects the
generated SQL outright. **This is the already-documented, standing
behavior of `computed`/`expression`** (`FieldSpec.expression`'s own
docstring in `ir.py`: translating discovery-draft logic into real SQL
is always a human decision, never automatic) — not a new finding.

### MEDIUM — `medium_subscription_billing.xlsx`
3-table join (`CUSTOMER`, `PLAN_CATALOG`) plus a currency lookup
(`FX_RATE`), across a real 6-sheet workbook (Overview, Join Map, one
grid per table). Extraction matched `expected_shape.md` closely, and
one part exceeded it: the `FX_RATE` join condition was correctly
qualified against the *joined* `customer` alias
(`"customer.billing_currency = fx_rate.currency_code"`), not the
primary — the model correctly recognized `billing_currency` lives on
`CUSTOMER`, not `SUBSCRIPTION`, and chained the join accordingly.
`source_table: SUBSCRIPTION` correct. No spurious `dedup` (correctly
absent — this document's `FX_RATE` is a plain one-row-per-currency
table). `structifact validate` passed clean.

`generate -g model` produced correct SQL for every plain field and
join. Execution failed only on `resolved_fx_rate`'s conditional
fallback expression (prose, not SQL) — **the same already-documented
gap as SIMPLE**, and the exact shape already proven in
`examples/workorder_demo`'s FX-rate case: `unresolved_notes` also
correctly flagged this fallback logic.

**New, precisely-scoped finding from isolating this one further:**
hand-patching *only* `resolved_fx_rate`'s expression to real SQL
(`coalesce(fx_rate.rate_to_usd, case when customer.billing_currency =
'USD' then 1.0 end)`) let the rest of the query — including
`monthly_price_usd`'s expression, which references *both* a joined
field (`plan_catalog.monthly_price_local`) and a **sibling computed
field's own alias** (`resolved_fx_rate`) in the same `SELECT` —
execute successfully and produce correct values on DuckDB. Verified
this is **not portable**: the identical pattern, tested directly
against a real local PostgreSQL server, fails with `column
"resolved_fx_rate" does not exist` — PostgreSQL does not permit
referencing another column's own alias within the same `SELECT`
list (DuckDB does, as a non-standard convenience). This means "hand-
patch the computed expression and the rest just works" is
engine-dependent in a way not previously documented — worth scoping
if `ModelGenerator` is ever extended to support this pattern
natively, since a fix that only works on DuckDB would be a real,
silent portability trap.

### HARD — `hard_insurance_claims.md`
Deliberately stacks three known-hard patterns: a same-table
3-role join+dedup (`PARTY_ROLE` as claimant/adjuster/beneficiary),
an as-of-date resolution (`policy_status_as_of_claim`, resolved as of
`claim_date` not today), and an aggregation-before-join
(`total_paid_amount`, summed from `CLAIM_PAYMENT`), plus a computed
field depending on the aggregate (`net_exposure`). `structifact
validate` passed clean (13 fields).

**The one part predicted NOT to fail, didn't:** all three `PARTY_ROLE`
roles came back as correct `sources` entries with correct `filter`/
`dedup`, and — verified by execution against synthetic data
specifically designed to exercise both branches of the dedup rule —
resolved correctly in every case (`is_current='Y'` priority branch,
and the no-`'Y'`/most-recent-`updated_at` fallback branch).

**Known-gap failures, as predicted:**
- `total_paid_amount`'s aggregation landed as prose in `computed`/
  `expression`, not a structured `AggregateRule` — expected, since
  `discover.py` was never extended to ask for `AggregateRule`'s shape
  the way it was for `sources`/`joins`/`dedup`. Its own
  `unresolved_notes` correctly explained why (`"the aggregation is a
  preprocessing step... already captured as a computed measure
  field"`).
- `net_exposure` referencing `total_paid_amount` inside its
  expression is the same "computed field referencing another
  computed/joined value" gap as MEDIUM's `monthly_price_usd`.

**Genuinely new findings from this round, precisely scoped:**

1. **`policy_status_as_of_claim`'s extraction was more sophisticated
   than predicted, and the sophistication itself produces a real,
   silent correctness bug — empirically confirmed, not inferred.**
   Rather than punting entirely to `unresolved_notes`, the extraction
   declared `policy_status` as a plain `sources` entry (no `dedup`)
   and folded the as-of-date filter directly into the join's `"on"`
   condition as an inequality: `"CLAIM_HDR.policy_id =
   policy_status.policy_id and policy_status.effective_date <=
   CLAIM_HDR.claim_date"`. Its own `unresolved_notes` honestly flagged
   the gap: `"requires selecting the row with the most recent
   effective_date... this dedup/priority rule is not fully
   expressible in the 'on' condition alone."` Built synthetic data
   with a policy that has two `POLICY_STATUS_HISTORY` rows both
   qualifying under the inequality (`effective_date <= claim_date`)
   and ran the generated SQL: **the claim silently duplicates into
   two output rows** — one correctly showing the latest status
   (`lapsed`), one a spurious stale duplicate (`active`) — with
   `total_paid_amount`/`net_exposure` *also* duplicated onto the
   phantom row. Any aggregate built on top of this dataset (e.g.
   summing exposure by status) would silently double-count. This is
   the same root cause as the already-known `DedupRule`-can't-rank-
   across-a-join limitation (`DedupRule`'s `ROW_NUMBER()` CTE is
   built only from the joined-in source's own columns, before any
   join happens — see `structifact/generators/model.py`'s
   `_source_cte`), first found in
   `examples/value_experiment/experiment_b_notes.md` — but manifests
   here as **silent row duplication via an inequality join with no
   row-reduction**, a materially different and arguably worse failure
   mode than value_experiment's case (which never attempted the join
   shortcut and instead required a full manual 2-stage pipeline
   redesign). **Note:** this known gap is documented in
   `examples/value_experiment/`'s own notes but, as of this round, is
   still not folded into `docs/FUTURE_WORK.md` or
   `docs/DECISION_HISTORY.md` — worth doing before it's forgotten,
   though that's a documentation task, not something this round's
   scope covers.

2. **The same-table-multi-role `source_column` inference is not
   consistent across documents — a real extraction-quality
   observation, not a structural bug.** `examples/workorder_demo`'s
   `PARTNER_ROLE` extraction (see its own README) correctly inferred
   ONE shared physical column (`source_column: "contact_name"`)
   reused identically across all three role sources — the realistic
   shape for "one physical table, several logical parties." This
   round's `PARTY_ROLE` extraction instead gave each role its own
   distinctly-named `source_column` (`claimant_name`, `adjuster_name`,
   `adjuster_email`, `beneficiary_name`) — i.e., it assumed a wide
   table with one column *per role* rather than one shared column
   varying *by row*. Structurally this still executes correctly (built
   synthetic `PARTY_ROLE` data matching this assumption and confirmed
   it), so it is not a broken output, but it is an inconsistency in
   how the AI infers an unstated physical schema detail for the
   *identical requirements-document pattern* across two different real
   documents — worth being aware of when reviewing a draft with this
   shape, since either inference is silently plausible-looking.
   Contributing factor, not fully separable from the finding itself:
   this document's own field grid listed each role's field under a
   distinct name (`claimant_name`, `adjuster_name`, ...) without
   stating they share one physical column, the same way
   `workorder_demo`'s grid also never states it explicitly — the AI
   inferred correctly there and didn't here, on genuinely ambiguous
   input in both cases.

3. **Minor, self-caught test-construction ambiguity, not a
   Structifact finding:** this document's `POLICY_STATUS_HISTORY`
   field grid named the *output* field (`policy_status_as_of_claim`)
   without separately stating the table's own raw physical column
   name. The extraction reasonably reused the output name as
   `source_column` too. Synthetic data was built to match that
   assumption so the test above remained valid; a clearer source
   document would have avoided the ambiguity in the first place.

## Summary table

| File | Type | validate | generate -g model | execution | Classification |
|---|---|---|---|---|---|
| `simple_expense_claims.md` | CLI-only | ✓ | ✓ (produces SQL) | ✗ (prose expression) | known gap |
| `medium_subscription_billing.xlsx` | CLI-only | ✓ | ✓ | ✗ (prose expression); ✓ once hand-patched, DuckDB-only | known gap + 1 new portability finding |
| `hard_insurance_claims.md` | CLI-only | ✓ | ✓ | ✗ (prose expression); silent row duplication once hand-patched | 2 known gaps + 2 new findings |
| `simple_product_inventory.yml` | site-testable | ✓ | ✓ | ✓ correct | fully passes |
| `complex_helpdesk_tickets.yml` | site-testable | ✓ | ✓ | ✓ correct (after a self-corrected expected value) | fully passes |

## What was NOT done, deliberately

No engine code was modified. No fix was attempted for any finding
above, including the two genuinely new ones (the silent row-
duplication bug and the inconsistent `source_column` inference) —
both are described precisely enough to be scoped deliberately later,
matching this project's standing discipline against designing a fix
under the momentum of the round that found it.
