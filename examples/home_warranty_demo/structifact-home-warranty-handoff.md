# Structifact Flagship Example — Implementation Handoff
## "Home Warranty Claims Coverage & Reimbursement"

**Status:** Scenario design is complete and reviewed. This document is the
implementation contract. Do not reopen candidate selection or scenario
design — that phase is done.

**Before writing any spec file:** reconcile Section 7's proposed YAML
against the actual current Structifact implementation and
`docs/EXAMPLES.md`/`docs/ARCHITECTURE.md` (current-state, not this
document, is authoritative on syntax). If real syntax, field names, or
capabilities differ from what's proposed here, adapt the example to the
engine as it actually exists and **report the discrepancy** rather than
silently proceeding. See Section 12 for specific open questions to
resolve during reconciliation.

---

## 1. Scenario Definition

A home warranty company needs to determine, per service claim, whether
it's covered, what the reimbursement amount is, and why — driven by
plan-tier coverage rules, a pre-existing-condition exclusion window, and
network-vs-non-network contractor status. The raw data comes from three
independently-maintained sources (registrar/contracts, claims intake,
underwriting's coverage rules, plus a contractor roster) that were never
designed to work together, plus an unstructured business memo describing
rules that aren't fully specified.

**What this example is intended to demonstrate:** the homepage's
"however you already describe your data" claim — that a messy,
heterogeneous, ambiguous real-world business handoff can become an
explicit, validated Structifact metadata contract, from which
correct, reproducible artifacts (SQL, docs, catalog, ERD) are
generated — such that a reader could reconstruct every important
business decision from the metadata alone, without needing to read the
generated SQL.

This is deliberately compact: 4 source files, 8 sample claims, one
composite join, four business-rule ambiguities, four categories of
input messiness. It is not meant to simulate a real claims-adjudication
system.

---

## 2. Raw Input Files (exact contents)

### `contracts.csv`

Header uses `start_date`, not `effective_date` — deliberate naming drift
from the registrar's own export convention (Mess #1, see Section 5).
Includes a duplicate/corrected entry for `C-1001` (Mess #2).

```csv
contract_id,homeowner_name,plan_tier,start_date,record_entered_date
C-1001,J. Alvarez,Standard,2025-03-10,2025-03-05
C-1001,J. Alvarez,Standard,2025-03-01,2025-03-12
C-1002,R. Chen,Basic,2024-11-01,2024-11-01
C-1003,M. Osei,Premium,2025-01-10,2025-01-10
C-1004,S. Patel,Standard,2025-05-01,2025-05-01
```

`record_entered_date` is the row's data-entry timestamp — distinct from
`start_date`, the contract's actual effective date. The first `C-1001`
row (`start_date: 2025-03-10`) was a data-entry error, corrected by a
second row (`start_date: 2025-03-01`) entered a week later. Both rows
have the same `plan_tier` — this is unambiguously a duplicate/
current-state-record problem, not a legitimate contract-version history.
The correct row is identifiable by **which was entered more recently**
(`record_entered_date`), not by which `start_date` value is larger —
ordering by `start_date` itself would incorrectly select the erroneous
row, since 2025-03-10 > 2025-03-01.

### `claims.csv`

Includes deliberately drifting date formats (Mess #3) and one claim with
a blank required field (Mess #5, `CL-07`). Includes one claim
(`CL-08`) specifically to exercise the "explicit `covered=FALSE`" path
distinct from "no matching coverage rule."

```csv
claim_id,contract_id,item_category,contractor_id,claim_amount,claim_date
CL-01,C-1001,HVAC,K-200,850.00,2025-04-12
CL-02,C-1002,Electrical,K-201,300.00,06/20/2025
CL-03,C-1003,Water Heater,K-202,1200.00,2025-03-15
CL-04,C-1004,Plumbing,K-203,450.00,08/10/2025
CL-05,C-1001,Appliance,K-204,220.00,2025-05-01
CL-06,C-1002,HVAC,K-201,900.00,07/02/2025
CL-07,C-1004,Plumbing,,500.00,2025-08-25
CL-08,C-1002,Plumbing,K-203,150.00,2025-07-10
```

`CL-07`'s `contractor_id` is deliberately blank — a real intake gap
(claim logged before all fields were known), not a formatting error.

### `coverage_rules.csv`

Deliberately sparse — not every `plan_tier` × `item_category` pair has a
row. Uses `WtrHtr` for the water-heater category, inconsistent with
`claims.csv`'s `Water Heater` (Mess #4 — category vocabulary drift; see
the numbering table in Section 5).
Includes both a genuinely-missing pair (`Basic`/`Electrical`, no row at
all) and an explicit exclusion (`Basic`/`Plumbing`, `covered=FALSE`) —
same business outcome, different data shape, both must be handled
distinctly in the spec (Ambiguity A4).

```csv
plan_tier,item_category,covered,copay_amount,coverage_cap
Standard,HVAC,TRUE,75,1000
Standard,Plumbing,TRUE,50,800
Standard,Appliance,TRUE,,500
Basic,HVAC,TRUE,100,600
Premium,HVAC,TRUE,50,
Premium,WtrHtr,TRUE,50,1500
Basic,Plumbing,FALSE,,
```

Blank `copay_amount` on `Standard`/`Appliance` means $0 copay (not "no
rule" — that distinction is carried by `covered`, not by this column).
Blank `coverage_cap` on `Premium`/`HVAC` means uncapped, not $0.

### `contractor_network.csv`

```csv
contractor_id,network_status
K-200,In-Network
K-201,Non-Network
K-202,In-Network
K-203,Non-Network
K-204,In-Network
```

---

## 3. Business Memo (as the fictional business user would actually provide it)

> Subject: Claims coverage rules
>
> Standard rule: no coverage for anything filed within 30 days of the
> contract start — that's our pre-existing-condition window, no
> exceptions for tier. If there's no coverage rule on file for a
> tier/category combo, it's not covered — don't guess. Copay comes off
> the claim before we apply the cap. Cap is cap — we never pay more
> than that, no matter what. If a contractor isn't in our network, we
> only reimburse 80% of whatever we'd otherwise owe. And obviously
> we're never paying out more than the claim amount itself.

This is the complete, unedited business input. It does not specify: the
order of operations between the coverage cap and the network multiplier;
whether "within 30 days" includes day 30 itself; what a blank copay or
cap cell means; or how a data-entry duplicate should be resolved. These
are the genuine ambiguities (Section 6) — the memo saying "cap is cap"
establishes that a cap exists and must be respected, but does not by
itself determine whether it's applied before or after the network
reduction. The metadata's job is to record which interpretation was
chosen, not to claim the source data determined a unique answer.

---

## 4. Transformation Model

**Grain:** one output row per claim (`claims` is the fact table).

**Relationships:**
```
claims.contract_id      -> contracts.contract_id            (many-to-one, after dedup)
claims.contractor_id    -> contractor_network.contractor_id (many-to-one)
(contracts.plan_tier, normalized(claims.item_category))
                         -> coverage_rules.(plan_tier, item_category)  (composite, LEFT — may not match)
```

The `coverage_rules` join is against `contracts.plan_tier`, a column
that only exists after the `contracts` join resolves — a real,
non-contrived multi-hop join dependency. It also joins against a
*normalized* version of `claims.item_category`, not the raw column
(see Mess #4 / Section 5).

`contracts` must be deduplicated to one row per `contract_id` (via
`DedupRule`, `partition_by: [contract_id]`, `order_by: [record_entered_date desc]`)
**before** the `claims` join — the whole point of this dedup case is
that it's an ordinary, single-source, non-cross-join dedup, deliberately
distinct from the parked DedupRule cross-join investigation.

---

## 5. Intentional Messiness → Existing Capability Mapping

| # | Mess | Where it appears | Resolves via | New capability needed? |
|---|---|---|---|---|
| 1 | Column header drift (`start_date` vs. target field `effective_date`) | `contracts.csv` | `FieldSpec.source_column` | No |
| 2 | Duplicate/corrected contract row, same `plan_tier`, resolved by entry recency not effective date | `contracts.csv` (`C-1001`) | Plain `DedupRule` (single-source, not cross-join) | No |
| 3 | Mixed date formats (`2025-04-12` vs. `06/20/2025`) | `claims.csv` | Structifact's existing date-type parsing — **verify exact behavior during reconciliation (Section 12)** | To be confirmed |
| 4 | Categorical vocabulary drift (`Water Heater` vs. `WtrHtr`) with a real functional consequence — it must resolve correctly or the composite join silently fails to match | `claims.csv` vs. `coverage_rules.csv` | A small, finite, explicitly-enumerated `CASE WHEN` normalization in a computed field — **not** fuzzy/similarity matching (deliberately distinct from Candidate B's parked fuzzy-matching gap; the category set is small and closed) | No |
| 5 | Missing required field (`contractor_id` blank on `CL-07`) | `claims.csv` | `structifact validate-data`'s `required` rule | No |

None of these require UNION, fuzzy/probabilistic matching, or the
parked DedupRule cross-join capability.

---

## 6. Business Ambiguities: Resolution and Metadata Visibility

**A1 — Coverage cap vs. network multiplier order of operations.**
`MIN(cap, amount)  0.8` and `MIN(cap, amount  0.8)` diverge whenever the
cap actually binds. The memo doesn't say.
**Resolution (declared, not inferred):** the cap applies first, the
network multiplier second — the cap represents the plan's maximum
covered amount; network status then determines what fraction of that
covered amount gets paid.
**Must remain visible as:** a field-level description on
`reimbursement_amount` stating the order and the reasoning, not just
implied by the expression's SQL structure (the expression's raw
`LEAST(..., cap) * multiplier` shape does not self-explain this
decision to a reader).

**A2 — Blank `copay_amount` vs. blank `coverage_cap` semantics.**
The same blank cell means two different things depending on which
column it's in: blank copay = $0 (there's a coverage rule, it just
doesn't charge a copay); blank cap = uncapped.
**Resolution:** `COALESCE(copay_amount, 0)` for copay;
`COALESCE(coverage_cap, claim_amount)` for cap (a no-op ceiling).
**Must remain visible as:** a description on each computed field
stating what a blank means for that specific column — this cannot be
inferred from the expression alone.

**A3 — "Within 30 days" boundary inclusivity.**
Does day 30 itself count as pre-existing, or only days 1–29?
**Resolution:** inclusive — `claim_date <= effective_date + 30 days` is
excluded.
**Must remain visible as:** stated explicitly in the
`is_pre_existing_exclusion` field description.

**A4 — Missing coverage-rule row vs. explicit `covered = FALSE` row.**
Both mean "not covered," but they're different data shapes and
different underlying causes (no rule was ever written, vs. a rule
explicitly excludes this combination). `CL-02` (Basic/Electrical, no
row) and `CL-08` (Basic/Plumbing, explicit `FALSE`) each exercise one
path.
**Resolution:** both treated as `is_covered = false`, via a null-check
on the missing-row case and a direct boolean check on the explicit-row
case — kept as two distinguishable conditions in the expression rather
than collapsed into one, specifically so the metadata shows both were
deliberately considered.
**Must remain visible as:** the `is_covered` field description
explicitly naming both paths and why they're treated identically.

---

## 7. Proposed YAML Metadata (design target — reconcile against real syntax before implementing)

```yaml
dataset:
  name: home_warranty_claims
  description: >
    Per-claim coverage determination and reimbursement, joining claim
    records against contract, coverage-rule, and contractor-network
    reference data. A missing coverage_rules match and an explicit
    covered=false row both mean "not covered" — treated as
    distinguishable causes with the same business outcome (see
    is_covered below).

sources:
  - name: contracts
    table: contracts
    dedup:
      partition_by: [contract_id]
      order_by: [record_entered_date desc]
  - name: claims
    table: claims
  - name: coverage_rules
    table: coverage_rules
  - name: contractor_network
    table: contractor_network

joins:
  - source: contracts
    on: "contracts.contract_id = claims.contract_id"
    type: left
  - source: coverage_rules
    on: >
      coverage_rules.plan_tier = contracts.plan_tier
      AND coverage_rules.item_category = normalized_item_category
    type: left
  - source: contractor_network
    on: "contractor_network.contractor_id = claims.contractor_id"
    type: left

fields:
  - name: claim_id
    type: string
    source: claims

  - name: contractor_id
    type: string
    source: claims
    nullable: false

  - name: plan_tier
    type: string
    source: contracts

  - name: effective_date
    type: date
    source: contracts
    source_column: start_date
    description: >
      Mapped from the source system's own column name (start_date) —
      registrar's export was never renamed to match this schema.

  - name: normalized_item_category
    type: string
    computed: true
    expression: >
      CASE WHEN claims.item_category = 'Water Heater' THEN 'WtrHtr'
      ELSE claims.item_category END
    description: >
      claims.csv and coverage_rules.csv use different spellings for
      the same category (Water Heater vs. WtrHtr). This is a small,
      finite, explicitly-enumerated mapping — not similarity/fuzzy
      matching — since the category vocabulary is closed and known.
      Required for the coverage_rules join to match correctly.

  - name: is_pre_existing_exclusion
    type: boolean
    computed: true
    expression: "claims.claim_date <= contracts.effective_date + INTERVAL '30 days'"
    description: >
      True if filed within 30 days (inclusive of day 30) of the
      contract's effective date. Absolute exclusion regardless of
      plan tier or category, per company policy.

  - name: is_covered
    type: boolean
    computed: true
    depends_on: [is_pre_existing_exclusion]
    expression: >
      NOT is_pre_existing_exclusion
      AND coverage_rules.covered IS NOT NULL
      AND coverage_rules.covered = TRUE
    description: >
      False if the pre-existing exclusion applies. Also false if no
      coverage_rules row matched this tier/category at all
      (coverage_rules.covered IS NULL — no rule was ever written), or
      if the matched row explicitly states covered=false (a rule was
      written that excludes this combination). Both cases are
      deliberately treated identically in outcome, despite being
      different underlying situations.

  - name: effective_copay
    type: decimal
    computed: true
    expression: "COALESCE(coverage_rules.copay_amount, 0)"
    description: >
      A blank copay_amount on a covered row means $0 copay, not "no
      rule" — that distinction is carried entirely by is_covered, not
      by this field.

  - name: reimbursement_amount
    type: decimal
    computed: true
    depends_on: [is_covered, effective_copay]
    expression: >
      CASE WHEN NOT is_covered THEN 0
      ELSE LEAST(
        GREATEST(claims.claim_amount - effective_copay, 0),
        COALESCE(coverage_rules.coverage_cap, claims.claim_amount)
      ) * CASE WHEN contractor_network.network_status = 'In-Network'
               THEN 1.0 ELSE 0.8 END
      END
    description: >
      The coverage cap is applied BEFORE the non-network 80%
      multiplier, not after — the cap represents the plan's maximum
      covered amount; network status then determines what fraction of
      that covered amount is actually paid. This ordering is a
      deliberate resolution of an ambiguity the source business memo
      did not specify (see project design notes) — the alternative
      ordering (multiplier first, then cap) produces different
      results whenever the cap actually binds. A blank coverage_cap
      means uncapped (COALESCE falls back to the claim amount itself
      as a no-op ceiling). Floored at zero via GREATEST() on the
      copay subtraction.

constraints:
  - type: foreign_key
    columns: [contract_id]
    target_table: contracts
    target_column: contract_id
  - type: foreign_key
    columns: [contractor_id]
    target_table: contractor_network
    target_column: contractor_id
```

**Flag for reconciliation:** this YAML assumes computed-field
expressions and join conditions can reference other computed fields
within the same dataset (e.g., `coverage_rules`'s join `ON` clause
referencing `normalized_item_category`, itself a computed field) and
can reference prior sources by their joined alias. Confirm this is how
`ModelGenerator` actually resolves reference order and aliasing —
adjust field/alias naming if the real implementation requires it.

---

## 8. Expected Output Rows

| claim_id | plan_tier | is_pre_existing_exclusion | is_covered | reimbursement_amount | why |
|---|---|---|---|---|---|
| CL-01 | Standard | false | true | **775.00** | (850−75)=775; cap 1000 → 775; in-network ×1.0 |
| CL-02 | Basic | false | false | **0.00** | no Basic/Electrical coverage_rules row at all |
| CL-03 | Premium | false | true | **1150.00** | (1200−50)=1150; cap 1500 → 1150; in-network ×1.0 (category normalized Water Heater→WtrHtr) |
| CL-04 | Standard | false | true | **320.00** | (450−50)=400; cap 800 → 400; non-network ×0.8 |
| CL-05 | Standard | false | true | **220.00** | (220−0, blank copay)=220; cap 500 → 220; in-network ×1.0 |
| CL-06 | Basic | false | true | **480.00** | (900−100)=800; cap 600 → 600; non-network ×0.8 |
| CL-07 | Standard | false | *(validation failure — see Section 9)* | — | blank contractor_id; not expected to reach the transformation cleanly |
| CL-08 | Basic | false | false | **0.00** | coverage_rules row exists but covered=FALSE explicitly (distinct cause from CL-02, same outcome) |

All values should be produced by an actual `structifact execute
--engine duckdb --materialize` run and verified against this table, not
assumed correct because the arithmetic was checked by hand here.

---

## 9. Expected Validation Behavior

Running `structifact validate-data` against `claims.csv` should report:
- A **required-field violation**: `contractor_id is blank at data row 7`
  (or the correct row index in the real file), for `CL-07`.

This should be run and its actual output captured as part of the
deliverable — not just asserted to work.

---

## 10. Expected Generated Artifacts

- **`generate` (default set)** — schema DDL, dbt YAML, minimal catalog.
- **`-g model`** — the real transformation SELECT, including the
  `contracts` dedup CTE and the composite join. This is what gets
  executed against DuckDB to produce Section 8's actual results.
- **`-g docs`** — per-field Markdown documentation. This is the
  artifact that most directly proves the thesis: every ambiguity
  resolution in Section 6 should be legible here without touching SQL.
- **`-g mermaid_erd`** — FK relationships (`claims`→`contracts`,
  `claims`→`contractor_network`). Note: the `coverage_rules`
  relationship will likely not render as a proper FK line, since it's
  a computed join condition rather than a `ConstraintSpec` — expected
  and fine, worth noting as a minor, known ERD-generator limitation
  for this example rather than something to fix.
- **`validate-data`** run against the real CSVs, output captured.
- **`structifact execute --engine duckdb --materialize`**, actual
  results compared against Section 8.

---

## 11. SQL-Free Reconstruction Test

Give someone the generated `-g docs` output and metadata YAML — **not**
the generated SQL. They should be able to correctly answer, for each
claim in Section 8, whether it's covered and what it's reimbursed,
including:
- Why the cap applies before the network multiplier (A1)
- What a blank copay cell vs. a blank cap cell each mean (A2)
- Whether day 30 itself counts toward the exclusion window (A3)
- Why CL-02 and CL-08 are both "not covered" for different underlying
  reasons (A4)

If any of these requires reading the raw SQL expression rather than the
field description to understand, that's a gap — the description needs
strengthening, not the SQL.

---

## 12. Capability Checklist / Open Questions for Reconciliation

Believed already supported (confirm against real code, don't assume):
- [ ] `FieldSpec.source_column` for header-drift mapping
- [ ] Plain (non-cross-join) `DedupRule` on a single source, ordered by
      a column other than the field being corrected
- [ ] Composite (multi-column) raw-SQL join condition via `JoinSpec.on`
- [ ] A join condition referencing a computed field from the same
      dataset (`normalized_item_category`) — **verify this resolves
      correctly; if the real `ModelGenerator` doesn't support
      referencing a computed field inside another source's join
      condition, this is a real discrepancy to report, not silently
      work around**
- [ ] A join condition referencing an already-joined source's column
      (`contracts.plan_tier` inside the `coverage_rules` join)
- [ ] Chained computed fields via `depends_on`
      (`is_pre_existing_exclusion` → `is_covered` → `reimbursement_amount`)
- [ ] `required` validation via `validate-data`
- [ ] Mixed date-format parsing in the CSV/type-coercion path — **this
      is a genuine unknown, not assumed; if Structifact's date parsing
      doesn't handle mixed formats within one column, report this as a
      discrepancy and decide whether to normalize the input file
      instead of expanding the type system**

**Explicitly out of scope — do not build to make this example work:**
UNION/stacking of multiple same-shaped sources, fuzzy/probabilistic
identity matching, and the parked DedupRule cross-join case. If
reconciliation reveals the approved scenario is genuinely impossible
without one of these, stop and report back rather than building it.

---

## 13. Implementation Boundaries

- No UNION, fuzzy matching, or new engine primitives.
- No expansion of the parked DedupRule cross-join investigation — this
  example deliberately uses only the plain, already-solid DedupRule
  case.
- No homepage changes. This is an engine/example deliverable only.
- If reconciliation (Section 7/12) finds the current engine genuinely
  cannot express something this design assumes, report the discrepancy
  and either adapt the example or flag it for a separate decision —
  never silently expand the engine to make the example fit.

---

## 14. Suggested Build Sequence

1. Add the four raw CSVs to a new `examples/home_warranty_demo/` (or
   similar) directory.
2. Add the business memo as a plain-text/markdown file alongside them.
3. Reconcile Section 7's YAML against real current syntax; write the
   actual spec file.
4. `structifact validate` the spec.
5. `structifact generate` the default set.
6. `structifact execute --engine duckdb --data ... --materialize`;
   compare results against Section 8, row by row.
7. `structifact validate-data` against `claims.csv`; confirm the
   `CL-07` required-field violation appears as expected.
8. Generate `-g model`, `-g docs`, `-g mermaid_erd`.
9. Perform the SQL-free reconstruction test (Section 11) — ideally by
   having someone (or a fresh Claude Code/chat instance with no prior
   context) actually attempt it against the generated docs alone.
10. Add tests covering the transformation and the edge cases (A1–A4,
    the dedup case, the validation failure).
11. Report back: what matched this design, what required adaptation,
    and the actual verified output — before any decision about
    homepage placement.
