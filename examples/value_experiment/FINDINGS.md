# Structifact Value Experiment — Findings

SYNTHETIC EXAMPLE (fictional company/data). Built to directly test the
open question from the prior workorder_demo/reconciliation_demo
diagnostic: does Structifact catch something a capable AI assistant
working alone, directly against the source schemas, would get wrong?

## Setup (for context — see individual files for full detail)

- **Business rule under test**: for each order, attribute the
  customer's status *as of the order's date* (most recent
  `customer_status_history` row with `effective_date <= order_date`),
  not the customer's current/most-recent status overall. This is a
  real, common bug class (a "current state applied retroactively"
  error), not a Structifact-specific construct — `REQUIREMENTS.md`
  describes it in plain business prose with no mention of Structifact
  or any IR vocabulary.
- **Data**: `customers.csv` (15), `customer_status_history.csv` (25
  rows, several customers with 2–3 status changes),
  `orders.csv` (39), `order_lines.csv` (59). Hand-authored, not
  randomized, so every row is traceable — see
  `generate_data_and_ground_truth.py`.
- **Ground truth**: computed independently in plain Python (no SQL,
  no Structifact) *before* either experiment arm ran — see
  `GROUND_TRUTH_DERIVATION.md`, `expected_result_per_order.csv`,
  `expected_result_summary.csv`. Of 39 orders, 11 have an as-of status
  that diverges from the customer's current status, and 1 (`O032`)
  predates the customer's earliest recorded status entirely (no
  determinable status — a deliberate edge case).
- **Isolation**: Experiment A and Experiment B were each run as a
  fresh subagent with no access to this findings file, the ground
  truth files, or each other's work — only `REQUIREMENTS.md` and the
  four raw CSVs. The ground-truth files did not exist in this
  directory until after both arms had finished.

## Part 4 — Comparison

### Did Experiment A's SQL produce the correct result?

**Yes — all 39 rows exactly correct**, verified by a programmatic diff
against `expected_result_per_order.csv` (status and revenue on every
row, zero mismatches). See `experiment_a_query.sql`,
`experiment_a_per_order.csv`, `experiment_a_summary.csv`. It used a
correlated scalar subquery (`ORDER BY effective_date DESC LIMIT 1`
filtered to `effective_date <= order_date`) — the standard as-of-date
join idiom — and correctly resolved `O032` to a NULL status rather
than guessing, per the requirements doc's explicit instruction not to
guess. Per `experiment_a_notes.md`, it was written in essentially one
pass with no logic errors or re-derivation.

### Did Experiment B's IR/generated SQL produce the correct result?

**Yes — all 39 rows exactly correct**, same diff, same result. See
`experiment_b_per_order.csv`, `experiment_b_summary.csv`,
`experiment_b_generated.sql`. It required three chained `DatasetSpec`
files rather than one (`order_status_and_revenue_candidates.yml` →
`order_status_resolved.yml` → `order_status_revenue_summary.yml`) —
see "Effort/friction" below for why.

**Both arms produced byte-identical per-order and summary output.**

### Did Structifact's validation step catch anything before execution?

**No.** `structifact validate` passed on all three YAML files on the
first try (`experiment_b_validate_output.txt`) — no schema errors, no
constraint violations, nothing flagged. Validation confirmed
structural well-formedness; it did not (and structurally could not)
check whether the *business logic* — the as-of join condition, the
dedup ordering — was correct. That determination only came from
executing the generated SQL against real data and comparing output,
same as Experiment A.

### Did reconciliation catch anything?

**No — it confirmed correctness, it didn't catch an error.**
Experiment B built a second, fully independent Python recomputation
of the same logic (no SQL, no Structifact) and ran `structifact
reconcile` against the Structifact-generated output:
`experiment_b_reconciliation_output.txt` shows 39/39 rows matched, 0
issues, exact aggregate agreement. This is a legitimate use of the
tool (an independent cross-check), but it's not evidence of
Structifact *catching* anything — both sides of that reconciliation
were already correct. This is the inverse of `reconciliation_demo`,
where reconciliation caught two real planted discrepancies. Here there
was nothing to catch.

### Effort/friction comparison

Asymmetric, and Structifact came out behind on this axis:

- **Experiment A**: one query, written in one pass, no debugging
  beyond a mechanical semicolon-splicing issue unrelated to the logic.
  `experiment_a_notes.md`'s own effort estimate: "an experienced
  analyst could write and test that directly against DuckDB... in
  well under 15 minutes."
