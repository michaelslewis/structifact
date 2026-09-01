# home_warranty_claims

Per-claim coverage determination and reimbursement, joining claim records against contract, coverage-rule, and contractor-network reference data. A missing coverage_rules match and an explicit covered=false row both mean "not covered" — treated as distinguishable causes with the same business outcome (see is_covered below).


## Fields

### claim_id

- **Type:** string
- **Declared as:** string
- **Nullable:** Yes

### contractor_id

- **Type:** string
- **Declared as:** string
- **Nullable:** No

### contract_id

- **Type:** string
- **Declared as:** string
- **Nullable:** Yes

The join key into contracts.contract_id — a real relationship, but deliberately not declared as a `constraints:` foreign_key below (see the note above `constraints:` for why: the raw contracts table is intentionally non-unique on this column before dedup, so DuckDB can't physically enforce it as a DDL FOREIGN KEY without contradicting the dedup scenario itself).


### plan_tier

- **Type:** string
- **Declared as:** string
- **Nullable:** Yes

### effective_date

- **Type:** date
- **Declared as:** date
- **Nullable:** Yes

Mapped from the source system's own column name (start_date) — registrar's export was never renamed to match this schema.


### normalized_item_category

- **Type:** string
- **Declared as:** string
- **Nullable:** Yes
- **Computed:** Yes
- **Expression:** `CASE WHEN claims.item_category = 'Water Heater' THEN 'WtrHtr' ELSE claims.item_category END`

claims.csv and coverage_rules.csv use different spellings for the same category (Water Heater vs. WtrHtr). This is a small, finite, explicitly-enumerated mapping — not similarity/fuzzy matching — since the category vocabulary is closed and known. The coverage_rules join above inlines this identical expression directly (rather than referencing this field's alias), since a JOIN condition cannot reference a computed SELECT-list alias — this field exists so the mapping is still visible in generated docs/output, not because the join itself depends on it.


### is_pre_existing_exclusion

- **Type:** boolean
- **Declared as:** boolean
- **Nullable:** Yes
- **Computed:** Yes
- **Expression:** `claims.claim_date <= effective_date + INTERVAL '30 days'`

True if filed within 30 days (inclusive of day 30) of the contract's effective date. Absolute exclusion regardless of plan tier or category, per company policy. References the effective_date field's own alias (declared earlier in this file), not contracts.start_date directly or a nonexistent contracts.effective_date column — DuckDB allows a later SELECT-list expression to reference an earlier one's alias within the same SELECT (a non-standard, DuckDB-specific convenience — see reimbursement_amount's note on why this example's field order matters).


### is_covered

- **Type:** boolean
- **Declared as:** boolean
- **Nullable:** Yes
- **Computed:** Yes
- **Expression:** `NOT is_pre_existing_exclusion AND coverage_rules.covered IS NOT NULL AND coverage_rules.covered = TRUE`
- **Depends on:** is_pre_existing_exclusion

False if the pre-existing exclusion applies. Also false if no coverage_rules row matched this tier/category at all (coverage_rules.covered IS NULL — no rule was ever written), or if the matched row explicitly states covered=false (a rule was written that excludes this combination). Both cases are deliberately treated identically in outcome, despite being different underlying situations. depends_on above documents this field's real dependency on is_pre_existing_exclusion, but is validated for referential integrity only — it does not itself drive generation order. What actually makes this expression resolve correctly is that is_pre_existing_exclusion is declared earlier in this file's fields list, combined with DuckDB's SELECT-list alias reuse (see that field's own description). Confirmed DuckDB-specific and non-portable to PostgreSQL — a known, already-logged limitation (see docs/FUTURE_WORK.md), not new to this example.


### effective_copay

- **Type:** decimal
- **Declared as:** decimal
- **Nullable:** Yes
- **Computed:** Yes
- **Expression:** `COALESCE(coverage_rules.copay_amount, 0)`

A blank copay_amount on a covered row means $0 copay, not "no rule" — that distinction is carried entirely by is_covered, not by this field.


### reimbursement_amount

- **Type:** decimal
- **Declared as:** decimal
- **Nullable:** Yes
- **Computed:** Yes
- **Expression:** `CASE WHEN NOT is_covered THEN 0 ELSE LEAST(GREATEST(claims.claim_amount - effective_copay, 0), COALESCE(coverage_rules.coverage_cap, claims.claim_amount)) * CASE WHEN contractor_network.network_status = 'In-Network' THEN 1.0 ELSE 0.8 END END`
- **Depends on:** is_covered, effective_copay

The coverage cap is applied BEFORE the non-network 80% multiplier, not after — the cap represents the plan's maximum covered amount; network status then determines what fraction of that covered amount is actually paid. This ordering is a deliberate resolution of an ambiguity the source business memo did not specify — the alternative ordering (multiplier first, then cap) produces different results whenever the cap actually binds. A blank coverage_cap means uncapped (COALESCE falls back to the claim amount itself as a no-op ceiling). Floored at zero via GREATEST() on the copay subtraction. Like is_covered above, depends_on documents the real dependency on is_covered and effective_copay but doesn't drive ordering itself — both are declared earlier in this file's fields list, which is what actually makes the DuckDB-specific alias reuse work here.


## Constraints

- **foreign_key**: contractor_id
