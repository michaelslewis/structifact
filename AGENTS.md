# AGENTS.md

Instructions for any AI assistant (Claude, ChatGPT, Claude Code, or
otherwise) working in this repository. This distills
`DESIGN_PRINCIPLES.md` and `DECISION_HISTORY.md` into concrete rules
rather than philosophy — read those two files for the "why."

## Non-negotiables

1. **Never bypass the IR.** Every code path from adapters to
   generators goes through `DatasetSpec` / `FieldSpec` /
   `ConstraintSpec` in `structifact/ir.py`. Do not add a shortcut that
   goes straight from a raw input format to an artifact.

2. **Adapters only load and normalize. No business logic.** An
   adapter's job is: read the source format, produce a `DatasetSpec`.
   Validation rules, generation logic, and business rules do not
   belong in `structifact/adapters/`.

3. **Fields describe structure. Constraints describe rules.** Don't
   add relational or business-rule attributes (e.g. `primary_key`,
   `unique`) directly onto `FieldSpec`. That's what `ConstraintSpec`
   is for. See `DECISION_HISTORY.md` for why this split exists.

4. **All type normalization goes through `structifact/types.py`**
   (`parse_type` / `normalize_type`). Every adapter (YAML, CSV, Excel)
   must normalize types the same way. Do not duplicate type-mapping
   logic in an adapter or generator.

5. **Generated output must be human-readable and inspectable.** No
   opaque generated code, no hidden runtime behavior. Someone should
   be able to look at generated SQL or dbt YAML and understand
   exactly why it looks the way it does.

6. **AI assistance is optional, never authoritative.** If you build
   AI-assisted features (schema discovery, suggestions, etc.), the
   deterministic pipeline must remain fully functional without them.
   AI suggests; a human approves; approved metadata is the only
   source of truth. Never let an AI-generated suggestion silently
   become production metadata.

7. **Never commit real or work-derived material, and never store it
   in a temporary location.** Real-world validation examples are
   hand-sanitized and re-aliased by the author, and live only in a
   scratchpad directory outside this repository — never in the repo,
   never in git history. Never suggest `/tmp`, `/private/tmp`, or any
   OS-managed temporary directory for that material: macOS purges
   those, and hours of hand-sanitization were lost that way once. Use
   a durable user directory, and never `git add` from it.

## Working practices

- **Update the GitHub project board (user michaelslewis, project 1)
  alongside doc commits, not as a separate thing to remember.** It
  went stale for an extended stretch (last current around "Phase 9
  v1 / Phase 8D v4") before being caught and backfilled — real work
  (a full 1.0 readiness audit, two real-world-validation rounds,
  native `.xlsx` discovery, reconciliation v1) had shipped and been
  documented without ever reaching the board. When you finish a
  feature's docs commit, also add/update the corresponding board item
  (`gh project item-create 1 --owner michaelslewis --title "..."`,
  then `gh project item-edit` to set Status) in the same pass.
- **Run the test suite before considering any change done.**
  `python3 -m pytest -q` (or the manual verification pattern used in
  this project's history if `pytest` isn't installed) — every change
  should leave all tests passing, not just the ones related to the
  change.
- **After `git push`, check that CI actually passed** (`gh run list`
  / `gh run view --log-failed`) — don't assume a locally-green
  `pytest` run means CI is green too. It once wasn't, for four
  commits in a row, unnoticed: one failure came from a test needing a
  package that happened to already be installed locally but was never
  a CI dependency, the other from a real headless-browser sandbox
  difference between macOS and GitHub's Linux runner. Neither was
  visible from the machine that ran the tests locally — see
  `DECISION_HISTORY.md`'s "CI Had Been Red for Four Commits Before
  Anyone Checked."
- **Check the test count, not just the green check.** CI attests only
  to what it collected, and collection depends on what CI installed.
  A module whose imports fail is dropped from collection silently —
  no error, no skip, no mention in the summary line — so a run can be
  green on a smaller suite than anyone thinks it's running. 37
  adapter tests went uncollected this way for an extended stretch,
  including a regression test for a real bug. Local and CI counts
  should reconcile exactly, with any difference fully explained by
  environment-gated tests (currently: CI's 580 = local's 559 + the 21
  PostgreSQL tests that need a real DSN).
- **When generator output changes, update the golden files.**
  `tests/golden/` and `examples/customers/generated/` must stay in
  sync with what the generators actually produce. A test that
  compares against a stale golden file is worse than no test.
- **Prefer small, focused commits over large ones.** One logical
  change per commit, with a message that explains *why*, not just
  *what*.
- **Never add `Co-Authored-By` trailers or "Generated with Claude
  Code" footers to commits.** Commit authorship in this repository
  belongs to the human author alone. This is also enforced by the
  `attribution` setting in `~/.claude/settings.json`, but it is
  stated here because not every assistant reads that file.
- **Write commit messages that read well to a stranger, in public,
  years from now.** Describe the change on its own terms. Don't
  editorialize about the author's circumstances, and don't describe a
  cleanup in language that invites a reader to go looking for what
  was cleaned up — a neutral, accurate subject line is both more
  honest and more useful than a dramatic one.
- **When you change behavior, check whether docs describe the old
  behavior.** This project has drifted between docs and reality
  before (see below) — don't let it happen again.
- **Don't leave dead code around "just in case."** If nothing
  imports it and it doesn't match current architecture, remove it
  rather than letting it accumulate.
- **Confirm cost before escalating spend on an AI-assisted task.**
  Raising a token cap, switching to a more expensive model, or
  retrying after a timeout are each a new spending decision, not a
  continuation of the approved one. Estimate aloud and get an
  explicit go-ahead each time — an unattended diagnostic loop once
  spent roughly ten times what had been estimated, without ever
  pausing to ask.

## Known project-specific traps (already hit once — don't repeat)

- `structifact/parser.py` was removed because it was an orphaned,
  pre-`DatasetSpec` code path that nothing imported. If you're adding
  a new metadata-loading path, make sure it's actually wired into
  `structifact/adapters/registry.py`, not a second untested route.
- Avoid backslashes inside f-string `{...}` expressions
  (`f"{','.join(x)}"` is fine; `f"{',\n'.join(x)}"` is not) — that
  syntax requires Python 3.12+, and this project's `pyproject.toml`
  declares `requires-python = ">=3.10"`. CI runs 3.11 specifically to
  catch this class of bug.
- CSV and Excel adapters must normalize types via `parse_type()` just
  like the YAML adapter does — they previously passed raw type
  strings straight through, which was an inconsistent contract across
  adapters even though no test caught it at the time.
- Multiple assistant sessions may be working in this repository
  concurrently. Check `git log` / `git status` for the real current
  state rather than trusting any single session's assumptions about
  what is committed.

## Where things live

- `structifact/ir.py` — the canonical model. Start here to understand
  the project.
- `structifact/adapters/` — input format handling (YAML, CSV, Excel).
- `structifact/generators/` — artifact generation (SQL, dbt YAML).
- `structifact/validation.py` — schema/constraint validation.
- `structifact/cli.py` — the `validate` and `generate` commands.
- `examples/customers/` — the golden-path example; a five-minute
  overview of the whole system for a new reader.
- `docs/` — the fuller design documentation this file summarizes.
