const vscode = require('vscode');
const { execFile } = require('child_process');
const path = require('path');

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
    const cliPath = vscode.workspace.getConfiguration('structifact').get('cliPath', 'structifact');
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(filePath);

    execFile(cliPath, ['validate', filePath], { cwd }, (error, stdout, stderr) => {
      if (!error) {
        diagnostics.delete(document.uri);
        vscode.window.setStatusBarMessage('Structifact: validation passed', 3000);
        return;
      }

      if (error.code === 'ENOENT') {
        vscode.window.showErrorMessage(
          `Structifact: could not run "${cliPath}". Set structifact.cliPath in Settings, ` +
          'or install Structifact (pip install -e .) so it is on your PATH.'
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
