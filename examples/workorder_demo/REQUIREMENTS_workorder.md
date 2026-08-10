# Requirements: work_order_source (SYNTHETIC EXAMPLE)

> This document is entirely fictional, written to match the *shape*
> of the more complex real-world requirements sheet described in
> conversation (multi-role partner joins, priority-based
> deduplication), for a made-up field-service company. No real
> company, schema, or business logic is represented here. Scoping
> material for Structifact, not an implemented feature.

---

## Section 1: Tables & Joins

| Table | Description | Join Info |
|---|---|---|
| WO_HDR | Work Order Header | 1, 2, 3 |
| WO_LINE | Work Order Line (labor/parts) | 1, 4 |
| CUST_MST | Customer Master | 2 |
| PARTNER_ROLE | Contact per work order per role | 3, 5, 6, 7 |
| PRICE_COND | Pricing condition (labor rate) | 4 |
| fx_rate_lookup | (existing intermediate model) | 8 |

**Join key list:**
1. `wo_hdr.wo_id = wo_line.wo_id`
2. `wo_hdr.customer_id = cust_mst.customer_id`
3. `wo_hdr.wo_id = partner_role.wo_id and partner_role.role_code = 'REQ'`
4. `wo_line.rate_code = price_cond.rate_code`
5. `wo_hdr.wo_id = partner_role.wo_id and partner_role.role_code = 'BILL'`
6. `wo_hdr.wo_id = partner_role.wo_id and partner_role.role_code = 'SITE'`
7. Same PARTNER_ROLE table joined three separate times (once per role
   above) — a customer can have multiple contacts recorded under the
   same role over time, only the current one should be used (see
   dedup note in Section 3).
8. `wo_hdr.currency_code = fx_rate_lookup.currency_code and wo_hdr.wo_date = fx_rate_lookup.rate_date`

---

## Section 2: Field Grids Per Table

### WO_HDR

| Column | Desc (name) | Folder | Dim or Meas | Datatype | Length | Logic |
|---|---|---|---|---|---|---|
| src_wo_hdr_wo_id | Work Order ID | Work Order | Dim | Varchar | 12 | |
| src_wo_hdr_wo_date | Work Order Date | Work Order | Dim | Date | | |
| src_wo_hdr_currency_code | Currency Code | Work Order | Dim | Varchar | 3 | |
| src_wo_hdr_wo_type | Work Order Type | Work Order | Dim | Varchar | 4 | |
| src_wo_hdr_status_code | Status Code | Work Order | Dim | Varchar | 2 | |
| sign_adjustment | Sign Adjustment | Work Order | Meas | Integer | | if src_wo_hdr_wo_type in ('CRM','RET') then -1 else 1 |

### WO_LINE

| Column | Desc (name) | Folder | Dim or Meas | Datatype | Length | Logic |
|---|---|---|---|---|---|---|
| src_wo_line_line_id | Line ID | Work Order Line | Dim | Varchar | 6 | |
| src_wo_line_labor_hours | Labor Hours | Work Order Line | Meas | Decimal | 7,2 | |
| src_wo_line_rate_code | Rate Code | Work Order Line | Dim | Varchar | 4 | |
| src_price_cond_labor_rate | Labor Rate | Work Order Line | Meas | Decimal | 9,2 | |
| labor_amount_lc | Labor Amount (LC) | Amounts | Meas | Decimal | 15,2 | src_wo_line_labor_hours * src_price_cond_labor_rate * sign_adjustment |
| labor_amount_usd | Labor Amount (USD) | Amounts | Meas | Decimal | 15,2 | labor_amount_lc * resolved_fx_rate |

### CUST_MST

| Column | Desc (name) | Folder | Dim or Meas | Datatype | Length | Logic |
|---|---|---|---|---|---|---|
| src_cust_mst_customer_name | Customer Name | Customer | Dim | Varchar | 60 | |
| src_cust_mst_region_code | Region Code | Customer | Dim | Varchar | 4 | |

### PARTNER_ROLE (joined three times — see Section 3)

| Column | Desc (name) | Folder | Dim or Meas | Datatype | Length | Logic |
|---|---|---|---|---|---|---|
| src_partner_requested_by_name | Requested By (Name) | Contacts | Dim | Varchar | 60 | |
| src_partner_billed_to_name | Billed To (Name) | Contacts | Dim | Varchar | 60 | |
| src_partner_site_contact_name | Site Contact (Name) | Contacts | Dim | Varchar | 60 | |
| src_partner_site_contact_phone | Site Contact (Phone) | Contacts | Dim | Varchar | 20 | |

---

## Section 3: Miscellaneous Notes (scattered freeform text on the page)

> PARTNER_ROLE must be joined three separate times — once per role
> (REQ = requested by, BILL = billed to, SITE = site contact) — using
> the same table with a different role_code filter each time, the
> same pattern as a real partner-role table with shipped-to/sold-to/
> payer/etc.

> A customer can have more than one contact recorded under the same
> role over time (e.g. a site contact who changed). For each role,
> only the CURRENT contact should be used: pick the row with
> is_current = 'Y' if one exists; if none is flagged current, fall
> back to the most recently updated row (highest updated_at). This is
> a priority/tiebreak rule, not a plain uniqueness join.

> Must use a lookup model for FX conversion, same shape as before:
> join fx_rate_lookup on currency_code and wo_date. If no rate is
> found and currency is USD, treat the rate as 1.0; otherwise leave
> the converted amount null.

> Row `src_wo_hdr_status_code` is highlighted grey in the original
> sheet — deprioritize, not needed for v1.
