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

## Working practices

- **Run the test suite before considering any change done.**
  `python3 -m pytest -q` (or the manual verification pattern used in
  this project's history if `pytest` isn't installed) — every change
  should leave all tests passing, not just the ones related to the
  change.
- **When generator output changes, update the golden files.**
  `tests/golden/` and `examples/customers/generated/` must stay in
  sync with what the generators actually produce. A test that
  compares against a stale golden file is worse than no test.
- **Prefer small, focused commits over large ones.** One logical
  change per commit, with a message that explains *why*, not just
  *what*.
- **When you change behavior, check whether docs describe the old
  behavior.** This project has drifted between docs and reality
  before (see below) — don't let it happen again.
- **Don't leave dead code around "just in case."** If nothing
  imports it and it doesn't match current architecture, remove it
  rather than letting it accumulate.

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
