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
        vscode.window.showErrorMessage(
          `Structifact: could not run "${cliPath}". Checked PATH and this workspace's ` +
          '.venv/venv, found nothing runnable there. Install Structifact ' +
          '(pip install structifact, or pip install -e . from a clone) so it is on your ' +
          'PATH, or set structifact.cliPath in Settings to point at it directly.'
        );
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
        vscode.window.showErrorMessage(
          `Structifact: could not run "${cliPath}". Checked PATH and this workspace's ` +
          '.venv/venv, found nothing runnable there. Install Structifact ' +
          '(pip install structifact, or pip install -e . from a clone) so it is on your ' +
          'PATH, or set structifact.cliPath in Settings to point at it directly.'
        );
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
}

// Matches structifact discover's own default output naming
// (DiscoveredDataset.name + ".discovered.yml" in discover.py) --
// passed explicitly via -o so the extension knows exactly where the
// file landed without parsing it back out of stdout.
function discoveredOutputPath(inputPath) {
  const base = path.basename(inputPath, path.extname(inputPath));
  return path.join(path.dirname(inputPath), `${base}.discovered.yml`);
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
function parseErrors(output) {
  const marker = 'Validation failed:';
  const markerIndex = output.indexOf(marker);
  const body = markerIndex >= 0 ? output.slice(markerIndex + marker.length) : output;

  const lines = body
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  return lines.length > 0
    ? lines
    : [output.trim() || 'structifact validate failed with no output.'];
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
