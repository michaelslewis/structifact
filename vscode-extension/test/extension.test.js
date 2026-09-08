'use strict';

// Minimal, dependency-free test for this extension's pure logic --
// deliberately not @vscode/test-electron (no real Extension Host,
// no new dependency), matching the extension's own zero-npm-package
// discipline. Covers the functions that don't need the real `vscode`
// API to be correct (discoveredOutputPath, extractFlagLine,
// parseErrors) plus resolveCliPath, which needs only a tiny fake of
// vscode.workspace.getConfiguration.
//
// Run with: node vscode-extension/test/extension.test.js
// Exits non-zero if any assertion fails.

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const Module = require('module');

let mockConfig = { value: undefined, explicit: false };

const fakeVscode = {
  workspace: {
    getConfiguration: () => ({
      inspect: () => (mockConfig.explicit ? { workspaceValue: mockConfig.value } : {}),
      get: (key, dflt) => (mockConfig.explicit ? mockConfig.value : dflt),
    }),
  },
};

const originalResolveFilename = Module._resolveFilename;
Module._resolveFilename = function (request, ...rest) {
  if (request === 'vscode') return 'vscode';
  return originalResolveFilename.call(this, request, ...rest);
};
require.cache.vscode = { id: 'vscode', filename: 'vscode', loaded: true, exports: fakeVscode };

const extensionSourcePath = path.join(__dirname, '..', 'extension.js');
const source = fs.readFileSync(extensionSourcePath, 'utf8');
const harness = new Module('extension-under-test');
harness.paths = Module._nodeModulePaths(path.dirname(extensionSourcePath));
harness._compile(
  `${source}\nmodule.exports.__test__ = { resolveCliPath, discoveredOutputPath, extractFlagLine, extractGeneratedArtifactPath, parseErrors };`,
  extensionSourcePath
);
const {
  resolveCliPath, discoveredOutputPath, extractFlagLine, extractGeneratedArtifactPath, parseErrors,
} = harness.exports.__test__;

function wsFolder(fsPath) {
  return { uri: { fsPath } };
}

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

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'structifact-ext-test-'));

// --- resolveCliPath (also covered ad hoc when it was first built;
// checked in here so it's a real regression test, not a one-off) ---

test('resolveCliPath finds .venv/bin/structifact when present', () => {
  const dir = path.join(tmpRoot, 'dotvenv');
  fs.mkdirSync(path.join(dir, '.venv', 'bin'), { recursive: true });
  fs.writeFileSync(path.join(dir, '.venv', 'bin', 'structifact'), '');
  mockConfig = { value: undefined, explicit: false };
  assert.strictEqual(
    resolveCliPath(wsFolder(dir)),
    path.join(dir, '.venv', 'bin', 'structifact')
  );
});

test('resolveCliPath falls back to plain venv/bin/structifact', () => {
  const dir = path.join(tmpRoot, 'plainvenv');
  fs.mkdirSync(path.join(dir, 'venv', 'bin'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'venv', 'bin', 'structifact'), '');
  mockConfig = { value: undefined, explicit: false };
  assert.strictEqual(
    resolveCliPath(wsFolder(dir)),
    path.join(dir, 'venv', 'bin', 'structifact')
  );
});

test('resolveCliPath falls back to bare "structifact" when neither exists', () => {
  const dir = path.join(tmpRoot, 'neither');
  fs.mkdirSync(dir, { recursive: true });
  mockConfig = { value: undefined, explicit: false };
  assert.strictEqual(resolveCliPath(wsFolder(dir)), 'structifact');
});

test('resolveCliPath respects an explicit setting over an available .venv', () => {
  const dir = path.join(tmpRoot, 'dotvenv');
  mockConfig = { value: '/custom/structifact', explicit: true };
  assert.strictEqual(resolveCliPath(wsFolder(dir)), '/custom/structifact');
});

test('resolveCliPath falls back to bare "structifact" with no workspace folder', () => {
  mockConfig = { value: undefined, explicit: false };
  assert.strictEqual(resolveCliPath(undefined), 'structifact');
});

// --- discoveredOutputPath ---

