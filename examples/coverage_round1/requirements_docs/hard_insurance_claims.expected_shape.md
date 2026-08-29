# Expected shape — hard_insurance_claims.md

Written BEFORE running `discover --requirements --ai` against this
document. This document deliberately stacks three currently-known
Structifact gaps on top of each other, so failure is EXPECTED here —
the point is confirming failures trace to the right, already-logged
causes, not finding a new bug.

## Dataset
One dataset, name close to `claim_ledger_summary`.

## Fields expected in the extraction
Dimension: `claim_id`, `policy_id`, `claim_date`, `claim_type`,
`status_code`, `claimant_name`, `adjuster_name`, `adjuster_email`,
`beneficiary_name`, `policy_status_as_of_claim`.
Measure: `claim_amount` (plain), `total_paid_amount` (computed,
aggregation-derived), `net_exposure` (computed, depends on
`total_paid_amount`).

## Sources / joins expected
`source_table` ~ `CLAIM_HDR`. Three `sources` entries for the same
`PARTY_ROLE` table under three roles (`claimant`, `adjuster`,
`beneficiary` — or similar aliases), each with `filter: "role_code =
'...'"` and a `dedup` rule (`partition_by` the claim key,
`order_by: ["is_current desc", "updated_at desc"]`) — this exact
shape is proven extractable (see `examples/workorder_demo`'s
`PARTNER_ROLE` pattern, now working end-to-end as of the
source_column/sources/joins/source_table work). **This part is NOT
expected to fail** — it's the one pattern in this document that's
fully solved already.

A `POLICY_STATUS_HISTORY` source and a `CLAIM_PAYMENT` source are
also plausible extractions, though the AI may instead route the
as-of-date and aggregation logic entirely into `unresolved_notes`
rather than attempting a `sources` entry for them — both are
reasonable, since `discover`'s prompt never explicitly asks for
effective-dated or pre-aggregated source patterns the way it does for
plain joins/dedup.

## Known-gap classification — expected failure points, not new findings

1. **`policy_status_as_of_claim` (as-of-date resolution).** Structifact's
   `DedupRule` ranks rows using only the joined-in source's OWN
   columns, before any join happens — it cannot rank using
   `claim_date` from the primary table, because that column isn't
   available yet at the point the source's own CTE is built (see
   `structifact/generators/model.py`'s `_source_cte`). A plain
   `dedup` rule on `POLICY_STATUS_HISTORY` can only express "the
   single latest status ever for this policy," not "status as of
   this claim's date." Found and documented in
   `examples/value_experiment/experiment_b_notes.md` (not yet folded
   into `FUTURE_WORK.md`/`DECISION_HISTORY.md` as of this round — see
   this round's own report for that gap). **If extraction or
   generation fails or produces a wrong-shaped result here, that's
   this known gap, not new.**

2. **`total_paid_amount` (aggregation-before-join) — mechanically
   solved by `AggregateRule`,** but the requirements document doesn't
   describe it in `AggregateRule`'s own vocabulary (`group_by`/
   `aggregates`) — it's prose ("SUM of every CLAIM_PAYMENT row...
   aggregated... before joining"). `discover`'s prompt was never
   extended to ask for `AggregateRule`'s shape the way it was for
   `SourceRef`/`JoinSpec`/`DedupRule` — that extension only ever
   covered dedup. **Expect this to land in `unresolved_notes` as
   prose, not as a structured `aggregate:` block** — this is a real,
   but unsurprising, gap: nothing in `discover.py` was ever built to
   extract `AggregateRule`'s shape at all, so its absence here isn't
   "AI failed," it's "this was never asked for."

3. **`net_exposure` (computed field referencing a joined/aggregated
   field inside an expression).** `ModelGenerator`'s own docstring is
   explicit this is "deliberately NOT yet supported... a computed
   field's expression referencing a joined-in field by source alias."
   Even if `total_paid_amount` were somehow fully resolved via
   `AggregateRule`, `net_exposure`'s expression referencing it
   directly would still not be something `ModelGenerator` can turn
   into correct, qualified SQL today. **Expect this to generate
   syntactically-present-but-semantically-broken SQL (an unqualified
   bare reference) if it gets far enough to generate at all** —
   matching exactly the `resolved_fx_rate` failure mode already
   proven in `examples/workorder_demo`.

## What would count as a genuinely NEW finding here
The `PARTY_ROLE` three-role join+dedup pattern working end-to-end
(fields, sources, joins, dedup, generation, execution) is the one
part of this document with no known gap standing in the way — if
*that* part fails, or if `structifact validate` itself rejects a
structurally valid draft, that's new and worth reporting precisely,
not attributed to any of the three gaps above.
