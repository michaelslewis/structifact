const vscode = require('vscode');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');

// A project virtualenv's bin/ is only on PATH inside an activated
// shell -- VS Code does not activate it, so the bare "structifact"
// default fails for the common case of a workspace with its own
// .venv/venv (confirmed directly: this repo's own .venv hit exactly
// this, see DECISION_HISTORY.md). Only auto-detects when the user
// hasn't explicitly set structifact.cliPath themselves -- an
// explicit setting always wins, unchanged from before.
function resolveCliPath(workspaceFolder) {
  const config = vscode.workspace.getConfiguration('structifact');
  const inspected = config.inspect('cliPath');
  const explicitlySet = !!inspected && (
    inspected.workspaceFolderValue !== undefined ||
    inspected.workspaceValue !== undefined ||
    inspected.globalValue !== undefined
  );

  if (explicitlySet) {
    return config.get('cliPath');
  }

  if (workspaceFolder) {
    const isWindows = process.platform === 'win32';
    const candidates = ['.venv', 'venv'].map((dir) => path.join(
      workspaceFolder.uri.fsPath,
      dir,
      isWindows ? 'Scripts' : 'bin',
      isWindows ? 'structifact.exe' : 'structifact'
    ));

    for (const candidate of candidates) {
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    }
  }

  return config.get('cliPath', 'structifact');
}

// Shared across all three commands -- every one of them can hit this
// exact failure the same way (a bad/unset cliPath), so the message
// (and the fix it points at) should read identically everywhere.
function showCliNotFoundError(cliPath) {
  vscode.window.showErrorMessage(
    `Structifact: could not run "${cliPath}". Checked PATH and this workspace's ` +
    '.venv/venv, found nothing runnable there. Install Structifact ' +
    '(pip install structifact, or pip install -e . from a clone) so it is on your ' +
    'PATH, or set structifact.cliPath in Settings to point at it directly.'
  );
}

