# workorder_demo

SYNTHETIC EXAMPLE (fictional company/data) — see
`REQUIREMENTS_workorder.md`'s own header for the full disclaimer.
This directory holds two unrelated things:

1. A hand-authored dataset (`work_order_source.yml`,
   `work_order_source.sql`, `work_order_catalog.csv`) — the
   flat/reference version, unaffected by anything below.
2. Three `discover --requirements --ai` **drafts**, produced by three
   real (live, paid) LLM runs against `REQUIREMENTS_workorder.md` at
   different points in `structifact/discover.py`'s development. Kept
   side by side deliberately, as a before/after record of a real bug
   found and fixed through this exact document — not meant to be
   "the" canonical discovered draft; see each one's own disposition
   below.

## The three discovery drafts

Each is the **unedited output of a real LLM call** (`claude-haiku-4-5`
via `AnthropicLLMClient`) piped through `parse_requirements_draft()` /
`render_requirements_draft_yaml()` — nothing in any of these three
files was hand-written or hand-corrected afterward. LLM output is not
deterministic: re-running `discover --requirements --ai` against the
same document today will not reproduce any of these three byte-for-
byte. They're snapshots of specific runs, not fixtures a test asserts
against.

### `work_order_source.discovered.yml` — before source_column/sources/joins existed

The original draft, from before `build_requirements_prompt()` had any
concept of `source_column`/`sources`/`joins` at all. Every join key,
the three-way `PARTNER_ROLE` self-join (REQ/BILL/SITE), the priority
dedup rule, and the FX-lookup join all get correctly *identified* by
the model, but every one of them lands in `unresolved_notes` as
freeform prose — including one entry that's a stringified Python
`dict` rather than real text (`str()` on a nested YAML mapping,
`repr`-shaped, not prose). This file is the evidence base for that
whole diagnostic.

### `work_order_source.discovered.v2.yml` — after source_column/sources/joins, before source_table

The first fix: `build_requirements_prompt()`/
`render_requirements_draft_yaml()` gained `source`/`source_column`
per field and dataset-level `sources`/`joins` (matching
`SourceRef`/`JoinSpec`/`DedupRule` in `ir.py`, and the exact shape
`adapters/yaml.py` already loads). All three `PARTNER_ROLE` roles came
back correctly as three distinct `sources` entries with the right
`filter`/`dedup`. `structifact validate` passes clean.

It is **not generate-able as-is** — two real bugs, found by actually
attempting `structifact generate -g model` against it, not by
inspection:

- No `source_table` was extracted. `ModelGenerator`'s primary-source
  alias is `dataset.source_table or dataset.name`
  (`structifact/generators/model.py`) — every join's `"on"` condition
  here was written against the primary table's own physical name
  (`wo_hdr.customer_id = ...`), which only resolves once
  `source_table` is set to that same name. Without it, the alias
  silently falls back to the dataset's logical `name`
  (`work_order_source`), which never appears anywhere in the `FROM`
  clause the join actually needs — every join breaks.
- `WO_LINE` is referenced as a join-condition alias
  (`price_condition`'s `"on": "wo_line.rate_code = ..."`) without
  ever being declared as its own `sources` entry — an undefined alias
  in the generated SQL.

Kept specifically **as** the "before" illustration of these two bugs —
not because it's useful as a draft to build from.

### `work_order_source.discovered.v3.yml` — current, correct

Both bugs above fixed: `build_requirements_prompt()` now explicitly
asks for a top-level `source_table` whenever `sources`/`joins` are
extracted (chosen over inferring it from the `on:` strings — that
would require parsing untyped raw SQL to guess which alias is
"primary," and this exact document is proof that heuristic breaks:
one join legitimately references `wo_line`, a non-primary source, not
the primary alias). If the model ever omits `source_table` despite
emitting `sources`/`joins`, `render_requirements_draft_yaml()` flags
it loudly in `unresolved_notes` — it does not guess.

This run: `source_table: "WO_HDR"` came back correctly and
consistently across every join, and `WO_LINE` is properly declared as
its own `sources` entry this time (a real run-to-run improvement, not
guaranteed by the fix itself). `structifact validate` passes, and
`structifact generate -g model` produces
`work_order_source.discovered.v3.generated_model.sql` — see below for
what happened running it.

## `work_order_source.discovered.v3.generated_model.sql`

The actual, unedited output of `structifact generate -g model` against
v3. Executed against synthetic data for all six source tables in
DuckDB. Two things about this specific run's SQL, both **pre-existing,
already-documented Structifact limitations unrelated to the
source_table fix**, not new bugs:

- `sign_adjustment`'s `computed` expression is the raw pseudocode
  copied verbatim from the requirements doc (`if src_wo_hdr_wo_type in
  ('CRM','RET') then -1 else 1`) — not valid SQL as written.
  `FieldSpec.expression`'s docstring in `ir.py` is explicit that
  turning discovery-draft logic into real SQL is a human decision,
  never automatic. This is exactly what breaks first: DuckDB's parser
  rejects the `if ... then ... else` syntax outright.
- This particular run omitted the `resolved_fx_rate` field entirely
  (self-flagged in its own `unresolved_notes` as under-specified in
  the source document), while `labor_amount_usd`'s expression still
  references it by name.

Running the file exactly as generated fails at DuckDB's parser on the
first issue above. Re-running the identical SQL with **only** those
two pre-existing gaps hand-patched (pseudocode → `CASE WHEN`;
`resolved_fx_rate` → a `COALESCE` expression) — every join, alias, and
`source_table` resolution left untouched — executed cleanly and
produced correct values for both synthetic work orders. That isolates
the result cleanly: the source_table/join/dedup machinery this fix
targeted is now fully sound end-to-end; the one remaining manual step
for a dataset like this is translating `computed` pseudocode into real
SQL, which is a distinct, already-documented gap (see `ir.py`'s
`FieldSpec.expression` docstring), not something this work claims to
have solved.
