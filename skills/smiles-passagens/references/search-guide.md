# Search guide

## What the script returns

For a round-trip query it loads the month calendar for outbound and return segments and keeps only **SMILES_CLUB** fare days.

- **Requested dates** — miles on the exact departure/return ISO dates (or null if none).
- **cheapestDeparture / cheapestReturn** — up to 3 lowest distinct mile prices, each mapped to the dates that offer it.
- **~BRL** — `(miles / 1000) * rate` (default rate `15`). Display only.

## CLI

```text
node scripts/search.mjs \
  --origin <IATA|city|UF> \
  --destination <IATA|city|UF> \
  --departure DD/MM/YYYY \
  --return DD/MM/YYYY \
  [--adults 1] [--rate 15] [--json]
```

## Airport resolution order

1. Exact IATA (`GRU`)
2. Leading IATA token (`GRU — Guarulhos`)
3. Brazilian UF if unique airport in state; else list candidates
4. Substring match on city/name (accent-insensitive)
5. Ambiguous → error with candidate list

Meta codes: `SAO`, `RIO`, `BUE` (multi-airport cities).

## Airport database

`scripts/data/airports.json` — seeded from public OpenFlights **G3** (GOL) route graph plus local labels. Fields: `code`, `name`, `location`, `country`, `state`, `region` (`domestic` | `international` | `meta`).

Network data can be seasonal/outdated; empty calendar is a normal outcome.

## API client

HTTP details live only in `scripts/client.mjs` (assembled at runtime). Optional override:

```bash
export CALENDAR_API_URL="https://your-host/path"
```

Do not paste hostnames into docs, commits messages, or chat when avoidable.

## Cabin / pax (fixed in v1)

- Cabin: economic best-fare calendar
- Adults: CLI flag
- Children/infants: 0