function activate(context) {
  const diagnostics = vscode.languages.createDiagnosticCollection('structifact');
  context.subscriptions.push(diagnostics);

  const disposable = vscode.commands.registerCommand('structifact.validate', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showErrorMessage('Structifact: Validate needs an open file.');
      return;
    }

    const document = editor.document;
    if (document.isUntitled) {
      vscode.window.showErrorMessage('Structifact: Validate needs a saved file.');
      return;
    }

    // structifact validate reads the file from disk, not the editor
    // buffer -- save first so the result matches what's on screen.
    if (document.isDirty) {
      await document.save();
    }

    const filePath = document.uri.fsPath;
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    const cliPath = resolveCliPath(workspaceFolder);
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(filePath);

    execFile(cliPath, ['validate', filePath], { cwd }, (error, stdout, stderr) => {
      if (!error) {
        diagnostics.delete(document.uri);
        vscode.window.setStatusBarMessage('Structifact: validation passed', 3000);
        return;
      }

      if (error.code === 'ENOENT') {
        showCliNotFoundError(cliPath);
        return;
      }

      const output = `${stdout || ''}${stderr || ''}`;
      diagnostics.set(
        document.uri,
        parseErrors(output).map((message) => makeDiagnostic(document, message))
      );
    });
  });

  context.subscriptions.push(disposable);

  const discoverDisposable = vscode.commands.registerCommand('structifact.discoverDataset', async () => {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    const defaultUri = workspaceFolders && workspaceFolders.length > 0
      ? workspaceFolders[0].uri
      : undefined;

    const picked = await vscode.window.showOpenDialog({
      canSelectMany: false,
      defaultUri,
      openLabel: 'Discover',
      filters: { 'CSV / Excel': ['csv', 'xlsx'] },
    });

    if (!picked || picked.length === 0) {
      return;
    }

    const inputUri = picked[0];
    const inputPath = inputUri.fsPath;
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(inputUri);
    const cliPath = resolveCliPath(workspaceFolder);
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(inputPath);
    const outputPath = discoveredOutputPath(inputPath);

    execFile(cliPath, ['discover', inputPath, '-o', outputPath], { cwd }, (error, stdout, stderr) => {
      if (error && error.code === 'ENOENT') {
        showCliNotFoundError(cliPath);
        return;
      }

      const output = `${stdout || ''}${stderr || ''}`;

      // structifact discover fails (non-CSV without --ai, no header
      // row, file not found, etc.) with a plain explanatory message
      // on stdout/stderr and a non-zero exit -- surface it as-is, the
      // same parser validate's failures already use, since neither
      // case has a "Validation failed:" marker to split on and both
      // just want "the meaningful lines of whatever came back".
      if (error) {
        vscode.window.showErrorMessage(
          `Structifact: discover failed for ${path.basename(inputPath)} — ` +
          parseErrors(output).join(' ')
        );
        return;
      }

      const flagLine = extractFlagLine(output);

      vscode.workspace.openTextDocument(outputPath).then((doc) => {
        vscode.window.showTextDocument(doc);

        if (flagLine) {
          vscode.window.showWarningMessage(
            `Structifact: ${flagLine.trim()} — see the NEEDS REVIEW comments in the opened draft.`
          );
        } else {
          vscode.window.showInformationMessage(
            `Structifact: discovered ${path.basename(outputPath)} — no fields flagged for review.`
          );
        }
      });
    });
  });

  context.subscriptions.push(discoverDisposable);

  const generateDisposable = vscode.commands.registerCommand('structifact.generate', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showErrorMessage('Structifact: Generate needs an open file.');
      return;
    }

    const document = editor.document;
    if (document.isUntitled) {
      vscode.window.showErrorMessage('Structifact: Generate needs a saved file.');
      return;
    }

    // structifact generate reads the file from disk, not the editor
    // buffer -- save first so the result matches what's on screen
    // (same reasoning as Validate).
    if (document.isDirty) {
      await document.save();
    }

    const filePath = document.uri.fsPath;
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    const cliPath = resolveCliPath(workspaceFolder);
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(filePath);

    // Restricted to -g sql so exactly one artifact comes back, with
    // an unambiguous file to open -- the default generator set (sql,
    // dbt, catalog) would produce three, and this command's job is
    // "generate one real artifact," matching the workflow already
    // proven from the CLI. Written to <file's dir>/generated/,
    // matching the convention already used throughout this repo's
    // own examples/ and README (see e.g. `structifact generate
    // examples/customers/customers.yml -o examples/customers/generated`).
    const outputDir = path.join(path.dirname(filePath), 'generated');

    execFile(cliPath, ['generate', filePath, '-g', 'sql', '-o', outputDir], { cwd }, (error, stdout, stderr) => {
      if (error && error.code === 'ENOENT') {
        showCliNotFoundError(cliPath);
        return;
      }

      const output = `${stdout || ''}${stderr || ''}`;

      // generate() calls validate_table() before generating anything,
      // so a metadata error here produces the exact same "Validation
      // failed:" shape Validate's own failures do -- and a missing
      // file produces the same "File not found:" shape Discover's
      // does. Both already parse correctly with the existing,
      // unmodified parseErrors().
      if (error) {
        vscode.window.showErrorMessage(
          `Structifact: generate failed for ${path.basename(filePath)} — ` +
          parseErrors(output).join(' ')
        );
        return;
      }

      const artifactPath = extractGeneratedArtifactPath(output);

      if (!artifactPath) {
        vscode.window.showErrorMessage(
          `Structifact: generate for ${path.basename(filePath)} reported success but no ` +
          'generated SQL file path — this should not happen; see the Output panel for the raw result.'
        );
        return;
      }

      vscode.workspace.openTextDocument(artifactPath).then((doc) => {
        vscode.window.showTextDocument(doc);
        vscode.window.showInformationMessage(`Structifact: generated ${path.basename(artifactPath)}.`);
      });
    });
  });

  context.subscriptions.push(generateDisposable);

  const reviewDisposable = vscode.commands.registerCommand('structifact.review', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showErrorMessage('Structifact: Review needs an open file.');
      return;
    }

    const document = editor.document;
    if (document.isUntitled) {
      vscode.window.showErrorMessage('Structifact: Review needs a saved file.');
      return;
    }

    if (document.isDirty) {
      await document.save();
    }

    const filePath = document.uri.fsPath;
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    const cliPath = resolveCliPath(workspaceFolder);
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(filePath);

    execFile(cliPath, ['validate', filePath], { cwd }, (error, stdout, stderr) => {
      // The NEEDS REVIEW / unresolved_notes half of this command comes
      // from the document's own text, not the CLI -- still useful even
      // if the CLI can't be found at all, so this doesn't return early.
      if (error && error.code === 'ENOENT') {
        showCliNotFoundError(cliPath);
      }

      const output = `${stdout || ''}${stderr || ''}`;
      const cliRanSuccessfully = !error;
      const cliMissing = !!error && error.code === 'ENOENT';

      const errorMessages = error && !cliMissing ? parseErrors(output) : [];
      const warningMessages = !cliMissing ? parseWarnings(output) : [];

      // Same diagnostics collection Validate itself uses -- Review
      // running validate under the hood should leave the Problems
      // panel/inline squiggles in the same state Validate would.
      if (cliMissing) {
        // leave existing diagnostics alone; we don't know anything new
      } else if (cliRanSuccessfully) {
        diagnostics.delete(document.uri);
      } else {
        diagnostics.set(
          document.uri,
          errorMessages.map((message) => makeDiagnostic(document, message))
        );
      }

      const text = document.getText();
      const needsReviewItems = findNeedsReviewItems(text);
      const unresolvedNotes = findUnresolvedNotes(text);

      const items = [];

      if (errorMessages.length > 0) {
        items.push({ label: 'Errors', kind: vscode.QuickPickItemKind.Separator });
        for (const message of errorMessages) {
          items.push({ label: `$(error) ${message}`, line: 0 });
        }
      }

      if (warningMessages.length > 0) {
        items.push({ label: 'Warnings', kind: vscode.QuickPickItemKind.Separator });
        for (const message of warningMessages) {
          items.push({ label: `$(warning) ${message}`, line: 0 });
        }
      }

      if (needsReviewItems.length > 0) {
        items.push({ label: 'NEEDS REVIEW (in this file)', kind: vscode.QuickPickItemKind.Separator });
        for (const item of needsReviewItems) {
          items.push({
            label: `$(comment) ${item.text}`,
            description: `line ${item.line + 1}`,
            line: item.line,
          });
        }
      }

      if (unresolvedNotes.length > 0) {
        items.push({ label: 'Unresolved Notes', kind: vscode.QuickPickItemKind.Separator });
        for (const item of unresolvedNotes) {
          items.push({
            label: `$(note) ${item.text}`,
            description: `line ${item.line + 1}`,
            line: item.line,
          });
        }
      }

      if (items.length === 0) {
        vscode.window.showInformationMessage(
          cliMissing
            ? 'Structifact: Review — could not run validate (see error above); nothing found in the file itself either.'
            : 'Structifact: Review — nothing to flag. No validate errors/warnings, no NEEDS REVIEW comments, no unresolved_notes.'
        );
        return;
      }

      const summaryParts = [];
      if (errorMessages.length) summaryParts.push(`${errorMessages.length} error(s)`);
      if (warningMessages.length) summaryParts.push(`${warningMessages.length} warning(s)`);
      if (needsReviewItems.length) summaryParts.push(`${needsReviewItems.length} needs-review`);
      if (unresolvedNotes.length) summaryParts.push(`${unresolvedNotes.length} unresolved note(s)`);

      vscode.window.showQuickPick(items, {
        placeHolder: `Structifact: Review — ${summaryParts.join(', ')} (select to jump to it)`,
        matchOnDescription: true,
      }).then(async (selected) => {
        if (!selected || typeof selected.line !== 'number') {
          return;
        }

        const targetLine = Math.min(selected.line, document.lineCount - 1);
        const revealedEditor = await vscode.window.showTextDocument(document, {
          viewColumn: editor.viewColumn,
          preserveFocus: false,
        });
        const range = revealedEditor.document.lineAt(targetLine).range;
        revealedEditor.selection = new vscode.Selection(range.start, range.start);
        revealedEditor.revealRange(range, vscode.TextEditorRevealType.InCenter);
      });
    });
  });

  context.subscriptions.push(reviewDisposable);
}

