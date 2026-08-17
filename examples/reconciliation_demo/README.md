# reconciliation_demo

Synthetic (fictional) acceptance fixture for `structifact reconcile`
(v1). Represents the real-world shape this feature targets: an old
system's exported data (`orders_legacy.yml`/`.csv`, legacy column
naming) and a replacement system's export of the same logical dataset
(`orders_new.yml`/`.csv`, modern column naming), reconciled via an
explicit field mapping (`reconciliation.yml`) — legacy and modern
naming conventions are assumed never to match automatically.

Planted, deliberately:

* order `1004` exists only in `orders_legacy` (dropped in the
  migration — a `missing_in_new` row-coverage issue)
* order `1006` exists only in `orders_new` (a new record — a
  `missing_in_old` row-coverage issue)
* order `1005`'s amount changed from `60.00` (old) to `65.00` (new) —
  a genuine value discrepancy on an otherwise-matched row

Run it:

```bash
structifact reconcile \
  orders_legacy.yml:orders_legacy.csv \
  orders_new.yml:orders_new.csv \
  --mapping reconciliation.yml
```

Expected report:

```
✓ Loaded schemas: orders_legacy (old), orders_new (new)
✓ Loaded data: 5 old row(s), 5 new row(s)

Row counts:
  old: 5
  new: 5
  matched: 4

✗ 3 issue(s) found

Row matching:
  - missing_in_new: 1 row
      key=1004
  - missing_in_old: 1 row
      key=1006

Aggregate comparison (matched rows):
  - order_amount: old_sum=485.50  new_sum=490.50  diff=+5.00
```

Note the aggregate is computed over the **matched** population only
(orders `1001`, `1002`, `1003`, `1005` — the four keys present on
both sides), not the full old/new populations. Summing the full
populations would report a `-255.00` diff dominated by the dropped
and added rows (already reported, exactly, by row matching above) and
would bury the actual value discrepancy on `1005` inside that larger
number. Restricting the aggregate to matched rows isolates the
question "do the numbers agree for the records both systems agree
exist" — the diagnostically useful one.

v1 does **not** claim these two datasets are semantically equivalent.
It establishes row-population coverage, key correspondence, and
aggregate equivalence for declared measures on the matched
population — not that every individual field value is identical.
Full column-level comparison on matched rows (which would catch
`1005`'s discrepancy directly, by field, rather than only via the
aggregate) is a deliberately deferred v2 — see `docs/FUTURE_WORK.md`.
