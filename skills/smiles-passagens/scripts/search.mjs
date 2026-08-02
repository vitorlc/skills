#!/usr/bin/env node
import { resolveAirport } from "./airports.mjs";
import { searchSmiles } from "./smilesSearch.mjs";

function printHelp() {
  console.log(`Usage:
  node search.mjs --origin <IATA|city> --destination <IATA|city> \\
    --departure DD/MM/YYYY --return DD/MM/YYYY \\
    [--adults 1] [--rate 15] [--json]

Options:
  -o, --origin         Origin airport (IATA, city, or UF)
  -d, --destination    Destination airport
  --departure          Outbound date DD/MM/YYYY
  --return             Return date DD/MM/YYYY
  --adults             Number of adults (default 1)
  --rate               BRL per 1000 miles for estimate (default 15)
  --json               Machine-readable output
  -h, --help           Show help
`);
}

function parseArgs(argv) {
  const out = {
    origin: null,
    destination: null,
    departure: null,
    return: null,
    adults: 1,
    rate: 15,
    json: false,
    help: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case "-h":
      case "--help":
        out.help = true;
        break;
      case "-o":
      case "--origin":
        out.origin = next();
        break;
      case "-d":
      case "--destination":
        out.destination = next();
        break;
      case "--departure":
        out.departure = next();
        break;
      case "--return":
        out.return = next();
        break;
      case "--adults":
        out.adults = Number(next());
        break;
      case "--rate":
        out.rate = Number(next());
        break;
      case "--json":
        out.json = true;
        break;
      default:
        if (a.startsWith("-")) throw new Error(`Unknown flag: ${a}`);
        throw new Error(`Unexpected argument: ${a}`);
    }
  }
  return out;
}

const DATE_RE = /^\d{2}\/\d{2}\/\d{4}$/;

function fmtMiles(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString("pt-BR");
}

function fmtBrl(miles, rate) {
  if (miles == null || typeof miles !== "number") return "—";
  const v = (miles / 1000) * rate;
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function fmtDateISO(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

function mustResolve(label, query) {
  const r = resolveAirport(query);
  if (!r.ok) {
    let msg = `${label}: ${r.error}`;
    if (r.candidates?.length) {
      msg +=
        "\n  Options:\n" +
        r.candidates
          .map(
            (a) =>
              `    ${a.code} — ${a.location}${a.state ? "/" + a.state : ""} (${a.country})`
          )
          .join("\n");
    }
    const err = new Error(msg);
    err.code = "VALIDATION";
    throw err;
  }
  return r.airport;
}

function enrich(result, rate) {
  const depM = result.departure.miles;
  const retM = result.return.miles;
  const totalMiles =
    typeof depM === "number" && typeof retM === "number" ? depM + retM : null;
  return {
    ...result,
    rate,
    departure: {
      ...result.departure,
      brl: typeof depM === "number" ? Math.round((depM / 1000) * rate * 100) / 100 : null,
    },
    return: {
      ...result.return,
      brl: typeof retM === "number" ? Math.round((retM / 1000) * rate * 100) / 100 : null,
    },
    total: {
      miles: totalMiles,
      brl:
        totalMiles != null
          ? Math.round((totalMiles / 1000) * rate * 100) / 100
          : null,
    },
  };
}

function formatMarkdown(data, originMeta, destMeta) {
  const lines = [];
  const oLabel = `${data.origin} (${originMeta.location})`;
  const dLabel = `${data.destination} (${destMeta.location})`;
  lines.push(`# Smiles  ${oLabel} → ${dLabel}  ·  ${data.adults} adulto(s)`);
  lines.push("");
  lines.push("## Datas pedidas");
  lines.push("");
  lines.push("| Trecho | Data | Milhas | ~R$ |");
  lines.push("|--------|------|--------|-----|");
  lines.push(
    `| Ida | ${fmtDateISO(data.departure.date)} | ${fmtMiles(data.departure.miles)} | ${fmtBrl(data.departure.miles, data.rate)} |`
  );
  lines.push(
    `| Volta | ${fmtDateISO(data.return.date)} | ${fmtMiles(data.return.miles)} | ${fmtBrl(data.return.miles, data.rate)} |`
  );
  lines.push(
    `| **Total** | | **${fmtMiles(data.total.miles)}** | **${fmtBrl(data.total.miles, data.rate)}** |`
  );
  lines.push("");
  lines.push(`_Estimativa R$ com taxa ${data.rate}/1.000 milhas (apenas referência)._`);
  lines.push("");

  const section = (title, map) => {
    lines.push(`## ${title}`);
    lines.push("");
    const entries = Object.entries(map || {}).sort((a, b) => Number(a[0]) - Number(b[0]));
    if (!entries.length) {
      lines.push("_Sem tarifas SMILES_CLUB no calendário._");
      lines.push("");
      return;
    }
    for (const [miles, dates] of entries) {
      const ds = dates.map(fmtDateISO).join(", ");
      lines.push(`- **${fmtMiles(Number(miles))} milhas** (~${fmtBrl(Number(miles), data.rate)}): ${ds}`);
    }
    lines.push("");
  };

  section("Melhores idas (top 3)", data.cheapestDeparture);
  section("Melhores voltas (top 3)", data.cheapestReturn);
  return lines.join("\n");
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (e) {
    console.error(e.message);
    printHelp();
    process.exit(1);
  }

  if (args.help) {
    printHelp();
    process.exit(0);
  }

  try {
    if (!args.origin || !args.destination || !args.departure || !args.return) {
      throw Object.assign(
        new Error("Required: --origin --destination --departure --return"),
        { code: "VALIDATION" }
      );
    }
    if (!DATE_RE.test(args.departure) || !DATE_RE.test(args.return)) {
      throw Object.assign(new Error("Dates must be DD/MM/YYYY"), {
        code: "VALIDATION",
      });
    }
    if (!Number.isFinite(args.adults) || args.adults < 1) {
      throw Object.assign(new Error("--adults must be >= 1"), {
        code: "VALIDATION",
      });
    }
    if (!Number.isFinite(args.rate) || args.rate <= 0) {
      throw Object.assign(new Error("--rate must be > 0"), {
        code: "VALIDATION",
      });
    }

    const originMeta = mustResolve("origin", args.origin);
    const destMeta = mustResolve("destination", args.destination);

    const raw = await searchSmiles({
      origin: originMeta.code,
      destination: destMeta.code,
      departureRaw: args.departure,
      returnRaw: args.return,
      adults: args.adults,
    });

    if (!raw) {
      console.error(
        "No calendar data for this route/dates (empty result or unsupported pair)."
      );
      process.exit(2);
    }

    const data = enrich(raw, args.rate);
    data.originName = originMeta.location;
    data.destinationName = destMeta.location;

    if (args.json) {
      console.log(JSON.stringify(data, null, 2));
    } else {
      console.log(formatMarkdown(data, originMeta, destMeta));
    }
  } catch (e) {
    if (e.code === "VALIDATION") {
      console.error(e.message);
      process.exit(1);
    }
    console.error(e.message || e);
    process.exit(2);
  }
}

main();