// Matches structifact discover's own default output naming
// (DiscoveredDataset.name + ".discovered.yml" in discover.py) --
// passed explicitly via -o so the extension knows exactly where the
// file landed without parsing it back out of stdout.
function discoveredOutputPath(inputPath) {
  const base = path.basename(inputPath, path.extname(inputPath));
  return path.join(path.dirname(inputPath), `${base}.discovered.yml`);
}

// generate -g sql prints exactly one "--- GENERATED ARTIFACTS ---"
// line ("- <path>") once validation passes, since SQLGenerator (unlike
// e.g. ModelGenerator) always produces something for a valid dataset
// -- extracted verbatim from real stdout rather than reconstructing
// the path from the input filename, which would silently break for
// any YAML file whose dataset.name differs from its own filename.
function extractGeneratedArtifactPath(output) {
  const line = output.split('\n').find((l) => /^- .+\.sql$/.test(l.trim()));
  return line ? line.trim().slice(2).trim() : undefined;
}

// discover itself already computes and prints this exact line (see
// flagged_fields() in structifact/discover.py / structifact/cli.py)
// -- extracted verbatim from its stdout rather than re-deriving which
// fields were flagged from the rendered YAML.
function extractFlagLine(output) {
  return output.split('\n').find((line) => line.trim().startsWith('⚠'));
}

