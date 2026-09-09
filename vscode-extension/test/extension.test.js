'use strict';

// Minimal, dependency-free test for this extension's pure logic --
// deliberately not @vscode/test-electron (no real Extension Host,
// no new dependency), matching the extension's own zero-npm-package
// discipline. Covers the functions that don't need the real `vscode`
// API to be correct (discoveredOutputPath, extractFlagLine,
// parseErrors) plus resolveCliPath, which needs only a tiny fake of
// vscode.workspace.getConfiguration.
//
// runAiDiscover needs more of vscode.window/workspace/commands faked
// (showWarningMessage, openTextDocument, showTextDocument,
// executeCommand) -- still no real Extension Host, just a bigger fake
// object -- plus a real child process: a small fake CLI script
// standing in for `structifact`, since the interactive-stdin
// technique (writing y/n to a live child's stdin after reading its
// "Estimate:" line off real stdout) is the actual thing worth
// covering, not something to mock away. Behavior is switched with the
// FAKE_CLI_MODE env var, since the real CLI's own fixed argument shape
// (['discover', input, '--ai', '-o', output]) has no room for a
// test-only flag.
//
// Run with: node vscode-extension/test/extension.test.js
// Exits non-zero if any assertion fails.

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const Module = require('module');

let mockConfig = { value: undefined, explicit: false };

// Call logs + a settable response for runAiDiscover's tests -- reset
// via resetVscodeMocks() before each of those.
let warningMessageCalls = [];
let warningMessageResponse;
let errorMessageCalls = [];
let infoMessageCalls = [];
let openTextDocumentCalls = [];
let showTextDocumentCalls = [];
let executeCommandCalls = [];

function resetVscodeMocks() {
  warningMessageCalls = [];
  warningMessageResponse = undefined;
  errorMessageCalls = [];
  infoMessageCalls = [];
  openTextDocumentCalls = [];
  showTextDocumentCalls = [];
  executeCommandCalls = [];
}

const fakeVscode = {
  workspace: {
    getConfiguration: () => ({
      inspect: () => (mockConfig.explicit ? { workspaceValue: mockConfig.value } : {}),
      get: (key, dflt) => (mockConfig.explicit ? mockConfig.value : dflt),
    }),
    openTextDocument: (target) => {
      openTextDocumentCalls.push(target);
      return Promise.resolve({ __fakeDoc: true, target });
    },
  },
  window: {
    showWarningMessage: (...args) => {
      warningMessageCalls.push(args);
      return Promise.resolve(warningMessageResponse);
    },
    showErrorMessage: (...args) => {
      errorMessageCalls.push(args);
    },
    showInformationMessage: (...args) => {
      infoMessageCalls.push(args);
    },
    showTextDocument: (doc) => {
      showTextDocumentCalls.push(doc);
      return Promise.resolve({});
    },
  },
  commands: {
    executeCommand: (...args) => {
      executeCommandCalls.push(args);
      return Promise.resolve();
    },
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
  `${source}\nmodule.exports.__test__ = { resolveCliPath, discoveredOutputPath, extractFlagLine, extractGeneratedArtifactPath, parseErrors, parseWarnings, findNeedsReviewItems, findUnresolvedNotes, isRequirementsDocument, runAiDiscover };`,
  extensionSourcePath
);
const {
  resolveCliPath, discoveredOutputPath, extractFlagLine, extractGeneratedArtifactPath, parseErrors,
  parseWarnings, findNeedsReviewItems, findUnresolvedNotes, isRequirementsDocument, runAiDiscover,
} = harness.exports.__test__;

function wsFolder(fsPath) {
  return { uri: { fsPath } };
}

let failures = 0;
// await fn() works whether fn is sync or returns a promise -- lets
// runAiDiscover's tests (which must await a real child process) share
// this same runner with every existing synchronous test below.
async function test(name, fn) {
  try {
    await fn();
    console.log(`PASS ${name}`);
  } catch (e) {
    failures += 1;
    console.log(`FAIL ${name}`);
    console.log(`  ${e.message}`);
  }
}

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'structifact-ext-test-'));