- **Experiment B**: `validate`/`generate` were clean on the first try
  throughout — zero iteration cost there. But getting to a working
  design took meaningfully longer, entirely because of one concrete
  IR limitation: **`DedupRule`'s ranking CTE is built only from the
  joined-in source's own columns, before any join happens** — it has
  no visibility into the primary table, so it can express "customer's
  single latest status ever" but not "latest status as of *this
  order's* date" (confirmed by reading `model.py`'s `_source_cte`,
  documented in `experiment_b_notes.md`). This forced a two-stage
  split: stage 1 produces a full fan-out of every status candidate
  that qualifies as of the order date (via a raw non-equi `on:`
  condition), stage 2 collapses that fan-out with `DedupRule` after
  the join has already happened and materialized.
- Applying `DedupRule` to stage 2/3 with no *new* join required an
  **undocumented workaround**: setting `source_table:` equal to the
  sole declared `SourceRef.name` so `ModelGenerator`'s bare `FROM
  {primary}` resolves to that source's own CTE. It works and
  `validate` raises no objection, but per `experiment_b_notes.md`,
  "nothing in `ir.py`'s docstrings or `validate` present this as an
  intended, documented pattern... it reads more like exploiting an
  implementation detail than using a supported feature."
- **`structifact generate` with no flags hides the transformation
  entirely** — only `-g model` reads `sources`/`joins`/`DedupRule`.
  The default output (DDL + catalog CSV) shows no `SELECT` at all,
  which the agent flagged as something a first-time user could easily
  miss and wrongly conclude the join/dedup metadata "wasn't doing
  anything."
- **No cross-file orchestration**: nothing in Structifact chains the
  three-stage pipeline automatically; the agent hand-sequenced three
  `CREATE TABLE ... AS <generated SQL>` statements in DuckDB itself.
- Experiment B's own effort estimate (`experiment_b_notes.md`):
  hand-written SQL "would clearly have been faster" for this task; the
  time that went into the Structifact path was almost entirely
  understanding IR constraints and designing around them, not
  `validate`/`generate` iteration, which was clean throughout.

### Classification

**Outcome 3 — both right; Structifact adds nothing meaningful here —
is the closest fit, with a real negative signal on top: outcome 3 as
scored on correctness (both arms are byte-identical to ground truth
and to each other), but the effort/friction data leans toward outcome
4's territory** (Structifact introduced meaningful friction — a
multi-stage split plus an undocumented workaround — without producing
a better or safer answer than plain SQL). It does not fully qualify as
outcome 4 because nothing was *wrong*: validate and generate were both
clean on the first try, and the final output was correct. But the
premise being tested — that Structifact's structure would catch a
business-logic error an AI working alone would miss — did not hold:
neither arm made the classic "current status" mistake the requirements
doc explicitly warns about. Both got the as-of-date logic right
unprompted, on the first attempt, from the same plain-English
requirements doc.

## Honest bottom line

This experiment does not show Structifact adding value on the
dimension it was built to test. An AI assistant working directly
against the raw schemas produced a fully correct answer, faster, with
no metadata layer. Structifact's own reconciliation feature has
previously demonstrated real value catching *actual* discrepancies
(`reconciliation_demo`'s planted dropped row and changed amount) — but
that is a different capability (comparing two already-produced
datasets) from the one under test here (whether declaring the
transformation *in* Structifact produces a more correct or more
trustworthy transformation than writing it directly). On that
narrower question, this experiment's result is negative: same
correctness, more effort, and one concrete IR gap (`DedupRule` cannot
rank on a column from the join's other side) that required an
undocumented workaround to route around.

This is one example, not a general proof — a harder or more ambiguous
requirements document, a case where the "obvious" SQL approach really
does tempt the classic bug, or a case stressing reuse/governance
(multiple downstream datasets depending on one canonical `DatasetSpec`
via `depends_on`) could plausibly produce a different result. But this
specific, deliberately realistic test did not surface that value.

## Artifacts in this directory

- `REQUIREMENTS.md` — business-prose requirements (Part 1)
- `customers.csv`, `customer_status_history.csv`, `orders.csv`,
  `order_lines.csv` — raw data, seen by both arms
- `generate_data_and_ground_truth.py` — deterministic data generator
  and independent (plain-Python) ground-truth computation
- `expected_result_per_order.csv`, `expected_result_summary.csv`,
  `GROUND_TRUTH_DERIVATION.md` — ground truth, withheld from both arms
  until after both finished
- `experiment_a_query.sql`, `experiment_a_per_order.csv`,
  `experiment_a_summary.csv`, `experiment_a_notes.md` — Experiment A
  (Claude alone)
- `order_status_and_revenue_candidates.yml`,
  `order_status_resolved.yml`, `order_status_revenue_summary.yml`,
  `experiment_b_validate_output.txt`, `experiment_b_generated.sql`,
  `experiment_b_per_order.csv`, `experiment_b_summary.csv`,
  `experiment_b_reconciliation_*`, `experiment_b_notes.md` —
  Experiment B (Claude + Structifact)
