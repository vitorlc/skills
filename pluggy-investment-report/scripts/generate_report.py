#!/usr/bin/env python3
"""
Pluggy Investment Report Generator
Usage: python generate_report.py <investments.json> [output.html]

investments.json must be a JSON array of objects with fields:
  name, institution, type, amount, value, return_amount, return_rate, maturity_date
"""
import json
import os
import sys
from datetime import datetime
from html import escape as _e


def format_currency(value: float) -> str:
    sign = "-R$ " if value < 0 else "R$ "
    formatted = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}{formatted}"


def format_percentage(value: float) -> str:
    return f"{value:.2f}%".replace(".", ",")


def get_type_label(type_code: str) -> str:
    return {
        "FIXED_INCOME": "Renda Fixa",
        "STOCK": "Ações",
        "FUND": "Fundos",
        "MUTUAL_FUND": "Fundos",
        "ETF": "ETF",
        "TREASURY": "Tesouro Direto",
        "REAL_ESTATE": "FIIs",
        "OTHER": "Outros",
    }.get(type_code, type_code)


def generate_html(investments: list, output_path: str = "relatorio.html") -> str:
    total_invested = sum(i.get("amount", 0) or 0 for i in investments)
    total_current = sum(i.get("value", 0) or 0 for i in investments)
    total_return = total_current - total_invested
    total_return_rate = (total_return / total_invested * 100) if total_invested else 0

    type_totals: dict = {}
    for inv in investments:
        label = get_type_label(inv.get("type", "OTHER"))
        type_totals[label] = type_totals.get(label, 0) + (inv.get("value", 0) or 0)

    inst_totals: dict = {}
    for inv in investments:
        inst = inv.get("institution") or "Desconhecido"
        inst_totals[inst] = inst_totals.get(inst, 0) + (inv.get("value", 0) or 0)

    type_labels_js = json.dumps(list(type_totals.keys()))
    type_values_js = json.dumps([round(v, 2) for v in type_totals.values()])
    inst_labels_js = json.dumps(list(inst_totals.keys()))
    inst_values_js = json.dumps([round(v, 2) for v in inst_totals.values()])

    rows_html = ""
    for inv in sorted(investments, key=lambda x: x.get("value", 0) or 0, reverse=True):
        ret_amt = inv.get("return_amount", 0) or 0
        ret_rate = inv.get("return_rate", 0) or 0
        ret_class = "positive" if ret_amt >= 0 else "negative"
        maturity = inv.get("maturity_date") or "-"
        type_code = inv.get("type", "OTHER") or "OTHER"
        rows_html += f"""
        <tr>
          <td>{_e(inv.get("name") or "-")}</td>
          <td>{_e(inv.get("institution") or "-")}</td>
          <td><span class="badge badge-{_e(type_code.lower())}">{_e(get_type_label(type_code))}</span></td>
          <td class="number">{format_currency(inv.get("amount", 0) or 0)}</td>
          <td class="number">{format_currency(inv.get("value", 0) or 0)}</td>
          <td class="number {ret_class}">{format_currency(ret_amt)}</td>
          <td class="number {ret_class}">{format_percentage(ret_rate)}</td>
          <td>{_e(str(maturity))}</td>
        </tr>"""

    ret_card_class = "positive" if total_return >= 0 else "negative"
    n = len(investments)
    asset_word = "ativo" if n == 1 else "ativos"
    generation_date = datetime.now().strftime("%d/%m/%Y às %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Relatório de Investimentos</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
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
      display: grid; grid-template-columns: repeat(3, 1fr);
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
    .badge {{
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      font-size: 0.74rem; font-weight: 500;
    }}
    .badge-fixed_income {{ background: #dbeafe; color: #1d4ed8; }}
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
        <div class="label">Total Investido</div>
        <div class="value">{format_currency(total_invested)}</div>
      </div>
      <div class="card">
        <div class="label">Valor Atual</div>
        <div class="value">{format_currency(total_current)}</div>
      </div>
      <div class="card">
        <div class="label">Rendimento Total</div>
        <div class="value {ret_card_class}">
          {format_currency(total_return)}<br>
          <small>{format_percentage(total_return_rate)}</small>
        </div>
      </div>
    </div>

    <div class="charts">
      <div class="chart-box">
        <h2>Alocação por Tipo</h2>
        <canvas id="pieChart"></canvas>
      </div>
      <div class="chart-box">
        <h2>Valor por Instituição</h2>
        <canvas id="barChart"></canvas>
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
            <th onclick="sortTable(3)" style="text-align:right">Investido ↕</th>
            <th onclick="sortTable(4)" style="text-align:right">Valor Atual ↕</th>
            <th onclick="sortTable(5)" style="text-align:right">Rendimento ↕</th>
            <th onclick="sortTable(6)" style="text-align:right">Retorno % ↕</th>
            <th onclick="sortTable(7)">Vencimento ↕</th>
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

    new Chart(document.getElementById('barChart'), {{
      type: 'bar',
      data: {{
        labels: {inst_labels_js},
        datasets: [{{
          label: 'Valor Atual',
          data: {inst_values_js},
          backgroundColor: COLORS, borderRadius: 6, borderWidth: 0
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
        print("Usage: generate_report.py <investments.json> [output.html]", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "relatorio.html"

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
    if not investments:
        print("Aviso: nenhum investimento encontrado no arquivo JSON.", file=sys.stderr)
    result = generate_html(investments, output_path)
    print(f"Relatório gerado: {result}")
