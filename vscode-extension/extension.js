const vscode = require('vscode');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const {
  MIN_PYTHON_VERSION,
  INSTALLED_CLI_PATH_KEY,
  looksLikeMissingExcelExtra,
  installStructifact,
  installExcelExtra,
} = require('./bootstrap');

// Where Review's "Acknowledge" state lives (see buildReviewQuickPickItems
// and noteAcknowledgeKey/relatedAcknowledgeKey below) -- workspaceState,
// not the file itself: acknowledging a note never writes YAML, and
// workspace-scoped (not global) so acknowledgments from one project's
// review session don't leak into an unrelated one.
const ACKNOWLEDGED_NOTES_STATE_KEY = 'structifact.acknowledgedNotes';

function getAcknowledgedKeys(context) {
  return new Set(context.workspaceState.get(ACKNOWLEDGED_NOTES_STATE_KEY, []));
}

async function acknowledgeNote(context, ackKey) {
  const keys = getAcknowledgedKeys(context);
  keys.add(ackKey);
  await context.workspaceState.update(ACKNOWLEDGED_NOTES_STATE_KEY, Array.from(keys));
}

// A project virtualenv's bin/ is only on PATH inside an activated
// shell -- VS Code does not activate it, so the bare "structifact"
// default fails for the common case of a workspace with its own
// .venv/venv (confirmed directly: this repo's own .venv hit exactly
// this, see DECISION_HISTORY.md). Only auto-detects when the user
// hasn't explicitly set structifact.cliPath themselves -- an
// explicit setting always wins, unchanged from before.
//
// `installedFallbackPath`, when given, is a THIRD, lowest-priority
// tier (below an explicit setting and a workspace .venv/venv, above
// bare "structifact" on PATH) -- the path this extension's own
// bootstrap install (bootstrap.js) wrote to context.globalState.
// Deliberately NOT read from the structifact.cliPath *setting*
// itself: writing the bootstrapped path there would make it
// "explicitly set" for every future workspace, silently outranking
// this exact .venv/venv check above for anyone who already has a
// real per-project venv. Checked with fs.existsSync the same way the
// workspace venv candidates are, in case the bootstrapped venv was
// since deleted.
function resolveCliPath(workspaceFolder, installedFallbackPath) {
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

  if (installedFallbackPath && fs.existsSync(installedFallbackPath)) {
    return installedFallbackPath;
  }

  return config.get('cliPath', 'structifact');
}

// Maps one bootstrap.js install-attempt result to a specific, honest
// message -- never a generic "install failed". `stderr`, when
// present, is real captured output from the real pip/venv command
// that failed (truncated to its last few lines) -- this is the one
// thing that can say something useful about a corporate-managed
// machine blocking pip, a proxy, or any other failure this code has
// no specific name for.
function showInstallFailureMessage(result) {
  if (result.reason === 'not-found') {
    vscode.window.showErrorMessage(
      'Structifact: could not find a Python interpreter anywhere on PATH (or via the ' +
      'VS Code Python extension, if installed). Install Python ' +
      `${MIN_PYTHON_VERSION.major}.${MIN_PYTHON_VERSION.minor}+ from python.org, then try ` +
      'again -- or, if Structifact is already installed somewhere, set structifact.cliPath ' +
      'in Settings to point at it directly.'
    );
    return;
  }

  if (result.reason === 'too-old') {
    const found = (result.attempted || [])
      .map((a) => `${a.command} (${a.version.major}.${a.version.minor})`)
      .join(', ') || 'none parseable';
    vscode.window.showErrorMessage(
      'Structifact: found Python, but none new enough (Structifact needs ' +
      `${MIN_PYTHON_VERSION.major}.${MIN_PYTHON_VERSION.minor}+; found: ${found}). Install a ` +
      'newer Python from python.org and try again.'
    );
    return;
  }

  const stderrExcerpt = (result.stderr || '').split('\n').slice(-8).join('\n').trim();
  const detail = stderrExcerpt ? `\n\nLast output:\n${stderrExcerpt}` : '';
  const fallback = 'You can set structifact.cliPath in Settings to point at an install of ' +
    'your own instead — see this extension\'s README.';

  if (result.reason === 'verify-failed') {
    vscode.window.showErrorMessage(
      `Structifact: installed, but could not confirm it runs correctly, so nothing was ` +
      `wired up. ${fallback}${detail}`
    );
    return;
  }

  // install-failed or venv-failed: nothing was left behind either
  // way (see runVenvInstall in bootstrap.js) -- covers no network,
  // no permission to write/install, and a corporate-managed machine
  // blocking pip alike, since none of those can be distinguished
  // reliably from pip's own error text alone.
  vscode.window.showErrorMessage(
    `Structifact: install failed (no network connection and a machine that blocks package ` +
    `installs are both common causes). Nothing was left behind. ${fallback}${detail}`
  );
}

