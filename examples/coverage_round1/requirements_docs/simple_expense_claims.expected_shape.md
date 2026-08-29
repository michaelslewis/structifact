# Expected shape — simple_expense_claims.md

Written BEFORE running `discover --requirements --ai` against this
document, per the coverage-round methodology: what a correct
extraction should produce, to check the AI's actual output against
afterward — not full ground-truth data, just the structural shape.

## Dataset
One dataset, name close to `employee_expense_claims`.

## Fields (10 non-computed + 2 computed = 12 total)
Non-computed, all dimension except `amount_usd` (measure):
`claim_id`, `employee_id`, `employee_name`, `department`, `category`,
`expense_date`, `submitted_date`, `approved_date`, `approved_flag`,
`amount_usd`.

Computed (role: measure, `computed: true`, raw pseudocode expression
preserved as-is — NOT translated to real SQL):
- `reimbursable_amount` — conditional on `approved_flag`.
- `days_to_approval` — date subtraction, `approved_date -
  submitted_date`.

## Sources / joins
**None expected.** This is a deliberately single-table document —
`source_table`/`sources`/`joins` should all be absent from the
draft. If the AI invents a join here, that's a real finding (over-
eager extraction), not a known gap — nothing in this document
describes more than one table.

## unresolved_notes
Should be short or empty. The only plausible candidate: `category`'s
fixed value set (Travel/Meals/Supplies/Other) — `discover`'s prompt
schema has no `accepted_values` slot, so a note flagging this (or
silence, since it's optional metadata not a join/logic gap) are both
acceptable; the field itself must still be extracted as a plain
dimension.

## Known-gap classification if something fails here
None of this document touches sources/joins/dedup at all, so a
failure here would NOT trace to any currently-known gap — it would
be a new finding in the "simplest possible case" and worth taking
seriously precisely because there's no complexity to blame it on.
