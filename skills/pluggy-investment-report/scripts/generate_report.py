#!/usr/bin/env python3
"""
Pluggy Investment Report Generator
Usage: python generate_report.py <investments.json> [output.html] [--diff diff.json]
                                 [--performance perf.json] [--rebalance reb.json]

investments.json must be a JSON array of objects with fields:
  id, name, institution, type, value, maturity_date
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from html import escape as _e
import snapshot_diff
from report_model import (TYPE_LABELS, build_allocation_analysis, coverage, data_dir, format_currency,
                          format_percentage, get_type_label, investments_list, migrate_legacy,
                          money_or_unknown, parse_ts, percent_or_unknown, private_write, profit_of, validate_targets)

TARGETS_PATH = str(data_dir() / "allocation_targets.json")


def format_delta(value: float) -> tuple[str, str]:
    """Returns (formatted string, css class)."""
    if value > 0:
        return f"↑ {format_currency(value)}", "positive"
    if value < 0:
        return f"↓ {format_currency(abs(value))}", "negative"
    return "—", "neutral"


def format_date(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        return str(value)


ALL_TYPE_LABELS = {"Renda Fixa", "Ações", "Fundos", "ETF", "Tesouro Direto", "FIIs", "Outros"}


def load_snapshots_series_full() -> list[dict]:
    """All snapshots oldest-first as {timestamp, x (epoch ms), label, value} for the line chart."""
    result = []
    for snap in snapshot_diff.list_snapshots():
        try:
            dt = parse_ts(snap["timestamp"])
            result.append({"timestamp": snap["timestamp"], "x": int(dt.timestamp() * 1000),
                           "label": dt.strftime("%d/%m/%Y %H:%M"), "value": round(snap["totals"]["current"], 2)})
        except (KeyError, ValueError, TypeError):
            continue
    return result


def load_all_snapshots(skip_timestamp: str | None = None) -> list[dict]:
    """Snapshots newest-first for the history panel, minus the one that belongs to the current run."""
    result = []
    for snap in reversed(snapshot_diff.list_snapshots()):
        if skip_timestamp and snap["timestamp"] == skip_timestamp:
            continue
        try:
            result.append({"timestamp": snap["timestamp"], "totals": snap["totals"],
                           "investments": snap.get("investments", [])})
        except KeyError:
            continue
    return result


def load_diff(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_targets() -> dict:
    try:
        with open(TARGETS_PATH, encoding="utf-8") as f:
            return validate_targets(json.load(f))
    except FileNotFoundError:
        return {}


def build_asset_deltas(diff: dict | None) -> dict:
    """Returns {investment_id: value_delta}. New assets get value_curr as delta."""
    if not diff or diff.get("first_run"):
        return {}
    deltas = {}
    for item in diff.get("assets", {}).get("changed", []):
        if item.get("id"):
            deltas[item["id"]] = item.get("value_delta", 0)
    for item in diff.get("assets", {}).get("new", []):
        if item.get("id"):
            deltas[item["id"]] = item.get("value_curr", 0)
    return deltas


def _build_targets_panel_html(type_totals: dict, targets: dict) -> str:
    all_cats = sorted(set(type_totals.keys()) | set(targets.keys()) | ALL_TYPE_LABELS)
    inputs_html = ""
    for label in all_cats:
        val = targets.get(label, "")
        inputs_html += (
            f'\n        <div class="target-row">'
            f'<label>{_e(label)}</label>'
            f'<input type="number" class="target-input" data-category="{_e(label)}"'
            f' min="0" max="100" step="0.1" value="{_e(str(val))}" oninput="updateTargetsTotal()">'
            f'<span>%</span></div>'
        )
    return (
        '<div class="targets-box">'
        '<div class="targets-header">'
        '<h2>Metas de Alocação</h2>'
        '<button id="toggleTargetsBtn" class="toggle-btn" onclick="toggleTargets()">'
        'Configurar ▾</button>'
        '</div>'
        '<div id="targetsPanel" style="display:none;" class="targets-panel">'
        f'<div class="targets-grid">{inputs_html}\n        </div>'
        '<div class="targets-footer">'
        '<span id="targetsTotal" class="targets-total">Total: 0%</span>'
        '<button class="save-btn" onclick="saveTargets()">⬇ Salvar metas</button>'
        '</div>'
        '<p class="targets-note">Após salvar, mova <code>allocation_targets.json</code>'
        ' para <code>pluggy-investment-report/tmp/</code> e regere o relatório.</p>'
        '</div>'
        '</div>'
    )


def _build_allocation_breakdown_html(type_totals: dict, total_current: float) -> str:
    if not type_totals or not total_current:
        return ""

    sorted_items = sorted(type_totals.items(), key=lambda x: x[1], reverse=True)
    rows_html = ""
    for label, value in sorted_items:
        pct = value / total_current * 100
        bar_width = round(pct, 1)
        rows_html += (
            f'<div class="alloc-row">'
            f'<span class="alloc-cat">{_e(label)}</span>'
            f'<div class="alloc-bar-wrap"><div class="alloc-bar" style="width:{bar_width}%"></div></div>'
            f'<span class="alloc-pct">{format_percentage(pct)}</span>'
            f'<span class="alloc-val">{format_currency(value)}</span>'
            f'</div>'
        )

    return (
        '<div class="alloc-box">'
        '<h2>Alocação da Carteira</h2>'
        f'<div class="alloc-grid">{rows_html}</div>'
        '</div>'
    )


def _build_analysis_html(analysis: dict | None) -> str:
    if not analysis:
        return ""

    rows_html = ""
    for row in analysis["rows"]:
        dev = row["deviation"]
        badge_cls = "badge-ok" if abs(dev) <= 1 else ("badge-over" if dev > 0 else "badge-under")
        sign = "+" if dev > 0 else ""
        rows_html += (
            f'<div class="analysis-row">'
            f'<span class="analysis-cat">{_e(row["category"])}</span>'
            f'<span class="analysis-meta">meta {_e(str(row["target_pct"]))}%</span>'
            f'<span class="analysis-atual">atual {_e(str(row["actual_pct"]))}%</span>'
            f'<span class="badge {badge_cls}">{sign}{dev}%</span>'
            f'</div>'
        )

    recs_html = ""
    for rec in analysis["recommendations"]:
        pill_cls = "pill-buy" if rec.startswith("↑") else "pill-sell"
        recs_html += f'<span class="pill {pill_cls}">{_e(rec)}</span>\n'

    imb = analysis["imbalance"]
    sign = "+" if imb["pct"] > 0 else ""
    imbalance_str = (
        f"⚠ Carteira desbalanceada em {abs(imb['pct']):.0f}%"
        f" — maior desvio: {imb['category']} ({sign}{imb['pct']:.0f}%)"
    )

    return (
        '<div class="analysis-box">'
        '<h2>Análise de Alocação</h2>'
        f'<div class="analysis-grid">{rows_html}</div>'
        f'<div class="analysis-recs">{recs_html}</div>'
        f'<div class="imbalance-msg">{_e(imbalance_str)}</div>'
        '</div>'
    )


def _delta_class(value: float | None) -> str:
    return "neutral" if not value else ("positive" if value > 0 else "negative")


def _build_performance_html(perf: dict | None) -> str:
    if not perf or perf.get("error") or not perf.get("portfolio"):
        return ""
    pf, bench, period = perf["portfolio"], perf.get("benchmarks"), perf["period"]
    f0 = parse_ts(period["from"]).strftime("%d/%m/%Y")
    f1 = parse_ts(period["to"]).strftime("%d/%m/%Y")
    stats = [("Rentabilidade", percent_or_unknown(pf["rate"]), _delta_class(pf["rate"])),
             ("Anualizada", percent_or_unknown(pf["annualized_rate"]), _delta_class(pf["annualized_rate"])),
             ("Rendimento", format_currency(pf["profit"]), _delta_class(pf["profit"])),
             ("Aportes líquidos", format_currency(pf["net_flow"]), "neutral")]
    if bench:
        stats += [("CDI no período", percent_or_unknown(bench["cdi_pct"]), "neutral"),
                  ("% do CDI", percent_or_unknown(pf.get("pct_of_cdi")), "neutral"),
                  ("Real (acima do IPCA)", percent_or_unknown(pf.get("real_rate")), _delta_class(pf.get("real_rate")))]
    stats_html = "".join(f'<div class="stat"><div class="label">{_e(k)}</div><div class="stat-value {c}">{_e(v)}</div></div>'
                         for k, v, c in stats)
    rows = "".join(
        f'<tr><td>{_e(r["name"])}</td><td class="number">{format_currency(r["v1"])}</td>'
        f'<td class="number {_delta_class(r["profit"])}">{format_currency(r["profit"])}</td>'
        f'<td class="number">{_e(percent_or_unknown(r["rate"]))}</td></tr>' for r in perf["by_category"])
    notes = "".join(f"<li>{_e(c)}</li>" for c in perf["caveats"])
    return ('<div class="panel-box"><h2>Rentabilidade no período</h2>'
            f'<p class="panel-sub">{f0} a {f1} ({period["days"]:.0f} dias) — separa rendimento de aportes e resgates</p>'
            f'<div class="stats">{stats_html}</div>'
            '<table class="mini-table"><thead><tr><th>Categoria</th><th class="number">Valor atual</th>'
            '<th class="number">Rendimento</th><th class="number">Rentab.</th></tr></thead>'
            f'<tbody>{rows}</tbody></table><ul class="panel-notes">{notes}</ul></div>')


def _build_rebalance_html(reb: dict | None) -> str:
    if not reb:
        return ""
    parts = []
    plan = reb.get("plan")
    if plan:
        if plan["actions"]:
            items = "".join(
                f'<li><span class="pill {"pill-buy" if a["action"] == "comprar" else "pill-sell"}">'
                f'{_e(a["action"].capitalize())}</span> {_e(a["category"])}: <strong>{format_currency(a["amount"])}</strong></li>'
                for a in plan["actions"])
        else:
            items = "<li>Sem movimentações: informe um aporte ou permita vendas.</li>"
        mode = "compras e vendas" if plan["allow_sell"] else "somente aporte (sem vender)"
        minimum = ""
        if plan.get("min_aporte_no_sell") is not None:
            minimum = f'<p class="panel-sub">Aporte mínimo para atingir todas as metas sem vender: <strong>{format_currency(plan["min_aporte_no_sell"])}</strong></p>'
        notes = "".join(f"<li>{_e(n)}</li>" for n in plan["notes"])
        parts.append(f'<h3>Movimentações sugeridas ({_e(mode)}; aporte {format_currency(plan["aporte"])})</h3>'
                     f'<ul class="action-list">{items}</ul>{minimum}<ul class="panel-notes">{notes}</ul>')
    if reb.get("indexers"):
        rows = "".join(f'<tr><td>{_e(r["indexer"])}</td><td class="number">{format_currency(r["value"])}</td>'
                       f'<td class="number">{format_percentage(r["pct"])}</td></tr>' for r in reb["indexers"])
        parts.append('<h3>Renda fixa por indexador</h3><table class="mini-table"><thead><tr><th>Indexador</th>'
                     '<th class="number">Valor</th><th class="number">% da renda fixa</th></tr></thead>'
                     f'<tbody>{rows}</tbody></table>')
    mats = reb.get("maturities") or {}
    if any(mats.values()):
        rows = ""
        for key, title in (("overdue", "Vencido"), ("next_30", "Até 30 dias"), ("next_90", "31 a 90 dias")):
            for m in mats.get(key, []):
                rows += (f'<tr><td>{_e(title)}</td><td>{_e(m["name"])}</td><td>{_e(m["institution"])}</td>'
                         f'<td>{_e(format_date(m["date"]))}</td><td class="number">{format_currency(m["value"])}</td></tr>')
        parts.append('<h3>Calendário de vencimentos</h3><table class="mini-table"><thead><tr><th>Prazo</th><th>Ativo</th>'
                     '<th>Instituição</th><th>Data</th><th class="number">Valor</th></tr></thead>'
                     f'<tbody>{rows}</tbody></table>')
    if reb.get("alerts"):
        items = "".join(f'<li><span class="sev sev-{_e(a["severity"].replace("ç", "c").replace("ã", "a"))}">{_e(a["severity"])}</span> {_e(a["message"])}</li>'
                        for a in reb["alerts"])
        parts.append(f'<h3>Alertas</h3><ul class="alert-list">{items}</ul>')
    if not parts:
        return ""
    return ('<div class="panel-box"><h2>Rebalanceamento e alertas</h2>' + "".join(parts) +
            '<p class="panel-disclaimer">Sugestões por classe de ativo, sem considerar seu perfil, impostos ou liquidez. '
            'Não constituem recomendação de investimento.</p></div>')


def _is_redeemed(inv: dict) -> bool:
    """Fully withdrawn positions carry no balance; the assets table hides them."""
    return inv.get("status") == "TOTAL_WITHDRAWAL" and not (inv.get("value") or 0)


def _group_key(inv: dict) -> tuple:
    return (inv.get("type"), inv.get("subtype"), inv.get("name"), inv.get("issuer"),
            inv.get("institution"), inv.get("rate_type"), inv.get("rate"), inv.get("fixed_annual_rate"))


def group_assets(investments: list) -> list[list[dict]]:
    """Group lots of the same asset (same name, issuer, institution and rate) so repeated
    purchases show as one line. Redeemed positions are dropped. Order is first-seen."""
    groups: dict[tuple, list[dict]] = {}
    for inv in investments:
        if _is_redeemed(inv):
            continue
        groups.setdefault(_group_key(inv), []).append(inv)
    return list(groups.values())


def _sum_or_unknown(values: list) -> tuple[float | None, bool]:
    """Sum of known values and whether every lot was known (None when none were)."""
    known = [v for v in values if v is not None]
    return (sum(known) if known else None), len(known) == len(values)


def _money_cell(total: float | None, complete: bool, klass: str = "") -> str:
    if total is None:
        return f'<td class="number neutral" data-sort="">{_e("não informado")}</td>'
    text = format_currency(total) + ("" if complete else " (parcial)")
    return f'<td class="number {klass}" data-sort="{total}">{_e(text)}</td>'


def _asset_row(inv: dict, asset_delta, lot: bool = False) -> str:
    ad_str, ad_class = format_delta(asset_delta) if asset_delta is not None else ("—", "neutral")
    maturity, maturity_sort = format_date(inv.get("maturity_date")), (inv.get("maturity_date") or "")[:10]
    type_code = inv.get("type", "OTHER") or "OTHER"
    value = inv.get("value", 0) or 0
    cost, profit = inv.get("amount"), profit_of(inv)
    cost_str = format_currency(cost) if cost is not None else "não informado"
    profit_str = format_currency(profit) if profit is not None else "não informado"
    if lot:
        issue = format_date(inv.get("issue_date")) if inv.get("issue_date") else "—"
        name_cell = f'<td class="lot-name" data-sort="">Lote emitido em {_e(issue)}</td>'
        inst_cell, type_cell = "<td></td>", "<td></td>"
        row_open = '<tr class="lot-row">'
    else:
        name_cell = f'<td>{_e(inv.get("name") or "-")}</td>'
        inst_cell = f'<td>{_e(inv.get("institution") or "-")}</td>'
        type_cell = f'<td><span class="badge badge-{_e(type_code.lower())}">{_e(get_type_label(type_code))}</span></td>'
        row_open = "<tr>"
    return f"""
        {row_open}
          {name_cell}
          {inst_cell}
          {type_cell}
          <td class="number" data-sort="{value}">{format_currency(value)}</td>
          <td class="number {'neutral' if cost is None else ''}" data-sort="{'' if cost is None else cost}">{_e(cost_str)}</td>
          <td class="number {_delta_class(profit)}" data-sort="{'' if profit is None else profit}">{_e(profit_str)}</td>
          <td class="number {ad_class}" data-sort="{asset_delta if asset_delta is not None else ''}">{_e(ad_str)}</td>
          <td data-sort="{_e(maturity_sort)}">{_e(maturity)}</td>
        </tr>"""


def _group_row(lots: list[dict], asset_deltas: dict) -> str:
    first = lots[0]
    type_code = first.get("type", "OTHER") or "OTHER"
    value = sum(l.get("value", 0) or 0 for l in lots)
    cost, cost_all = _sum_or_unknown([l.get("amount") for l in lots])
    profit, profit_all = _sum_or_unknown([profit_of(l) for l in lots])
    deltas = [asset_deltas[l.get("id", "")] for l in lots if l.get("id", "") in asset_deltas]
    delta = sum(deltas) if deltas else None
    ad_str, ad_class = format_delta(delta) if delta is not None else ("—", "neutral")
    maturities = sorted((l.get("maturity_date") or "")[:10] for l in lots if l.get("maturity_date"))
    maturity_sort = maturities[0] if maturities else ""
    maturity = format_date(maturity_sort) if maturity_sort else format_date(None)
    maturity_title = ""
    if len(set(maturities)) > 1:
        maturity_title = f' title="{_e("Vencimentos de " + format_date(maturities[0]) + " a " + format_date(maturities[-1]))}"'
    name = first.get("name") or "-"
    head = f"""
        <tr class="group-main">
          <td data-sort="{_e(name)}"><button type="button" class="lot-toggle" aria-expanded="false" onclick="toggleLots(this)">▸</button>{_e(name)} <span class="lot-count">({len(lots)} lotes)</span></td>
          <td>{_e(first.get("institution") or "-")}</td>
          <td><span class="badge badge-{_e(type_code.lower())}">{_e(get_type_label(type_code))}</span></td>
          <td class="number" data-sort="{value}">{format_currency(value)}</td>
          {_money_cell(cost, cost_all)}
          {_money_cell(profit, profit_all, _delta_class(profit))}
          <td class="number {ad_class}" data-sort="{delta if delta is not None else ''}">{_e(ad_str)}</td>
          <td data-sort="{_e(maturity_sort)}"{maturity_title}>{_e(maturity)}</td>
        </tr>"""
    lot_rows = "".join(_asset_row(l, asset_deltas.get(l.get("id", "")), lot=True)
                       for l in sorted(lots, key=lambda l: l.get("maturity_date") or ""))
    return f'<tbody class="asset-group">{head}{lot_rows}</tbody>'


def build_assets_table_body(investments: list, asset_deltas: dict) -> tuple[str, dict]:
    """One <tbody> per line so a group and its lots sort together. Returns the HTML and counts."""
    ordered = sorted(group_assets(investments),
                     key=lambda g: (get_type_label(g[0].get("type", "OTHER") or "OTHER"), g[0].get("name") or ""))
    body = ""
    for lots in ordered:
        if len(lots) == 1:
            body += f'<tbody class="asset-group">{_asset_row(lots[0], asset_deltas.get(lots[0].get("id", "")))}</tbody>'
        else:
            body += _group_row(lots, asset_deltas)
    redeemed = sum(1 for i in investments if _is_redeemed(i))
    return body, {"lines": len(ordered), "redeemed": redeemed,
                  "grouped": sum(len(g) for g in ordered if len(g) > 1)}


def generate_html(investments: list, output_path: str, diff: dict | None = None, targets: dict | None = None,
                  performance: dict | None = None, rebalance: dict | None = None) -> str:
    investments = investments_list(investments)

    total_current = sum(i.get("value", 0) or 0 for i in investments)
    cov = coverage(investments)

    first_run = diff.get("first_run", True) if diff else True
    prev_ts_str = ""
    total_delta = 0.0
    if diff and not first_run:
        prev_ts = diff.get("previous_timestamp", "")
        try:
            prev_ts_str = parse_ts(prev_ts).strftime("%d/%m/%Y às %H:%M")
        except (ValueError, TypeError, AttributeError):
            prev_ts_str = prev_ts or ""
        total_delta = diff.get("totals", {}).get("current", {}).get("delta", 0)

    asset_deltas = build_asset_deltas(diff)

    type_totals: dict = {}
    for inv in investments:
        label = get_type_label(inv.get("type", "OTHER"))
        type_totals[label] = type_totals.get(label, 0) + (inv.get("value", 0) or 0)

    targets = targets or {}
    analysis = build_allocation_analysis(type_totals, targets, total_current)
    targets_panel_html = _build_targets_panel_html(type_totals, targets)
    analysis_html = _build_analysis_html(analysis)
    allocation_breakdown_html = _build_allocation_breakdown_html(type_totals, total_current)
    performance_html = _build_performance_html(performance)
    rebalance_html = _build_rebalance_html(rebalance)

    type_labels_js = json.dumps(list(type_totals.keys())).replace("<", "\\u003c")
    type_values_js = json.dumps([round(v, 2) for v in type_totals.values()])
    total_value_js = json.dumps(round(total_current, 2))

    snap_series_full = load_snapshots_series_full()
    snap_series_full_js = json.dumps(snap_series_full)

    # The snapshot written by this run (same timestamp as the diff) is not "previous".
    history_snapshots = load_all_snapshots(diff.get("current_timestamp") if diff else None)
    history_js = json.dumps(history_snapshots).replace("<", "\\u003c")
    history_count = len(history_snapshots)

    delta_str, delta_class = format_delta(total_delta)
    avanco_label = f"Avanço desde {prev_ts_str}" if prev_ts_str else "Avanço"
    avanco_note = f"desde {prev_ts_str} (inclui aportes e resgates)" if prev_ts_str else "primeira execução"

    if cov["known_count"]:
        scope = "" if cov["complete"] else f"{cov['known_count']} de {cov['count']} ativos com custo informado"
        invested_str, invested_note = format_currency(cov["invested"]), scope or "custo original"
        return_str = f"{format_currency(cov['return_amount'])} ({percent_or_unknown(cov['return_rate'])})"
        return_class, return_note = _delta_class(cov["return_amount"]), scope or "desde a aplicação"
    else:
        invested_str = return_str = "não informado"
        invested_note = return_note = "sem custo informado pelas instituições"
        return_class = "neutral"

    rows_html, table_stats = build_assets_table_body(investments, asset_deltas)

    n = len(investments)
    asset_word = "ativo" if n == 1 else "ativos"
    title_parts = [f"{n} {asset_word}"]
    if table_stats["redeemed"]:
        title_parts.append(f'{table_stats["redeemed"]} resgatados ocultos')
    if table_stats["grouped"]:
        title_parts.append(f'{table_stats["grouped"]} lotes agrupados')
    assets_title = " · ".join(title_parts)
    generation_date = datetime.now().strftime("%d/%m/%Y às %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Relatório de Investimentos</title>

  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #f0f2f5; color: #1a1a2e; padding: 24px;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    header {{
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 28px;
    }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; }}
    header .date {{ font-size: 0.85rem; color: #666; }}
    .cards {{
      display: grid; grid-template-columns: repeat(2, 1fr);
      gap: 16px; margin-bottom: 28px;
    }}
    .card {{
      background: #fff; border-radius: 12px; padding: 20px 24px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
    }}
    .card .label {{
      font-size: 0.78rem; color: #888; text-transform: uppercase;
      letter-spacing: .05em; margin-bottom: 8px;
    }}
    .card .note {{ font-size: 0.75rem; color: #aaa; margin-top: 4px; }}
    .card .value {{ font-size: 1.5rem; font-weight: 700; }}
    .charts {{
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 16px; margin-bottom: 28px;
    }}
    .chart-box, .table-box {{
      background: #fff; border-radius: 12px; padding: 20px 24px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
    }}
    .table-box {{ margin-bottom: 28px; }}
    .chart-box h2, .table-box h2 {{
      font-size: 0.9rem; font-weight: 600; color: #444; margin-bottom: 16px;
    }}
    .chart-box canvas {{ max-height: 260px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.87rem; }}
    thead th {{
      text-align: left; padding: 10px 12px;
      border-bottom: 2px solid #e5e7eb;
      color: #666; font-weight: 600; font-size: 0.76rem;
      text-transform: uppercase; cursor: pointer;
      user-select: none; white-space: nowrap;
    }}
    thead th:hover {{ color: #1a1a2e; }}
    tbody tr:hover {{ background: #f9fafb; }}
    .lot-row {{ display: none; background: #fafbfc; font-size: 0.9em; }}
    .asset-group.open .lot-row {{ display: table-row; }}
    .lot-name {{ padding-left: 36px !important; color: #6b7280; }}
    .lot-count {{ color: #6b7280; font-size: 0.85em; }}
    .lot-toggle {{ border: 0; background: none; cursor: pointer; font-size: 0.9em; width: 20px; color: #6b7280; }}
    tbody td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }}
    .number {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .positive {{ color: #16a34a; font-weight: 600; }}
    .negative {{ color: #dc2626; font-weight: 600; }}
    .neutral  {{ color: #9ca3af; }}
    .badge {{
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      font-size: 0.74rem; font-weight: 500;
    }}
    .badge-fixed_income {{ background: #dbeafe; color: #1d4ed8; }}
    .badge-equity,
    .badge-stock      {{ background: #fef3c7; color: #92400e; }}
    .badge-fund,
    .badge-mutual_fund {{ background: #ede9fe; color: #6d28d9; }}
    .badge-etf        {{ background: #d1fae5; color: #065f46; }}
    .badge-treasury   {{ background: #e0f2fe; color: #0369a1; }}
    .badge-real_estate {{ background: #fce7f3; color: #9d174d; }}
    .badge-other      {{ background: #f3f4f6; color: #4b5563; }}
    .print-btn {{
      display: block; margin: 0 auto 12px;
      background: #1a1a2e; color: #fff; border: none;
      padding: 12px 32px; border-radius: 8px;
      font-size: 0.95rem; cursor: pointer; font-weight: 600;
    }}
    .print-btn:hover {{ background: #2d2d4e; }}
    .alloc-box {{
      background: #fff; border-radius: 12px; padding: 20px 24px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 28px;
    }}
    .alloc-box h2 {{
      font-size: 0.9rem; font-weight: 600; color: #444; margin-bottom: 16px;
    }}
    .alloc-grid {{ display: flex; flex-direction: column; gap: 10px; }}
    .alloc-row {{
      display: grid; grid-template-columns: 130px 1fr 60px 130px;
      align-items: center; gap: 12px; font-size: 0.87rem;
    }}
    .alloc-cat {{ color: #444; font-weight: 500; }}
    .alloc-bar-wrap {{
      background: #f0f2f5; border-radius: 999px; height: 8px; overflow: hidden;
    }}
    .alloc-bar {{
      background: #3b82f6; height: 100%; border-radius: 999px;
      transition: width .4s ease;
    }}
    .alloc-pct {{ text-align: right; font-weight: 600; color: #1a1a2e; font-variant-numeric: tabular-nums; }}
    .alloc-val {{ text-align: right; color: #666; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .targets-box {{
      background: #fff; border-radius: 12px; padding: 20px 24px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 28px;
    }}
    .targets-header {{
      display: flex; justify-content: space-between; align-items: center;
    }}
    .targets-header h2 {{
      font-size: 0.9rem; font-weight: 600; color: #444; margin-bottom: 0;
    }}
    .toggle-btn {{
      background: #3b82f6; color: #fff; border: none;
      padding: 6px 18px; border-radius: 20px; font-size: 0.82rem;
      cursor: pointer; font-weight: 500;
    }}
    .toggle-btn:hover {{ background: #2563eb; }}
    .targets-panel {{ margin-top: 16px; }}
    .targets-grid {{ display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }}
    .target-row {{
      display: grid; grid-template-columns: 1fr 72px 20px;
      align-items: center; gap: 8px; font-size: 0.87rem;
    }}
    .target-row label {{ color: #444; }}
    .target-row input {{
      border: 1px solid #d1d5db; border-radius: 6px;
      padding: 4px 8px; font-size: 0.87rem; text-align: right; width: 100%;
    }}
    .target-row input:focus {{ outline: none; border-color: #3b82f6; box-shadow: 0 0 0 2px #bfdbfe; }}
    .targets-footer {{
      display: flex; justify-content: space-between; align-items: center;
      padding-top: 12px; border-top: 1px solid #f0f0f0; margin-bottom: 10px;
    }}
    .targets-total {{ font-size: 0.85rem; font-weight: 600; color: #dc2626; transition: color .2s; }}
    .save-btn {{
      background: #1a1a2e; color: #fff; border: none;
      padding: 8px 20px; border-radius: 8px; font-size: 0.85rem;
      cursor: pointer; font-weight: 500;
    }}
    .save-btn:hover {{ background: #2d2d4e; }}
    .targets-note {{ font-size: 0.75rem; color: #9ca3af; margin-top: 0; }}
    .targets-note code {{ background: #f3f4f6; padding: 1px 4px; border-radius: 3px; font-size: 0.72rem; }}
    .analysis-box {{
      background: #1a1a2e; color: #fff; border-radius: 12px;
      padding: 20px 24px; margin-bottom: 28px;
    }}
    .analysis-box h2 {{
      font-size: 0.82rem; font-weight: 700; color: #94a3b8;
      text-transform: uppercase; letter-spacing: .08em; margin-bottom: 16px;
    }}
    .analysis-grid {{ display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }}
    .analysis-row {{
      display: grid; grid-template-columns: 1fr 90px 90px 52px;
      align-items: center; gap: 8px; font-size: 0.87rem;
    }}
    .analysis-cat {{ color: #e2e8f0; }}
    .analysis-meta {{ color: #94a3b8; text-align: right; font-size: 0.8rem; }}
    .analysis-atual {{ color: #e2e8f0; text-align: right; }}
    .badge-ok    {{ background: #16a34a; color: #fff; border-radius: 4px; padding: 2px 6px; font-size: 0.75rem; text-align: center; }}
    .badge-over  {{ background: #ef4444; color: #fff; border-radius: 4px; padding: 2px 6px; font-size: 0.75rem; text-align: center; }}
    .badge-under {{ background: #3b82f6; color: #fff; border-radius: 4px; padding: 2px 6px; font-size: 0.75rem; text-align: center; }}
    .analysis-recs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
    .pill        {{ padding: 4px 14px; border-radius: 20px; font-size: 0.82rem; font-weight: 600; }}
    .pill-buy    {{ background: #3b82f6; color: #fff; }}
    .pill-sell   {{ background: #ef4444; color: #fff; }}
    .imbalance-msg {{
      background: #0f172a; border-radius: 8px; padding: 10px 14px;
      font-size: 0.85rem; color: #f59e0b; font-weight: 600;
    }}
    .panel-box {{
      background: #fff; border-radius: 12px; padding: 20px 24px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 28px;
    }}
    .panel-box h2 {{ font-size: 0.9rem; font-weight: 600; color: #444; margin-bottom: 6px; }}
    .panel-box h3 {{ font-size: 0.82rem; font-weight: 600; color: #666; margin: 18px 0 8px; }}
    .panel-sub {{ font-size: 0.8rem; color: #888; margin-bottom: 12px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .stat {{ background: #f9fafb; border-radius: 8px; padding: 10px 14px; }}
    .stat .label {{ font-size: 0.7rem; color: #888; text-transform: uppercase; letter-spacing: .05em; }}
    .stat-value {{ font-size: 1.1rem; font-weight: 700; margin-top: 4px; }}
    .mini-table {{ font-size: 0.83rem; }}
    .mini-table th {{ cursor: default; }}
    .panel-notes, .action-list, .alert-list {{ margin: 10px 0 0 18px; font-size: 0.8rem; color: #666; line-height: 1.6; }}
    .action-list, .alert-list {{ list-style: none; margin-left: 0; font-size: 0.87rem; color: #1a1a2e; }}
    .action-list li, .alert-list li {{ padding: 4px 0; }}
    .sev {{ display: inline-block; padding: 1px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 700; margin-right: 6px; }}
    .sev-alto {{ background: #fee2e2; color: #b91c1c; }}
    .sev-atencao {{ background: #fef3c7; color: #92400e; }}
    .sev-info {{ background: #e0f2fe; color: #0369a1; }}
    .panel-disclaimer {{ font-size: 0.72rem; color: #9ca3af; margin-top: 16px; }}
    @media print {{
      body {{ background: #fff; padding: 8px; }}
      .print-btn {{ display: none; }}
      .card, .chart-box, .table-box {{
        box-shadow: none; border: 1px solid #e5e7eb;
        page-break-inside: avoid;
      }}
    }}
    @media (max-width: 768px) {{
      .cards {{ grid-template-columns: 1fr; }}
      .charts {{ grid-template-columns: 1fr; }}
    }}
    .history-section {{ text-align: center; margin-top: 6px; }}
    .history-toggle {{
      background: none; border: none; color: #c0c4cc;
      font-size: 0.75rem; cursor: pointer; padding: 10px 20px;
      letter-spacing: .02em;
    }}
    .history-toggle:hover {{ color: #6b7280; }}
    .history-panel {{
      background: #fff; border-radius: 10px; margin-top: 6px;
      box-shadow: 0 1px 3px rgba(0,0,0,.06); text-align: left; overflow: hidden;
    }}
    .history-panel-header {{
      padding: 10px 20px; font-size: 0.72rem; color: #9ca3af;
      text-transform: uppercase; letter-spacing: .06em; font-weight: 600;
      border-bottom: 1px solid #f0f0f0;
    }}
    .history-row {{
      display: grid; grid-template-columns: 1fr auto auto auto;
      align-items: center; padding: 9px 20px; gap: 16px;
      border-bottom: 1px solid #f9f9f9; cursor: pointer; font-size: 0.84rem;
    }}
    .history-row:hover {{ background: #fafafa; }}
    .history-row:last-of-type {{ border-bottom: none; }}
    .h-ts  {{ color: #4b5563; }}
    .h-val {{ color: #1a1a2e; font-weight: 600; font-variant-numeric: tabular-nums; }}
    .h-cnt {{ color: #9ca3af; font-size: 0.78rem; }}
    .h-btn {{
      background: none; border: 1px solid #e5e7eb; border-radius: 4px;
      color: #aab; font-size: 0.73rem; padding: 2px 8px; cursor: pointer;
    }}
    .history-row:hover .h-btn {{ border-color: #d1d5db; color: #6b7280; }}
    .h-del {{
      background: none; border: none; color: #e2e8f0;
      font-size: 0.7rem; padding: 1px 3px; cursor: pointer; line-height: 1;
    }}
    .history-row:hover .h-del {{ color: #f87171; }}
    .history-detail {{
      background: #f9fafb; border-bottom: 1px solid #f0f0f0;
      padding: 10px 20px 14px; display: none; overflow-x: auto;
    }}
    .history-detail table {{ font-size: 0.81rem; width: 100%; border-collapse: collapse; }}
    .history-detail thead th {{
      font-size: 0.71rem; padding: 5px 10px; border-bottom: 1px solid #e5e7eb;
      color: #9ca3af; text-transform: uppercase; letter-spacing: .04em;
    }}
    .history-detail tbody td {{ padding: 6px 10px; border-bottom: 1px solid #f3f4f6; }}
    @media print {{ .history-section {{ display: none; }} }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Relatório de Investimentos</h1>
      <span class="date">Gerado em {generation_date}</span>
    </header>

    <div class="cards">
      <div class="card">
        <div class="label">Valor Atual</div>
        <div class="value">{format_currency(total_current)}</div>
        <div class="note">{n} {asset_word}</div>
      </div>
      <div class="card">
        <div class="label" id="avanco-label">{_e(avanco_label)}</div>
        <div class="value {delta_class}" id="avanco-value">{_e(delta_str)}</div>
        <div class="note" id="avanco-note">{_e(avanco_note)}</div>
      </div>
      <div class="card">
        <div class="label">Total Investido</div>
        <div class="value {"neutral" if cov["known_count"] == 0 else ""}">{_e(invested_str)}</div>
        <div class="note">{_e(invested_note)}</div>
      </div>
      <div class="card">
        <div class="label">Rendimento Total</div>
        <div class="value {return_class}">{_e(return_str)}</div>
        <div class="note">{_e(return_note)}</div>
      </div>
    </div>

    <div class="charts">
      <div class="chart-box">
        <h2>Alocação por Tipo</h2>
        <canvas id="pieChart"></canvas>
      </div>
      <div class="chart-box">
        <h2>Evolução do Valor Total</h2>
        <canvas id="lineChart"></canvas>
      </div>
    </div>

    {allocation_breakdown_html}

    {targets_panel_html}

    <div class="table-box">
      <h2>Ativos ({assets_title})</h2>
      <table id="assetsTable">
        <thead>
          <tr>
            <th onclick="sortTable(0)">Nome ↕</th>
            <th onclick="sortTable(1)">Instituição ↕</th>
            <th onclick="sortTable(2)">Tipo ↕</th>
            <th onclick="sortTable(3)" style="text-align:right">Valor Atual ↕</th>
            <th onclick="sortTable(4)" style="text-align:right">Custo ↕</th>
            <th onclick="sortTable(5)" style="text-align:right">Rendimento ↕</th>
            <th onclick="sortTable(6)" style="text-align:right">Avanço ↕</th>
            <th onclick="sortTable(7)">Vencimento ↕</th>
          </tr>
        </thead>
        {rows_html}
      </table>
    </div>

    {analysis_html}

    {performance_html}

    {rebalance_html}

    <button class="print-btn" onclick="window.print()">Imprimir / Salvar como PDF</button>

    {"" if history_count == 0 else f'''<div class="history-section">
      <button class="history-toggle" id="historyToggle" onclick="toggleHistory()">
        relatórios anteriores ({history_count}) ▾
      </button>
      <div id="history-panel" class="history-panel" style="display:none">
        <div class="history-panel-header">Histórico de snapshots</div>
        <div id="history-list"></div>
      </div>
    </div>'''}
  </div>

  <div id="chart-error" style="display:none;color:#dc2626;text-align:center;padding:20px;font-weight:600;">
  ⚠ Erro ao carregar a biblioteca de gráficos. Recarregue a página ou verifique sua conexão.
</div>

  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"
          integrity="sha384-e6nUZLBkQ86NJ6TVVKAeSaK8jWa3NhkYWZFomE39AvDbQWeie9PlQqM3pmYW5d1g"
          crossorigin="anonymous"
          onerror="document.getElementById('chart-error').style.display='block'"></script>
  <script>
    function createChart(canvas, config) {{
      if (typeof Chart === "function") return new Chart(canvas, config);
      document.getElementById("chart-error").style.display = "block";
      return {{data: config.data, update() {{}}}};
    }}
    const COLORS = ['#3b82f6','#f59e0b','#8b5cf6','#10b981','#ef4444','#06b6d4','#f97316','#6366f1'];

    createChart(document.getElementById('pieChart'), {{
      type: 'doughnut',
      data: {{
        labels: {type_labels_js},
        datasets: [{{ data: {type_values_js}, backgroundColor: COLORS, borderWidth: 0 }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: true,
        plugins: {{ legend: {{ position: 'right', labels: {{ font: {{ size: 12 }} }} }} }}
      }}
    }});

    const SNAP_SERIES_FULL = {snap_series_full_js};
    const DELETED_KEY      = 'pluggy_deleted_snapshots';
    function getDeleted() {{
      try {{ return new Set(JSON.parse(localStorage.getItem(DELETED_KEY) || '[]')); }} catch(e) {{ return new Set(); }}
    }}
    function seriesPoints() {{
      const deleted = getDeleted();
      return SNAP_SERIES_FULL.filter(s => !deleted.has(s.timestamp)).map(s => ({{x: s.x, y: s.value}}));
    }}
    const fmtDate = ms => new Date(ms).toLocaleDateString('pt-BR');

    const lineChartInstance = createChart(document.getElementById('lineChart'), {{
      type: 'line',
      data: {{
        datasets: [{{
          label: 'Valor Total',
          data: seriesPoints(),
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.08)',
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: '#3b82f6',
          fill: true,
          tension: 0.3
        }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: true,
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{ callbacks: {{ title: items => items.length ? new Date(items[0].parsed.x).toLocaleString('pt-BR') : '' }} }}
        }},
        scales: {{
          y: {{
            ticks: {{ callback: v => 'R$ ' + v.toLocaleString('pt-BR') }},
            grid: {{ color: '#f0f0f0' }}
          }},
          x: {{
            type: 'linear',
            ticks: {{ maxTicksLimit: 6, callback: v => fmtDate(v) }},
            grid: {{ display: false }}
          }}
        }}
      }}
    }});

    // ── Histórico de relatórios ──────────────────────────────────────────────
    const TOTAL_VAL        = {total_value_js};
    const HISTORY          = {history_js};
    function fmtBRL(v) {{
      const sign = v < 0 ? '-R$ ' : 'R$ ';
      return sign + Math.abs(v).toLocaleString('pt-BR', {{minimumFractionDigits:2, maximumFractionDigits:2}});
    }}

    function visibleHistory() {{
      const deleted = getDeleted();
      return HISTORY.filter(s => !deleted.has(s.timestamp));
    }}

    function updateToggleCount() {{
      const btn = document.getElementById('historyToggle');
      if (!btn) return;
      const n    = visibleHistory().length;
      const open = document.getElementById('history-panel')?.style.display !== 'none';
      btn.textContent = 'relatórios anteriores (' + n + (open ? ') ▴' : ') ▾');
      if (n === 0) document.getElementById('history-panel').style.display = 'none';
    }}

    function toggleHistory() {{
      const panel = document.getElementById('history-panel');
      if (!panel) return;
      const opening = panel.style.display === 'none';
      panel.style.display = opening ? 'block' : 'none';
      updateToggleCount();
      if (opening && !document.getElementById('history-list').children.length) renderHistory();
    }}

    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, c => ({{"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}}[c]));
    }}

    function renderHistory() {{
      const list    = document.getElementById('history-list');
      const visible = visibleHistory();
      if (!visible.length) {{
        list.innerHTML = '<div style="padding:14px 20px;color:#9ca3af;font-size:0.84rem;">Nenhum snapshot anterior encontrado.</div>';
        return;
      }}
      const TYPE_MAP = {json.dumps(TYPE_LABELS)};
      list.innerHTML = visible.map((snap, i) => {{
        const dt  = new Date(snap.timestamp.replace('T',' '));
        const ts  = dt.toLocaleDateString('pt-BR') + ' às ' + dt.toLocaleTimeString('pt-BR',{{hour:'2-digit',minute:'2-digit'}});
        const fv  = 'R$ ' + snap.totals.current.toLocaleString('pt-BR',{{minimumFractionDigits:2,maximumFractionDigits:2}});
        const n   = snap.investments ? snap.investments.length : '—';
        const rows = (snap.investments || [])
          .slice().sort((a,b) => ((TYPE_MAP[a.type]||a.type||'').localeCompare(TYPE_MAP[b.type]||b.type||'')) || (a.name||'').localeCompare(b.name||''))
          .map(inv => {{
            const v = (inv.value||0).toLocaleString('pt-BR',{{minimumFractionDigits:2,maximumFractionDigits:2}});
            return `<tr><td>${{escapeHtml(inv.name||'-')}}</td><td>${{escapeHtml(TYPE_MAP[inv.type]||'Outros')}}</td>`+
                   `<td style="text-align:right;font-variant-numeric:tabular-nums;">R$ ${{v}}</td></tr>`;
          }}).join('');
        const table = `<table><thead><tr>
            <th style="text-align:left">Nome</th><th style="text-align:left">Tipo</th>
            <th style="text-align:right">Valor</th>
          </tr></thead><tbody>${{rows}}</tbody></table>`;
        const tsEsc = snap.timestamp.replace(/'/g, "\\'");
        return `<div class="history-row" id="hrow-${{i}}" onclick="toggleHistoryDetail(${{i}})">
            <span class="h-ts">${{ts}}</span>
            <span class="h-val">${{fv}}</span>
            <span class="h-cnt">${{n}} ativos</span>
            <div style="display:flex;gap:2px;align-items:center;">
              <button class="h-btn" id="hbtn-${{i}}">ver ▸</button>
              <button class="h-del" onclick="deleteSnapshot(event,${{i}},'${{tsEsc}}')">✕</button>
            </div>
          </div>
          <div class="history-detail" id="hdetail-${{i}}">${{table}}</div>`;
      }}).join('');
    }}

    function toggleHistoryDetail(i) {{
      const detail = document.getElementById('hdetail-'+i);
      const btn    = document.getElementById('hbtn-'+i);
      const opening = detail.style.display !== 'block';
      detail.style.display = opening ? 'block' : 'none';
      btn.textContent = opening ? 'fechar ▾' : 'ver ▸';
    }}

    function rebuildLineChart() {{
      lineChartInstance.data.datasets[0].data = seriesPoints();
      lineChartInstance.update();
    }}

    function updateAvanco() {{
      const lbl  = document.getElementById('avanco-label');
      const val  = document.getElementById('avanco-value');
      const note = document.getElementById('avanco-note');
      if (!lbl || !val || !note) return;
      const vis = visibleHistory();
      if (!vis.length) {{
        lbl.textContent  = 'Avanço';
        val.textContent  = '—';
        val.className    = 'value neutral';
        note.textContent = 'primeira execução';
        return;
      }}
      const prev  = vis[0];
      const delta = TOTAL_VAL - prev.totals.current;
      const dt    = new Date(prev.timestamp.replace('T', ' '));
      const tsStr = dt.toLocaleDateString('pt-BR') + ' às ' +
                    dt.toLocaleTimeString('pt-BR', {{hour:'2-digit', minute:'2-digit'}});
      let dText, dCls;
      if (delta > 0)      {{ dText = '↑ ' + fmtBRL(delta);            dCls = 'positive'; }}
      else if (delta < 0) {{ dText = '↓ ' + fmtBRL(Math.abs(delta));  dCls = 'negative'; }}
      else                {{ dText = '—';                               dCls = 'neutral';  }}
      lbl.textContent  = 'Avanço desde ' + tsStr;
      val.textContent  = dText;
      val.className    = 'value ' + dCls;
      note.textContent = 'desde ' + tsStr;
    }}

    function deleteSnapshot(e, i, ts) {{
      e.stopPropagation();
      const deleted = getDeleted();
      deleted.add(ts);
      localStorage.setItem(DELETED_KEY, JSON.stringify([...deleted]));
      document.getElementById('hrow-'+i)?.remove();
      document.getElementById('hdetail-'+i)?.remove();
      updateToggleCount();
      rebuildLineChart();
      updateAvanco();
    }}

    // ── Ordenação da tabela de ativos ────────────────────────────────────────
    let _sortDir = {{}};
    function toggleLots(btn) {{
      const tb = btn.closest('tbody');
      const open = tb.classList.toggle('open');
      btn.textContent = open ? '▾' : '▸';
      btn.setAttribute('aria-expanded', open);
    }}

    function sortTable(col) {{
      const table = document.getElementById('assetsTable');
      // Each tbody is one line (a group keeps its lots); the first row carries the sort cells.
      const bodies = [...table.querySelectorAll('tbody.asset-group')];
      _sortDir[col] = !_sortDir[col];
      // Cells carry data-sort with the raw value (signed numbers, ISO dates); empty means unknown.
      const key = cell => cell.dataset.sort !== undefined ? cell.dataset.sort : cell.textContent.trim();
      bodies.sort((a, b) => {{
        const av = key(a.rows[0].cells[col]), bv = key(b.rows[0].cells[col]);
        const an = av === '' ? NaN : Number(av), bn = bv === '' ? NaN : Number(bv);
        let cmp;
        if (!isNaN(an) && !isNaN(bn)) cmp = an - bn;
        else if (av === '' || bv === '') cmp = av === bv ? 0 : (av === '' ? -1 : 1);
        else cmp = av.localeCompare(bv, 'pt-BR');
        return _sortDir[col] ? cmp : -cmp;
      }});
      bodies.forEach(tb => table.appendChild(tb));
    }}

    // Snapshots hidden in earlier sessions must also be hidden in the first paint.
    if (getDeleted().size) {{ updateAvanco(); }}

    function toggleTargets() {{
      const panel = document.getElementById('targetsPanel');
      const btn = document.getElementById('toggleTargetsBtn');
      const opening = panel.style.display === 'none';
      panel.style.display = opening ? 'block' : 'none';
      btn.textContent = opening ? 'Fechar ✕' : 'Configurar ▾';
      if (opening) updateTargetsTotal();
    }}

    function updateTargetsTotal() {{
      const inputs = document.querySelectorAll('.target-input');
      let total = 0;
      inputs.forEach(inp => {{ total += parseFloat(inp.value) || 0; }});
      total = Math.round(total * 10) / 10;
      const el = document.getElementById('targetsTotal');
      el.textContent = 'Total: ' + total + '%';
      el.style.color = Math.abs(total - 100) < 0.05 ? '#16a34a' : '#dc2626';
    }}

    function saveTargets() {{
      const inputs = document.querySelectorAll('.target-input');
      const targets = {{}};
      let total = 0;
      inputs.forEach(inp => {{
        const val = parseFloat(inp.value) || 0;
        targets[inp.dataset.category] = val;
        total += val;
      }});
      total = Math.round(total * 10) / 10;
      if (Math.abs(total - 100) > 0.05) {{
        alert('As metas devem somar 100%. Total atual: ' + total + '%');
        return;
      }}
      const blob = new Blob([JSON.stringify(targets, null, 2)], {{type: 'application/json'}});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'allocation_targets.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
    }}
  </script>
</body>
</html>"""

    private_write(output_path, html)

    return output_path


def _load_optional_json(path: str | None, label: str) -> dict | None:
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"Aviso: {label} ilegível em {path}; seção omitida.", file=sys.stderr)
        return None
    return data if isinstance(data, dict) else None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gera o relatório HTML da carteira.")
    parser.add_argument("investments", help="investments.json normalizado")
    parser.add_argument("output", nargs="?", default="relatorio.html")
    parser.add_argument("--diff", help="diff.json de snapshot_diff.py")
    parser.add_argument("--performance", help="JSON de performance.py --json")
    parser.add_argument("--rebalance", help="JSON de rebalance.py --json")
    args = parser.parse_args()

    try:
        with open(args.investments, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Erro: arquivo não encontrado: {args.investments}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Erro: JSON inválido em {args.investments}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        investments = investments_list(data)
        migrate_legacy()
        result = generate_html(investments, args.output, load_diff(args.diff), targets=load_targets(),
                               performance=_load_optional_json(args.performance, "performance"),
                               rebalance=_load_optional_json(args.rebalance, "rebalance"))
    except (ValueError, OSError) as exc:
        print(f"Erro no relatório: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Relatório gerado: {result}")