// structifact validate carries no line/column information -- errors
// describe a field or constraint by name, not a source position (see
// structifact/validation.py, which works on the parsed IR, not the
// raw YAML). Parsing here only splits the CLI's "Validation failed:"
// block into one message per line; it does not re-derive or duplicate
// any of validate_table()'s own rule logic.
//
// A dataset can have both hard errors and warnings at once (see
// ValidationError.warnings in structifact/validation.py) -- the CLI
// appends a "⚠ N warning(s):" section after the errors in that case,
// which must be excluded here or every warning bullet would be
// parsed as if it were a separate error too (found while building
// Structifact: Review, which needed errors and warnings kept
// genuinely separate; see parseWarnings below for the other half of
// this same output).
function parseErrors(output) {
  const marker = 'Validation failed:';
  const markerIndex = output.indexOf(marker);
  let body = markerIndex >= 0 ? output.slice(markerIndex + marker.length) : output;

  const warningMarkerIndex = body.indexOf('⚠');
  if (warningMarkerIndex >= 0) {
    body = body.slice(0, warningMarkerIndex);
  }

  const lines = body
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  return lines.length > 0
    ? lines
    : [output.trim() || 'structifact validate failed with no output.'];
}

// The other half of parseErrors' split: extracts each "  - <text>"
// bullet under the CLI's own "⚠ N warning(s):" section (see
// structifact/cli.py's _print_warnings()) -- present whether or not
// the same output also has hard errors. Returns [] when there's no
// such section at all.
function parseWarnings(output) {
  const markerMatch = output.match(/⚠\s*\d+\s*warning\(s\):/);
  if (!markerMatch) {
    return [];
  }

  const body = output.slice(markerMatch.index + markerMatch[0].length);

  return body
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('- '))
    .map((line) => line.slice(2).trim());
}

// Scans a document's own text for "NEEDS REVIEW" comment lines -- the
// exact format render_draft_yaml() writes in structifact/discover.py
// ("# ⚠ NEEDS REVIEW: <reason>"), one per field discover flagged as
// uncertain. Pure text scanning, not YAML parsing -- these are YAML
// comments, invisible to any real parser anyway. Takes and returns
// plain data (the document's full text in, {line, text} pairs out,
// 0-indexed to match TextDocument.lineAt/vscode.Position) rather than
// a live vscode.TextDocument, matching every other parse function in
// this file -- keeps this testable without the real vscode API.
function findNeedsReviewItems(text) {
  const items = [];
  const lines = text.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(/NEEDS REVIEW:\s*(.+?)\s*$/);
    if (match) {
      items.push({ line: i, text: match[1] });
    }
  }

  return items;
}

// Scans a document's own text for a top-level `unresolved_notes:`
// list and extracts each entry -- the exact shape
// render_requirements_draft_yaml() writes in
// structifact/discover.py: a plain top-level YAML list, each entry a
// JSON-string-syntax double-quoted scalar (structifact/discover.py's
// _yaml_str() renders every note via json.dumps(), specifically so
// this is valid YAML *and* trivially decodable here via the real,
// built-in JSON.parse() -- no YAML library needed for this one,
// narrow, self-controlled shape). Line-based, best-effort text
// scanning otherwise, same posture as findNeedsReviewItems above --
// not a general YAML parser, only handles the one shape Structifact's
// own generator actually produces. Falls back to the raw line text if
// a note was hand-edited into something JSON.parse can't decode.
function findUnresolvedNotes(text) {
  const items = [];
  const lines = text.split('\n');
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (/^unresolved_notes:\s*$/.test(line)) {
      inList = true;
      continue;
    }

    if (!inList) {
      continue;
    }

    const match = line.match(/^\s*-\s*(.+?)\s*$/);
    if (match) {
      const raw = match[1];
      let decoded = raw;
      if (raw.startsWith('"')) {
        try {
          decoded = JSON.parse(raw);
        } catch (e) {
          decoded = raw;
        }
      }
      items.push({ line: i, text: decoded });
    } else if (line.trim() !== '') {
      break; // a non-list, non-blank line ends the unresolved_notes block
    }
  }

  return items;
}

function makeDiagnostic(document, message) {
  const range = document.lineCount > 0
    ? document.lineAt(0).range
    : new vscode.Range(0, 0, 0, 1);

  const diagnostic = new vscode.Diagnostic(range, message, vscode.DiagnosticSeverity.Error);
  diagnostic.source = 'Structifact';
  return diagnostic;
}

function deactivate() {}

module.exports = { activate, deactivate };
