// Bootstraps a real `structifact` install for a user who has none --
// the Marketplace-published extension's first-run problem. Nothing
// here duplicates Structifact's own logic: this only finds a Python
// interpreter, creates a dedicated virtualenv, and runs the real
// `pip install structifact[...]` / `python -m venv` / `structifact
// --help` commands a person would type by hand. See
// docs/DECISION_HISTORY.md for the investigation this implements
// (interpreter detection strategy, why a dedicated venv, the
// resolveCliPath precedence question, and the real, measured install
// footprint that motivated installing only the `ai` extra by default).
//
// Split out of extension.js purely for size/organization -- same
// zero-npm-dependency posture, same "only the pure logic is unit
// tested, the real install flow needs a real Extension Host" split
// as everything else in this extension.

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const { execFile } = require('child_process');
const { promisify } = require('util');

const execFileAsync = promisify(execFile);

// Matches pyproject.toml's `requires-python = ">=3.11"` exactly --
// not independently decided here. If that constraint ever changes,
// this must change with it (nothing automated keeps the two in sync,
// same as every other place this project already accepts that
// tradeoff rather than adding a build step to derive one from the
// other).
const MIN_PYTHON_VERSION = { major: 3, minor: 11 };

// Where an install this extension itself bootstrapped is recorded --
// context.globalState, NOT the structifact.cliPath *setting*.
// Keeping these separate is load-bearing: resolveCliPath's existing
// precedence (an explicit cliPath setting always beats a workspace's
// own .venv/venv) must keep working unchanged for anyone who already
// has a real per-project venv -- writing this into the same
// user-facing setting would silently outrank that for every future
// workspace. This key is consulted as a NEW, lowest-priority
// fallback tier instead (see extension.js's resolveCliPath).
const INSTALLED_CLI_PATH_KEY = 'structifact.installedCliPath';

const VENV_DIR_NAME = 'python-env';

// Probed in order. VS Code's own Python extension (if installed and
// it has an interpreter selected) is tried first, ahead of this list,
// by findPythonInterpreter() below -- this is only the plain-PATH
// fallback, which is what most first-time users without that
// extension installed will actually hit. `py` (the launcher the
// official python.org Windows installer registers independently of
// PATH) is tried before bare `python`/`python3` on Windows
// specifically because the Microsoft Store's `python3.exe` stub is a
// known trap -- it opens the Store instead of running anything if no
// real interpreter is installed, which would otherwise look like a
// found-but-broken candidate rather than a clean "not found".
function pythonCandidates(platform) {
  if (platform === 'win32') {
    return [
      { command: 'py', args: ['-3'] },
      { command: 'py', args: [] },
      { command: 'python', args: [] },
      { command: 'python3', args: [] },
    ];
  }

  return [
    { command: 'python3', args: [] },
    { command: 'python', args: [] },
  ];
}

// Parses this module's own version-probe output (see
// VERSION_PROBE_ARGS below) -- not a general Python-version parser,
// only the exact "MAJOR.MINOR" shape that probe always prints on
// success. Returns null for anything else (a candidate that doesn't
// exist, an unexpected program answering to the same name, a
// truncated/garbled read) rather than guessing.
function parsePythonVersionOutput(output) {
  const match = (output || '').trim().match(/^(\d+)\.(\d+)$/);
  if (!match) {
    return null;
  }
  return { major: parseInt(match[1], 10), minor: parseInt(match[2], 10) };
}

// Plain tuple comparison, (major, minor) only -- structifact's own
// requires-python constraint has never needed a patch-level check,
// and Python itself doesn't expose one meaningfully for this purpose
// (3.11.0 and 3.11.9 are equally acceptable here).
function isVersionSupported(version, minimum) {
  if (!version) {
    return false;
  }
  if (version.major !== minimum.major) {
    return version.major > minimum.major;
  }
  return version.minor >= minimum.minor;
}

// Absolute paths to the three binaries this module ever needs inside
// a venv it created. Uses path.win32.join/path.posix.join explicitly
// (not the ambient, host-OS-flavored `path.join`) so this is
// correctly testable for both layouts from either host OS -- in
// production `platform` is always process.platform, so this matches
// the real OS's own path.join behavior exactly either way.
function venvPaths(venvDir, platform) {
  const isWindows = platform === 'win32';
  const join = isWindows ? path.win32.join : path.posix.join;
  const binDir = join(venvDir, isWindows ? 'Scripts' : 'bin');

  return {
    python: join(binDir, isWindows ? 'python.exe' : 'python'),
    pip: join(binDir, isWindows ? 'pip.exe' : 'pip'),
    structifact: join(binDir, isWindows ? 'structifact.exe' : 'structifact'),
  };
}

