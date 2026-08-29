# Requirements: claim_ledger_summary (SYNTHETIC EXAMPLE)

> This document is entirely fictional, written to deliberately stress
> several patterns Structifact has previously found tricky, in one
> document, for a made-up insurance company. No real company, schema,
> or business logic is represented here. Coverage/dogfooding material
> for `discover --requirements --ai`, not implemented production
> logic.

---

## Section 1: Tables & Joins

| Table | Description | Join Info |
|---|---|---|
| CLAIM_HDR | Claim Header | (primary) |
| PARTY_ROLE | Contact per claim per role | 1, 2, 3 |
| POLICY_STATUS_HISTORY | Policy status changes over time | 4 |
| CLAIM_PAYMENT | Individual payments made against a claim | 5 |

**Join key list:**
1. `claim_hdr.claim_id = party_role.claim_id and party_role.role_code = 'CLAIMANT'`
2. `claim_hdr.claim_id = party_role.claim_id and party_role.role_code = 'ADJUSTER'`
3. `claim_hdr.claim_id = party_role.claim_id and party_role.role_code = 'BENEFICIARY'`
4. `claim_hdr.policy_id = policy_status_history.policy_id`, resolved
   to whichever status was in effect as of the claim's own date (see
   Section 3).
5. `claim_hdr.claim_id = claim_payment.claim_id`, aggregated to one
   total per claim before joining (see Section 3).

---

## Section 2: Field Grids Per Table

### CLAIM_HDR

| Column | Desc (name) | Dim or Meas | Datatype | Length | Logic |
|---|---|---|---|---|---|
| claim_id | Claim ID | Dim | Varchar | 12 | |
| policy_id | Policy ID | Dim | Varchar | 12 | |
| claim_date | Date the claim was filed | Dim | Date | | |
| claim_type | Claim Type (Auto/Property/Liability) | Dim | Varchar | 20 | |
| status_code | Claim Status Code | Dim | Varchar | 4 | |
| claim_amount | Claim Amount (as filed) | Meas | Decimal | 12,2 | |
| total_paid_amount | Total Paid To Date | Meas | Decimal | 12,2 | sum of all CLAIM_PAYMENT rows for this claim |
| net_exposure | Net Exposure Remaining | Meas | Decimal | 12,2 | claim_amount - total_paid_amount |

### PARTY_ROLE (joined three times — see Section 3)

| Column | Desc (name) | Dim or Meas | Datatype | Length | Logic |
|---|---|---|---|---|---|
| claimant_name | Claimant Name | Dim | Varchar | 80 | |
| adjuster_name | Assigned Adjuster Name | Dim | Varchar | 80 | |
| adjuster_email | Assigned Adjuster Email | Dim | Varchar | 100 | |
| beneficiary_name | Beneficiary Name (if applicable) | Dim | Varchar | 80 | |

### POLICY_STATUS_HISTORY

| Column | Desc (name) | Dim or Meas | Datatype | Length | Logic |
|---|---|---|---|---|---|
| policy_status_as_of_claim | Policy Status As Of The Claim Date | Dim | Varchar | 20 | most recent POLICY_STATUS_HISTORY row where effective_date <= claim_date |

---

## Section 3: Miscellaneous Notes (scattered freeform text on the page)

> PARTY_ROLE must be joined three separate times — once per role
> (CLAIMANT, ADJUSTER, BENEFICIARY) — using the same table with a
> different role_code filter each time, the same pattern as a
> requester/biller/site-contact table where one physical table
> carries several logical parties.

> A claim can have more than one contact recorded under the same
> role over time (e.g. an adjuster reassignment). For each role, only
> the CURRENT contact should be used: pick the row with is_current =
> 'Y' if one exists; if none is flagged current, fall back to the
> most recently updated row (highest updated_at). This is a
> priority/tiebreak rule, not a plain uniqueness join.

> `policy_status_as_of_claim` must reflect the policy's status ON THE
> CLAIM'S OWN DATE, not the policy's current status today. A policy
> can change status (active, lapsed, cancelled, reinstated) after a
> claim was already filed against it — using today's status would
> retroactively misclassify old claims. Look up the
> POLICY_STATUS_HISTORY row for that policy_id with the latest
> effective_date that is on or before claim_date.

> `total_paid_amount` is the SUM of every CLAIM_PAYMENT row's
> payment_amount for that claim_id — payments accumulate over time as
> a claim gets processed, sometimes across many small disbursements.
> This must be aggregated to one total per claim BEFORE joining back
> to CLAIM_HDR — CLAIM_HDR must stay one row per claim, never
> duplicated by however many payment rows exist underneath it.

> `net_exposure` depends on `total_paid_amount` above, so it can only
> be computed after that aggregation resolves.
