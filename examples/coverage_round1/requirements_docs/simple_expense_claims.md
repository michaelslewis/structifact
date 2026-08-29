# Requirements: employee_expense_claims (SYNTHETIC EXAMPLE)

> This document is entirely fictional, written for a made-up
> company's internal expense system. No real company, schema, or
> business logic is represented here. Coverage/dogfooding material
> for Structifact's `discover --requirements --ai`, not implemented
> production logic.

## Background

Finance wants a flat report of employee expense claims: who
submitted what, when, and whether it's been approved. Each row is
one claim. There's no joining to another system needed here — every
claim already carries the employee's name and department directly on
the claim record.

## Fields

| Column | Description | Dim or Meas | Datatype |
|---|---|---|---|
| claim_id | Unique identifier for the expense claim | Dim | Varchar(12) |
| employee_id | Employee who submitted the claim | Dim | Varchar(10) |
| employee_name | Employee's full name | Dim | Varchar(80) |
| department | Employee's department at time of submission | Dim | Varchar(40) |
| category | Expense category: Travel, Meals, Supplies, or Other | Dim | Varchar(20) |
| expense_date | Date the expense was actually incurred | Dim | Date |
| submitted_date | Date the claim was submitted for approval | Dim | Date |
| approved_date | Date the claim was approved (blank if not yet approved) | Dim | Date |
| approved_flag | Y if approved, N if not yet approved or rejected | Dim | Varchar(1) |
| amount_usd | Claimed amount in USD | Meas | Decimal(10,2) |

## Business Rules

1. **Reimbursable amount**: if `approved_flag` = 'Y', the reimbursable
   amount is the full claimed `amount_usd`; otherwise it's 0 (nothing
   is reimbursed until approved).

2. **Days to approval**: for approved claims, the number of days
   between `submitted_date` and `approved_date`. Not meaningful for
   claims that aren't approved yet.

No other systems are involved — this is a single table, no lookups,
no joins.
