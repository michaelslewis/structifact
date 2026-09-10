'use strict';

// Dependency-free tests for bootstrap.js's PURE logic only --
// interpreter candidate ordering, Python-version parsing/comparison,
// venv path construction, and the missing-excel-extra message match.
// Everything else in bootstrap.js (findPythonInterpreter,
// runVenvInstall, installStructifact, installExcelExtra) spawns real
// processes (a real Python interpreter, a real `python -m venv`, a
// real `pip install`) and talks to the real vscode API -- there is no
// meaningful way to unit test "did this actually find Python and
// install a working venv" without a real machine and a real
// Extension Host, so that half is manual-only, the same posture this
// extension's other impure commands already have (see
// extension.test.js's own header comment).
//
// A minimal fake 'vscode' module is registered below purely so
// bootstrap.js's own top-level `require('vscode')` doesn't crash
// outside a real Extension Host -- none of the tests here ever call
// into it (the pure functions under test never touch vscode.*).
//
// Run with: node vscode-extension/test/bootstrap.test.js
// Exits non-zero if any assertion fails.

const assert = require('assert');
const path = require('path');
const Module = require('module');

const fakeVscode = {
  extensions: { getExtension: () => undefined },
  window: {},
  workspace: {},
  ProgressLocation: { Notification: 1 },
};

const originalResolveFilename = Module._resolveFilename;
Module._resolveFilename = function (request, ...rest) {
  if (request === 'vscode') return 'vscode';
  return originalResolveFilename.call(this, request, ...rest);
};
require.cache.vscode = { id: 'vscode', filename: 'vscode', loaded: true, exports: fakeVscode };

const {
  MIN_PYTHON_VERSION,
  pythonCandidates,
  parsePythonVersionOutput,
  isVersionSupported,
  venvPaths,
  looksLikeMissingExcelExtra,
} = require(path.join(__dirname, '..', 'bootstrap.js'));

let failures = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (e) {
    failures += 1;
    console.log(`FAIL ${name}`);
    console.log(`  ${e.message}`);
  }
}

// --- pythonCandidates ---

test('pythonCandidates tries py -3 first on Windows, then py, then python, then python3', () => {
  // `py` (the launcher the official python.org Windows installer
  // registers independently of PATH) before bare python/python3
  // specifically because the Microsoft Store's python3.exe stub is a
  // known trap that opens the Store instead of running anything.
  assert.deepStrictEqual(pythonCandidates('win32'), [
    { command: 'py', args: ['-3'] },
    { command: 'py', args: [] },
    { command: 'python', args: [] },
    { command: 'python3', args: [] },
  ]);
});

test('pythonCandidates tries python3 before python on macOS and Linux', () => {
  assert.deepStrictEqual(pythonCandidates('darwin'), [
    { command: 'python3', args: [] },
    { command: 'python', args: [] },
  ]);
  assert.deepStrictEqual(pythonCandidates('linux'), [
    { command: 'python3', args: [] },
    { command: 'python', args: [] },
  ]);
});

// --- parsePythonVersionOutput ---

test('parsePythonVersionOutput parses the real probe output shape', () => {
  assert.deepStrictEqual(parsePythonVersionOutput('3.12'), { major: 3, minor: 12 });
});

test('parsePythonVersionOutput trims trailing newline/whitespace', () => {
  assert.deepStrictEqual(parsePythonVersionOutput('3.11\n'), { major: 3, minor: 11 });
  assert.deepStrictEqual(parsePythonVersionOutput('  3.9  \n'), { major: 3, minor: 9 });
});

test('parsePythonVersionOutput returns null for unparseable output', () => {
  assert.strictEqual(parsePythonVersionOutput('not a version'), null);
  assert.strictEqual(parsePythonVersionOutput(''), null);
  assert.strictEqual(parsePythonVersionOutput(undefined), null);
  // major.minor only, by design -- a patch-level suffix means this
  // wasn't our own probe script's output.
  assert.strictEqual(parsePythonVersionOutput('3.12.1'), null);
});

// --- isVersionSupported ---

test('isVersionSupported: exactly the minimum version is supported', () => {
  assert.strictEqual(isVersionSupported({ major: 3, minor: 11 }, MIN_PYTHON_VERSION), true);
});

test('isVersionSupported: a newer minor is supported', () => {
  assert.strictEqual(isVersionSupported({ major: 3, minor: 12 }, MIN_PYTHON_VERSION), true);
});

test('isVersionSupported: an older minor is not supported', () => {
  assert.strictEqual(isVersionSupported({ major: 3, minor: 10 }, MIN_PYTHON_VERSION), false);
});

test('isVersionSupported: a newer major is supported regardless of its own minor', () => {
  assert.strictEqual(isVersionSupported({ major: 4, minor: 0 }, MIN_PYTHON_VERSION), true);
});

test('isVersionSupported: an older major (e.g. Python 2) is never supported', () => {
  assert.strictEqual(isVersionSupported({ major: 2, minor: 7 }, MIN_PYTHON_VERSION), false);
});

test('isVersionSupported: a null/undefined version is not supported', () => {
  assert.strictEqual(isVersionSupported(null, MIN_PYTHON_VERSION), false);
  assert.strictEqual(isVersionSupported(undefined, MIN_PYTHON_VERSION), false);
});

// --- venvPaths ---

test('venvPaths uses bin/ with no extension on macOS/Linux', () => {
  assert.deepStrictEqual(venvPaths('/Users/me/venv', 'darwin'), {
    python: '/Users/me/venv/bin/python',
    pip: '/Users/me/venv/bin/pip',
    structifact: '/Users/me/venv/bin/structifact',
  });
  assert.deepStrictEqual(venvPaths('/home/me/venv', 'linux'), {
    python: '/home/me/venv/bin/python',
    pip: '/home/me/venv/bin/pip',
    structifact: '/home/me/venv/bin/structifact',
  });
});

test('venvPaths uses Scripts\\ with .exe on Windows, regardless of the host OS running this test', () => {
  // Uses path.win32.join internally specifically so this is
  // meaningfully testable from a non-Windows CI/dev machine -- see
  // bootstrap.js's own comment on venvPaths.
  assert.deepStrictEqual(venvPaths('C:\\Users\\me\\venv', 'win32'), {
    python: 'C:\\Users\\me\\venv\\Scripts\\python.exe',
    pip: 'C:\\Users\\me\\venv\\Scripts\\pip.exe',
    structifact: 'C:\\Users\\me\\venv\\Scripts\\structifact.exe',
  });
});

// --- looksLikeMissingExcelExtra ---

test('looksLikeMissingExcelExtra recognizes the real CLI message', () => {
  // Verbatim from structifact/cli.py's discover_requirements().
  const output = (
    "\nReading a .xlsx requirements document requires the 'excel' " +
    'extra: pip install -e ".[excel]"\n'
  );
  assert.strictEqual(looksLikeMissingExcelExtra(output), true);
});

test('looksLikeMissingExcelExtra is false for an unrelated failure', () => {
  assert.strictEqual(looksLikeMissingExcelExtra('\nFile not found: /tmp/x.xlsx\n'), false);
  assert.strictEqual(looksLikeMissingExcelExtra(''), false);
  assert.strictEqual(looksLikeMissingExcelExtra(undefined), false);
});

if (failures > 0) {
  console.log(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log('\nAll tests passed.');
}
