# Structifact: Validate (VS Code extension, MVP)

One command: **Structifact: Validate**. It saves the active file if dirty,
shells out to the real `structifact validate <file>` CLI, and shows the
result as native VS Code diagnostics (Problems panel + inline squiggle) on
failure, or a status-bar message on success.

This is deliberately the smallest useful slice, not a full extension:

- No validation logic is duplicated in JavaScript — every rule check still
  happens in `structifact/validation.py`, invoked exactly as the CLI runs
  it. This command is a thin, literal wrapper around a subprocess call.
- No line/column positions. `structifact validate`'s errors describe a
  field or constraint by name, not a source location (`validation.py`
  works on the parsed IR, which carries no YAML line/column data) — every
  diagnostic is anchored to the file's first line as a best-effort
  placeholder, not a real position.
- No YAML shape/schema validation here — that's already covered live by
  `schemas/structifact-dataset.schema.json` + the Red Hat YAML extension
  (see `.vscode/settings.json`). This command covers the separate,
  larger rule set that requires actually running Structifact: cross-field
  and cross-reference checks (a join's `source` naming a real declared
  source, a foreign key's target, etc.) that a static JSON Schema can't
  express.
- No webview, sidebar, additional commands, or packaging/publishing setup
  yet — see `docs/FUTURE_WORK.md`'s "IDE Integration" section for what
  might come after this, if it proves useful.

## Prerequisites

Structifact itself must be installed so its `structifact` console script
exists:

```bash
pip install -e .
```

**You should not need to set `structifact.cliPath` manually anymore.**
Earlier, a project virtualenv's `structifact` wasn't found because a
venv's `bin/` is only on `PATH` inside an activated shell, and VS Code
doesn't activate it — the extension now checks the open workspace's own
`.venv/` or `venv/` folder for a `structifact` binary directly (before
falling back to bare `PATH`), so the normal case — a virtualenv living
inside the project, exactly like this repo's own `.venv/` — resolves
with zero configuration. Confirmed directly against this repo's real
`.venv/bin/structifact`. Only set `structifact.cliPath` yourself for an
unusual setup (a virtualenv with some other name, or living outside the
workspace folder).

## Running it

1. Open the repo root (`structifact/`) as a VS Code workspace folder.
2. Press F5 (or Run → Start Debugging) — this uses the
   `Run Structifact: Validate extension` launch config in
   `.vscode/launch.json` to open a new Extension Development Host window
   with this extension loaded.
3. In that new window, open any real dataset YAML file (e.g.
   `examples/customers.yml`), then run **Structifact: Validate** from the
   Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`).
4. Introduce a real validation error (not a YAML-shape one — the schema
   already catches those live) — e.g. a `foreign_key` constraint naming a
   column that doesn't exist as a field — save, and re-run the command to
   see it appear in the Problems panel.