// Offers to install Structifact when the configured CLI can't be
// run at all (see the ENOENT checks below) -- never automatic, per
// the "state cost/confirm before any real action" posture this
// extension already applies to real API calls (runAiDiscover). On
// acceptance, runs bootstrap.js's real install flow inside a native
// progress notification with honest, specific step messages; nothing
// is reported as successful until installStructifact's own
// `structifact --help` verification actually passes.
async function handleCliNotFound(cliPath, context) {
  const choice = await vscode.window.showErrorMessage(
    `Structifact: could not run "${cliPath}". Checked PATH and this workspace's .venv/venv, ` +
    'found nothing runnable there.',
    'Install Structifact',
    'Set Path Manually'
  );

  if (choice === 'Set Path Manually') {
    await vscode.commands.executeCommand('workbench.action.openSettings', 'structifact.cliPath');
    return;
  }

  if (choice !== 'Install Structifact') {
    return;
  }

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'Structifact', cancellable: false },
    async (progress) => {
      const report = (message) => progress.report({ message });
      const result = await installStructifact({ context, report });

      if (result.success) {
        vscode.window.showInformationMessage(
          `Structifact: installed successfully at ${result.cliPath}. Run the command again.`
        );
        return;
      }

      showInstallFailureMessage(result);
    }
  );
}

