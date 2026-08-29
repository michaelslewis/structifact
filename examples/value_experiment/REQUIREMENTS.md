# Requirements: Order Revenue by Customer Status

## Background

We're trying to understand how much order revenue is coming from
customers in each lifecycle status (trial, active, at_risk, churned,
reactivated). This feeds a report the account management team uses to
decide who to reach out to.

We have four data files:

- `customers.csv` — one row per customer.
- `customer_status_history.csv` — customer lifecycle status changes
  over time. A customer can change status more than once (e.g. trial
  → active, or active → churned → reactivated). Each row has the
  status and the date it took effect.
- `orders.csv` — one row per order, with the customer who placed it
  and the date it was placed.
- `order_lines.csv` — one or more line items per order (SKU,
  quantity, unit price). An order's revenue is the sum of
  `quantity * unit_price` across its line items.

## What we need

For every order, attach the customer's status **as of the date the
order was placed** — not whatever the customer's status happens to be
today. A customer's status can change after an order was placed, and
we've been burned before by reports that quietly used "current
status" for everything, which retroactively reclassifies old revenue
under a status the customer didn't even have yet when they placed the
order. We want it done correctly this time: look at the order date,
and find whichever status was in effect on that date.

Concretely: if a customer was `trial` on January 1st, changed to
`active` on February 15th, and placed an order on January 20th, that
order should be counted under `trial`, even though the customer is
`active` today (or by the time anyone runs this report).

If somehow an order exists dated before the customer has *any*
recorded status yet, don't guess — that order simply has no
determinable status as of its date.

## Output needed

1. A row per order with its resolved customer status (as of the order
   date) and the order's revenue.
2. A summary: total revenue grouped by that resolved status.

That's it — this doesn't need to be fancy, we just need the status
attribution to actually be correct as of each order's date, not
today's status applied retroactively to old orders.
