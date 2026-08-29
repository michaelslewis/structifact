# coverage_round1

SYNTHETIC EXAMPLES (fictional companies/data throughout). Dogfooding/
coverage round: new synthetic test materials at varying complexity,
run through real end-to-end tests. No engine code was changed as
part of this round — see `REPORT.md` for the full account of what
was tested, what passed, and what failed (and why).

## CLI-only vs. site-testable — read this before touching either file

**`requirements_docs/`** — freeform requirements documents for
`discover --requirements --ai` (CLI-only). structifact.com's upload
dropzone does **not** do AI extraction; it only accepts already-
structured, clean column/type specs. Dropping one of these `.md`/
`.xlsx` files into the website directly would not work as intended —
that's expected, not a bug, and none of these should be tested there.

**`yaml_specs/`** — hand-authored YAML dataset specs, already in
Structifact's clean canonical shape. These ARE safe and appropriate
to drop into structifact.com directly for `validate`/`generate`.

| File | Type |
|---|---|
| `requirements_docs/simple_expense_claims.md` | CLI-only (discover --requirements --ai) |
| `requirements_docs/medium_subscription_billing.xlsx` | CLI-only (discover --requirements --ai) |
| `requirements_docs/hard_insurance_claims.md` | CLI-only (discover --requirements --ai) |
| `yaml_specs/simple_product_inventory.yml` | site-testable (drop into structifact.com) |
| `yaml_specs/complex_helpdesk_tickets.yml` | site-testable (drop into structifact.com) |

## Layout

`requirements_docs/` — for each of the three tiers: the requirements
document itself, an `.expected_shape.md` written and committed
**before** running `discover` (what a correct extraction should
produce), the raw unedited LLM response (`.raw_llm_response.txt`),
the rendered draft (`.discovered.yml`), and the `-g model` generated
SQL (`.generated_model.sql`) as actually produced — nothing hand-
corrected in any of these.

`yaml_specs/` — for each of the two hand-authored specs: the YAML
itself, a `_data/` directory with synthetic CSVs and an `EXPECTED.md`
written before running `generate`/`execute`, and the generated model
SQL.

`REPORT.md` — Part 4's full writeup: what passed cleanly, what
failed and why, and which failures trace to already-known gaps
versus genuinely new findings from this round.
