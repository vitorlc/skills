import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_PATH = path.join(__dirname, "data", "airports.json");

let _cache = null;

export function loadAirports() {
  if (_cache) return _cache;
  const raw = JSON.parse(fs.readFileSync(DATA_PATH, "utf8"));
  _cache = raw.airports || [];
  return _cache;
}

export function listAirports({ region } = {}) {
  const all = loadAirports();
  if (!region) return all;
  return all.filter((a) => a.region === region);
}

/**
 * Resolve free text / IATA / UF / city to a single airport.
 * @returns {{ ok: true, airport } | { ok: false, error: string, candidates?: object[] }}
 */
export function resolveAirport(query) {
  if (query == null || String(query).trim() === "") {
    return { ok: false, error: "Empty airport query" };
  }

  const all = loadAirports();
  const text = String(query).trim();
  const upper = text.toUpperCase();

  // Exact IATA
  const byCode = all.find((a) => a.code === upper);
  if (byCode) return { ok: true, airport: byCode };

  // Head token (e.g. "GRU — Guarulhos")
  const head = upper.split(/[\s—\-,/|]+/)[0];
  if (head.length === 3) {
    const h = all.find((a) => a.code === head);
    if (h) return { ok: true, airport: h };
  }

  // Brazilian state UF (2 letters) — prefer capital/main if multiple
  if (/^[A-Z]{2}$/.test(upper)) {
    const inState = all.filter((a) => a.state === upper && a.region === "domestic");
    if (inState.length === 1) return { ok: true, airport: inState[0] };
    if (inState.length > 1) {
      return {
        ok: false,
        error: `Ambiguous state ${upper}: pick an IATA code`,
        candidates: inState,
      };
    }
  }

  const term = text.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
  const matches = all.filter((a) => {
    const loc = (a.location || "").toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
    const name = (a.name || "").toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
    return loc.includes(term) || name.includes(term) || loc === term;
  });

  if (matches.length === 1) return { ok: true, airport: matches[0] };
  if (matches.length > 1) {
    const exact = matches.filter((a) => {
      const loc = (a.location || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/\p{M}/gu, "");
      return loc === term;
    });
    if (exact.length === 1) return { ok: true, airport: exact[0] };
    // Multi-airport city → prefer meta code (BUE, SAO, RIO)
    const pool = exact.length ? exact : matches;
    const meta = pool.filter((a) => a.region === "meta");
    if (meta.length === 1) return { ok: true, airport: meta[0] };
    return {
      ok: false,
      error: `Ambiguous query "${query}": pick an IATA code`,
      candidates: pool.slice(0, 12),
    };
  }

  return { ok: false, error: `Airport not found: ${query}` };
}