// A fake `structifact` CLI, real enough to exec: prints the same
// "Estimate: ..." line the real AnthropicLLMClient.estimate_cost()
// produces, then reads one line of stdin the same way the real CLI's
// y/N prompt does. FAKE_CLI_MODE (read fresh on each run) switches
// what happens after approval -- set it synchronously right before
// each runAiDiscover() call, since execFile captures the current env
// immediately, before any await.
const fakeCliPath = path.join(tmpRoot, 'fake-discover-cli.js');
fs.writeFileSync(fakeCliPath, [
  '#!/usr/bin/env node',
  "'use strict';",
  "const fs = require('fs');",
  "const mode = process.env.FAKE_CLI_MODE || 'success';",
  'const args = process.argv.slice(2);',
  "const outIdx = args.indexOf('-o');",
  'const outputPath = outIdx >= 0 ? args[outIdx + 1] : undefined;',
  '',
  "process.stdout.write('Estimate: ~$0.05 estimated (rough approximation)\\n');",
  '',
  "let buf = '';",
  "process.stdin.on('data', (chunk) => {",
  '  buf += chunk.toString();',
  "  if (!buf.includes('\\n')) return;",
  '  const answer = buf.trim();',
  '',
  "  if (answer !== 'y') {",
  "    process.stdout.write('Discover cancelled.\\n');",
  '    process.exit(0);',
  '  }',
  '',
  "  if (mode === 'fail-after-approve') {",
  "    process.stderr.write('Something went wrong calling the model.\\n');",
  '    process.exit(1);',
  '  }',
  '',
  '  if (outputPath) {',
  '    fs.writeFileSync(outputPath, \'dataset:\\n  name: "Test"\\nfields: []\\n\');',
  '  }',
  "  process.stdout.write('Wrote draft metadata to ' + outputPath + '\\n');",
  '  process.exit(0);',
  '});',
  '',
].join('\n'));
fs.chmodSync(fakeCliPath, 0o755);

