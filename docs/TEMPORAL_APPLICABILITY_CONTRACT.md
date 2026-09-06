# Paper Contract: References to Effective-Dated / Versioned Tables

**Status: DRAFT — for review only. No code, schema, or test changes have
been made. This document investigates a problem and evaluates candidate
designs; it does not endorse implementing any of them yet.**

## Motivating Evidence

`STAGE3_FINDINGS.md` (`expense-reimbursement-experiment` repo) recorded a
real, verified finding: making `expense_policy`'s primary key composite
(`category, effective_start_date` — necessary to represent a cap that
changes on a date) broke the existing `foreign_key` constraint from
`expense_reimbursement_lines.category` to `expense_policy.category`,
since `category` alone was no longer unique on the target side. The
constraint was removed from the metadata; the finding was logged as a
real cost of the representation change, not patched around.

Effective-dated / slowly-changing reference tables (price lists, policy
caps, tax rates, org-chart assignments, product catalogs with revisions)
are a recurring data-modeling pattern in real systems generally. The
evidence available to Structifact specifically, however, is still one
concrete example — this document treats that distinction deliberately
(see Recommendation): the semantic analysis below doesn't depend on how
common the pattern turns out to be within Structifact's own real-world
usage, but implementing anything in response to it should wait for a
second, independently motivated case to confirm this isn't peculiar to
the expense-policy scenario.

## The Actual Question

Before considering any IR change, it's worth being precise about what
relationship a consuming row (an expense line) actually has to a
versioned table (the policy table). This document distinguishes two
readings that could both plausibly be meant by "this line references
`Meals (international)`," and treats them as genuinely different claims:

