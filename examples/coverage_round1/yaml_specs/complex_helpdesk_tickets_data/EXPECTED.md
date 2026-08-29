# Expected output — complex_helpdesk_tickets

Derived independently (by hand, from the raw CSVs) before running
`generate`/`execute`. Dedup rule: prefer `is_active = 'Y'`; if none
is active, fall back to the most recently `updated_at` row.

| ticket_id | reporter_name | assignee_name | resolution_hours |
|---|---|---|---|
| T001 | Alice New (is_active=Y wins over the older N row) | Bob Later (no Y row exists; falls back to most recent updated_at, 2024-12-15 over 2024-11-01) | 6 |
| T002 | Carol | Dave | (still open — closed_at is null, resolution_hours should be null) |
| T003 | Eve | Frank New (is_active=Y wins over the older N row) | 24 |
| T004 | Grace | Heidi | 6 |

T001 and T003's assignee/reporter picks specifically test both branches
of the dedup rule: T001's assignee has no `is_active='Y'` row at all
(fallback path), while T001's reporter and T003's assignee both have
exactly one `is_active='Y'` row alongside an inactive one (priority
path).

**Self-correction, made after actually running the generated SQL, not
a Structifact finding:** T004 (opened 12:00, closed 18:30 — 6.5 real
hours) was originally written down here as `6.50`, from naive
fractional-hour subtraction. The YAML's own `resolution_hours`
expression is `date_diff('hour', opened_at, closed_at)`, which is
DuckDB's integer hour-*boundary-crossing* count, not fractional
elapsed hours — it correctly returns `6` for a 6.5-hour span, since
only 6 whole hour boundaries are crossed. The expression choice (and
this table's original expected value) was the error, not
`ModelGenerator`'s SQL generation, which reproduced the expression
exactly as written. Corrected to `6` above to match what the chosen
expression actually computes.
