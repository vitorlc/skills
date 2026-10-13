import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const home = fs.mkdtempSync(path.join(os.tmpdir(), 'skills-install-'));
// Isolate the installer without modifying HOME or touching actual host installations.
os.homedir = () => home;
const { installSkill, uninstallSkill } = await import('../src/install.mjs');
const { skillPath, resolveTargets } = await import('../src/targets.mjs');
const { findInstalledMeta, readMeta, writeMeta } = await import('../src/manifest.mjs');
const name = 'smiles-passagens';
const put = (file, value) => { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, value); };
const read = file => fs.readFileSync(file, 'utf8');

function reset() { for (const entry of fs.readdirSync(home)) fs.rmSync(path.join(home, entry), { recursive: true, force: true }); }
test.after(() => fs.rmSync(home, { recursive: true, force: true }));
test.beforeEach(reset);

test('dry run does not create installs', () => {
  installSkill(name, { dryRun: true });
  assert.deepEqual(fs.readdirSync(home), []);
});
test('default links share state and update preserves cache/config/history/dependencies', () => {
  installSkill(name);
  const primary = skillPath('claude', name);
  for (const rel of ['tmp/snapshots/x.json', 'data/x', '.cache/session', '.env', 'report.html', 'scripts/node_modules/custom/index.js']) put(path.join(primary, rel), rel);
  put(path.join(primary, 'obsolete.mjs'), 'remove me');
  installSkill(name, { force: true });
  for (const rel of ['tmp/snapshots/x.json', 'data/x', '.cache/session', '.env', 'report.html', 'scripts/node_modules/custom/index.js']) assert.equal(read(path.join(primary, rel)), rel);
  assert.ok(!fs.existsSync(path.join(primary, 'obsolete.mjs')));
  assert.ok(fs.lstatSync(skillPath('agents', name)).isSymbolicLink());
  assert.ok(fs.existsSync(path.join(primary, 'scripts/data/airports.json')));
});
test('independent copies retain their own state even on a default update', () => {
  installSkill(name, { copy: true });
  for (const host of ['claude', 'agents', 'opencode']) put(path.join(skillPath(host, name), 'tmp/state'), host);
  installSkill(name, { force: true });
  for (const host of ['claude', 'agents', 'opencode']) {
    assert.equal(read(path.join(skillPath(host, name), 'tmp/state')), host);
    assert.ok(!fs.lstatSync(skillPath(host, name)).isSymbolicLink());
  }
});
test('target-specific update detaches a link without changing an unselected host', () => {
  installSkill(name);
  const primary = skillPath('claude', name);
  put(path.join(primary, 'tmp/state'), 'keep');
  put(path.join(primary, 'local-code.txt'), 'unselected');
  installSkill(name, { target: 'agents', force: true });
  assert.equal(read(path.join(primary, 'local-code.txt')), 'unselected');
  assert.equal(read(path.join(skillPath('agents', name), 'tmp/state')), 'keep');
  assert.ok(!fs.existsSync(path.join(skillPath('agents', name), 'local-code.txt')));
});
test('unchanged install skips and --force reinstalls; damaged code is repaired', () => {
  installSkill(name, { target: 'claude' });
  const dest = skillPath('claude', name);
  writeMeta(dest, { ...readMeta(dest), installedAt: 'sentinel' });
  installSkill(name, { target: 'claude' });
  assert.equal(readMeta(dest).installedAt, 'sentinel');
  installSkill(name, { target: 'claude', force: true });
  assert.notEqual(readMeta(dest).installedAt, 'sentinel');
  put(path.join(dest, 'SKILL.md'), 'damaged');
  installSkill(name, { target: 'claude' });
  assert.match(read(path.join(dest, 'SKILL.md')), /name: smiles-passagens/);
});
test('installation lookup respects selected targets and recognizes unmanaged copies', () => {
  installSkill(name, { target: 'claude' });
  assert.equal(findInstalledMeta(name, ['agents']), null);
  put(path.join(skillPath('agents', name), 'SKILL.md'), 'manual');
  assert.equal(findInstalledMeta(name, ['agents']).meta, null);
});
test('invalid paths and empty targets fail before mutation', () => {
  assert.throws(() => uninstallSkill('../outside'), /Invalid skill name/);
  assert.throws(() => resolveTargets(','), /at least one/);
  assert.deepEqual(fs.readdirSync(home), []);
});
test('uninstall refuses to strand unselected links; --copy detaches with nested links intact', () => {
  installSkill(name);
  const primary = skillPath('claude', name);
  put(path.join(primary, 'tmp/private.json'), 'state');
  fs.chmodSync(path.join(primary, 'tmp/private.json'), 0o600);
  fs.symlinkSync('private.json', path.join(primary, 'tmp/latest.json'));
  assert.throws(() => uninstallSkill(name, { target: 'claude' }), /shares/);
  installSkill(name, { target: 'agents', copy: true });
  const detached = skillPath('agents', name);
  assert.equal(read(path.join(detached, 'tmp/latest.json')), 'state');
  assert.equal(fs.statSync(path.join(detached, 'tmp/private.json')).mode & 0o777, 0o600);
  uninstallSkill(name, { target: 'claude,opencode' });
  assert.equal(read(path.join(detached, 'tmp/latest.json')), 'state');
});
test('dependency lock changes invalidate installed modules without deleting runtime state', () => {
  const flight = 'melhor-preco-passagens';
  installSkill(flight, { target: 'claude' });
  const dest = skillPath('claude', flight);
  put(path.join(dest, '.cache/session'), 'keep');
  put(path.join(dest, 'scripts/node_modules/old/index.js'), 'obsolete');
  put(path.join(dest, 'scripts/package-lock.json'), '{}');
  installSkill(flight, { target: 'claude' });
  assert.ok(!fs.existsSync(path.join(dest, 'scripts/node_modules')));
  assert.equal(read(path.join(dest, '.cache/session')), 'keep');
});
