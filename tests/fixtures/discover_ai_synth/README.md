# Synthetic Requirements-Document Fixture

Replaces the sanitized `deliveries` excerpt lost when macOS purged `/tmp`
(see `scratch/STRATEGY_LOG.md`). Reproduces the same structural challenge with
**entirely fictional content** — SAP table/field abbreviations are public schema
names, nothing here derives from any employer material.

Because there's no IP constraint, this fixture can be committed, put in CI, and
shown publicly — none of which the sanitized original could ever do. Hence its
location: this generator, the scorer, and this README live in
`tests/fixtures/discover_ai_synth/` and are committed. The documents they
generate and the run outputs they're scored against are not — point `-o` at
`scratch/synth/out/` (gitignored) to keep those local, regenerable from the
committed script and a `--seed` rather than checked in themselves.

---

## The challenge it reproduces

1. Section 2 defines every field under one prefix — `struct_<table>_<field>`.
2. Sections of processing notes create distance.
3. Section 4 ("Revisions") supersedes a subset of those fields — under a
   **different** prefix, `sap_<table>_<field>`.

Correct extraction merges each revision **into the existing field**: replacing
its description and attaching the note as `comment`. It must not emit a second
field under the `sap_` name.

---

## Generate

Run from the repo root; `-o` should point into the gitignored `scratch/synth/out/`,
not into this directory.

```bash
G=tests/fixtures/discover_ai_synth/make_requirements_doc.py

# small — cheap, fast, for repeat runs
python3 $G --fields 40 --overrides 4 --filler 8 -o scratch/synth/out/small/

# full scale — comparable to the real document (~39k tokens; raise --filler for more)
python3 $G --fields 500 --overrides 12 --filler 900 -o scratch/synth/out/full/

# .xlsx instead of markdown (needs openpyxl)
python3 $G --fields 40 --overrides 4 --xlsx -o scratch/synth/out/small/

# --hard: no self-explaining preamble, no forward-reference, neutral section
# title, table placed mid-document -- see DECISION_HISTORY.md's override-merge
# entry for why this variant exists (the non-hard fixture handed the model
# the answer, so Arms A/D measured instruction-following, not correlation)
python3 $G --fields 500 --overrides 12 --filler 900 --hard -o scratch/synth/out/full_hard/
```

Each run emits `<stem>.md` and `<stem>.groundtruth.json`. `--seed` varies content
while holding structure constant.

**`--fields` and `--filler` are the scale dial.** The real document existed at
exactly one size, so the scale hypothesis in `DECISION_HISTORY.md` could never be
tested against it. Here the same override pattern can be run at 40 fields and at
500, which isolates scale as a variable for the first time.

---

## Score a run

```bash
S=tests/fixtures/discover_ai_synth/check_extraction.py

python3 $S draft.yml scratch/synth/out/small/<stem>.groundtruth.json
python3 $S draft.yml scratch/synth/out/small/<stem>.groundtruth.json --json
```

Scoring is mechanical, so every protocol run is judged by one rule with no
per-run inspection.

| Code | Meaning |
|---|---|
| `OK` | Revision correctly merged into the existing field |
| `F-IGNORE` | Original description kept; revision dropped |
| `F-DUP` | A second field emitted under the revision's own name |
| `F-MISFILE` | Original description kept, revised text misfiled into `comment` |
| `F-PARTIAL` | Description applied but comment missing, or the reverse |
| `F-DROP` | Field absent entirely |
| `F-OTHER` | Present, matches nothing above |

The first three correspond to the three real failure shapes recorded in
`DECISION_HISTORY.md`.

Also reported: **`false_success_claim`** — whether the draft's `unresolved_notes`
asserts the revisions were applied when they weren't. Your notes called that
"worse than a silent miss," and it's a distinct defect from the merge failure, so
it's tracked separately rather than folded into the outcome code.

---

## Validation of the scorer itself

Both scripts were checked against synthesized drafts covering all six outcomes
before any API spend. That check caught a real bug: the revised description
contains the original as a prefix, so a plain substring test scored `F-IGNORE`
(the failure mode the full document actually exhibited) as `F-PARTIAL`. The
ground truth now carries `original_description` and the scorer tests the
revision-only remainder.

Worth re-running that check after any edit to either file:

```bash
python3 - <<'PY'
import json, yaml
gt = json.load(open("scratch/synth/out/small/<stem>.groundtruth.json"))
# build one draft per failure mode from the ground truth, score each,
# confirm the reported code matches the mode you constructed
PY
```

---

## Caveat, stated plainly

`DECISION_HISTORY.md` already established that synthetic and real documents
diverged on this exact question — the blank-role-marker fix showed measurable
improvement on a 20-field synthetic document and *zero* improvement on the real
~500-field one. So a result here is evidence about this fixture, and only
provisionally about real documents.

What it answers cleanly: **run-to-run stability**, which nothing in the record
currently measures, since every prior result is n=1 for its configuration.
