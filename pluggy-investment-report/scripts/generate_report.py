#!/usr/bin/env python3
"""
Pluggy Investment Report Generator
Usage: python generate_report.py <investments.json> [output.html] [--diff diff.json]

investments.json must be a JSON array of objects with fields:
  id, name, institution, type, value, maturity_date
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from html import escape as _e


def format_currency(value: float) -> str:
    sign = "-R$ " if value < 0 else "R$ "
    formatted = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}{formatted}"


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


def get_type_label(type_code: str) -> str:
    return {
        "FIXED_INCOME": "Renda Fixa",
        "EQUITY": "Ações",
        "FUND": "Fundos",
        "MUTUAL_FUND": "Fundos",
        "ETF": "ETF",
        "TREASURY": "Tesouro Direto",
        "REAL_ESTATE": "FIIs",
        "OTHER": "Outros",
    }.get(type_code, type_code)


def load_snapshots_series() -> tuple[list[str], list[float]]:
    """Returns (labels, values) from all saved snapshots, sorted by timestamp."""
    snap_dir = Path(__file__).resolve().parent.parent / "tmp" / "snapshots"
    if not snap_dir.exists():
        return [], []
    labels, values = [], []
    for f in sorted(snap_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text())
            dt = datetime.fromisoformat(d["timestamp"])
            labels.append(dt.strftime("%d/%m %H:%M"))
            values.append(round(d["totals"]["current"], 2))
        except (KeyError, ValueError):
            continue
    return labels, values


def load_diff(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


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


def generate_html(investments: list, output_path: str, diff: dict | None) -> str:
    investments = [i for i in investments if (i.get("value") or 0) > 0]

    total_current = sum(i.get("value", 0) or 0 for i in investments)

    first_run = diff.get("first_run", True) if diff else True
    prev_ts_str = ""
    total_delta = 0.0
    if diff and not first_run:
        prev_ts = diff.get("previous_timestamp", "")
        try:
            dt = datetime.fromisoformat(prev_ts)
            prev_ts_str = dt.strftime("%d/%m/%Y às %H:%M")
        except (ValueError, TypeError):
            prev_ts_str = prev_ts
        total_delta = diff.get("totals", {}).get("current", {}).get("delta", 0)

    asset_deltas = build_asset_deltas(diff)

    type_totals: dict = {}
    for inv in investments:
        label = get_type_label(inv.get("type", "OTHER"))
        type_totals[label] = type_totals.get(label, 0) + (inv.get("value", 0) or 0)

    type_labels_js = json.dumps(list(type_totals.keys()))
    type_values_js = json.dumps([round(v, 2) for v in type_totals.values()])

    snap_labels, snap_values = load_snapshots_series()
    snap_labels_js = json.dumps(snap_labels)
    snap_values_js = json.dumps(snap_values)

    delta_str, delta_class = format_delta(total_delta)
    avanco_label = f"Avanço desde {prev_ts_str}" if prev_ts_str else "Avanço"
    avanco_note = f"desde {prev_ts_str}" if prev_ts_str else "primeira execução"

    rows_html = ""
    for inv in sorted(investments, key=lambda x: x.get("value", 0) or 0, reverse=True):
        inv_id = inv.get("id", "")
        asset_delta = asset_deltas.get(inv_id)
        if asset_delta is not None:
            ad_str, ad_class = format_delta(asset_delta)
        else:
            ad_str, ad_class = "—", "neutral"

        maturity = format_date(inv.get("maturity_date"))
        type_code = inv.get("type", "OTHER") or "OTHER"
        rows_html += f"""
        <tr>
          <td>{_e(inv.get("name") or "-")}</td>
          <td>{_e(inv.get("institution") or "-")}</td>
          <td><span class="badge badge-{_e(type_code.lower())}">{_e(get_type_label(type_code))}</span></td>
          <td class="number">{format_currency(inv.get("value", 0) or 0)}</td>
          <td class="number {ad_class}">{_e(ad_str)}</td>
          <td>{_e(maturity)}</td>
        </tr>"""

    n = len(investments)
    asset_word = "ativo" if n == 1 else "ativos"
    generation_date = datetime.now().strftime("%d/%m/%Y às %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Relatório de Investimentos</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"
          integrity="sha384-e6nUZLBkQ86NJ6TVVKAeSaK8jWa3NhkYWZFomE39AvDbQWeie9PlQqM3pmYW5d1g"
          crossorigin="anonymous"></script>
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
        <div class="label">{_e(avanco_label)}</div>
        <div class="value {delta_class}">{_e(delta_str)}</div>
        <div class="note">{_e(avanco_note)}</div>
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

    <div class="table-box">
      <h2>Ativos ({n} {asset_word})</h2>
      <table id="assetsTable">
        <thead>
          <tr>
            <th onclick="sortTable(0)">Nome ↕</th>
            <th onclick="sortTable(1)">Instituição ↕</th>
            <th onclick="sortTable(2)">Tipo ↕</th>
            <th onclick="sortTable(3)" style="text-align:right">Valor Atual ↕</th>
            <th onclick="sortTable(4)" style="text-align:right">Avanço ↕</th>
            <th onclick="sortTable(5)">Vencimento ↕</th>
          </tr>
        </thead>
        <tbody>{rows_html}
        </tbody>
      </table>
    </div>

    <button class="print-btn" onclick="window.print()">Imprimir / Salvar como PDF</button>
  </div>

  <script>
    const COLORS = ['#3b82f6','#f59e0b','#8b5cf6','#10b981','#ef4444','#06b6d4','#f97316','#6366f1'];

    new Chart(document.getElementById('pieChart'), {{
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

    new Chart(document.getElementById('lineChart'), {{
      type: 'line',
      data: {{
        labels: {snap_labels_js},
        datasets: [{{
          label: 'Valor Total',
          data: {snap_values_js},
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
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          y: {{
            ticks: {{ callback: v => 'R$ ' + v.toLocaleString('pt-BR') }},
            grid: {{ color: '#f0f0f0' }}
          }},
          x: {{ grid: {{ display: false }} }}
        }}
      }}
    }});

    let _sortDir = {{}};
    function sortTable(col) {{
      const tbody = document.querySelector('#assetsTable tbody');
      const rows = [...tbody.querySelectorAll('tr')];
      _sortDir[col] = !_sortDir[col];
      rows.sort((a, b) => {{
        const av = a.cells[col].textContent.trim();
        const bv = b.cells[col].textContent.trim();
        const an = parseFloat(av.replace(/[^\\d,\\-]/g, '').replace('.', '').replace(',', '.'));
        const bn = parseFloat(bv.replace(/[^\\d,\\-]/g, '').replace('.', '').replace(',', '.'));
        if (!isNaN(an) && !isNaN(bn)) return _sortDir[col] ? an - bn : bn - an;
        return _sortDir[col] ? av.localeCompare(bv, 'pt-BR') : bv.localeCompare(av, 'pt-BR');
      }});
      rows.forEach(r => tbody.appendChild(r));
    }}
  </script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: generate_report.py <investments.json> [output.html] [--diff diff.json]", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    output_path = "relatorio.html"
    diff_path = None

    args = sys.argv[2:]
    positional = []
    i = 0
    while i < len(args):
        if args[i] == "--diff" and i + 1 < len(args):
            diff_path = args[i + 1]
            i += 2
        else:
            positional.append(args[i])
            i += 1
    if positional:
        output_path = positional[0]

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Erro: arquivo não encontrado: {json_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Erro: JSON inválido em {json_path}: {e}", file=sys.stderr)
        sys.exit(1)

    investments = data if isinstance(data, list) else data.get("investments", [])
    diff = load_diff(diff_path)
    result = generate_html(investments, output_path, diff)
    print(f"Relatório gerado: {result}")