**Reading A — entity reference.** "This line's category is
`Meals (international)`, a real, recognized member of the domain of
categories this system knows about." This is a claim about *domain
membership* — it doesn't care which policy version is in force, or
whether one currently is. It would be satisfied even if
`Meals (international)` currently has zero active rows (say, its policy
lapsed and hasn't been renewed) — the category still exists as a
concept.

**Reading B — resolved/applicable-version reference.** "This line's
category and date, together, identify exactly one specific row of
`expense_policy` — the one whose effective window contains this line's
`submitted_date`." This is a claim about *existence of an applicable
row*, evaluated against two columns of the consuming row (`category`
*and* `submitted_date`), not one.

**These are not the same constraint, and conflating them produces a bad
design.** A's check is a plain, permanent, unconditional
value-membership test — exactly what `ConstraintSpec.foreign_key`
already does, and does correctly, for any ordinary (non-versioned)
target. B's check is conditional and per-row-parameterized: whether it
passes for a given consuming row depends on that row's own date value,
compared against a *range* on the target side, not a single equality
comparison against a single target column. A's check can be answered
by "does this value appear in that column's set of values." B's check
can only be answered by "does there exist a target row satisfying two
independent conditions simultaneously" — structurally the same shape as
a `JoinSpec.on` + `pick_one_order_by` evaluation, not a `foreign_key`
evaluation.

The original, un-versioned `expense_policy` (one row per category)
happened to make A and B indistinguishable — with only one row per
category, "the category exists" and "the applicable row exists" were
the same fact. Making the table effective-dated is what split them
apart. The Stage 3 finding is really the discovery of this split, not
a bug in the FK mechanism.

## Three Layers, Not Two

Reading B itself turns out to bundle two separable claims once
`pick_one_order_by` is brought into the picture. Laid out as three
distinct layers, mapped onto where each already lives or would live in
Structifact's architecture:

1. **Domain membership** — `line.category → policy.category` means
   "this category value is a real, recognized member of the target's
   declared domain." Static, unconditional, permanent. This is
   Reading A, and it is exactly what `ConstraintSpec.foreign_key`
   already does. **Architectural home: `constraint` (schema layer).**

2. **Applicability** — `(line.category, line.date) → policy.category +
   effective_period` means "this particular consuming row has *at
   least one* applicable target version." Conditional, per-row,
   evaluated against real data. This is the newly-identified gap this
   contract investigates. **Architectural home: data quality
   (`quality.py`/`validate-data`), if built at all — not yet built.**

3. **Selection** — given that one or more applicable versions exist,
   "which one supplies the values for this row." Already solved.
   **Architectural home: transformation/join (`JoinSpec.on` +
   `pick_one_order_by`), already implemented.**

`domain membership → applicability → selection` maps cleanly onto
`constraint → data quality → transformation/join` — three genuinely
different questions, at three genuinely different points in
Structifact's existing architecture, not three variations on one
"foreign key" concept. This mapping is arguably the more durable
takeaway from this investigation than any specific recommendation
below: it clarifies that the *reason* a single `foreign_key` field
can't cover all of Reading B isn't an implementation gap in
`ConstraintSpec` — it's that Reading B was never one question.

**Important scoping note on layer 2, given layer 3 exists separately:**
an applicability check answers only "does at least one qualifying row
exist" — it does not, and should not be read to, certify that the
relationship is unambiguous. If a target table's effective periods
overlap (two versions both claiming to apply to the same date — see
"Explicitly Out of Scope" below), applicability would still report
success, correctly, while the actual row selected at generation time
depends entirely on `pick_one_order_by`'s ordering. An applicability
check passing is not a claim that selection is well-defined; it is
only a claim that selection has something to select from. Any future
naming or documentation for this check should make that boundary
explicit rather than implying "as-of referential integrity" covers
uniqueness too.

## What This Means for `ConstraintSpec.foreign_key`

**Recommendation: do not extend `ConstraintSpec.foreign_key` to
understand temporal/range targets.** Reasoning:

- `foreign_key`'s entire contract — in the IR (`ir.py`), in
  `validation.py`'s `resolve_references()`, and in `quality.py`'s v3
  data-level check — is built around "one source column, one target
  column, target column is (or claims to be) uniquely keyed." Making it
  temporally aware would mean teaching `ConstraintSpec` to carry a second
  kind of raw-SQL-fragment condition (an effective-date range comparison
  against another column pair), duplicating what `JoinSpec.on` +
  `pick_one_order_by` already express at the join layer. That's two
  independent implementations of "find the applicable row," which will
  drift from each other over time — the same class of risk `DESIGN_
  PRINCIPLES.md`'s "Explicit over Magic" and "one mechanism per concern"
  precedent (see `AggregateRule`'s single-mechanism-covers-two-shapes
  resolution) argues against.
- A `foreign_key` that silently became conditional would also be a
  meaningful semantic regression for every *other*, ordinary FK already
  in the IR: today, "target_column must be a real declared field" and
  "the referenced schema's own name matches" are the only preconditions
  (`quality.py`'s `resolve_references()` docstring). Adding a second,
  fundamentally different evaluation mode to the same field risks
  `foreign_key` meaning two different things depending on whether the
  target table happens to be versioned — implicit, not explicit.

**What already answers Reading A, today, with no new capability:** a
plain `foreign_key` against a target table that has *at least one* row
per possible category value is already sufficient to validate domain
membership, if such a table exists. `expense_policy` here doesn't
cleanly separate "the list of valid categories" from "the versioned cap
rows" — but a real system this shape recurs in typically would (a
`category_master`/dimension table, separate from the effective-dated
fact/reference table). Whether that separation is worth introducing is
a modeling decision for the dataset's author, not something Structifact
needs new IR to support — it's already expressible with today's
`sources`/`foreign_key`.

**What answers Reading B: nothing today, and it doesn't belong in
`ConstraintSpec` at all — see next section.**

## Where Reading B Actually Belongs

Reading B — "does an applicable row exist as of this row's own date" —
is not a schema-shape question. It's a question about real data:
*given the actual rows in both datasets, does every consuming row
resolve to at least one applicable target row?* That is exactly the
kind of question `structifact/quality.py` already exists to answer,
and exactly the kind `validation.py` deliberately does not — the same
metadata-vs-data boundary this project has held consistently (Phase 6's
`quality.py` was split out from `validation.py` for precisely this
reason; see `DESIGN_PRINCIPLES.md` and `CURRENT_STATE.md`'s Validation
Framework section).

**Candidate direction: a new `validate-data`-level check, not a new
`ConstraintSpec` type.** Conceptually, an *applicability* check: for
each row of the consuming dataset, confirm at least one row of the
referenced dataset satisfies a condition combining an equality match
(the category) with a date-range condition (the consuming row's date
falling within the target row's effective period). The exact
expression shape above is illustrative of the *kind* of condition
involved, not a proposed API — see the Open Question on interval
semantics below for why even this illustrative form shouldn't be taken
as settled. Whatever form this eventually takes, it should sit
alongside `quality.py`'s existing v3 foreign-key check as a distinct,
separately-opted-into rule — not a modification to the existing one,
since existing plain FKs must keep behaving exactly as they do today
(see Backward Compatibility below). This document does not commit to
`--ref` or any specific parameter shape as the mechanism — see
Recommendation.

This framing also cleanly separates two questions this design pass
originally risked conflating: **existence** (does at least one
applicable row exist at all — this section's concern) versus
**selection** (given that one or more exist, which one wins — already
solved, for generation purposes, by `pick_one_order_by`). A dataset
could have `pick_one_order_by`-based *generation* working correctly
(it always resolves to some row, or `NULL` for a `left` join) while
still having *real data* where a given expense line's date falls in a
genuine gap between policy versions — generation wouldn't reveal that
gap (a `left` join with zero qualifying rows just yields `NULL`
silently), but a validate-data-level existence check would. That is a
real, distinct value proposition for this check, not a redundant
restatement of what `pick_one_order_by` already guarantees.

## Open Question: Interval Semantics

This document deliberately does not resolve what "applicable as of a
date" precisely means at the boundaries, and flags this as a genuine
open question for whenever (if ever) implementation is scoped, rather
than silently assuming an answer:

- **Inclusive or exclusive bounds?** Is the interval
  `effective_start_date <= date AND effective_end_date >= date`
  (both bounds inclusive), or `effective_start_date <= date AND date 
  effective_end_date` (end exclusive, the more common convention for
  adjacent, non-overlapping periods, since it lets one period's
  `effective_end_date` equal the next period's `effective_start_date`
  without ambiguity)? `expense_policy`'s own Stage 3 data used
  `effective_start_date`/`effective_end_date` with the earlier period's
  `effective_end_date` set to the day *before* the later period's
  `effective_start_date` (2026-06-30 / 2026-07-01) — a convention that
  happens to work under either inclusive-inclusive or the
  end-exclusive reading, which means this one example cannot settle
  the question.
- **What does a `NULL` `effective_end_date` mean?** Presumably "still
  in effect, no known end" — consistent with how `expense_policy`'s
  Stage 3 data used it — but this should be an explicit, documented
  convention, not an assumption baked silently into a comparison
  expression.
- **What does a `NULL` `effective_start_date` mean?** Not exercised by
  the Stage 3 example at all. Plausible readings include "always been
  in effect" or "not yet effective / invalid row" — genuinely
  ambiguous without a real example to ground the decision.
- **Column naming/shape is not assumed to generalize.**
  `effective_start_date`/`effective_end_date` are this example's own
  column names, not a proposed IR convention — a real second example
  might use a single `effective_date` with an implicit "until
  superseded" semantics instead of an explicit end column, which would
  change the shape of any future check's parameters substantially.

None of this needs resolving now — it's listed here specifically so
that if/when a second example motivates implementation, this question
gets a real, evidence-grounded answer rather than an implicit default
inherited from having only looked at one dataset.

## Interactions With Existing Systems

- **Validation (`validation.py`):** unaffected. This capability doesn't
  live here; ordinary `ConstraintSpec.foreign_key` well-formedness
  checks are untouched.
- **Uniqueness:** a related-but-distinct question surfaced by this
  investigation, deliberately out of scope for this contract (see
  below): nothing currently checks whether an effective-dated table's
  *own* rows have non-overlapping periods per key (e.g., two
  `Meals (international)` rows with overlapping effective windows,
  which would make Reading B ambiguous — more than one "applicable"
  row for some dates). This is a same-table temporal-uniqueness concern
  (sometimes called a period/exclusion constraint), not a
  cross-dataset reference concern, and doesn't require anything this
  contract proposes.
- **Joins / generated SQL:** unaffected. `JoinSpec.on` +
  `pick_one_order_by` already handle *generation-time* resolution
  correctly (confirmed: this is exactly the mechanism Arm B's Stage 3
  evaluator reused for the `expense_policy` join). This contract's
  candidate is a `validate-data`-time check on real rows, run
  independently of (and prior to, in a typical workflow) generation —
  it would not change anything about what SQL gets generated.
  A dataset author would likely want to run both: an applicability
  check to catch a genuine data gap before it matters, and
  `pick_one_order_by` to correctly resolve whichever rows do qualify.
- **Execution (`executors/`):** unaffected. This is a `validate-data`
  concern, evaluated against CSV rows before any DDL/execution step,
  the same boundary the existing v1/v2/v3 `quality.py` checks already
  respect.
- **`quality.py`'s existing v3 foreign-key check:** would need a new,
  separate function/check type alongside `check_foreign_keys()` — not a
  modification to it. The existing check's "existence/membership only"
  contract (a duplicate value on the target side is the target
  dataset's own uniqueness concern, not this check's) is explicitly
  preserved; an applicability check has an inherently different
  evaluation shape (two source columns compared against a range, not
  one column compared for membership) and should not be forced into
  the same function without its own scoping pass — including its own
  decision about whether it reuses `--ref` or needs a different
  mechanism entirely (see Recommendation).

## Backward Compatibility

Nothing in this contract proposes changing `ConstraintSpec.foreign_key`
itself, `validation.py`'s existing checks, or `quality.py`'s existing v3
foreign-key check. Every existing dataset with a plain, non-versioned
`foreign_key` constraint is entirely unaffected — this document
recommends *not* touching that code path at all, precisely because
doing so risked making its meaning conditional on the target table's
shape.

## Explicitly Out of Scope (for this contract)

- **Same-table temporal-uniqueness / period-overlap checking** on an
  effective-dated table's own rows (mentioned under Uniqueness above)
  — a real, valuable, but genuinely separate concern from cross-dataset
  referencing. Worth its own investigation if a real example surfaces
  a genuine overlap bug, not designed here to avoid scope creep.
- **Any change to `pick_one_order_by`, `JoinSpec`, `DedupRule`, or
  `AggregateRule`** — all confirmed working as designed; this
  investigation found no gap in generation-time resolution, only in
  static schema-level reference validation.
- **A general "temporal FK" IR primitive** usable outside `quality.py`
  (e.g. embedded in generated DDL, enforced by the database itself) —
  no real engine Structifact targets (DuckDB, PostgreSQL) has a
  first-class temporal-FK primitive to generate DDL for; this would be
  a Structifact-side-only check, matching how `quality.py`'s existing
  checks already work independently of what the target database can
  itself enforce.
- **Deciding whether `category_master`-style domain tables should
  become a documented pattern** for Reading A — noted as already
  expressible with existing IR, not designed further here.

## Tradeoffs Among the Candidates Considered

| Candidate | Verdict |
|---|---|
| Extend `ConstraintSpec.foreign_key` to accept a temporal/range target | **Rejected.** Duplicates `JoinSpec.on`/`pick_one_order_by`'s existing resolution logic in a second place; blurs what `foreign_key` means for every existing, ordinary FK. |
| A distinct "scoped uniqueness" / period constraint on the target table alone | Valuable, but answers a different question (does the *target* have ambiguous periods) than the one this contract investigates (does every *consuming* row have an applicable target row at all). Out of scope here, not rejected — worth its own future contract. |
| A "current record" view/abstraction | **Rejected as a general answer.** "Currently effective" is a moving target; the real requirement (an expense line's *own* date, which can be historical) needs "effective as of an arbitrary date," which a single "current" view can't express. |
| A new `validate-data`-level applicability check (this contract's architectural recommendation; mechanism/API deliberately unscoped) | Matches the existing `quality.py`/`validation.py` boundary exactly: this is a real-data existence question, not a schema-shape question. Composes cleanly with `pick_one_order_by` (applicability vs. selection) without touching it. |
| No new capability at all | A legitimate fallback if no second real example surfaces this need — see Recommendation below for why this document still argues for scoping it now rather than waiting. |

## Recommendation

**Architectural conclusion (settled by this document, not contingent
on further evidence):** `ConstraintSpec.foreign_key` should not be
extended to understand temporal/range targets. The applicability
question this contract investigates belongs at the data-quality layer
(`quality.py`/`validate-data`'s general territory), not the schema
layer — this follows from the domain-membership / applicability /
selection distinction above, which doesn't get more or less true with
additional examples.

**Implementation recommendation (contingent, deliberately unscoped):**
if a second, independently motivated real example confirms this need,
investigate an explicit data-quality mechanism for as-of referential
applicability at that point — determining its metadata representation
and CLI surface then, against that second example's actual shape, not
now. This document deliberately does not commit to `validate-data`'s
`--ref` mechanism, a specific new flag, or any particular parameter
shape (e.g., a second column pair) as the eventual implementation —
earlier language in this draft suggesting `--ref ... extended to accept
a second column pair` overstated what this investigation has actually
established, and is retracted here. The Open Question above (interval
semantics) is exactly the kind of thing a real second example should
settle before any API is chosen, not something this document should
guess at from one dataset.

This recommendation is made with one honest caveat: **this contract is
motivated by exactly one real example** (the Stage 3 `expense_policy`
finding). This project's own real-example-first discipline (see
`CURRENT_STATE.md`'s Development Philosophy, and how `AggregateRule`
and `source_filter` both waited for a second confirming example before
generalizing) argues for waiting on a second, independently-motivated
case before scoping implementation at all — not merely before finalizing
its parameter shape. The reason to write this contract now, rather than
waiting entirely, is that the *architectural* conclusion above (where
this capability would live, and why `foreign_key` is the wrong home)
doesn't depend on how many examples confirm the need — only the
decision to actually *build* something does.

**If a second real example never surfaces this need, the correct action
is to leave this as a design record and not build it** — a documented,
reasoned "no" is a legitimate and valuable outcome of a paper contract,
not a failure to ship something.
