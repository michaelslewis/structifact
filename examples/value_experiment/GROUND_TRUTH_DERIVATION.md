# Ground truth derivation notes
Computed entirely in plain Python (see generate.py) by, for each order, scanning that customer's status_history rows and picking the one with the latest effective_date <= the order's order_date. No SQL was written or run to produce this file.

Total orders: 39. Orders where as-of-date status differs from the customer's current/most-recent status: 11.

## Diverging orders (as-of status != current status)
- O004 (customer C02, dated 2024-12-01): as-of status = **trial**, but current status = **active**. Revenue $77.50 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O005 (customer C02, dated 2025-01-20): as-of status = **trial**, but current status = **active**. Revenue $142.00 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O008 (customer C03, dated 2024-12-15): as-of status = **trial**, but current status = **at_risk**. Revenue $113.50 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O009 (customer C03, dated 2025-02-01): as-of status = **active**, but current status = **at_risk**. Revenue $190.00 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O014 (customer C05, dated 2024-12-01): as-of status = **active**, but current status = **reactivated**. Revenue $107.50 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O015 (customer C05, dated 2025-03-15): as-of status = **churned**, but current status = **reactivated**. Revenue $182.00 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O022 (customer C08, dated 2024-11-10): as-of status = **active**, but current status = **at_risk**. Revenue $59.50 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O023 (customer C08, dated 2025-02-01): as-of status = **active**, but current status = **at_risk**. Revenue $118.00 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O029 (customer C11, dated 2024-11-15): as-of status = **trial**, but current status = **churned**. Revenue $110.00 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O030 (customer C11, dated 2025-01-05): as-of status = **active**, but current status = **churned**. Revenue $131.50 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.
- O032 (customer C12, dated 2024-05-01): as-of status = **UNKNOWN_NO_HISTORY_YET**, but current status = **trial**. Revenue $89.50 would be attributed to the wrong status bucket if 'current status' were used instead of 'status as of order date'.

## Edge case: order predates any status history
- O032 (customer C12, dated 2024-05-01): no status_history row has effective_date <= 2024-05-01 yet, so no status can be determined as of that date. Current status is 'trial', which would be WRONG to backfill onto this order.
