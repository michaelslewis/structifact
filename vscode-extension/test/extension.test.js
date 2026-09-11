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
  // Only what buildReviewQuickPickItems touches: a Separator marker
  // (its exact value doesn't matter, only that items can be compared
  // against it) and a real-shaped ThemeIcon stand-in (the Acknowledge
  // button's iconPath) -- no other Quick Pick machinery is faked here
  // since createQuickPick() itself is exercised only in a real
  // Extension Host, never by these tests (see this file's own header
  // comment).
  QuickPickItemKind: { Separator: -1 },
  ThemeIcon: class ThemeIcon {
    constructor(id) {
      this.id = id;
    }
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
// _compile's own filename argument (below) sets __filename/__dirname
// inside the compiled code, but NOT this Module instance's own
// .filename -- and extension.js now has a real relative require
// (./bootstrap), which Module.prototype.require resolves against
// THIS module's .filename, not its .paths (.paths is only consulted
// for bare/node_modules-style specifiers). Set explicitly so that
// resolution lands on the real bootstrap.js next to the real
// extension.js, not on the literal id string 'extension-under-test'.
harness.filename = extensionSourcePath;
harness.paths = Module._nodeModulePaths(path.dirname(extensionSourcePath));
harness._compile(
  `${source}\nmodule.exports.__test__ = { resolveCliPath, discoveredOutputPath, extractFlagLine, extractGeneratedArtifactPath, parseErrors, parseWarnings, findNeedsReviewItems, findUnresolvedNotes, isRequirementsDocument, runAiDiscover, findRelatedNotes, noteAcknowledgeKey, relatedAcknowledgeKey, buildReviewQuickPickItems };`,
  extensionSourcePath
);
const {
  resolveCliPath, discoveredOutputPath, extractFlagLine, extractGeneratedArtifactPath, parseErrors,
  parseWarnings, findNeedsReviewItems, findUnresolvedNotes, isRequirementsDocument, runAiDiscover,
  findRelatedNotes, noteAcknowledgeKey, relatedAcknowledgeKey, buildReviewQuickPickItems,
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

// --- resolveCliPath's new third tier: an extension-bootstrapped
// install (bootstrap.js), below an explicit setting and a workspace
// .venv/venv, above bare "structifact" on PATH ---

await test('resolveCliPath falls back to a bootstrapped install when no explicit setting and no workspace venv exist', () => {
  const dir = path.join(tmpRoot, 'no-workspace-venv');
  fs.mkdirSync(dir, { recursive: true });
  const installed = path.join(tmpRoot, 'bootstrapped', 'bin', 'structifact');
  fs.mkdirSync(path.dirname(installed), { recursive: true });
  fs.writeFileSync(installed, '');
  mockConfig = { value: undefined, explicit: false };

  assert.strictEqual(resolveCliPath(wsFolder(dir), installed), installed);
});

await test('resolveCliPath ignores a bootstrapped install path that no longer exists on disk', () => {
  const dir = path.join(tmpRoot, 'no-workspace-venv');
  const deletedInstall = path.join(tmpRoot, 'bootstrapped-deleted', 'bin', 'structifact');
  mockConfig = { value: undefined, explicit: false };

  // Same posture as the workspace .venv/venv check above: a path
  // that doesn't actually exist (the venv could have been deleted
  // since install) falls through to the next tier rather than being
  // trusted blindly.
  assert.strictEqual(resolveCliPath(wsFolder(dir), deletedInstall), 'structifact');
});

await test('resolveCliPath still prefers an explicit setting over a bootstrapped install', () => {
  const dir = path.join(tmpRoot, 'no-workspace-venv');
  const installed = path.join(tmpRoot, 'bootstrapped', 'bin', 'structifact');
  mockConfig = { value: '/custom/structifact', explicit: true };

  assert.strictEqual(resolveCliPath(wsFolder(dir), installed), '/custom/structifact');
});

await test('resolveCliPath still prefers a workspace .venv over a bootstrapped install', () => {
  const dir = path.join(tmpRoot, 'dotvenv'); // has .venv/bin/structifact from the first test above
  const installed = path.join(tmpRoot, 'bootstrapped', 'bin', 'structifact');
  fs.mkdirSync(path.dirname(installed), { recursive: true });
  fs.writeFileSync(installed, '');
  mockConfig = { value: undefined, explicit: false };

  assert.strictEqual(
    resolveCliPath(wsFolder(dir), installed),
    path.join(dir, '.venv', 'bin', 'structifact')
  );
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

// --- findRelatedNotes ---
// Each excerpt below is drawn directly from a real discover --ai
// draft already in this repo (or, for hard_insurance_claims, was
// once real output before the pick_one_order_by fix -- see
// docs/PICK_ONE_ORDER_BY_CONTRACT.md) -- not synthesized in the
// abstract, matching investigation finding #5's own evidence.

await test('findRelatedNotes links the real resolved_fx_rate/labor_amount_usd case (workorder_demo)', () => {
  // examples/workorder_demo/work_order_source.discovered.yml: a
  // computed field's expression references resolved_fx_rate, which
  // is never itself declared as a field -- the note doesn't name
  // "resolved_fx_rate" as a declared identifier (it can't; nothing by
  // that name is declared), but it does name "labor_amount_usd", the
  // real declared field whose expression is the actual problem.
  const text = [
    'fields:',
    '  - name: "labor_amount_lc"',
    '    type: "decimal(15,2)"',
    '',
    '  - name: "labor_amount_usd"',
    '    type: "decimal(15,2)"',
    '    computed: true',
    '    expression: "labor_amount_lc * resolved_fx_rate"',
    '',
    'unresolved_notes:',
    '  - "resolved_fx_rate is referenced in labor_amount_usd expression but not explicitly defined as a source column \\u2014 inferred as output of FX lookup with fallback logic applied"',
  ].join('\n');

  assert.deepStrictEqual(findRelatedNotes(text), [
    {
      name: 'labor_amount_usd',
      kind: 'field',
      declarationLine: 4,
      noteLine: 10,
      noteText: (
        'resolved_fx_rate is referenced in labor_amount_usd expression but not ' +
        'explicitly defined as a source column — inferred as output of FX ' +
        'lookup with fallback logic applied'
      ),
    },
  ]);
});

await test('findRelatedNotes links the real policy_status join case (hard_insurance_claims) to both its source and its join', () => {
  // examples/coverage_round1/requirements_docs/hard_insurance_claims.discovered.yml:
  // the note names "policy_status" (and, lowercased, its table
  // POLICY_STATUS_HISTORY) -- both the sources[] declaration and the
  // joins[] entry pulling it in are real, separate declarations that
  // should each surface this note, not just one of them.
  const text = [
    'fields:',
    '  - name: "policy_status_as_of_claim"',
    '    source: "policy_status"',
    '',
    'source_table: "CLAIM_HDR"',
    '',
    'sources:',
    '  - name: "policy_status"',
    '    table: "POLICY_STATUS_HISTORY"',
    '',
    'joins:',
    '  - source: "policy_status"',
    '    "on": "CLAIM_HDR.policy_id = policy_status.policy_id and policy_status.effective_date <= CLAIM_HDR.claim_date"',
    '',
    'unresolved_notes:',
    '  - "policy_status join on policy_status_history requires selecting the row with the most recent effective_date on or before the claim_date; this dedup/priority rule is not fully expressible in the \'on\' condition alone and may require window function logic in the actual query."',
  ].join('\n');

  const noteText = (
    'policy_status join on policy_status_history requires selecting the row ' +
    "with the most recent effective_date on or before the claim_date; this " +
    "dedup/priority rule is not fully expressible in the 'on' condition alone " +
    'and may require window function logic in the actual query.'
  );

  assert.deepStrictEqual(findRelatedNotes(text), [
    { name: 'policy_status', kind: 'source', declarationLine: 7, noteLine: 15, noteText },
    { name: 'policy_status', kind: 'join', declarationLine: 11, noteLine: 15, noteText },
  ]);
});

await test('findRelatedNotes links the real ADRC filter case (output/Vendors.discovered.yml) and leaves the unlinkable sibling note unlinked', () => {
  // This repo's own real end-to-end test file (this session):
  // output/Vendors.discovered.yml has two notes about the same ADRC
  // filter -- one that names "ADRC" (linkable) and a second that
  // names nothing declared at all ("filter text inserted as-is
  // pending clarification"), a real, unlinkable case -- confirming
  // this function correctly returns nothing for a note it has no
  // real basis to link, rather than guessing.
  const text = [
    'sources:',
    '  - name: "lfb1"',
    '    table: "lfb1"',
    '  - name: "adrc"',
    '    table: "adrc"',
    '    filter: "date_from <= \'12/31/9999\' AND date_to >= \'12/31/9999\'"',
    '',
    'joins:',
    '  - source: "adrc"',
    '    "on": "lfa1.adrnr = adrc.addrnumber"',
    '',
    'unresolved_notes:',
    '  - "ADRC table note states \'Filter = Valid To 12/31/9999\' but the exact filter logic (whether this is a date range constraint or equality check) is not fully specified; interpreted as a validity window constraint."',
    '  - "No explicit \'Valid To 12/31/9999\' filter SQL syntax provided; filter text inserted as-is pending clarification."',
  ].join('\n');

  const links = findRelatedNotes(text);

  const adrcNoteText = (
    "ADRC table note states 'Filter = Valid To 12/31/9999' but the exact " +
    'filter logic (whether this is a date range constraint or equality ' +
    'check) is not fully specified; interpreted as a validity window constraint.'
  );

  assert.deepStrictEqual(links, [
    { name: 'adrc', kind: 'source', declarationLine: 3, noteLine: 12, noteText: adrcNoteText },
    { name: 'adrc', kind: 'join', declarationLine: 8, noteLine: 12, noteText: adrcNoteText },
  ]);

  // The second note (line 13) never names ADRC or lfb1 -- confirm
  // nothing links to it.
  assert.ok(!links.some((l) => l.noteLine === 13));
});

await test('findRelatedNotes does not false-positive on a name embedded inside a longer compound token', () => {
  // A real excerpt from output/Vendors.discovered.yml: the note talks
  // about "struct_lfb1_mandt" (a descriptive compound term the AI
  // invented, not a real declared identifier) -- "lfb1" must NOT be
  // treated as mentioned just because it appears as a substring of
  // that compound word. The same note also genuinely names the real
  // declared field "mandt" as its own quoted word, which SHOULD link.
  const text = [
    'fields:',
    '  - name: "mandt"',
    '',
    'sources:',
    '  - name: "lfb1"',
    '    table: "lfb1"',
    '',
    'unresolved_notes:',
    '  - "struct_lfb1_mandt, struct_lfm1_mandt, struct_adrc_client, struct_adr6_client appear to represent the same \'mandt\' (Client) field across multiple source tables; only included from lfa1 main table and referenced via source joins."',
  ].join('\n');

  const links = findRelatedNotes(text);

  const noteText = (
    'struct_lfb1_mandt, struct_lfm1_mandt, struct_adrc_client, struct_adr6_client ' +
    "appear to represent the same 'mandt' (Client) field across multiple source " +
    'tables; only included from lfa1 main table and referenced via source joins.'
  );

  assert.deepStrictEqual(links, [
    { name: 'mandt', kind: 'field', declarationLine: 1, noteLine: 8, noteText },
  ]);
  assert.ok(!links.some((l) => l.name === 'lfb1'));
});

await test('findRelatedNotes returns an empty array when there are no unresolved_notes', () => {
  const text = 'fields:\n  - name: "customer_id"\n    type: "integer"\n';
  assert.deepStrictEqual(findRelatedNotes(text), []);
});

// --- noteAcknowledgeKey / relatedAcknowledgeKey ---
// The whole point of a content-based key: it must survive the note's
// own line number changing (an edit anywhere earlier in the file
// shifts every line below it) -- these test the raw key functions in
// isolation; buildReviewQuickPickItems' own tests below cover the
// same guarantee at the level Review actually uses it.

await test('noteAcknowledgeKey produces the same key for the same text regardless of line number', () => {
  const text = 'resolved_fx_rate is referenced in labor_amount_usd expression but not explicitly defined as a source column';
  assert.strictEqual(noteAcknowledgeKey(text), noteAcknowledgeKey(text));
  // deliberately no line number is ever passed in -- this line exists
  // only to make that omission explicit, not to exercise anything
  // noteAcknowledgeKey's own signature doesn't already guarantee.
});

await test('noteAcknowledgeKey produces different keys for different text', () => {
  assert.notStrictEqual(noteAcknowledgeKey('first note'), noteAcknowledgeKey('second note'));
});

await test('relatedAcknowledgeKey produces the same key regardless of declarationLine, but differs by kind or name', () => {
  assert.strictEqual(relatedAcknowledgeKey('source', 'policy_status'), relatedAcknowledgeKey('source', 'policy_status'));
  assert.notStrictEqual(relatedAcknowledgeKey('source', 'policy_status'), relatedAcknowledgeKey('join', 'policy_status'));
  assert.notStrictEqual(relatedAcknowledgeKey('source', 'policy_status'), relatedAcknowledgeKey('source', 'fx_rate'));
});

// --- buildReviewQuickPickItems ---
// Real-shaped fixtures reused from findRelatedNotes' own tests above
// (the workorder resolved_fx_rate note, the hard_insurance_claims
// policy_status source/join pair) -- not synthesized in the abstract.

function _fixtureInput(overrides) {
  return Object.assign({
    errorMessages: [],
    warningMessages: [],
    needsReviewItems: [],
    unresolvedNotes: [],
    relatedGroups: [],
    acknowledgedKeys: new Set(),
  }, overrides);
}

const FX_NOTE_TEXT = (
  'resolved_fx_rate is referenced in labor_amount_usd expression but not ' +
  'explicitly defined as a source column — inferred as output of FX ' +
  'lookup with fallback logic applied'
);
const POLICY_STATUS_GROUP = {
  kind: 'source', name: 'policy_status', declarationLine: 7, noteLines: [15],
};

await test('buildReviewQuickPickItems shows an Acknowledge button on note/related items and no Acknowledged section when nothing is acknowledged', () => {
  const items = buildReviewQuickPickItems(_fixtureInput({
    unresolvedNotes: [{ line: 10, text: FX_NOTE_TEXT }],
    relatedGroups: [POLICY_STATUS_GROUP],
  }));

  const labels = items.map((i) => i.label);
  assert.ok(labels.includes('Unresolved Notes'));
  assert.ok(labels.includes('Related to Unresolved Notes'));
  assert.ok(!labels.includes('Acknowledged'));

  const noteItem = items.find((i) => i.label === `$(note) ${FX_NOTE_TEXT}`);
  assert.ok(noteItem, 'expected the note item to be present, unacknowledged');
  assert.strictEqual(noteItem.buttons.length, 1);
  assert.strictEqual(noteItem.ackKey, noteAcknowledgeKey(FX_NOTE_TEXT));

  const relatedItem = items.find((i) => i.ackKey === relatedAcknowledgeKey('source', 'policy_status'));
  assert.ok(relatedItem, 'expected the related-note item to be present, unacknowledged');
  assert.strictEqual(relatedItem.buttons.length, 1);
});

await test('buildReviewQuickPickItems demotes an acknowledged note into a trailing Acknowledged section, with no button, and drops the empty Unresolved Notes section', () => {
  const items = buildReviewQuickPickItems(_fixtureInput({
    unresolvedNotes: [{ line: 10, text: FX_NOTE_TEXT }],
    relatedGroups: [POLICY_STATUS_GROUP], // left unacknowledged, for contrast
    acknowledgedKeys: new Set([noteAcknowledgeKey(FX_NOTE_TEXT)]),
  }));

  const labels = items.map((i) => i.label);
  assert.ok(!labels.includes('Unresolved Notes'), 'the only note was acknowledged, so this section should be gone');
  assert.ok(labels.includes('Acknowledged'));
  assert.ok(labels.includes('Related to Unresolved Notes'), 'the unrelated, unacknowledged related-note item should still show normally');

  const acknowledgedItem = items.find((i) => i.label === `$(check) ${FX_NOTE_TEXT}`);
  assert.ok(acknowledgedItem, 'expected the checkmark-relabeled item');
  assert.ok(acknowledgedItem.description.includes('acknowledged'));
  assert.ok(!acknowledgedItem.buttons || acknowledgedItem.buttons.length === 0);
});

await test('buildReviewQuickPickItems recognizes an acknowledgment even when the note\'s line number has since changed', () => {
  // The acknowledgment was recorded against this exact text while it
  // sat at line 10 (e.g. before an unrelated edit earlier in the file
  // shifted everything below it down); Review now finds the SAME text
  // at line 42. A line-keyed implementation would miss this and show
  // it as unacknowledged again -- the whole reason this is
  // content-keyed at all.
  const acknowledgedKeys = new Set([noteAcknowledgeKey(FX_NOTE_TEXT)]);

  const items = buildReviewQuickPickItems(_fixtureInput({
    unresolvedNotes: [{ line: 42, text: FX_NOTE_TEXT }],
    acknowledgedKeys,
  }));

  const acknowledgedItem = items.find((i) => i.label === `$(check) ${FX_NOTE_TEXT}`);
  assert.ok(acknowledgedItem, 'expected the note to still be recognized as acknowledged at its new line');
  assert.ok(acknowledgedItem.description.includes('line 43'));
  assert.ok(!items.some((i) => i.label === 'Unresolved Notes'));
});

await test('buildReviewQuickPickItems never attaches an Acknowledge button to Errors/Warnings/NEEDS REVIEW items', () => {
  const items = buildReviewQuickPickItems(_fixtureInput({
    errorMessages: ['bad thing'],
    warningMessages: ['careful'],
    needsReviewItems: [{ line: 2, text: 'looks off' }],
  }));

  const nonSeparators = items.filter((i) => i.kind !== fakeVscode.QuickPickItemKind.Separator);
  assert.ok(nonSeparators.length > 0);
  for (const item of nonSeparators) {
    assert.ok(!item.buttons, `expected no buttons on: ${item.label}`);
    assert.strictEqual(item.ackKey, undefined);
  }
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
