# Experiment A notes

## Approach

1. Computed per-order revenue first (`SUM(quantity * unit_price)` from
   `order_lines.csv`, grouped by `order_id`), joining to `orders.csv`
   for `customer_id` and `order_date`.
2. Resolved each order's customer status via a correlated scalar
   subquery against `customer_status_history.csv`: for a given order,
   take the status row for that `customer_id` with the latest
   `effective_date` that is `<= order_date`. If no such row exists,
   the subquery returns NULL.
3. Summary is a straight `GROUP BY resolved_status` with `SUM(revenue)`
   over the per-order result.

Used a correlated subquery (`ORDER BY effective_date DESC LIMIT 1`)
rather than a window function (e.g. `ROW_NUMBER() OVER (PARTITION BY
customer_id ORDER BY effective_date DESC)`) mainly for readability —
both approaches are equivalent here since it's a single scalar lookup
per order. Ran the whole thing with DuckDB directly against the CSVs
via `read_csv_auto()`, no intermediate tables.

## Assumptions

- "Status as of the order date" is inclusive of the effective date
  itself (`effective_date <= order_date`), i.e., a status change that
  takes effect the same day an order is placed applies to that order.
  The requirements doc's own worked example (order before the
  Feb 15 change stays under the pre-change status) doesn't test the
  same-day boundary directly, but "as of" read most naturally as
  inclusive.
- Per the requirements doc's explicit instruction, an order dated
  before a customer's earliest recorded status has no determinable
  status — resolved to NULL/blank rather than guessing (e.g.
  guessing "trial" as a default for a new customer). This is not
  hypothetical in the sample data: order `O032` (customer C12,
  order_date 2024-05-01) predates C12's earliest history row
  (2024-06-01, trial), and correctly comes out as NULL status in the
  per-order output and its own (blank-status) row in the summary.
- `customers.csv` (customer_name, signup_date) wasn't needed for
  either output and wasn't joined in — the requirements only ask for
  order, resolved status, and revenue.
- Revenue is per-order in the per-order output (not per-line), matching
  "each order's revenue" in the requirements.
- No currency/rounding handling was applied beyond whatever DuckDB's
  default float arithmetic and CSV export produce.

## Effort

Wrote the query in essentially one pass — the correlated-subquery
"latest effective_date <= order_date" pattern is the standard
as-of-date join idiom and didn't need debugging. The only hiccup was
mechanical: my first attempt at the separate summary query failed
with a trailing-semicolon parser error when wrapping the per-order
query as a subquery in Python (fixed by stripping the semicolon before
splicing it into the `GROUP BY` query). No logic errors or re-derivation
needed. Spot-checked a few rows by hand against
`customer_status_history.csv` (C08's Nov 2024 order resolving to
`active`, not `at_risk`, since the at_risk change is dated March 2025;
C05's three orders spanning active/churned/reactivated) and they
matched expectations.