// structifact/cli.py's discover_requirements() prints this exact
// message (verbatim, not paraphrased) when a .xlsx file is picked
// without the `excel` extra installed -- matched here, not
// reimplemented, so runAiDiscover can offer to install that one
// extra specifically instead of just showing the CLI's raw text.
function looksLikeMissingExcelExtra(output) {
  return (output || '').includes("requires the 'excel' extra");
}

// ---------------------------------------------------------------------
// Everything below this line is impure (spawns real processes, talks
// to the real vscode API, writes to disk) and is deliberately NOT
// unit tested -- see test/bootstrap.test.js's own header comment.
// Manual verification in a real Extension Host is the only real
// coverage for this half, same as every other command this extension
// already ships.
// ---------------------------------------------------------------------

const VERSION_PROBE_ARGS = ['-c', 'import sys; print("%d.%d" % sys.version_info[:2])'];

// Best-effort only: vscode.extensions.getExtension('ms-python.python')
// gives direct access to that extension's raw exports without adding
// an npm dependency (the alternative, @vscode/python-extension, is
// just a typed wrapper over this same object -- see
// docs/DECISION_HISTORY.md) at the cost of no compile-time guarantee
// this shape is still correct. Wrapped entirely in try/catch and
// treated as "no signal" on any failure -- this is an enhancement
// over the plain candidate-list probing below, never a requirement,
// since plenty of users of a YAML/SQL-facing tool won't have the
// Python extension installed at all.
async function _pythonExtensionInterpreterPath() {
  try {
    const ext = vscode.extensions.getExtension('ms-python.python');
    if (!ext) {
      return undefined;
    }
    if (!ext.isActive) {
      await ext.activate();
    }

    const exports = ext.exports;
    if (!exports || !exports.environments || typeof exports.environments.getActiveEnvironmentPath !== 'function') {
      return undefined;
    }

    const envPath = exports.environments.getActiveEnvironmentPath();
    return (envPath && envPath.path) ? envPath.path : undefined;
  } catch (e) {
    return undefined;
  }
}

async function _probeCandidate(command, args) {
  try {
    const { stdout } = await execFileAsync(command, [...args, ...VERSION_PROBE_ARGS]);
    const version = parsePythonVersionOutput(stdout);
    return version ? { version } : null;
  } catch (e) {
    return null;
  }
}

// Finds the first interpreter that satisfies MIN_PYTHON_VERSION,
// preferring the VS Code Python extension's own reported interpreter
// (see above) over the plain candidate list. Returns a plain result
// object rather than throwing -- `found: false` carries enough of a
// reason (`not-found` vs `too-old`, plus every version actually seen)
// for a specific, honest error message, not a generic failure.
async function findPythonInterpreter(report) {
  if (report) report('Looking for Python...');

  const extPath = await _pythonExtensionInterpreterPath();
  if (extPath) {
    const result = await _probeCandidate(extPath, []);
    if (result && isVersionSupported(result.version, MIN_PYTHON_VERSION)) {
      return { found: true, command: extPath, args: [], version: result.version };
    }
  }

  const attempted = [];
  for (const candidate of pythonCandidates(process.platform)) {
    const result = await _probeCandidate(candidate.command, candidate.args);
    if (!result) {
      continue;
    }

    attempted.push({ command: candidate.command, version: result.version });

    if (isVersionSupported(result.version, MIN_PYTHON_VERSION)) {
      return { found: true, command: candidate.command, args: candidate.args, version: result.version };
    }
  }

  return attempted.length > 0
    ? { found: false, reason: 'too-old', attempted }
    : { found: false, reason: 'not-found' };
}

function _lastStderr(error) {
  return ((error && (error.stderr || error.message)) || '').toString().trim();
}