test("discoveredOutputPath matches discover.py's own default naming", () => {
  assert.strictEqual(
    discoveredOutputPath('/a/b/messy_orders.csv'),
    path.join('/a/b', 'messy_orders.discovered.yml')
  );
});

test('discoveredOutputPath strips the extension regardless of type', () => {
  assert.strictEqual(
    discoveredOutputPath('/a/b/requirements.xlsx'),
    path.join('/a/b', 'requirements.discovered.yml')
  );
});

// --- extractFlagLine ---

test('extractFlagLine finds the real CLI summary line', () => {
  const output = [
    '✓ Read 6 row(s)',
    '✓ Sampled 6 row(s)',
    '✓ Inferred 7 column(s)',
    '⚠ 4 field(s) flagged for review: order_id, order_date, amount, zip_code',
    '✓ Wrote draft metadata to messy_orders.discovered.yml',
    '',
  ].join('\n');

  assert.strictEqual(
    extractFlagLine(output),
    '⚠ 4 field(s) flagged for review: order_id, order_date, amount, zip_code'
  );
});

test('extractFlagLine returns undefined when nothing was flagged', () => {
  const output = [
    '✓ Read 4 row(s)',
    '✓ Sampled 4 row(s)',
    '✓ Inferred 5 column(s)',
    '✓ Wrote draft metadata to raw_customers.discovered.yml',
    '',
  ].join('\n');

  assert.strictEqual(extractFlagLine(output), undefined);
});

// --- extractGeneratedArtifactPath ---

test('extractGeneratedArtifactPath finds the real generate -g sql line', () => {
  // Captured from a real `structifact generate ... -g sql -o ...` run.
  const output = [
    '',
    '--- STRUCTURED VIEW ---',
    '',
    'Table: customers',
    '',
    'Fields:',
    '- customer_id (integer)',
    '- created_at (timestamp)',
    '',
    '--- GENERATED ARTIFACTS ---',
    '- /a/b/generated/customers.sql',
    '',
  ].join('\n');

  assert.strictEqual(extractGeneratedArtifactPath(output), '/a/b/generated/customers.sql');
});

test('extractGeneratedArtifactPath returns undefined when no .sql line is present', () => {
  const output = '\n--- STRUCTURED VIEW ---\n\nTable: customers\n';
  assert.strictEqual(extractGeneratedArtifactPath(output), undefined);
});

// --- parseErrors, exercised against real discover/generate failure
// shapes, not just validate's ---

test('parseErrors surfaces a plain discover failure message', () => {
  const output = '\nFile not found: /tmp/does_not_exist.csv\n';
  assert.deepStrictEqual(parseErrors(output), ['File not found: /tmp/does_not_exist.csv']);
});

test('parseErrors surfaces the real xlsx-without---ai message', () => {
  // This extension never passes --ai, so picking an .xlsx file in the
  // file picker always hits this exact message (structifact/cli.py's
  // discover_requirements()) -- confirmed against the real CLI, not
  // guessed, since an earlier draft of this test had the wrong text.
  const output = (
    '\nA requirements document has no data rows to sample, so ' +
    'structifact can only draft a schema from one with --ai ' +
    '(this reads the document with an LLM; nothing here is ' +
    'generated deterministically).\n'
  );
  assert.deepStrictEqual(parseErrors(output), [
    'A requirements document has no data rows to sample, so structifact can only draft a schema from one with --ai (this reads the document with an LLM; nothing here is generated deterministically).',
  ]);
});

test('parseErrors surfaces a real generate validation failure', () => {
  // Captured from a real `structifact generate` run against a field
  // with an unsupported type -- generate() calls validate_table()
  // before generating anything, so this is byte-identical in shape
  // to a Validate command failure.
  const output = "\nValidation failed:\n\nUnsupported type 'bogus_type' for field 'f1'\n";
  assert.deepStrictEqual(parseErrors(output), [
    "Unsupported type 'bogus_type' for field 'f1'",
  ]);
});

fs.rmSync(tmpRoot, { recursive: true, force: true });

if (failures > 0) {
  console.log(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log('\nAll tests passed.');
}
