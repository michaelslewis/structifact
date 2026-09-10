# Walkthrough: from a messy requirements doc to a validated data definition

This is the canonical Structifact example. It follows one real,
synthetic dataset — a field-service company's work order data —
through the whole workflow: a messy requirements document, an AI
first pass at turning it into metadata, what Structifact's checks
actually caught wrong with that first pass, a human correction, and
the deterministic SQL that correction produces.

Every command below was actually run against the files in this
directory. Nothing here is simulated or described from memory — if
you have Structifact installed, you can run every one of them
yourself and get the same output.

## 1. The ugly real input

[`REQUIREMENTS_workorder.md`](REQUIREMENTS_workorder.md) is a
synthetic-but-realistic requirements document: a fictional field-
service company's spec for a work-order dataset, in the shape a real
one actually shows up in — a couple of grid tables, join keys given
as a separate numbered list you have to cross-reference back into the
tables, one column marked for exclusion only by prose ("highlighted
grey in the original sheet — deprioritize"), and a dedup rule ("only
the CURRENT contact should be used... if none is flagged current,
fall back to the most recently updated row") buried in a paragraph
below the tables it actually governs. The document contains some
structured pieces (tables, column names, the numbered join-key list),
but the important relationships and business rules aren't expressed
in one machine-readable structure — they have to be read and
cross-referenced.

## 2. What AI discovery proposed

```
structifact discover REQUIREMENTS_workorder.md --ai -o work_order_source.discovered.v3.yml
```

This is the real, unedited output of that command — see
[`work_order_source.discovered.v3.yml`](work_order_source.discovered.v3.yml)
(one of three real runs against this document kept in this folder;
see this directory's `README.md` for what the other two show — LLM
output isn't deterministic, so re-running this today won't reproduce
any of them byte-for-byte).

It got a lot right: it correctly identified all six join keys from
the numbered list, correctly modeled `PARTNER_ROLE` as three separate
joined instances (one per role) each with the right priority-dedup
rule, and correctly declined to guess a source table for the FX rate
column it couldn't fully pin down — pushing that uncertainty into
`unresolved_notes` instead of inventing something:

```yaml
  - name: "labor_amount_usd"
    description: "Labor Amount (USD)"
    role: "measure"
    type: "decimal(15,2)"
    computed: true
    expression: "labor_amount_lc * resolved_fx_rate"
```
```yaml
unresolved_notes:
  - "Field resolved_fx_rate used in labor_amount_usd computation — source and exact column name not specified in document; assumed to come from fx_rate_lookup join result."
```

Notice what's missing, though: `resolved_fx_rate` is used in that
expression, and the AI declared a `fx_rate` source and joined it in —
but never actually declared `resolved_fx_rate` as a field pulling
from that source. It flagged the uncertainty in prose, but the
structured metadata still doesn't hold together. That's exactly what
the next step catches.

## 3. What Structifact's checks actually flagged

```
$ structifact validate work_order_source.discovered.v3.yml

Validation failed:

Field 'sign_adjustment' has an expression referencing unknown identifier 'if' — it does not match any field name or source_column in this dataset
Field 'labor_amount_usd' has an expression referencing unknown identifier 'resolved_fx_rate' — it does not match any field name or source_column in this dataset

⚠ 1 warning(s):

  - Orphaned source: source 'fx_rate' is declared and joined but is not referenced by any output field, computed expression, or filter. Review whether this source is intentionally used only for join filtering, or whether fields were attributed to another source — this check cannot verify legitimate join-only-filter usage, so that case is real and not caught here.
```

Two real errors, one real warning, all genuinely useful:

- **The `resolved_fx_rate` gap from Step 2**, caught directly: the
  dangling-identifier check reads every `expression` and confirms
  each bare name it references actually exists somewhere in this
  same dataset. It doesn't — this is a real correctness bug (not a
  style nitpick) that would otherwise only surface once you tried to
  actually generate and run the SQL.
- **The same gap, seen from the other side**: the orphaned-source
  warning independently notices that `fx_rate` was declared and
  joined but never actually used by anything — the same underlying
  problem, caught by a second, unrelated check.
- **`sign_adjustment`'s `if ... then ... else`**: the requirements
  document's own pseudocode (`if src_wo_hdr_wo_type in ('CRM','RET')
  then -1 else 1`, copied verbatim per Structifact's own documented
  rule that translating discovery-draft logic into real SQL is always
  a human decision, never automatic) isn't valid SQL syntax, so it
  trips the same check. This one isn't really a "bug" — it's the one
  step the tooling was never going to do for you.

## 4. The human-reviewed, corrected definition

[`work_order_source.reviewed.yml`](work_order_source.reviewed.yml)
fixes exactly those two problems and nothing else — every other
field, source, join, and note is carried over from Step 2's draft
unchanged (see that file's own header comment for the full, itemized
diff):

```yaml
  - name: "resolved_fx_rate"
    description: "Exchange rate to USD, resolved from fx_rate_lookup with a 1.0 fallback for USD-denominated work orders only"
    role: "measure"
    source: "fx_rate"
    type: "decimal(9,6)"