async function main() {

// --- resolveCliPath (also covered ad hoc when it was first built;
// checked in here so it's a real regression test, not a one-off) ---

await test('resolveCliPath finds .venv/bin/structifact when present', () => {
  const dir = path.join(tmpRoot, 'dotvenv');
  fs.mkdirSync(path.join(dir, '.venv', 'bin'), { recursive: true });
  fs.writeFileSync(path.join(dir, '.venv', 'bin', 'structifact'), '');
  mockConfig = { value: undefined, explicit: false };
  assert.strictEqual(
    resolveCliPath(wsFolder(dir)),
    path.join(dir, '.venv', 'bin', 'structifact')
  );
});

await test('resolveCliPath falls back to plain venv/bin/structifact', () => {
  const dir = path.join(tmpRoot, 'plainvenv');
  fs.mkdirSync(path.join(dir, 'venv', 'bin'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'venv', 'bin', 'structifact'), '');
  mockConfig = { value: undefined, explicit: false };
  assert.strictEqual(
    resolveCliPath(wsFolder(dir)),
    path.join(dir, 'venv', 'bin', 'structifact')
  );
});

await test('resolveCliPath falls back to bare "structifact" when neither exists', () => {
  const dir = path.join(tmpRoot, 'neither');
  fs.mkdirSync(dir, { recursive: true });
  mockConfig = { value: undefined, explicit: false };
  assert.strictEqual(resolveCliPath(wsFolder(dir)), 'structifact');
});

await test('resolveCliPath respects an explicit setting over an available .venv', () => {
  const dir = path.join(tmpRoot, 'dotvenv');
  mockConfig = { value: '/custom/structifact', explicit: true };
  assert.strictEqual(resolveCliPath(wsFolder(dir)), '/custom/structifact');
});

await test('resolveCliPath falls back to bare "structifact" with no workspace folder', () => {
  mockConfig = { value: undefined, explicit: false };
  assert.strictEqual(resolveCliPath(undefined), 'structifact');
});

// --- discoveredOutputPath ---

await test("discoveredOutputPath matches discover.py's own default naming", () => {
  assert.strictEqual(
    discoveredOutputPath('/a/b/messy_orders.csv'),
    path.join('/a/b', 'messy_orders.discovered.yml')
  );
});

await test('discoveredOutputPath strips the extension regardless of type', () => {
  assert.strictEqual(
    discoveredOutputPath('/a/b/requirements.xlsx'),
    path.join('/a/b', 'requirements.discovered.yml')
  );
});

// --- isRequirementsDocument ---

await test('isRequirementsDocument is true for .md, .txt, .xlsx (case-insensitive)', () => {
  assert.strictEqual(isRequirementsDocument('/a/b/requirements.md'), true);
  assert.strictEqual(isRequirementsDocument('/a/b/requirements.TXT'), true);
  assert.strictEqual(isRequirementsDocument('/a/b/Vendors.xlsx'), true);
  assert.strictEqual(isRequirementsDocument('/a/b/Vendors.XLSX'), true);
});

await test('isRequirementsDocument is false for .csv and any other extension', () => {
  // .csv is the one case that matters most here -- it must keep
  // routing through the deterministic discover() branch, unchanged.
  assert.strictEqual(isRequirementsDocument('/a/b/orders.csv'), false);
  assert.strictEqual(isRequirementsDocument('/a/b/notes.json'), false);
  assert.strictEqual(isRequirementsDocument('/a/b/noextension'), false);
});

// --- extractFlagLine ---

await test('extractFlagLine finds the real CLI summary line', () => {
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

await test('extractFlagLine returns undefined when nothing was flagged', () => {
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

await test('extractGeneratedArtifactPath finds the real generate -g sql line', () => {
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

await test('extractGeneratedArtifactPath returns undefined when no .sql line is present', () => {
  const output = '\n--- STRUCTURED VIEW ---\n\nTable: customers\n';
  assert.strictEqual(extractGeneratedArtifactPath(output), undefined);
});

// --- parseErrors, exercised against real discover/generate failure
// shapes, not just validate's ---

await test('parseErrors surfaces a plain discover failure message', () => {
  const output = '\nFile not found: /tmp/does_not_exist.csv\n';
  assert.deepStrictEqual(parseErrors(output), ['File not found: /tmp/does_not_exist.csv']);
});

await test('parseErrors surfaces the real xlsx-without---ai message', () => {
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

await test('parseErrors surfaces a real generate validation failure', () => {
  // Captured from a real `structifact generate` run against a field
  // with an unsupported type -- generate() calls validate_table()
  // before generating anything, so this is byte-identical in shape
  // to a Validate command failure.
  const output = "\nValidation failed:\n\nUnsupported type 'bogus_type' for field 'f1'\n";
  assert.deepStrictEqual(parseErrors(output), [
    "Unsupported type 'bogus_type' for field 'f1'",
  ]);
});

await test('parseErrors excludes the warnings section when a dataset has both', () => {
  // Real, captured output: structifact validate against a fixture
  // with one hard error AND one join-risk warning. Before this fix,
  // parseErrors kept reading past "Validation failed:" all the way to
  // the end of the string, so the "⚠ N warning(s):" line and every
  // warning bullet were parsed as if they were separate errors too.
  const output = (
    "\nValidation failed:\n\nUnsupported type 'banana' for field 'claim_id'\n\n" +
    "⚠ 1 warning(s):\n\n" +
    "  - Join on source 'policy_status' has a non-equality condition correlated " +
    "with another source, but no pick_one_order_by — if more than one row of " +
    "'policy_status' can qualify per primary row, this can silently duplicate " +
    "or drop rows (see docs/PICK_ONE_ORDER_BY_CONTRACT.md). Review whether " +
    "pick_one_order_by is needed here.\n"
  );

  assert.deepStrictEqual(parseErrors(output), [
    "Unsupported type 'banana' for field 'claim_id'",
  ]);
});

// --- parseWarnings ---

await test('parseWarnings extracts the warning bullet alongside a hard error', () => {
  const output = (
    "\nValidation failed:\n\nUnsupported type 'banana' for field 'claim_id'\n\n" +
    "⚠ 1 warning(s):\n\n" +
    "  - Join on source 'policy_status' has a non-equality condition...\n"
  );

  assert.deepStrictEqual(parseWarnings(output), [
    "Join on source 'policy_status' has a non-equality condition...",
  ]);
});

await test('parseWarnings extracts multiple bullets from a clean-pass-with-warnings output', () => {
  const output = (
    '✓ Loaded metadata\n✓ Parsed 6 fields\n✓ Valid schema\n✓ No constraint violations\n\n' +
    '⚠ 2 warning(s):\n\n' +
    '  - first warning\n' +
    '  - second warning\n'
  );

  assert.deepStrictEqual(parseWarnings(output), ['first warning', 'second warning']);
});

await test('parseWarnings returns an empty array when there is no warnings section', () => {
  const output = '✓ Loaded metadata\n✓ Parsed 2 fields\n✓ Valid schema\n✓ No constraint violations\n';
  assert.deepStrictEqual(parseWarnings(output), []);
});

// --- findNeedsReviewItems ---

await test('findNeedsReviewItems finds real NEEDS REVIEW comments with correct line numbers', () => {
  // A real excerpt from a messy_orders.csv discover draft.
  const text = [
    '  - name: order_id',
    '    type: string',
    "    description: TODO  # sampled 6 value(s), all sampled values unique — possible key",
    "    # ⚠ NEEDS REVIEW: looks numeric, but at least one value has a leading zero",
    '',
    '  - name: customer_email',
    '    type: string',
  ].join('\n');

  const items = findNeedsReviewItems(text);

  assert.strictEqual(items.length, 1);
  assert.strictEqual(items[0].line, 3);
  assert.strictEqual(items[0].text, 'looks numeric, but at least one value has a leading zero');
});

await test('findNeedsReviewItems returns an empty array when there are none', () => {
  const text = 'dataset:\n  name: customers\nfields:\n  - name: customer_id\n    type: integer\n';
  assert.deepStrictEqual(findNeedsReviewItems(text), []);
});

// --- findUnresolvedNotes ---

await test('findUnresolvedNotes decodes real JSON-escaped note text with correct line numbers', () => {
  // A real excerpt: structifact/discover.py's _yaml_str() renders
  // each note via json.dumps(), which escapes non-ASCII characters
  // (an em dash here) as \uXXXX -- findUnresolvedNotes must decode
  // that back to a real em dash, not show the literal escape to a
  // human.
  const text = [
    'joins:',
    '  - source: "fx_rate"',
    '    "on": "WO_HDR.currency_code = fx_rate.currency_code"',
    '',
    'unresolved_notes:',
    '  - "Field \'resolved_fx_rate\' is referenced but not defined \\u2014 review this."',
    '  - "A second note."',
  ].join('\n');

  const items = findUnresolvedNotes(text);

  assert.strictEqual(items.length, 2);
  assert.strictEqual(items[0].line, 5);
  assert.strictEqual(
    items[0].text,
    "Field 'resolved_fx_rate' is referenced but not defined — review this."
  );
  assert.strictEqual(items[1].line, 6);
  assert.strictEqual(items[1].text, 'A second note.');
});

await test('findUnresolvedNotes returns an empty array for unresolved_notes: []', () => {
  const text = 'dataset:\n  name: x\nfields: []\n\nunresolved_notes:\n  []\n';
  assert.deepStrictEqual(findUnresolvedNotes(text), []);
});

await test('findUnresolvedNotes falls back to raw text for a non-JSON-quoted entry', () => {
  // A hand-edited note without quotes must not crash -- falls back to
  // the raw line content rather than throwing.
  const text = 'unresolved_notes:\n  - a note without quotes\n';
  assert.deepStrictEqual(findUnresolvedNotes(text), [
    { line: 1, text: 'a note without quotes' },
  ]);
});

// --- runAiDiscover ---
// Exercises the real function against the real fake-CLI child process
// above (not a mock of execFile) -- the interactive-stdin technique
// itself (reading "Estimate:" off live stdout, then writing y/n to
// stdin) is the thing worth covering, the same way it was empirically
// verified against real .md/.xlsx files before this code was written
// (see DECISION_HISTORY.md).

await test('runAiDiscover shows the real CLI estimate in a modal, then writes output and chains into Review on approval', async () => {
  resetVscodeMocks();
  warningMessageResponse = 'Proceed';
  delete process.env.FAKE_CLI_MODE;

  const inputPath = path.join(tmpRoot, 'requirements.md');
  const outputPath = path.join(tmpRoot, 'requirements.discovered.yml');
  fs.writeFileSync(inputPath, '# requirements\n');

  await runAiDiscover({ cliPath: fakeCliPath, cwd: tmpRoot, inputPath, outputPath });

  assert.strictEqual(warningMessageCalls.length, 1);
  const [message, options, button] = warningMessageCalls[0];
  assert.ok(message.includes('~$0.05 estimated'), `expected the real estimate text in the modal, got: ${message}`);
  assert.deepStrictEqual(options, { modal: true });
  assert.strictEqual(button, 'Proceed');

  assert.ok(fs.existsSync(outputPath), 'expected the output file to be written after approval');
  assert.deepStrictEqual(openTextDocumentCalls, [outputPath]);
  assert.strictEqual(showTextDocumentCalls.length, 1);
  assert.deepStrictEqual(executeCommandCalls, [['structifact.review']]);
  assert.strictEqual(errorMessageCalls.length, 0);
});

await test('runAiDiscover declines without writing output or opening anything when the user does not proceed', async () => {
  resetVscodeMocks();
  warningMessageResponse = undefined; // dismissing the modal (Escape / no click) resolves to undefined
  delete process.env.FAKE_CLI_MODE;

  const inputPath = path.join(tmpRoot, 'requirements2.txt');
  const outputPath = path.join(tmpRoot, 'requirements2.discovered.yml');
  fs.writeFileSync(inputPath, 'some requirements text\n');

  await runAiDiscover({ cliPath: fakeCliPath, cwd: tmpRoot, inputPath, outputPath });

  assert.strictEqual(warningMessageCalls.length, 1);
  assert.ok(!fs.existsSync(outputPath), 'expected nothing to be written when declined');
  assert.deepStrictEqual(openTextDocumentCalls, []);
  assert.deepStrictEqual(executeCommandCalls, []);
  assert.strictEqual(infoMessageCalls.length, 1);
  assert.ok(infoMessageCalls[0][0].includes('nothing written'));
});

await test('runAiDiscover surfaces a real CLI failure after approval as an error message', async () => {
  resetVscodeMocks();
  warningMessageResponse = 'Proceed';
  process.env.FAKE_CLI_MODE = 'fail-after-approve';

  const inputPath = path.join(tmpRoot, 'requirements3.xlsx');
  const outputPath = path.join(tmpRoot, 'requirements3.discovered.yml');
  fs.writeFileSync(inputPath, '');

  await runAiDiscover({ cliPath: fakeCliPath, cwd: tmpRoot, inputPath, outputPath });
  delete process.env.FAKE_CLI_MODE;

  assert.ok(!fs.existsSync(outputPath));
  assert.strictEqual(errorMessageCalls.length, 1);
  assert.ok(errorMessageCalls[0][0].includes('discover failed for requirements3.xlsx'));
  assert.ok(errorMessageCalls[0][0].includes('Something went wrong calling the model.'));
  assert.deepStrictEqual(openTextDocumentCalls, []);
});

await test('runAiDiscover reports a clear error when the CLI cannot be found at all', async () => {
  resetVscodeMocks();
  warningMessageResponse = 'Proceed';

  const inputPath = path.join(tmpRoot, 'requirements4.txt');
  const outputPath = path.join(tmpRoot, 'requirements4.discovered.yml');
  const missingCliPath = path.join(tmpRoot, 'does-not-exist-structifact');

  await runAiDiscover({ cliPath: missingCliPath, cwd: tmpRoot, inputPath, outputPath });

  assert.strictEqual(warningMessageCalls.length, 0, 'should fail before ever reaching a cost estimate');
  assert.strictEqual(errorMessageCalls.length, 1);
  assert.ok(errorMessageCalls[0][0].includes(`could not run "${missingCliPath}"`));
});

}

main().then(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });

  if (failures > 0) {
    console.log(`\n${failures} test(s) failed.`);
    process.exit(1);
  } else {
    console.log('\nAll tests passed.');
  }
});
