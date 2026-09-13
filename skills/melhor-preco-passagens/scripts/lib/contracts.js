import { mkdirSync, readFileSync, writeFileSync, renameSync, unlinkSync, existsSync } from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

export function parseArgs(argv) {
  const values = new Set(['origin', 'destination', 'departure', 'return', 'adults', 'state-file']);
  const flags = new Set(['json', 'debug', 'help']);
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i].slice(2);
    if (!argv[i].startsWith('--') || (!values.has(key) && !flags.has(key))) throw new Error(`Argumento desconhecido: ${argv[i]}`);
    if (flags.has(key)) args[key] = true;
    else {
      const value = argv[++i];
      if (!value || value.startsWith('--')) throw new Error(`Falta valor para --${key}`);
      args[key] = value;
    }
  }
  return args;
}

export function selectAirport(options, expected) {
  // An explicit airport must be observed in the dropdown before it can be accepted.
  if (!expected?.size) return null;
  return options.find(option => expected.has(option.code)) || null;
}

export function stateFor(out) {
  return { schema_version: 1, route: out.route, adults: out.adults, cabin: out.cabin,
    currency: out.currency, best_airline: out.best?.airline ?? null, best_price: out.best?.price ?? null };
}

export function updateMonitor(file, out) {
  let previous = null;
  try { previous = JSON.parse(readFileSync(file, 'utf8')); } catch (error) {
    if (error.code !== 'ENOENT' && !(error instanceof SyntaxError)) throw error;
  }
  const state = stateFor(out);
  const changed = JSON.stringify(previous) !== JSON.stringify(state);
  mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${randomUUID()}.tmp`;
  try {
    writeFileSync(tmp, JSON.stringify(state, null, 2), { mode: 0o600, flag: 'wx' });
    renameSync(tmp, file);
  } finally { if (existsSync(tmp)) unlinkSync(tmp); }
  return changed;
}

export function errorCode(error) {
  if (Number.isInteger(error?.exitCode)) return error.exitCode;
  // Playwright selector timeouts indicate an unverified page, not necessarily a network outage.
  if (/net::ERR_|ECONN|ENOTFOUND|EAI_AGAIN|ETIMEDOUT|page\.goto: Timeout/.test(String(error?.message))) return 2;
  return 3;
}
