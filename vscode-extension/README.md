# Structifact for VS Code (MVP)

Three commands, all thin, literal wrappers around the real `structifact`
CLI — no logic is duplicated in JavaScript, no webview/sidebar, no
packaging/publishing setup yet:

- **Structifact: Validate** — saves the active file if dirty, runs
  `structifact validate <file>`, and shows the result as native VS Code
  diagnostics (Problems panel + inline squiggle) on failure, or a
  status-bar message on success.
- **Structifact: Discover Dataset** — lets you pick an existing CSV or
  Excel file, runs `structifact discover <file>` against it, opens the
  resulting `.discovered.yml` draft, and tells you plainly whether any
  fields came back flagged for review.
- **Structifact: Generate** — runs `structifact generate <file> -g sql`
  against the currently open Structifact YAML file and opens the
  resulting `.sql` file.

Notes that apply to all three:

- No validation, discovery, or generation logic is duplicated in
  JavaScript — every rule check happens in `structifact/validation.py`,
  every type/format inference happens in `structifact/discover.py` and
  `structifact/types.py`, and SQL generation happens in
  `structifact/generators/sql.py`, invoked exactly as the CLI runs them.
- No line/column positions on Validate's diagnostics. `structifact
  validate`'s errors describe a field or constraint by name, not a
  source location (`validation.py` works on the parsed IR, which
  carries no YAML line/column data) — every diagnostic is anchored to
  the file's first line as a best-effort placeholder, not a real
  position.
- No YAML shape/schema validation here — that's already covered live by
  `schemas/structifact-dataset.schema.json` + the Red Hat YAML extension
  (see `.vscode/settings.json`). Validate covers the separate, larger
  rule set that requires actually running Structifact: cross-field and
  cross-reference checks (a join's `source` naming a real declared
  source, a foreign key's target, etc.) that a static JSON Schema can't
  express.
- Discover Dataset never passes `--ai` — it only runs the deterministic
  half of `structifact discover`. Picking an `.xlsx` file will fail with
  the CLI's own real "requires --ai" message (there's no deterministic
  way to parse a raw Excel/requirements file) — this is Structifact's
  actual, correct behavior surfaced as-is, not a bug in this extension.
- Generate always runs with `-g sql` — restricted to exactly one
  generator (out of the CLI's default three: sql/dbt/catalog) so there's
  exactly one unambiguous file to open, matching the "generate one real
  artifact" scope this whole workflow was built and proven against from
  the CLI. Output goes to `<file's directory>/generated/`, the same
  convention already used throughout this repo's own `examples/` and
  README.
- No graphical review UI, autocomplete, hover, navigation, or dependency
  visualization yet — see `docs/FUTURE_WORK.md`'s "IDE Integration"
  section for what might come after this, if it proves useful.

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

**Validate:**

3. In that new window, open any real dataset YAML file (e.g.
   `examples/customers.yml`), then run **Structifact: Validate** from the
   Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`).
4. Introduce a real validation error (not a YAML-shape one — the schema
   already catches those live) — e.g. a `foreign_key` constraint naming a
   column that doesn't exist as a field — save, and re-run the command to
   see it appear in the Problems panel.

**Discover Dataset:**

3. Run **Structifact: Discover Dataset** from the Command Palette.
4. In the file picker, choose a raw CSV file — e.g.
   `tests/fixtures/messy_orders.csv`, a genuinely messy fixture (mixed
   date formats, inconsistent currency formatting, zero-padded IDs).
5. The resulting `messy_orders.discovered.yml` opens automatically, and
   a notification reports whether any fields were flagged for review —
   for this fixture, a warning naming `order_id`, `order_date`, `amount`,
   and `zip_code`, each with a `NEEDS REVIEW` comment in the opened file
   explaining why.

**Generate:**

3. Open a real, valid Structifact dataset YAML file (e.g.
   `examples/customers.yml`), then run **Structifact: Generate** from
   the Command Palette.
4. The generated `customers.sql` opens automatically in
   `examples/generated/customers.sql`, alongside a confirmation
   notification.

## Tests

The pure logic (CLI-path resolution, output-path naming, parsing the
real CLI's stdout for its own flagged-fields and generated-artifact
lines) has a small, dependency-free test file — no
`@vscode/test-electron`, no real Extension Host, matching this
extension's zero-npm-dependency stance:

```bash
cd vscode-extension
npm test
```

This does not replace manually running the commands in a real
Extension Development Host — it only covers the logic that doesn't
need the real `vscode` API to be correct.
