import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { parseArgs, selectAirport, updateMonitor, errorCode } from '../scripts/lib/contracts.js';
import { resolveAirport } from '../scripts/lib/airports.js';

test('arguments reject unknown flags, missing values and unexpected positional data', () => {
  for (const args of [['--adults'], ['--origin', '--json'], ['--unknown'], ['GYN']]) assert.throws(() => parseArgs(args));
  assert.deepEqual(parseArgs(['--origin', 'GYN', '--json']), { origin: 'GYN', json: true });
});
test('an unexpected airport is never selected as fallback', () => {
  assert.equal(selectAirport([{ code: 'GRX' }], new Set(['GYN'])), null);
  assert.equal(selectAirport([], new Set(['GYN'])), null);
  assert.equal(selectAirport([{ code: 'GYN' }], new Set(['GYN'])).code, 'GYN');
  assert.equal(resolveAirport('MIA'), null);
  assert.equal(resolveAirport('cidade desconhecida'), null);
  assert.ok(resolveAirport('MS').expect.has('CGR'));
});
test('monitor identity includes route, passengers, dates and currency, with atomic state', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flight-state-'));
  try {
    const file = path.join(dir, 'nested', 'state.json');
    const out = { route: { origin: 'GYN', destination: 'REC', departure: '2027-03-15', return: '2027-03-22' }, adults: 1, cabin: 'ECONOMY', currency: 'BRL', best: { airline: 'GOL', price: 1000 } };
    assert.equal(updateMonitor(file, out), true);
    assert.equal(updateMonitor(file, { ...out, fetched_at: 'later' }), false);
    for (const change of [{ adults: 2 }, { route: { ...out.route, origin: 'BSB' } }, { best: { airline: 'AZUL', price: 1000 } }, { best: { airline: 'GOL', price: 999 } }]) {
      updateMonitor(file, out);
      assert.equal(updateMonitor(file, { ...out, ...change }), true);
    }
    fs.writeFileSync(file, 'invalid JSON');
    assert.equal(updateMonitor(file, out), true);
    assert.deepEqual(fs.readdirSync(path.dirname(file)), ['state.json']);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
test('network errors differ from unverified UI and setup errors', () => {
  assert.equal(errorCode(new Error('page.goto: net::ERR_NAME_NOT_RESOLVED')), 2);
  assert.equal(errorCode(new Error('page.goto: Timeout 60000ms exceeded')), 2);
  assert.equal(errorCode(new Error('locator.click: Timeout')), 3);
  assert.equal(errorCode({ exitCode: 1 }), 1);
});
test('CLI rejects invalid trips before browser initialization and never prints a fare', async () => {
  const { spawnSync } = await import('node:child_process');
  const cli = new URL('../scripts/search.mjs', import.meta.url);
  for (const args of [
    ['--adults', '1.5'], ['--adults', '2people'],
    ['--departure', '31/02/2099'], ['--origin', 'MIA'], ['--unknown'],
  ]) {
    const result = spawnSync(process.execPath, [cli.pathname, '--origin', 'GYN', '--destination', 'REC', '--departure', '15/03/2099', '--return', '22/03/2099', ...args], { encoding: 'utf8' });
    assert.equal(result.status, 1, result.stderr);
    assert.equal(result.stdout, '');
  }
});
