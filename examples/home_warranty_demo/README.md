# home_warranty_demo

SYNTHETIC EXAMPLE (fictional company/data) — Structifact's flagship
complex example. Built from `structifact-home-warranty-handoff.md` in
this folder, which is itself the design/reconciliation contract, not a
finished spec — every deviation from it below is a deliberate
adaptation to the real engine, verified by actually running the
commands, not assumed.

**What this demonstrates:** the homepage's "however you already
describe your data" claim — a messy, heterogeneous, ambiguous
real-world business handoff (three independently-maintained sources
plus a freeform business memo) becomes an explicit, validated
Structifact metadata contract, from which correct, reproducible
artifacts (SQL, docs, catalog, ERD) are generated, such that a reader
can reconstruct every important business decision from the generated
docs alone, without reading SQL.

## Files

- `contracts.csv`, `claims.csv`, `coverage_rules.csv`,
  `contractor_network.csv` — the four raw sources. `claims.csv`'s
  three US-format dates (CL-02/04/06) are pre-normalized to
  `YYYY-MM-DD` (see "Genuine gaps," #2 below).
- `business_memo.md` — the unedited business rules memo.
- `contracts.yml`, `claims.yml`, `coverage_rules.yml`,
  `contractor_network.yml` — minimal per-source ingestion schemas.
  `claims.yml` is also the schema used for the `validate-data` step.
- `home_warranty_claims.yml` — the composite transformation spec.
- `generated/` — real output of `structifact generate`/`execute`
  against the files above, including `home_warranty.duckdb`, the
  materialized database.

## Reconciliation summary

The handoff's Section 12 checklist, checked against the real engine:

| Item | Verdict |
|---|---|
| `FieldSpec.source_column` for header drift | Matches |
| Plain single-source `DedupRule` before join | Matches |
| Join `on` referencing a computed field's alias | **Genuine gap** |
| Join `on` referencing an already-joined source's column | Matches |
| `depends_on` producing computation ordering | Needs adaptation |
| Mixed date-format parsing | **Genuine gap** |
| `nullable: false` for the required-field check | Matches (scoping correction) |

Full writeup of each item's reasoning lived in conversation during
reconciliation; the adaptations actually applied are documented inline
in `home_warranty_claims.yml`'s comments, next to each affected field/
join/constraint. In short:

- **Join referencing a computed alias** (`coverage_rules`'s join
  needing `normalized_item_category`): confirmed impossible — a
  `JOIN...ON` clause resolves during the `FROM` clause, before the
  `SELECT` list (where a computed field's alias exists) is evaluated
  at all. Verified directly against DuckDB (`BinderException`).
  Adapted by inlining the same `CASE` expression directly in the
  join's `on:`, duplicated rather than aliased.
- **`depends_on` chain**: does nothing at generation time — it's
  validated for referential integrity only. What actually makes
  `is_pre_existing_exclusion` → `is_covered` → `reimbursement_amount`
  compute correctly is (a) declaring fields in that order in the YAML,
  and (b) DuckDB's non-standard support for a later `SELECT`-list
  expression referencing an earlier one's alias — already logged as a
  known DuckDB-only limitation in `docs/FUTURE_WORK.md`, not new here.
- **Mixed date formats**: confirmed DuckDB's implicit `VARCHAR→DATE`
  cast only accepts `YYYY-MM-DD`; `claims.csv` is pre-normalized
  rather than expanding Structifact's type system.
- **`nullable: false` required check**: matches exactly, but needs its
  own minimal `claims.yml` schema for `validate-data` — the composite
  spec's fields don't correspond 1:1 with `claims.csv`'s raw columns.

## Discrepancies found only by actually building and running this

None of these were flagged by the pre-build reconciliation — each was
found by generating real artifacts and executing them against real
data, matching this project's own "run it, don't just review it"
discipline (see `docs/DECISION_HISTORY.md` for prior instances of the
same pattern).

1. **The proposed YAML's primary source was unset.** `source_table`
   defaults to the dataset's own name when omitted, so without setting
   `source_table: claims`, `ModelGenerator` would target a nonexistent
   `home_warranty_claims` table. Fixed by setting `source_table:
   claims` and removing `claims` from `sources:` (it's the primary
   source, not a joined-in one) — and, found only by then actually
   running `validate`, removing `source: claims` from `claim_id`/
   `contractor_id`'s field definitions too, since a field's `source`
   must name a joined-in `SourceRef`, not the primary source.

2. **`is_pre_existing_exclusion`'s expression referenced a column that
   doesn't exist.** The proposed `contracts.effective_date` is neither
   a real physical column (the raw table only has `start_date`) nor a
   valid qualified reference to the `effective_date` *alias* (an alias
   can't be prefixed with a source name). Fixed by referencing the
   bare alias `effective_date` instead — the same pattern already used
   correctly elsewhere in the spec (`is_covered` referencing
   `is_pre_existing_exclusion` bare).

3. **A YAML formatting bug broke the generated DDL.** Three computed
   fields' `expression` values used YAML `>` folded block scalars with
   inconsistent internal indentation (and, more simply, `>`'s default
   trailing newline) — both produce embedded newlines in the parsed
   string. `SQLGenerator` renders a computed field's expression as a
   single-line SQL comment (`-- computed: <expr>`); an embedded
   newline splits that comment mid-statement and produces a syntax
   error in the generated `CREATE TABLE`. Only visible by generating
   the actual DDL and reading it — `structifact generate` itself
   reports no error, since nothing validates the *content* of
   `expression`. Fixed by writing all three as genuinely single-line
   strings.

4. **`execute --data` doesn't coerce a blank CSV cell to SQL `NULL`,
   for any column type.** Confirmed on two different failure shapes
   from the same root cause:
   - `coverage_rules.csv`'s blank `copay_amount`/`coverage_cap` cells
     (deliberately present — Ambiguity A2) load as literal empty
     strings, which DuckDB's typed `DECIMAL` column can't accept
     (`Conversion Error: Could not convert string "" to DECIMAL`).
   - `claims.csv`'s blank `contractor_id` on `CL-07` (deliberately
     present — Mess #5) also loads as `''`, not `NULL` — which
     silently satisfies a `NOT NULL` column check (`'' != NULL`), then
     fails downstream instead, as a foreign-key violation against
     `contractor_network` once the composite table is materialized.

   Adapted, not patched: `coverage_rules` and `claims` are loaded via
   DuckDB's own `COPY ... (HEADER, NULLSTR '')` / `read_csv(...,
   nullstr='')` instead of `structifact execute --data`, so a blank
   cell becomes real `NULL`. `contracts` and `contractor_network` (no
   blank cells) still use `execute --data` directly, demonstrating
   that path working as designed on clean data.

5. **A `contract_id` foreign key can't be physically enforced against
   the raw `contracts` table.** DuckDB requires an FK's target column
   to already carry a `PRIMARY KEY`/`UNIQUE` constraint — but the raw
   `contracts` table is *deliberately* non-unique on `contract_id`
   before dedup (that's the entire point of Mess #2's duplicate
   `C-1001` row). Enforcing this FK against the raw table would
   contradict the scenario itself. Adapted by dropping this one
   `constraints:` entry (the relationship is still fully documented in
   `contract_id`'s own field description) while keeping `contractor_id
   → contractor_network` (physically valid — `contractor_network` is
   genuinely unique on `contractor_id`, given a `primary_key`
   constraint so the FK is real, DB-enforced, and shows as a proper
   line in the generated ERD).

6. **`CL-07` can't cleanly reach the materialized composite table
   either way** — with contractor_id loaded as `''` it fails the FK
   check; loaded as real `NULL` it fails `claims.contractor_id`'s own
   `NOT NULL` constraint (correctly — it really is invalid data per
   the declared schema). This matches the handoff's own Section 8,
   which already anticipated CL-07 "is not expected to reach the
   transformation cleanly." Adapted by excluding CL-07 from the raw
   `claims` table used for materialization (the other 9 claims
   materialize and verify normally) while running `validate-data`
   separately against the full, unmodified `claims.csv` (all 10 rows)
   to catch it — which is the real, intended gate for this exact
   failure mode, not the transformation step.

None of the above touched `structifact/` engine code, added UNION,
fuzzy matching, or the parked `DedupRule` cross-join case — every
adaptation is in the example's own YAML/CSV files or in how the
upstream tables were populated for this one build.

## Verified results

`structifact execute --engine duckdb --materialize`, run against
`generated/home_warranty.duckdb`:

| claim_id | plan_tier | is_pre_existing_exclusion | is_covered | reimbursement_amount |
|---|---|---|---|---|
| CL-01 | Standard | false | true | 775.00 |
| CL-02 | Basic | false | false | 0.00 |
| CL-03 | Premium | false | true | 1150.00 |
| CL-04 | Standard | false | true | 320.00 |
| CL-05 | Standard | false | true | 220.00 |
| CL-06 | Basic | false | true | 480.00 |
| CL-08 | Basic | false | false | 0.00 |
| CL-09 | Standard | **true** | false | 0.00 |
| CL-10 | Standard | false | true | 525.00 |

All 9 values match the handoff's Section 8 expectations exactly,
including the two boundary claims added to actually exercise A3 (day
30 is inclusive-excluded; day 31 is covered). CL-07 is intentionally
absent — see discrepancy #6 above.

`structifact validate-data examples/home_warranty_demo/claims.yml
examples/home_warranty_demo/claims.csv`:

```
✓ Loaded schema: claims
✓ Loaded data: 10 rows

✗ 1 issue(s) found

Required-field violations:
  - contractor_id is blank at data row 7
```

Individual semantic proofs (all confirmed against the real database):

- **C-1001 dedup**: CL-01/CL-05 both resolve `effective_date` to
  `2025-03-01` (the more-recently-entered row), not `2025-03-10`.
- **CL-03 normalization**: `normalized_item_category = 'WtrHtr'`,
  `is_covered = true` — the Water Heater/WtrHtr join match only
  succeeds because of the normalization.
- **CL-02 vs. CL-08**: both `is_covered = false`, but the underlying
  `coverage_rules` match differs — CL-02 matches no row at all (`NULL`
  from the join), CL-08 matches an explicit `covered = FALSE` row.
- **CL-05 blank copay**: `effective_copay = 0.00`, `reimbursement =
  220.00` (full claim amount, no copay deducted).
- **CL-06 cap-before-multiplier**: `reimbursement = 480.00` — proving
  the cap ($600) applies to the post-copay amount ($800→$600) *before*
  the 80% non-network multiplier, not $400.00 (multiplier-then-cap) or
  $384.00 (some other ordering).
- **CL-09/CL-10 A3 boundary**: see the results table above.

## Automated tests

`tests/test_home_warranty_demo.py` runs the real files here (loaded
via `load_yaml()`, not hand-constructed `DatasetSpec` objects) against
a real in-memory DuckDB, asserting exact values for every claim above,
plus dedicated tests for the C-1001 dedup and Water Heater/WtrHtr
normalization cases, plus the `validate-data` CL-07 check.

## Not yet done

The SQL-free reconstruction test (handoff Section 11 — giving someone
the generated `-g docs` output and metadata YAML, without the SQL, and
confirming they can answer every A1–A4 question from it alone) was
spot-checked during the build against `generated/home_warranty_claims.md`
but not run as a formal fresh-context exercise. All four answers
(cap-before-multiplier ordering, blank-copay-vs-blank-cap semantics,
the 30-day inclusive boundary, and CL-02-vs-CL-08's distinct causes)
are present in the generated docs without needing the SQL — worth a
real fresh-context pass before any homepage-placement decision.