```

```diff
- expression: "if src_wo_hdr_wo_type in ('CRM','RET') then -1 else 1"
+ expression: "CASE WHEN src_wo_hdr_wo_type IN ('CRM','RET') THEN -1 ELSE 1 END"
```

```
$ structifact validate work_order_source.reviewed.yml

✓ Loaded metadata
✓ Parsed 18 fields
✓ Valid schema
✓ No constraint violations
```

One thing this file deliberately does **not** fix: the FX
conversion's conditional fallback rule ("if no rate is found and
currency is USD, treat the rate as 1.0; otherwise leave the amount
null") stays in `unresolved_notes`, exactly where the AI draft
already correctly left it. Structifact doesn't yet have a way to
express conditional-fallback business logic like this in its metadata
(see `ir.py`) — that's a real, currently-open gap, not something this
walkthrough papers over.

## 5. The deterministic artifact it produced

```
$ structifact generate work_order_source.reviewed.yml -o generated

--- GENERATED ARTIFACTS ---
- generated/work_order_source.sql
- generated/work_order_source.yml
- generated/work_order_source_catalog.csv
```

[`generated/work_order_source.sql`](generated/work_order_source.sql),
in full, exactly as produced:

```sql
CREATE TABLE "work_order_source" (
    "wo_id" VARCHAR(12),
    "wo_date" DATE,
    "currency_code" VARCHAR(3),
    "wo_type" VARCHAR(4),
    -- computed: sign_adjustment = CASE WHEN src_wo_hdr_wo_type IN ('CRM','RET') THEN -1 ELSE 1 END,
    "sign_adjustment" INTEGER,
    "line_id" VARCHAR(6),
    "labor_hours" DECIMAL(7,2),
    "rate_code" VARCHAR(4),
    "labor_rate" DECIMAL(9,2),
    -- computed: labor_amount_lc = src_wo_line_labor_hours * src_price_cond_labor_rate * sign_adjustment,
    "labor_amount_lc" DECIMAL(15,2),
    "resolved_fx_rate" DECIMAL(9,6),
    -- computed: labor_amount_usd = labor_amount_lc * resolved_fx_rate,
    "labor_amount_usd" DECIMAL(15,2),
    "customer_name" VARCHAR(60),
    "region_code" VARCHAR(4),
    "requested_by_name" VARCHAR(60),
    "billed_to_name" VARCHAR(60),
    "site_contact_name" VARCHAR(60),
    "site_contact_phone" VARCHAR(20)
);
```

Every identifier is quoted (a separate, unrelated fix — see this
repo's Issue #1 — that happens to be visible here too). This is
mechanical, deterministic output: run `generate` on the same reviewed
YAML ten times and you get this exact text ten times, unlike the AI
draft in Step 2, which won't reproduce itself even once.

The reviewed metadata is now structurally valid, so Structifact can
deterministically generate its current implementation artifacts from
it. In this example, the SQL generator produces the target table
definition — it does not implement the joins, the contact dedup, the
FX lookup, the sign adjustment, or the USD conversion. Those
transformations remain represented in the reviewed metadata (as
`sources`/`joins`/`computed` expressions) for downstream
implementation, not compiled into this DDL.

## 6. Why not just ask an AI to write the YAML directly?

You could. This document shows why that's not the end of the story on
its own. The Step 2 draft wasn't a bad first pass — it correctly
found every join key, correctly modeled the three-way self-join and
its dedup rule, and correctly refused to guess things it wasn't sure
of. But it also produced YAML that was internally inconsistent in a
way that isn't obvious just from reading it: a field's expression
referenced something that was never actually declared, while the
source meant to back that field sat unused a few lines away. That's
exactly the kind of gap that's easy to miss on a read-through and easy
to catch with a deterministic rule that actually cross-checks every
reference against what's declared — which is what Step 3 did, for
real, on this exact document. And re-running discovery against the
identical document doesn't reliably converge on the same result
either (see this folder's `README.md` for two other real runs that
each got different pieces right and wrong) — so "ask the AI again"
isn't a substitute for a deterministic check that gives the same
answer every time. The AI draft is a genuinely useful first pass, not
a finished one; the review-and-check step is what turns it into
metadata Structifact can deterministically generate its current
artifacts from — not, on its own, a finished executable
implementation of the transformation (see Step 5).

## Run it yourself

```bash
# from this directory
structifact validate work_order_source.discovered.v3.yml   # Step 3 — real errors/warning
structifact validate work_order_source.reviewed.yml         # Step 4 — clean
structifact generate work_order_source.reviewed.yml -o generated  # Step 5
```

`structifact discover REQUIREMENTS_workorder.md --ai` (Step 2) is
**not** re-run above — it costs a real, paid LLM call, and re-running
it will not reproduce
[`work_order_source.discovered.v3.yml`](work_order_source.discovered.v3.yml)
byte-for-byte (see this folder's `README.md`). The checked-in file is
a real, previously-run result, not a fixture regenerated on demand.
