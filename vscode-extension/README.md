# Structifact for VS Code

From messy spreadsheets and requirements docs to validated, generated artifacts — with a human in the loop at every step.

Structifact for VS Code brings that whole workflow into the editor: pick a messy input, let AI propose a first-pass draft when there's no deterministic way to read it, review and triage what it found, and generate real artifacts from what you've confirmed — all as thin, literal wrappers around the real [`structifact`](https://pypi.org/project/structifact/) CLI. No logic is duplicated in JavaScript; every check, inference, and generation step runs in the real engine, exactly as the CLI runs it.

## Requirements

Structifact itself needs to be installed (Python 3.11+) — but you don't have to do this yourself first. If the extension can't find it, the first command that needs it offers to install it for you: a dedicated, isolated environment (not your global Python, not an unrelated project's), with real progress shown at each step, and nothing wired up until the install is confirmed actually working. It's entirely optional — decline it and point `structifact.cliPath` at your own install instead (see **Settings** below).

AI-assisted discovery (see below) additionally needs an [Anthropic API key](https://console.anthropic.com) set as `ANTHROPIC_API_KEY` — only required at the moment you actually use it, never for Validate, Review, or Generate.

## Commands

### Structifact: Validate

Saves the active file if it has unsaved changes, runs `structifact validate` against it, and shows the result as native VS Code diagnostics — inline squiggles and Problems-panel entries on failure, a status-bar confirmation on success.

### Structifact: Discover Dataset

Pick a file to turn into a first-draft metadata definition:

- **CSV** — deterministic inference (column names, types, nullability). Anything the inference is genuinely unsure about is written into the draft with a `NEEDS REVIEW` comment explaining why, not silently guessed.
- **Requirements document (.md, .txt) or Excel (.xlsx)** — there's no deterministic way to read freeform text or a spreadsheet's layout, so this always uses AI. Before any request is sent, you see the CLI's own real cost estimate and a modal asking you to confirm — nothing is sent, and nothing is written, unless you explicitly approve. If you have a previously reviewed version of this same document saved nearby (see below), you're offered to include it as context first.

Either way, the resulting draft opens automatically and flows straight into Review.

### Structifact: Review

Runs `validate` against the currently open file and combines its findings with whatever the file's own text already flags — `NEEDS REVIEW` comments from CSV discovery, `unresolved_notes` from AI discovery — into one Quick Pick list, grouped by kind. Selecting an item jumps the editor to that line.

Note-shaped items carry an **Acknowledge** action: mark something as reviewed without changing the file at all — nothing gets written back to the YAML. Acknowledged items move into their own section, so you can always see what's actually still outstanding versus what you've already triaged.

### Structifact: Generate

Choose what to produce from the currently open, valid dataset definition:

- **SQL schema** — a `CREATE TABLE` definition for the target shape.
- **Transformation model** — the executable `SELECT` that actually implements the dataset's joins, dedup rules, and computed fields.
- **Both.**

Whatever's produced opens automatically. (A dataset with no joins, computed fields, filters, or renamed columns has nothing for the transformation model to add beyond the schema — you're told that plainly rather than seeing an error.)

## Reviewed-metadata context

If you've hand-corrected an AI-generated draft and saved it as `<document-name>.reviewed.yml` next to the original source document, the next time you run AI-assisted Discover Dataset on that same document, you'll be offered to include your corrected version as context — so the AI has a chance to build on your correction instead of starting from scratch. This is entirely additive: skip it, and discovery behaves exactly as it would without a reviewed file present.

## Settings

- **`structifact.cliPath`** — path to the Structifact CLI executable. You shouldn't normally need to set this: the extension checks this workspace's own `.venv/`/`venv/` folder, then an install it may have bootstrapped for you, before falling back to `PATH`. Set this explicitly only for an unusual setup — a differently-named or differently-located virtualenv, or an install you manage yourself.

---

## Development / Contributing

The sections above are what a Marketplace install needs. Everything below is for running this extension from source.

### Running it from source

1. Open the repo root (`structifact/`) as a VS Code workspace folder.
2. Press F5 (or Run → Start Debugging) — this uses the `Run Structifact: Validate extension` launch config in `.vscode/launch.json` to open a new Extension Development Host window with this extension loaded.
3. From that new window's Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`), the four commands above are available exactly as they would be from a Marketplace install.

A few real fixtures already in this repo are useful for trying each command:

- **Validate**: open `examples/customers.yml`, introduce a real validation error (e.g. a `foreign_key` naming a column that doesn't exist), save, and re-run.
- **Discover Dataset**: pick `tests/fixtures/messy_orders.csv` — a genuinely messy fixture (mixed date formats, inconsistent currency formatting, zero-padded IDs) that reliably produces real `NEEDS REVIEW` flags.
- **Generate**: run against `examples/customers.yml`.
- **Review**: run against the `messy_orders.discovered.yml` produced above (real findings to review), then again against a clean file like `examples/customers.yml` (the "nothing to flag" case).

### Tests

The pure logic — CLI-path resolution, output-path naming, parsing the real CLI's stdout, Quick Pick item construction, the CLI-bootstrap helpers — has two small, dependency-free test files. No `@vscode/test-electron`, no real Extension Host, matching this extension's zero-npm-dependency stance:

```bash
cd vscode-extension
npm test
```

This does not replace manually running the commands in a real Extension Development Host — it only covers the logic that doesn't need the real `vscode` API to be correct. Anything that depends on actual Quick Pick/dialog interaction, the real install flow, or real process spawning needs to be exercised by hand in a real Extension Host.