// The deferred, explicitly-prompted follow-up for .xlsx discovery
// specifically (see runAiDiscover below) -- only ever offered when
// the CLI actually in use is this extension's own bootstrapped
// install (checked at the call site), since this extension has no
// business pip-installing into a venv/interpreter it didn't create.
async function offerExcelExtraInstall(context, inputPath) {
  const choice = await vscode.window.showWarningMessage(
    `Structifact: reading ${path.basename(inputPath)} needs the 'excel' extra (~110MB more, ` +
    'via pandas) on top of the base install. Install it now?',
    'Install',
    'Not now'
  );

  if (choice !== 'Install') {
    return;
  }

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'Structifact', cancellable: false },
    async (progress) => {
      const report = (message) => progress.report({ message });
      const result = await installExcelExtra({ context, report });

      if (result.success) {
        vscode.window.showInformationMessage(
          "Structifact: the 'excel' extra is installed. Try discovering this file again."
        );
        return;
      }

      showInstallFailureMessage(result);
    }
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
    const cliPath = resolveCliPath(workspaceFolder, context.globalState.get(INSTALLED_CLI_PATH_KEY));
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(filePath);

    execFile(cliPath, ['validate', filePath], { cwd }, (error, stdout, stderr) => {
      if (!error) {
        diagnostics.delete(document.uri);
        vscode.window.setStatusBarMessage('Structifact: validation passed', 3000);
        return;
      }

      if (error.code === 'ENOENT') {
        handleCliNotFound(cliPath, context);
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
      filters: { 'CSV / Excel / Requirements (.md, .txt)': ['csv', 'xlsx', 'md', 'txt'] },
    });

    if (!picked || picked.length === 0) {
      return;
    }

    const inputUri = picked[0];
    const inputPath = inputUri.fsPath;
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(inputUri);
    const cliPath = resolveCliPath(workspaceFolder, context.globalState.get(INSTALLED_CLI_PATH_KEY));
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(inputPath);
    const outputPath = discoveredOutputPath(inputPath);

    // .md/.txt/.xlsx route to discover_requirements() in
    // structifact/cli.py, which always requires --ai -- there is no
    // deterministic half for a requirements document (no data rows
    // to sample). A separate branch, not a change to the CSV path
    // below, which is completely untouched.
    if (isRequirementsDocument(inputPath)) {
      await runAiDiscover({ cliPath, cwd, inputPath, outputPath, context });
      return;
    }

    execFile(cliPath, ['discover', inputPath, '-o', outputPath], { cwd }, (error, stdout, stderr) => {
      if (error && error.code === 'ENOENT') {
        handleCliNotFound(cliPath, context);
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
    const cliPath = resolveCliPath(workspaceFolder, context.globalState.get(INSTALLED_CLI_PATH_KEY));
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
        handleCliNotFound(cliPath, context);
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
    const cliPath = resolveCliPath(workspaceFolder, context.globalState.get(INSTALLED_CLI_PATH_KEY));
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(filePath);

    execFile(cliPath, ['validate', filePath], { cwd }, (error, stdout, stderr) => {
      // The NEEDS REVIEW / unresolved_notes half of this command comes
      // from the document's own text, not the CLI -- still useful even
      // if the CLI can't be found at all, so this doesn't return early.
      if (error && error.code === 'ENOENT') {
        handleCliNotFound(cliPath, context);
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
      const relatedNotes = findRelatedNotes(text);

      // Group findRelatedNotes' flat (note, declaration) pairs back
      // up by the declaration -- surfaced as one Quick Pick row per
      // field/source/join that has at least one linked note, rather
      // than the reviewer having to notice the name match themselves
      // while reading the Unresolved Notes section above. Selecting a
      // row jumps to the first linked note (the actionable next
      // step); the description shows where the field/source/join
      // itself is declared.
      const relatedGroups = new Map();
      for (const link of relatedNotes) {
        const key = `${link.kind}|${link.name}|${link.declarationLine}`;
        if (!relatedGroups.has(key)) {
          relatedGroups.set(key, {
            kind: link.kind,
            name: link.name,
            declarationLine: link.declarationLine,
            noteLines: [],
          });
        }
        relatedGroups.get(key).noteLines.push(link.noteLine);
      }

      const relatedGroupsArray = Array.from(relatedGroups.values());
      const buildItems = () => buildReviewQuickPickItems({
        errorMessages,
        warningMessages,
        needsReviewItems,
        unresolvedNotes,
        relatedGroups: relatedGroupsArray,
        acknowledgedKeys: getAcknowledgedKeys(context),
      });

      const items = buildItems();

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
      if (relatedGroupsArray.length) summaryParts.push(`${relatedGroupsArray.length} note link(s)`);

      const jumpToLine = async (line) => {
        const targetLine = Math.min(line, document.lineCount - 1);
        const revealedEditor = await vscode.window.showTextDocument(document, {
          viewColumn: editor.viewColumn,
          preserveFocus: false,
        });
        const range = revealedEditor.document.lineAt(targetLine).range;
        revealedEditor.selection = new vscode.Selection(range.start, range.start);
        revealedEditor.revealRange(range, vscode.TextEditorRevealType.InCenter);
      };

      // createQuickPick(), not the simpler showQuickPick() this command
      // used before -- only the lower-level API fires
      // onDidTriggerItemButton, which the Acknowledge button needs.
      // Rebuilding and reassigning .items after an acknowledgment keeps
      // this same still-open session in sync too, not just future runs.
      const quickPick = vscode.window.createQuickPick();
      quickPick.items = items;
      quickPick.placeholder = `Structifact: Review — ${summaryParts.join(', ')} (select to jump to it)`;
      quickPick.matchOnDescription = true;

      quickPick.onDidTriggerItemButton(async (event) => {
        if (!event.item || !event.item.ackKey) {
          return;
        }
        await acknowledgeNote(context, event.item.ackKey);
        quickPick.items = buildItems();
      });

      quickPick.onDidAccept(async () => {
        const selected = quickPick.selectedItems[0];
        quickPick.hide();

        if (!selected || typeof selected.line !== 'number') {
          return;
        }

        await jumpToLine(selected.line);
      });

      quickPick.onDidHide(() => quickPick.dispose());

      quickPick.show();
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

// .md/.txt/.xlsx route to discover_requirements() in
// structifact/cli.py, which always requires --ai -- there is no
// deterministic half for a requirements document (no data rows to
// sample). .csv keeps using the existing deterministic-by-default
// path in the command above, completely unchanged.
function isRequirementsDocument(inputPath) {
  return /\.(md|txt|xlsx)$/i.test(inputPath);
}

// Runs `structifact discover <path> --ai -o <path>` WITHOUT -y, reads
// the CLI's own real cost estimate off its live stdout (the exact
// "Estimate: ..." line AnthropicLLMClient.estimate_cost() produces),
// and shows it in a modal VS Code dialog *before* writing "y"/"n" to
// the child process's stdin -- the same y/N prompt a real terminal
// user would answer, answered through native VS Code UI instead of a
// terminal this extension has no way to render. No cost-estimation
// logic is duplicated in JavaScript; the number always comes from the
// real CLI, read off its real output, never recomputed here.
//
// Confirmed directly before building this (see DECISION_HISTORY.md):
// the estimate line reliably streams through execFile's own returned
// ChildProcess handle in well under a second, even without forcing
// unbuffered Python output -- verified against real .md and real
// .xlsx requirements documents, declining each time (zero cost, zero
// API calls, nothing written), before this code existed at all.
function runAiDiscover({ cliPath, cwd, inputPath, outputPath, context }) {
  return new Promise((resolve) => {
    let buffer = '';
    let responded = false;
    let declined = false;

    const timeout = setTimeout(() => {
      if (!responded) {
        responded = true;
        vscode.window.showErrorMessage(
          `Structifact: discover --ai for ${path.basename(inputPath)} never reached its ` +
          'cost estimate within 20s.'
        );
        child.kill();
      }
    }, 20000);

    const child = execFile(
      cliPath,
      ['discover', inputPath, '--ai', '-o', outputPath],
      { cwd },
      (error, stdout, stderr) => {
        clearTimeout(timeout);

        if (error && error.code === 'ENOENT') {
          handleCliNotFound(cliPath, context);
          resolve();
          return;
        }

        if (declined) {
          vscode.window.showInformationMessage(
            'Structifact: discover skipped — no AI request made, nothing written.'
          );
          resolve();
          return;
        }

        const output = `${stdout || ''}${stderr || ''}`;

        // A missing 'excel' extra is a specific, actionable case --
        // offer the same explicit-confirmation install flow as a
        // missing CLI, but only when the CLI actually in use is this
        // extension's own bootstrapped venv (checked against the
        // same globalState key handleCliNotFound's install writes to)
        // -- this extension has no business pip-installing into a
        // venv/interpreter it didn't create itself.
        if (
          error &&
          looksLikeMissingExcelExtra(output) &&
          context &&
          cliPath === context.globalState.get(INSTALLED_CLI_PATH_KEY)
        ) {
          offerExcelExtraInstall(context, inputPath);
          resolve();
          return;
        }

        // Covers both "failed after a real attempt" and "closed
        // before ever reaching the estimate line at all" (e.g. a
        // missing ANTHROPIC_API_KEY) -- either way, the same parser
        // every other command's failures already use.
        if (error) {
          vscode.window.showErrorMessage(
            `Structifact: discover failed for ${path.basename(inputPath)} — ` +
            parseErrors(output).join(' ')
          );
          resolve();
          return;
        }

        vscode.workspace.openTextDocument(outputPath).then(async (doc) => {
          await vscode.window.showTextDocument(doc);

          // Chains directly into the already-built Review command --
          // it re-runs validate and combines errors/warnings/
          // unresolved_notes into one Quick Pick; nothing about that
          // is re-implemented here.
          await vscode.commands.executeCommand('structifact.review');
          resolve();
        });
      }
    );

    child.stdout.on('data', (chunk) => {
      buffer += chunk.toString();

      if (responded) {
        return;
      }

      const match = buffer.match(/Estimate:\s*(.+)/);
      if (!match) {
        return;
      }

      responded = true;
      clearTimeout(timeout);

      vscode.window.showWarningMessage(
        `Structifact: AI-assisted extraction for ${path.basename(inputPath)} — ` +
        `${match[1].trim()}. Proceed with this real API call?`,
        { modal: true },
        'Proceed'
      ).then((choice) => {
        if (choice === 'Proceed') {
          child.stdin.write('y\n');
        } else {
          declined = true;
          child.stdin.write('n\n');
        }
      });
    });
  });
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

// Scans a document's own text for where each field/source/join is
// DECLARED -- same lightweight text-scanning posture as
// findNeedsReviewItems/findUnresolvedNotes above, tracking which
// top-level YAML section (fields:/sources:/joins:/etc.) each line
// falls under by watching for an unindented "<word>:" header line,
// the same shape render_requirements_draft_yaml()/render_draft_yaml()
// always emit those top-level keys in (see discover.py). Not a real
// YAML parser -- only recognizes the exact declaration shapes those
// two renderers actually produce:
//   fields:   "  - name: <value>"
//   sources:  "  - name: <value>" (the source's own logical alias),
//             plus a same-block "    table: <value>" (the physical
//             table name) folded into the SAME declaration rather
//             than a second one -- a note mentioning either name is
//             evidence about the same source, and findRelatedNotes
//             below should link both back to one place, not two.
//   joins:    "  - source: <value>" (the sources[].name being joined
//             in here)
function findDeclaredNames(text) {
  const declarations = [];
  const lines = text.split('\n');
  let section = null;
  let pendingSource = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    const sectionHeader = line.match(/^([A-Za-z_][A-Za-z0-9_]*):\s*$/);
    if (sectionHeader) {
      section = sectionHeader[1];
      pendingSource = null;
      continue;
    }

    if (section === 'fields') {
      const match = line.match(/^\s*-\s*name:\s*"?([A-Za-z0-9_]+)"?\s*$/);
      if (match) {
        declarations.push({ name: match[1], kind: 'field', line: i });
      }
    } else if (section === 'sources') {
      const nameMatch = line.match(/^\s*-\s*name:\s*"?([A-Za-z0-9_]+)"?\s*$/);
      if (nameMatch) {
        pendingSource = { name: nameMatch[1], kind: 'source', line: i };
        declarations.push(pendingSource);
        continue;
      }

      const tableMatch = line.match(/^\s*table:\s*"?([A-Za-z0-9_]+)"?\s*$/);
      if (tableMatch && pendingSource) {
        pendingSource.table = tableMatch[1];
      }
    } else if (section === 'joins') {
      const match = line.match(/^\s*-\s*source:\s*"?([A-Za-z0-9_]+)"?\s*$/);
      if (match) {
        declarations.push({ name: match[1], kind: 'join', line: i });
      }
    }
  }

  return declarations;
}

// True if `decl` (a field/source/join declaration from
// findDeclaredNames) is mentioned by name in `noteText` -- whole-word,
// case-insensitive. Whole-word matters: a real unresolved_notes entry
// referencing "struct_lfb1_mandt" (a compound descriptive term, not a
// real declared identifier) must NOT be treated as a mention of the
// real declared source "lfb1" just because it appears as a substring
// -- confirmed against a real note in output/Vendors.discovered.yml
// that does exactly this (see findRelatedNotes' own tests).
function _declarationMentionedIn(decl, noteText) {
  const candidates = decl.table ? [decl.name, decl.table] : [decl.name];
  return candidates.some((candidate) => new RegExp(`\\b${candidate}\\b`, 'i').test(noteText));
}

// Investigation finding #5 (see DECISION_HISTORY.md): rather than
// asking the AI to self-report provenance (a prompt/IR change, out of
// scope here), an unresolved_notes entry can very often be linked
// back to the specific field/source/join it's actually about
// deterministically, because the AI's own note text already names it
// -- confirmed against three real, independently-discovered problem
// drafts before this was written: examples/workorder_demo (a note
// naming "labor_amount_usd", the field whose expression references
// the undefined resolved_fx_rate), examples/coverage_round1's
// hard_insurance_claims (a note naming "policy_status", both the
// declared source and the join pulling it in), and this repo's own
// output/Vendors.discovered.yml (a note naming "ADRC", the source
// carrying a filter whose exact logic the AI says it interpreted
// rather than read verbatim).
//
// Deliberately does not attempt to link a note that names nothing
// declared (a real, unlinkable case exists in that same Vendors.xlsx
// draft — see this function's tests) -- no fallback guess, matching
// every other best-effort text scan in this file: silence here means
// "no name match found", not "nothing to review".
function findRelatedNotes(text) {
  const declarations = findDeclaredNames(text).filter((d) => d.name.length >= 3);
  const notes = findUnresolvedNotes(text);

  const links = [];
  for (const note of notes) {
    for (const decl of declarations) {
      if (_declarationMentionedIn(decl, note.text)) {
        links.push({
          name: decl.name,
          kind: decl.kind,
          declarationLine: decl.line,
          noteLine: note.line,
          noteText: note.text,
        });
      }
    }
  }

  return links;
}

// Tooltip shown on the per-item "Acknowledge" button in Review's
// Unresolved Notes / Related to Unresolved Notes sections --
// deliberately not "Accept" or "Resolve": acknowledging a note only
// records that a human has looked at it, it never changes the file
// (no YAML is written), and it says so explicitly so it can't be
// mistaken for validation of the note's content.
const ACKNOWLEDGE_BUTTON_TOOLTIP = 'Mark as reviewed (does not change the file)';

// Content-based keys for acknowledgment, deliberately NOT based on
// line number -- an edit anywhere earlier in the file shifts every
// line below it, which would silently disconnect a real acknowledgment
// from the note a human actually reviewed (see findRelatedNotes'
// investigation, DECISION_HISTORY.md). Keying by the note's own text
// (or, for a related-note group, by which field/source/join it's
// about) means an already-acknowledged note keeps matching after
// unrelated edits shift its line, and -- for free -- a note a human
// has since fixed by hand simply stops being found by
// findUnresolvedNotes() at all, so its old acknowledgment just never
// matches anything again rather than needing explicit cleanup.
function noteAcknowledgeKey(text) {
  return `note:${text}`;
}

function relatedAcknowledgeKey(kind, name) {
  return `related:${kind}:${name}`;
}

// Builds Review's full Quick Pick item list, including the
// Acknowledge button on note/related-note items and the
// filter/demote behavior once one has been acknowledged -- pure and
// testable: takes plain data in (including `acknowledgedKeys`, a
// Set<string> the caller reads from context.workspaceState) and
// returns a plain items array, no vscode UI interaction of its own.
// An acknowledged item is never removed from the list entirely (the
// button's own tooltip promises only "reviewed," not "resolved" or
// "gone") -- it's relabeled with a checkmark and moved into a
// trailing "Acknowledged" section instead, so it stays visible and
// still jumps to its line if selected again.
function buildReviewQuickPickItems({
  errorMessages,
  warningMessages,
  needsReviewItems,
  unresolvedNotes,
  relatedGroups,
  acknowledgedKeys,
}) {
  const items = [];
  const acknowledgedItems = [];

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

  const activeNotes = [];
  for (const item of unresolvedNotes) {
    const ackKey = noteAcknowledgeKey(item.text);
    if (acknowledgedKeys.has(ackKey)) {
      acknowledgedItems.push({
        label: `$(check) ${item.text}`,
        description: `line ${item.line + 1} · acknowledged`,
        line: item.line,
      });
    } else {
      activeNotes.push({
        label: `$(note) ${item.text}`,
        description: `line ${item.line + 1}`,
        line: item.line,
        buttons: [{ iconPath: new vscode.ThemeIcon('check'), tooltip: ACKNOWLEDGE_BUTTON_TOOLTIP }],
        ackKey,
      });
    }
  }
  if (activeNotes.length > 0) {
    items.push({ label: 'Unresolved Notes', kind: vscode.QuickPickItemKind.Separator });
    items.push(...activeNotes);
  }

  const activeRelated = [];
  for (const group of relatedGroups) {
    const ackKey = relatedAcknowledgeKey(group.kind, group.name);
    const count = group.noteLines.length;
    const label = `$(link) ${group.kind} '${group.name}' — ${count} related unresolved ${count === 1 ? 'note' : 'notes'}`;
    if (acknowledgedKeys.has(ackKey)) {
      acknowledgedItems.push({
        label: label.replace('$(link)', '$(check)'),
        description: `declared at line ${group.declarationLine + 1} · acknowledged`,
        line: group.noteLines[0],
      });
    } else {
      activeRelated.push({
        label,
        description: `declared at line ${group.declarationLine + 1}`,
        line: group.noteLines[0],
        buttons: [{ iconPath: new vscode.ThemeIcon('check'), tooltip: ACKNOWLEDGE_BUTTON_TOOLTIP }],
        ackKey,
      });
    }
  }
  if (activeRelated.length > 0) {
    items.push({ label: 'Related to Unresolved Notes', kind: vscode.QuickPickItemKind.Separator });
    items.push(...activeRelated);
  }

  if (acknowledgedItems.length > 0) {
    items.push({ label: 'Acknowledged', kind: vscode.QuickPickItemKind.Separator });
    items.push(...acknowledgedItems);
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
