#!/usr/bin/env python3
"""
Rebalancing plan and portfolio risk alerts for pluggy-investment-report.

Usage:
  python rebalance.py <investments.json> [--aporte VALOR] [--allow-sell]
                      [--tolerance 2] [--max-issuer-pct 20] [--max-asset-pct 10]
                      [--json OUT.json]

By default the plan only suggests where NEW money should go (--aporte), which
avoids sales and therefore income tax, IOF and come-cotas. --allow-sell also
suggests selling overweight classes. Suggestions are per asset class, never
for specific securities, and are not investment advice.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from generate_report import load_targets
from report_model import (category_totals, format_currency, format_percentage, investments_list,
                          migrate_legacy, private_json)

FGC_LIMIT = 250_000.0
FGC_WARN_RATIO = 0.8
FGC_SUBTYPES = {"CDB", "LCI", "LCA", "LC", "LF", "LIG", "RDB"}
MIN_AMOUNT = 1.0  # ignore suggestions below R$ 1


# ── Allocation plan ──────────────────────────────────────────────────────────

def plan_rebalance(cat_values: dict, targets: dict, aporte: float = 0.0, tolerance: float = 2.0,
                   allow_sell: bool = False) -> dict | None:
    total = sum(cat_values.values())
    if not targets or total <= 0 and aporte <= 0:
        return None
    new_total = total + aporte
    cats = sorted(set(cat_values) | set(targets))
    rows = []
    for c in cats:
        cur, tgt = cat_values.get(c, 0.0), targets.get(c, 0)
        desired = tgt / 100 * new_total
        actual_pct = cur / total * 100 if total else 0.0
        rows.append({"category": c, "target_pct": tgt, "actual_pct": round(actual_pct, 1),
                     "deviation": round(actual_pct - tgt, 1), "current": cur,
                     "desired": desired, "gap": desired - cur})

    buys: dict[str, float] = {}
    sells: dict[str, float] = {}
    leftover = 0.0
    if allow_sell:
        for r in rows:
            if abs(r["deviation"]) >= tolerance:
                (buys if r["gap"] > 0 else sells)[r["category"]] = abs(r["gap"])
        funds = sum(sells.values()) + aporte
        need = sum(buys.values())
        if need > funds and need > 0:
            buys = {k: v * funds / need for k, v in buys.items()}
        leftover = max(funds - sum(buys.values()), 0.0)
    elif aporte > 0:
        needs = {r["category"]: max(r["gap"], 0.0) for r in rows if r["gap"] > 0}
        need_total = sum(needs.values())
        if need_total > 0:
            scale = min(aporte / need_total, 1.0)
            buys = {k: v * scale for k, v in needs.items()}
        leftover = aporte - sum(buys.values())
        if leftover > MIN_AMOUNT:  # every class reached its target: split the rest by target weight
            for c, tgt in targets.items():
                buys[c] = buys.get(c, 0.0) + leftover * tgt / 100
            leftover = 0.0

    actions = [{"category": c, "action": "comprar", "amount": round(v, 2)} for c, v in buys.items() if v >= MIN_AMOUNT]
    actions += [{"category": c, "action": "vender", "amount": round(v, 2)} for c, v in sells.items() if v >= MIN_AMOUNT]
    actions.sort(key=lambda a: a["amount"], reverse=True)

    # Smallest deposit that reaches every target using only purchases.
    positive = {c: t for c, t in targets.items() if t > 0}
    min_aporte, blocked = None, [c for c in cat_values if cat_values[c] > 0 and targets.get(c, 0) == 0]
    if positive and total > 0:
        needed_total = max(cat_values.get(c, 0.0) / (t / 100) for c, t in positive.items())
        min_aporte = max(needed_total - total, 0.0)
    notes = []
    if blocked:
        notes.append("Sem vender, não é possível zerar: " + ", ".join(blocked) + ".")
    if allow_sell and sells:
        notes.append("Vendas podem gerar IR, IOF e come-cotas e perder carência/liquidez; avalie o custo antes.")
    if leftover > MIN_AMOUNT:
        notes.append(f"Sobra de {format_currency(leftover)} sem destino pelas metas.")
    return {"total": total, "aporte": aporte, "new_total": new_total, "tolerance": tolerance,
            "allow_sell": allow_sell, "rows": rows, "actions": actions,
            "min_aporte_no_sell": min_aporte, "notes": notes}


# ── Alerts ───────────────────────────────────────────────────────────────────

def _day(value) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def _is_sovereign(inv: dict) -> bool:
    return inv.get("type") == "TREASURY" or inv.get("subtype") == "TREASURY"


def indexer_label(inv: dict) -> str:
    kind = (inv.get("rate_type") or "").upper()
    if kind == "CDI":
        return "CDI"
    if kind == "IPCA":
        return "IPCA+"
    if kind == "SELIC":
        return "Selic"
    if kind:
        return kind
    return "Pré-fixado" if inv.get("rate") is not None or inv.get("fixed_annual_rate") is not None else "Não informado"


def build_alerts(invs: list[dict], today: date | None = None, fgc_limit: float = FGC_LIMIT,
                 max_issuer_pct: float = 20.0, max_asset_pct: float = 10.0) -> dict:
    today = today or date.today()
    total = sum(i.get("value") or 0 for i in invs)
    alerts = []

    # FGC covers the ISSUER (not the broker holding the asset), per CPF and conglomerate.
    by_issuer: dict[str, float] = {}
    unknown_issuer = 0
    for i in invs:
        if (i.get("subtype") or "").upper() in FGC_SUBTYPES:
            issuer = i.get("issuer")
            if issuer:
                by_issuer[issuer] = by_issuer.get(issuer, 0.0) + (i.get("value") or 0)
            else:
                unknown_issuer += 1
    for issuer, value in sorted(by_issuer.items(), key=lambda kv: kv[1], reverse=True):
        if value > fgc_limit:
            alerts.append({"kind": "fgc", "severity": "alto",
                           "message": f"{issuer}: {format_currency(value)} acima do limite FGC de {format_currency(fgc_limit)} por emissor"})
        elif value >= fgc_limit * FGC_WARN_RATIO:
            alerts.append({"kind": "fgc", "severity": "atenção",
                           "message": f"{issuer}: {format_currency(value)} ({value / fgc_limit * 100:.0f}% do limite FGC)"})
    if unknown_issuer:
        alerts.append({"kind": "fgc", "severity": "info",
                       "message": f"{unknown_issuer} título(s) bancário(s) sem emissor informado ficaram fora da checagem do FGC"})

    if total > 0:
        issuers: dict[str, float] = {}
        for i in invs:
            if i.get("issuer") and not _is_sovereign(i):
                issuers[i["issuer"]] = issuers.get(i["issuer"], 0.0) + (i.get("value") or 0)
        for issuer, value in sorted(issuers.items(), key=lambda kv: kv[1], reverse=True):
            if value / total * 100 > max_issuer_pct:
                alerts.append({"kind": "concentracao", "severity": "atenção",
                               "message": f"Emissor {issuer} concentra {value / total * 100:.1f}% da carteira (limite {max_issuer_pct:g}%)"})
        for i in sorted(invs, key=lambda x: x.get("value") or 0, reverse=True):
            pct = (i.get("value") or 0) / total * 100
            if pct > max_asset_pct and not _is_sovereign(i):
                alerts.append({"kind": "concentracao", "severity": "atenção",
                               "message": f"{i.get('name') or '-'} concentra {pct:.1f}% da carteira (limite {max_asset_pct:g}%)"})

    fixed = [i for i in invs if i.get("type") in ("FIXED_INCOME", "TREASURY")]
    fixed_total = sum(i.get("value") or 0 for i in fixed)
    indexers: dict[str, float] = {}
    for i in fixed:
        label = indexer_label(i)
        indexers[label] = indexers.get(label, 0.0) + (i.get("value") or 0)
    indexer_rows = [{"indexer": k, "value": v, "pct": v / fixed_total * 100 if fixed_total else 0.0}
                    for k, v in sorted(indexers.items(), key=lambda kv: kv[1], reverse=True)]

    maturities = {"overdue": [], "next_30": [], "next_90": []}
    for i in invs:
        d = _day(i.get("maturity_date"))
        if d is None:
            continue
        days = (d - today).days
        item = {"name": i.get("name") or "-", "institution": i.get("institution") or "-",
                "date": d.isoformat(), "days": days, "value": i.get("value") or 0}
        if days < 0:
            maturities["overdue"].append(item)
        elif days <= 30:
            maturities["next_30"].append(item)
        elif days <= 90:
            maturities["next_90"].append(item)
    for bucket in maturities.values():
        bucket.sort(key=lambda m: m["days"])
    if maturities["next_30"]:
        value = sum(m["value"] for m in maturities["next_30"])
        alerts.append({"kind": "vencimento", "severity": "info",
                       "message": f"{len(maturities['next_30'])} ativo(s) vencem em 30 dias ({format_currency(value)}): planeje o reinvestimento"})
    if maturities["overdue"]:
        alerts.append({"kind": "vencimento", "severity": "atenção",
                       "message": f"{len(maturities['overdue'])} ativo(s) com vencimento já passado ainda constam na carteira"})
    return {"alerts": alerts, "indexers": indexer_rows, "maturities": maturities}


def analyze(invs, targets, aporte=0.0, tolerance=2.0, allow_sell=False, today=None,
            max_issuer_pct=20.0, max_asset_pct=10.0) -> dict:
    cat_values = category_totals(invs)
    return {"plan": plan_rebalance(cat_values, targets, aporte, tolerance, allow_sell),
            **build_alerts(invs, today, max_issuer_pct=max_issuer_pct, max_asset_pct=max_asset_pct)}


# ── Output ───────────────────────────────────────────────────────────────────

def render(result: dict) -> str:
    lines = ["## Rebalanceamento", ""]
    plan = result["plan"]
    if not plan:
        lines.append("Sem metas de alocação configuradas: defina-as com o fluxo de metas para receber um plano.")
    else:
        mode = "compras e vendas" if plan["allow_sell"] else "somente aporte (sem vender)"
        lines += [f"Modo: {mode}. Aporte considerado: {format_currency(plan['aporte'])}.", "",
                  "| Categoria | Meta | Atual | Desvio | Alvo em R$ | Diferença |", "|---|---|---|---|---|---|"]
        for r in plan["rows"]:
            lines.append(f"| {r['category']} | {r['target_pct']}% | {r['actual_pct']}% | {r['deviation']:+.1f}% | "
                         f"{format_currency(r['desired'])} | {format_currency(r['gap'])} |")
        lines += ["", "### Movimentações sugeridas", ""]
        if plan["actions"]:
            lines += [f"- {a['action'].capitalize()} {a['category']}: {format_currency(a['amount'])}" for a in plan["actions"]]
        elif plan["aporte"] <= 0 and not plan["allow_sell"]:
            lines.append("- Sem aporte informado e sem vendas: nada a mover. Use --aporte VALOR ou --allow-sell.")
        else:
            lines.append("- Nenhuma classe fora da banda de tolerância.")
        if plan["min_aporte_no_sell"] is not None:
            lines += ["", f"Aporte mínimo para atingir todas as metas sem vender: {format_currency(plan['min_aporte_no_sell'])}."]
        lines += [f"- {n}" for n in plan["notes"]]

    if result["indexers"]:
        lines += ["", "### Renda fixa por indexador", "", "| Indexador | Valor | % da renda fixa |", "|---|---|---|"]
        lines += [f"| {r['indexer']} | {format_currency(r['value'])} | {format_percentage(r['pct'])} |" for r in result["indexers"]]
    m = result["maturities"]
    if any(m.values()):
        lines += ["", "### Vencimentos", ""]
        for key, title in (("overdue", "Vencidos"), ("next_30", "Próximos 30 dias"), ("next_90", "31 a 90 dias")):
            for item in m[key]:
                lines.append(f"- {title}: {item['name']} ({item['institution']}) em {item['date'][8:]}/{item['date'][5:7]}/{item['date'][:4]} — {format_currency(item['value'])}")
    if result["alerts"]:
        lines += ["", "### Alertas", ""]
        lines += [f"- [{a['severity']}] {a['message']}" for a in result["alerts"]]
    lines += ["", "_Sugestões por classe de ativo, sem recomendar títulos específicos e sem considerar seu perfil, "
              "impostos ou liquidez: não constituem recomendação de investimento._"]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("investments")
    parser.add_argument("--aporte", type=float, default=0.0, help="New money to allocate, in R$")
    parser.add_argument("--allow-sell", action="store_true", help="Also suggest selling overweight classes")
    parser.add_argument("--tolerance", type=float, default=2.0, help="Band in percentage points (default 2)")
    parser.add_argument("--max-issuer-pct", type=float, default=20.0)
    parser.add_argument("--max-asset-pct", type=float, default=10.0)
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args(argv[1:])
    if args.aporte < 0 or args.tolerance < 0:
        print("--aporte and --tolerance must not be negative", file=sys.stderr)
        return 2
    try:
        invs = investments_list(json.loads(Path(args.investments).read_text()))
        migrate_legacy()
        result = analyze(invs, load_targets(), args.aporte, args.tolerance, args.allow_sell,
                         max_issuer_pct=args.max_issuer_pct, max_asset_pct=args.max_asset_pct)
        if args.json_out:
            private_json(args.json_out, result)
        print(render(result))
    except (ValueError, OSError) as exc:
        print(f"Rebalance failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
