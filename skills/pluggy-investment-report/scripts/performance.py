#!/usr/bin/env python3
"""
Period performance for pluggy-investment-report.

Usage:
  python performance.py <investments.json> [--since 30d|12m|ytd|YYYY-MM-DD]
                        [--benchmarks] [--json OUT.json]

Compares the current collection with a stored snapshot and separates real
return from deposits/withdrawals using the Modified Dietz method:

    return = (V1 - V0 - F) / (V0 + sum(F_i * weight_i))

Run it BEFORE snapshot_diff.py records the current collection, otherwise the
baseline can be this very collection. Read-only: it never writes history.

--benchmarks queries the public Banco Central SGS API (CDI daily series 12,
IPCA monthly series 433; no credentials) with a local 12h cache. Failures
there never fail the analysis.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

import snapshot_diff
from report_model import (coverage, data_dir, format_currency, format_percentage, get_type_label,
                          investments_list, migrate_legacy, parse_ts, private_json, private_write)

BCB_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
CDI_SERIES, IPCA_SERIES = 12, 433
CACHE_TTL_SECONDS = 12 * 3600
MIN_ANNUALIZE_DAYS = 30
INFLOW_TYPES, OUTFLOW_TYPES = {"BUY"}, {"SELL", "AMORTIZATION"}


class BenchmarkError(RuntimeError):
    pass


# ── Flows ────────────────────────────────────────────────────────────────────

def _tx_date(value: str) -> datetime | None:
    try:
        return parse_ts(value)
    except (ValueError, AttributeError):
        return None


def asset_flows(prev: dict, curr: dict, t0: datetime, t1: datetime):
    """Net money moved into (+) / out of (-) one asset between two observations.

    Returns (flows, source). flows is a list of (datetime | None, amount); None
    means "unknown moment", weighted as mid-period.
    source: transactions | estimated (cost-basis change) | assumed (all change is return).
    """
    txs = curr.get("transactions")
    if txs is not None:
        flows = []
        for tx in txs:
            moment = _tx_date(tx["date"])
            if moment is None or not t0 < moment <= t1:
                continue
            amount = abs(tx["amount"])
            if tx["type"] in INFLOW_TYPES:
                flows.append((moment, amount))
            elif tx["type"] in OUTFLOW_TYPES:
                flows.append((moment, -amount))
        return flows, "transactions"
    if prev.get("amount") is not None and curr.get("amount") is not None:
        delta = curr["amount"] - prev["amount"]
        return ([(None, delta)] if abs(delta) > 0.005 else []), "estimated"
    return [], "assumed"


def dietz(records: list[dict], t0: datetime, t1: datetime) -> dict:
    total_seconds = max((t1 - t0).total_seconds(), 1.0)
    v0 = sum(r["v0"] for r in records)
    v1 = sum(r["v1"] for r in records)
    flow = weighted = 0.0
    for r in records:
        for moment, amount in r["flows"]:
            flow += amount
            if moment is None:
                weight = 0.5
            else:
                weight = min(max((t1 - moment).total_seconds() / total_seconds, 0.0), 1.0)
            weighted += amount * weight
    profit = v1 - v0 - flow
    denominator = v0 + weighted
    rate = profit / denominator * 100 if denominator > 0 else None
    days = total_seconds / 86400
    annualized = None
    if rate is not None and days >= MIN_ANNUALIZE_DAYS and rate > -100:
        annualized = ((1 + rate / 100) ** (365 / days) - 1) * 100
    return {"v0": v0, "v1": v1, "net_flow": flow, "profit": profit, "rate": rate, "annualized_rate": annualized}


# ── Benchmarks (Banco Central, public) ───────────────────────────────────────

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_sgs(code: int, start: date, end: date, cache_dir: Path | None = None) -> list[tuple[date, float]]:
    cache_dir = cache_dir if cache_dir is not None else data_dir() / "cache"
    cache = cache_dir / f"bcb_{code}_{start:%Y%m%d}_{end:%Y%m%d}.json"
    try:
        if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL_SECONDS:
            return [(date.fromisoformat(d), v) for d, v in json.loads(cache.read_text())]
    except (OSError, ValueError, TypeError):
        pass
    query = urlencode({"formato": "json", "dataInicial": start.strftime("%d/%m/%Y"),
                       "dataFinal": end.strftime("%d/%m/%Y")})
    request = Request(f"{BCB_URL.format(code=code)}?{query}", headers={"Accept": "application/json"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=15) as response:
            raw = json.load(response)
        points = [(datetime.strptime(r["data"], "%d/%m/%Y").date(), float(r["valor"])) for r in raw]
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
        raise BenchmarkError(f"Banco Central indisponível (série {code})") from None
    try:
        private_write(cache, json.dumps([[d.isoformat(), v] for d, v in points]))
    except OSError:
        pass
    return points


def _compound(values) -> float | None:
    values = list(values)
    if not values:
        return None
    factor = 1.0
    for v in values:
        factor *= 1 + v / 100
    return (factor - 1) * 100


def benchmarks_for(t0: datetime, t1: datetime, fetch=fetch_sgs) -> dict:
    """Accumulated CDI and IPCA for the period. Never raises."""
    out = {"cdi_pct": None, "ipca_pct": None, "ipca_months": 0, "notes": []}
    d0, d1 = t0.date(), t1.date()
    try:
        cdi = [v for d, v in fetch(CDI_SERIES, d0 + timedelta(days=1), d1)]
        out["cdi_pct"] = _compound(cdi)
        if out["cdi_pct"] is None:
            out["notes"].append("CDI sem dados no período")
    except BenchmarkError as exc:
        out["notes"].append(str(exc))
    try:
        points = fetch(IPCA_SERIES, date(d0.year, d0.month, 1), d1)
        full = []
        for d, v in points:
            nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
            if d >= d0 and nxt - timedelta(days=1) <= d1:
                full.append(v)
        out["ipca_pct"], out["ipca_months"] = _compound(full), len(full)
        if not full:
            out["notes"].append("IPCA: período sem mês cheio publicado")
        else:
            out["notes"].append(f"IPCA cobre {len(full)} mês(es) cheio(s) do período")
    except BenchmarkError as exc:
        out["notes"].append(str(exc))
    return out


def vs_benchmarks(rate: float | None, bench: dict | None) -> dict:
    result = {"pct_of_cdi": None, "excess_over_cdi": None, "real_rate": None}
    if rate is None or not bench:
        return result
    cdi, ipca = bench.get("cdi_pct"), bench.get("ipca_pct")
    if cdi:
        result["pct_of_cdi"] = rate / cdi * 100 if cdi > 0 else None
        result["excess_over_cdi"] = rate - cdi
    if ipca is not None:
        result["real_rate"] = ((1 + rate / 100) / (1 + ipca / 100) - 1) * 100
    return result


# ── Analysis ─────────────────────────────────────────────────────────────────

def _group(records, key, t0, t1, bench=None):
    buckets: dict[str, list[dict]] = {}
    for r in records:
        buckets.setdefault(r[key], []).append(r)
    rows = []
    for name, items in buckets.items():
        row = {"name": name, "assets": len(items), **dietz(items, t0, t1)}
        row.update(vs_benchmarks(row["rate"], bench))
        rows.append(row)
    return sorted(rows, key=lambda r: r["v1"], reverse=True)


def analyze(baseline: dict | None, curr_invs: list[dict], now: datetime | None = None,
            bench_fetch=None, note: str | None = None) -> dict:
    now = now or datetime.now().astimezone()
    result = {"since_inception": coverage(curr_invs), "period": None}
    if baseline is None:
        result["error"] = "Sem histórico anterior: registre snapshots com snapshot_diff.py para medir períodos."
        return result

    t0, t1 = parse_ts(baseline["timestamp"]), now
    pairs, new, removed = snapshot_diff.match_assets(baseline.get("investments", []), curr_invs)
    records, sources = [], {"transactions": 0, "estimated": 0, "assumed": 0}
    for prev, curr in pairs:
        flows, source = asset_flows(prev, curr, t0, t1)
        sources[source] += 1
        records.append({"name": curr.get("name") or "-", "institution": curr.get("institution") or "-",
                        "category": get_type_label(curr.get("type") or "OTHER"),
                        "v0": prev.get("value") or 0, "v1": curr.get("value") or 0, "flows": flows})

    bench = benchmarks_for(t0, t1, bench_fetch) if bench_fetch else None
    portfolio = dietz(records, t0, t1)
    portfolio.update(vs_benchmarks(portfolio["rate"], bench))
    portfolio["assets"] = len(records)

    new_total = sum(i.get("value") or 0 for i in new)
    removed_total = sum(i.get("value") or 0 for i in removed)
    total0 = sum(i.get("value") or 0 for i in baseline.get("investments", []))
    total1 = sum(i.get("value") or 0 for i in curr_invs)

    eligible = [r for r in records if r["v0"] > 0 and r["v0"] >= 0.005 * max(portfolio["v0"], 1)]
    per_asset = []
    for r in eligible:
        d = dietz([r], t0, t1)
        if d["rate"] is not None:
            per_asset.append({"name": r["name"], "institution": r["institution"], "category": r["category"], **d})
    per_asset.sort(key=lambda a: a["rate"], reverse=True)

    days = (t1 - t0).total_seconds() / 86400
    caveats = ["Valores da Pluggy são líquidos de impostos já provisionados; CDI é bruto.",
               "Rentabilidade passada não garante retorno futuro."]
    if days < 7:
        caveats.append("Período curto (< 7 dias): a rentabilidade é pouco significativa.")
    if sources["assumed"]:
        caveats.append(f"{sources['assumed']} ativo(s) sem custo informado: toda a variação foi tratada como rendimento.")
    if sources["estimated"]:
        caveats.append(f"{sources['estimated']} ativo(s) sem transações: aportes estimados pela variação do custo original.")
    if new or removed:
        caveats.append("Ativos novos/removidos ficam fora da rentabilidade (sem valor inicial/final comparável).")
    if note:
        caveats.append(note)

    result.update({
        "period": {"from": t0.isoformat(timespec="seconds"), "to": t1.isoformat(timespec="seconds"),
                   "days": round(days, 1)},
        "portfolio": portfolio,
        "wallet_change": {"v0": total0, "v1": total1, "change": total1 - total0,
                          "return_effect": portfolio["profit"], "net_flow": portfolio["net_flow"],
                          "new_assets": new_total, "removed_assets": -removed_total},
        "flow_sources": sources,
        "new": [{"name": i.get("name"), "value": i.get("value") or 0} for i in new],
        "removed": [{"name": i.get("name"), "value": i.get("value") or 0} for i in removed],
        "by_category": _group(records, "category", t0, t1, bench),
        "by_institution": _group(records, "institution", t0, t1, bench),
        "best": per_asset[:5], "worst": list(reversed(per_asset[-5:])) if len(per_asset) > 5 else [],
        "benchmarks": bench,
        "caveats": caveats,
    })
    return result


# ── Output ───────────────────────────────────────────────────────────────────

def _pct(v):
    return format_percentage(v) if v is not None else "n/d"


def render(result: dict) -> str:
    lines = ["## Rentabilidade no período", ""]
    if result.get("error"):
        lines.append(result["error"])
    else:
        p, w, pf = result["period"], result["wallet_change"], result["portfolio"]
        f0, f1 = parse_ts(p["from"]).strftime("%d/%m/%Y"), parse_ts(p["to"]).strftime("%d/%m/%Y")
        bench = result.get("benchmarks")
        lines += [f"Período: {f0} a {f1} ({p['days']:.0f} dias)", "",
                  "| Métrica | Valor |", "|---|---|",
                  f"| Rentabilidade no período | {_pct(pf['rate'])} |",
                  f"| Rentabilidade anualizada | {_pct(pf['annualized_rate'])} |",
                  f"| Rendimento em R$ | {format_currency(pf['profit'])} |",
                  f"| Aportes líquidos (ativos comparáveis) | {format_currency(pf['net_flow'])} |"]
        if bench:
            lines += [f"| CDI no período | {_pct(bench['cdi_pct'])} |",
                      f"| % do CDI | {_pct(pf['pct_of_cdi'])} |",
                      f"| IPCA (meses cheios) | {_pct(bench['ipca_pct'])} |",
                      f"| Rentabilidade real (acima do IPCA) | {_pct(pf['real_rate'])} |"]
        lines += ["", "### De onde veio a variação do patrimônio", "", "| Componente | Valor |", "|---|---|",
                  f"| Patrimônio inicial | {format_currency(w['v0'])} |",
                  f"| Rendimento | {format_currency(w['return_effect'])} |",
                  f"| Aportes líquidos | {format_currency(w['net_flow'])} |",
                  f"| Ativos novos | {format_currency(w['new_assets'])} |",
                  f"| Ativos que saíram | {format_currency(w['removed_assets'])} |",
                  f"| Patrimônio atual | {format_currency(w['v1'])} |"]
        lines += ["", "### Por categoria", "", "| Categoria | Valor atual | Rendimento | Rentab. |" + (" % CDI |" if bench else ""),
                  "|---|---|---|---|" + ("---|" if bench else "")]
        for r in result["by_category"]:
            extra = f" {_pct(r['pct_of_cdi'])} |" if bench else ""
            lines.append(f"| {r['name']} | {format_currency(r['v1'])} | {format_currency(r['profit'])} | {_pct(r['rate'])} |{extra}")
        if result["best"]:
            lines += ["", "### Melhores e piores ativos", "", "| Ativo | Rentab. | Rendimento |", "|---|---|---|"]
            for a in result["best"][:3] + result["worst"][:3]:
                lines.append(f"| {a['name'].replace('|', '/')} | {_pct(a['rate'])} | {format_currency(a['profit'])} |")
        if bench and bench["notes"]:
            lines += ["", *[f"- {n}" for n in bench["notes"]]]
        lines += ["", "### Observações", "", *[f"- {c}" for c in result["caveats"]]]

    cov = result["since_inception"]
    lines += ["", "### Desde o início (custo informado)", ""]
    if cov["known_count"]:
        lines.append(f"Rendimento de {format_currency(cov['return_amount'])} ({_pct(cov['return_rate'])}) sobre "
                     f"{format_currency(cov['invested'])} investidos, em {cov['known_count']} de {cov['count']} ativos "
                     f"({cov['value_pct']:.0f}% do valor da carteira).")
    else:
        lines.append("Nenhum ativo com custo informado.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("investments")
    parser.add_argument("--since", default="30d")
    parser.add_argument("--benchmarks", action="store_true", help="Compare with CDI/IPCA (Banco Central, public)")
    parser.add_argument("--json", dest="json_out", help="Also write the structured result here (private file)")
    args = parser.parse_args(argv[1:])
    try:
        invs = investments_list(json.loads(Path(args.investments).read_text()))
        now = datetime.now().astimezone()
        migrate_legacy()
        baseline, note = snapshot_diff.pick_baseline(snapshot_diff.list_snapshots(),
                                                     snapshot_diff.resolve_since(args.since, now))
        result = analyze(baseline, invs, now, fetch_sgs if args.benchmarks else None, note)
        if args.json_out:
            private_json(args.json_out, result)
        print(render(result))
    except (ValueError, OSError) as exc:
        print(f"Performance failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