// Creates a dedicated venv at venvDir with the given interpreter,
// installs structifact[<extras>] into it, and verifies the result
// actually runs (`structifact --help`, exit 0 -- there is no
// `--version` flag; inventing one would mean changing the Python CLI
// for a JS-only bootstrap problem, out of scope here) before
// reporting success. On ANY failure here, the venv is deleted rather
// than left half-installed for a future run to half-trust -- nothing
// is wired up (resolveCliPath's new fallback tier, see extension.js)
// unless verification actually passed.
async function runVenvInstall({ command, args, venvDir, extras, report }) {
  try {
    if (report) report('Creating a virtual environment...');
    fs.mkdirSync(path.dirname(venvDir), { recursive: true });
    await execFileAsync(command, [...args, '-m', 'venv', venvDir]);
  } catch (venvError) {
    fs.rmSync(venvDir, { recursive: true, force: true });
    return { success: false, reason: 'venv-failed', stderr: _lastStderr(venvError) };
  }

  const paths = venvPaths(venvDir, process.platform);
  const packageSpec = extras ? `structifact[${extras}]` : 'structifact';

  try {
    if (report) report(`Installing ${packageSpec} (this can take a minute)...`);
    await execFileAsync(paths.pip, ['install', packageSpec]);
  } catch (installError) {
    fs.rmSync(venvDir, { recursive: true, force: true });
    return { success: false, reason: 'install-failed', stderr: _lastStderr(installError) };
  }

  try {
    if (report) report('Verifying installation...');
    await execFileAsync(paths.structifact, ['--help']);
  } catch (verifyError) {
    fs.rmSync(venvDir, { recursive: true, force: true });
    return { success: false, reason: 'verify-failed', stderr: _lastStderr(verifyError) };
  }

  return { success: true, cliPath: paths.structifact };
}

// The first-run bootstrap: finds Python, creates
// <globalStorage>/python-env/, installs structifact[ai] (NOT
// [ai,excel] -- measured directly: [ai] is 44MB, adding [excel] pulls
// in pandas+numpy for 153MB total, tripling the install for a .xlsx
// feature most first installs won't touch immediately; see
// installExcelExtra below for the deferred, explicitly-prompted
// follow-up), and records the result in globalState on success only.
async function installStructifact({ context, report }) {
  const interpreter = await findPythonInterpreter(report);
  if (!interpreter.found) {
    return { success: false, reason: interpreter.reason, attempted: interpreter.attempted };
  }

  const venvDir = path.join(context.globalStorageUri.fsPath, VENV_DIR_NAME);
  const result = await runVenvInstall({
    command: interpreter.command,
    args: interpreter.args,
    venvDir,
    extras: 'ai',
    report,
  });

  if (result.success) {
    await context.globalState.update(INSTALLED_CLI_PATH_KEY, result.cliPath);
  }

  return result;
}

// The deferred follow-up: adds the `excel` extra to the SAME venv
// installStructifact already created, only ever offered when the
// active cliPath is that same extension-managed install (see
// extension.js's runAiDiscover) -- this extension has no business
// pip-installing into a venv/interpreter it didn't create itself. A
// failure here deliberately does NOT delete the venv (unlike
// installStructifact's own failure handling): the base [ai] install
// in it already works, and a failed extras upgrade shouldn't destroy
// that.
async function installExcelExtra({ context, report }) {
  const installedPath = context.globalState.get(INSTALLED_CLI_PATH_KEY);
  if (!installedPath) {
    return { success: false, reason: 'not-installed' };
  }

  const venvDir = path.join(context.globalStorageUri.fsPath, VENV_DIR_NAME);
  const paths = venvPaths(venvDir, process.platform);

  try {
    if (report) report("Installing the 'excel' extra (this can take a minute)...");
    await execFileAsync(paths.pip, ['install', 'structifact[excel]']);
  } catch (installError) {
    return { success: false, reason: 'install-failed', stderr: _lastStderr(installError) };
  }

  try {
    if (report) report('Verifying...');
    await execFileAsync(paths.structifact, ['--help']);
  } catch (verifyError) {
    return { success: false, reason: 'verify-failed', stderr: _lastStderr(verifyError) };
  }

  return { success: true, cliPath: paths.structifact };
}

module.exports = {
  MIN_PYTHON_VERSION,
  INSTALLED_CLI_PATH_KEY,
  VENV_DIR_NAME,
  pythonCandidates,
  parsePythonVersionOutput,
  isVersionSupported,
  venvPaths,
  looksLikeMissingExcelExtra,
  findPythonInterpreter,
  runVenvInstall,
  installStructifact,
  installExcelExtra,
};
