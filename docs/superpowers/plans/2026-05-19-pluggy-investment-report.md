# Pluggy Investment Report Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Claude Code skill (`pluggy-investment-report`) that fetches consolidated investment data from the Pluggy API, displays a Markdown summary in the terminal, and generates a rich HTML dashboard with charts and PDF export.

**Architecture:** The skill lives in `~/.claude/skills/pluggy-investment-report/` and is developed in `/Users/vitorlc/Documents/skills/pluggy-investment-report/`. SKILL.md instructs Claude to call the Pluggy REST API, normalize the response into a flat JSON, then invoke `scripts/generate_report.py` which produces a standalone `relatorio.html`. All API calls are made by Claude; the script handles only HTML generation.

**Tech Stack:** Python 3.8+ stdlib, Chart.js 4.4 via CDN, Pluggy REST API (`https://api.pluggy.ai`), `unittest` for testing.

---

## File Map

| File | Responsibility |
|---|---|
| `pluggy-investment-report/SKILL.md` | Instructions for Claude: auth flow, API calls, summary format, script invocation |
| `pluggy-investment-report/scripts/generate_report.py` | Reads normalized investment JSON → writes `relatorio.html` |
| `pluggy-investment-report/references/pluggy-api.md` | Compact Pluggy API reference Claude reads at runtime |
| `pluggy-investment-report/tests/test_generate_report.py` | Unit tests for `generate_report.py` |

---

## Task 1: Create Directory Structure

**Files:**
- Create: `pluggy-investment-report/scripts/.gitkeep`
- Create: `pluggy-investment-report/references/.gitkeep`
- Create: `pluggy-investment-report/tests/.gitkeep`

- [ ] **Step 1: Create directories**

```bash
mkdir -p pluggy-investment-report/scripts
mkdir -p pluggy-investment-report/references
mkdir -p pluggy-investment-report/tests
touch pluggy-investment-report/scripts/.gitkeep
touch pluggy-investment-report/references/.gitkeep
touch pluggy-investment-report/tests/.gitkeep
```

Expected: directories created with no errors.

- [ ] **Step 2: Verify structure**

```bash
find pluggy-investment-report -type d
```

Expected output:
```
pluggy-investment-report
pluggy-investment-report/scripts
pluggy-investment-report/references
pluggy-investment-report/tests
```

- [ ] **Step 3: Commit**

```bash
git add pluggy-investment-report/
git commit -m "feat: scaffold pluggy-investment-report skill directory"
```

---

## Task 2: Write Pluggy API Reference

**Files:**
- Create: `pluggy-investment-report/references/pluggy-api.md`

- [ ] **Step 1: Create the API reference file**

Write `pluggy-investment-report/references/pluggy-api.md` with this exact content:

```markdown
# Pluggy API Reference

Base URL: `https://api.pluggy.ai`

All requests (except `/auth`) require the header:
```
X-API-KEY: {apiKey}
```

---

## 1. Authentication

**POST /auth**

Request:
```json
{
  "clientId": "YOUR_CLIENT_ID",
  "clientSecret": "YOUR_CLIENT_SECRET"
}
```

Response (200):
```json
{
  "apiKey": "abc123..."
}
```

Error (403): invalid credentials.

---

## 2. List Connected Items (Accounts)

**GET /items**

Response (200):
```json
{
  "total": 2,
  "results": [
    {
      "id": "item-uuid-1",
      "status": "UPDATED",
      "connector": {
        "id": 201,
        "name": "Nubank",
        "type": "PERSONAL_BANK"
      },
      "updatedAt": "2026-05-19T10:00:00Z"
    }
  ]
}
```

Collect all `results[].id` values — these are `itemId`s.

---

## 3. Fetch Investments for an Item

**GET /investments?itemId={itemId}**

Response (200):
```json
{
  "total": 3,
  "results": [
    {
      "id": "inv-uuid-1",
      "name": "Tesouro IPCA+ 2029",
      "balance": 5430.50,
      "amount": 5000.00,
      "profits": 430.50,
      "lastTwelveMonthsRate": 8.61,
      "dueDate": "2029-05-15",
      "type": "FIXED_INCOME",
      "subtype": "LFT",
      "issuer": "Tesouro Nacional",
      "currencyCode": "BRL",
      "date": "2023-01-10",
      "quantity": 0.5
    }
  ]
}
```

Repeat for each `itemId`. Concatenate all `results` arrays.

---

## 4. Field Mapping to Report Model

| Pluggy field | Report field | Notes |
|---|---|---|
| `name` | `name` | Asset name |
| `connector.name` (from item) | `institution` | Bank/broker name — carry it when iterating |
| `type` | `type` | FIXED_INCOME, STOCK, FUND, ETF, MUTUAL_FUND, REAL_ESTATE |
| `amount` | `amount` | Original amount invested |
| `balance` | `value` | Current market value |
| `profits` | `return_amount` | Gross return in R$ (balance - amount if missing) |
| `lastTwelveMonthsRate` | `return_rate` | Return % (calculate as profits/amount*100 if missing) |
| `dueDate` | `maturity_date` | May be null for stocks/ETFs |

**Institution lookup:** When iterating items, store a map `{itemId → connector.name}`. Use this when processing each investment.

---

## 5. Sandbox Setup

1. Go to https://pluggy.ai and create a free account
2. In the dashboard, create an **App** — this gives you Client ID and Client Secret
3. In sandbox mode, use the **Pluggy Connect Widget** or the API directly to connect a test account:
   - `POST /connect-token` with your `apiKey` to get a `connectToken`
   - Use the sandbox connector ID `201` (Nubank sandbox) for test data
4. Sandbox investments are pre-populated with realistic fake data

---

## 6. Pagination

Both `/items` and `/investments` support `page` and `pageSize` query params.
Default `pageSize` is 20. Check `total` vs `results.length` — if `total > pageSize`, fetch additional pages:

```
GET /investments?itemId={id}&page=2&pageSize=20
```

For most personal accounts, a single page is sufficient.
```

- [ ] **Step 2: Verify file was created**

```bash
wc -l pluggy-investment-report/references/pluggy-api.md
```

Expected: at least 80 lines.

- [ ] **Step 3: Commit**

```bash
git add pluggy-investment-report/references/pluggy-api.md
git commit -m "feat: add Pluggy API reference documentation"
```

---

## Task 3: Write Tests for generate_report.py (RED)

**Files:**
- Create: `pluggy-investment-report/tests/test_generate_report.py`

- [ ] **Step 1: Write the test file**

Write `pluggy-investment-report/tests/test_generate_report.py`:

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

SAMPLE_INVESTMENTS = [
    {
        "name": "Tesouro IPCA+ 2029",
        "institution": "Nubank",
        "type": "FIXED_INCOME",
        "amount": 5000.00,
        "value": 5430.50,
        "return_amount": 430.50,
        "return_rate": 8.61,
        "maturity_date": "2029-05-15",
    },
    {
        "name": "PETR4",
        "institution": "XP Investimentos",
        "type": "STOCK",
        "amount": 2000.00,
        "value": 1850.00,
        "return_amount": -150.00,
        "return_rate": -7.50,
        "maturity_date": None,
    },
]


class TestFormatHelpers(unittest.TestCase):
    def setUp(self):
        from generate_report import format_currency, format_percentage, get_type_label
        self.format_currency = format_currency
        self.format_percentage = format_percentage
        self.get_type_label = get_type_label

    def test_format_currency_integer(self):
        self.assertEqual(self.format_currency(7000.00), "R$ 7.000,00")

    def test_format_currency_decimals(self):
        self.assertEqual(self.format_currency(5430.50), "R$ 5.430,50")

    def test_format_currency_negative(self):
        self.assertEqual(self.format_currency(-150.00), "-R$ 150,00")

    def test_format_currency_zero(self):
        self.assertEqual(self.format_currency(0), "R$ 0,00")

    def test_format_percentage_positive(self):
        self.assertEqual(self.format_percentage(8.61), "8,61%")

    def test_format_percentage_negative(self):
        self.assertEqual(self.format_percentage(-7.50), "-7,50%")

    def test_get_type_label_fixed_income(self):
        self.assertEqual(self.get_type_label("FIXED_INCOME"), "Renda Fixa")

    def test_get_type_label_stock(self):
        self.assertEqual(self.get_type_label("STOCK"), "Ações")

    def test_get_type_label_fund(self):
        self.assertEqual(self.get_type_label("FUND"), "Fundos")

    def test_get_type_label_mutual_fund(self):
        self.assertEqual(self.get_type_label("MUTUAL_FUND"), "Fundos")

    def test_get_type_label_etf(self):
        self.assertEqual(self.get_type_label("ETF"), "ETF")

    def test_get_type_label_unknown_passthrough(self):
        self.assertEqual(self.get_type_label("CUSTOM_TYPE"), "CUSTOM_TYPE")


class TestGenerateHTML(unittest.TestCase):
    def setUp(self):
        from generate_report import generate_html
        self.generate_html = generate_html
        self.tmpdir = tempfile.mkdtemp()
        self.output = os.path.join(self.tmpdir, "report.html")

    def _html(self, investments=None):
        inv = investments if investments is not None else SAMPLE_INVESTMENTS
        self.generate_html(inv, self.output)
        with open(self.output, encoding="utf-8") as f:
            return f.read()

    def test_creates_file(self):
        self._html()
        self.assertTrue(os.path.exists(self.output))

    def test_total_invested_in_output(self):
        # 5000 + 2000 = 7000
        html = self._html()
        self.assertIn("7.000,00", html)

    def test_total_current_value_in_output(self):
        # 5430.50 + 1850.00 = 7280.50
        html = self._html()
        self.assertIn("7.280,50", html)

    def test_asset_names_in_output(self):
        html = self._html()
        self.assertIn("Tesouro IPCA+ 2029", html)
        self.assertIn("PETR4", html)

    def test_institution_names_in_output(self):
        html = self._html()
        self.assertIn("Nubank", html)
        self.assertIn("XP Investimentos", html)

    def test_chartjs_loaded(self):
        html = self._html()
        self.assertIn("chart.js", html.lower())

    def test_print_button_present(self):
        html = self._html()
        self.assertIn("window.print()", html)

    def test_media_print_css(self):
        html = self._html()
        self.assertIn("@media print", html)

    def test_positive_return_class(self):
        html = self._html()
        self.assertIn('class="number positive"', html)

    def test_negative_return_class(self):
        html = self._html()
        self.assertIn('class="number negative"', html)

    def test_empty_investments_generates_file(self):
        html = self._html([])
        self.assertIn("R$ 0,00", html)
        self.assertTrue(os.path.exists(self.output))

    def test_null_maturity_date_renders_dash(self):
        html = self._html()
        # PETR4 has maturity_date=None, should show "-"
        self.assertIn("-</td>", html)

    def test_pie_chart_data_injected(self):
        html = self._html()
        self.assertIn("Renda Fixa", html)
        self.assertIn("doughnut", html)

    def test_bar_chart_data_injected(self):
        html = self._html()
        self.assertIn("barChart", html)

    def test_sortable_table_script(self):
        html = self._html()
        self.assertIn("sortTable", html)

    def test_returns_output_path(self):
        from generate_report import generate_html
        result = generate_html(SAMPLE_INVESTMENTS, self.output)
        self.assertEqual(result, self.output)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_cli_reads_json_file_and_generates_html(self):
        json_path = os.path.join(self.tmpdir, "investments.json")
        output_path = os.path.join(self.tmpdir, "out.html")
        with open(json_path, "w") as f:
            json.dump(SAMPLE_INVESTMENTS, f)

        import subprocess
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'generate_report.py')
        result = subprocess.run(
            [sys.executable, script, json_path, output_path],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(output_path))

    def test_cli_accepts_list_wrapped_in_dict(self):
        json_path = os.path.join(self.tmpdir, "wrapped.json")
        output_path = os.path.join(self.tmpdir, "out2.html")
        with open(json_path, "w") as f:
            json.dump({"investments": SAMPLE_INVESTMENTS}, f)

        import subprocess
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'generate_report.py')
        result = subprocess.run(
            [sys.executable, script, json_path, output_path],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(output_path))

    def test_cli_exits_nonzero_without_args(self):
        import subprocess
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'generate_report.py')
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — verify they FAIL (script doesn't exist yet)**

```bash
python -m pytest pluggy-investment-report/tests/test_generate_report.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'generate_report'` — this is correct, RED phase.

- [ ] **Step 3: Commit the failing tests**

```bash
git add pluggy-investment-report/tests/test_generate_report.py
git commit -m "test: add unit tests for generate_report.py (RED)"
```

---

## Task 4: Implement generate_report.py (GREEN)

**Files:**
- Create: `pluggy-investment-report/scripts/generate_report.py`

- [ ] **Step 1: Write the implementation**

Write `pluggy-investment-report/scripts/generate_report.py`:

```python
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
          <td>{inv.get("name") or "-"}</td>
          <td>{inv.get("institution") or "-"}</td>
          <td><span class="badge badge-{type_code.lower()}">{get_type_label(type_code)}</span></td>
          <td class="number">{format_currency(inv.get("amount", 0) or 0)}</td>
          <td class="number">{format_currency(inv.get("value", 0) or 0)}</td>
          <td class="number {ret_class}">{format_currency(ret_amt)}</td>
          <td class="number {ret_class}">{format_percentage(ret_rate)}</td>
          <td>{maturity}</td>
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
        const an = parseFloat(av.replace(/[^\d,.-]/g, '').replace(',', '.'));
        const bn = parseFloat(bv.replace(/[^\d,.-]/g, '').replace(',', '.'));
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

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    investments = data if isinstance(data, list) else data.get("investments", [])
    result = generate_html(investments, output_path)
    print(f"Relatório gerado: {result}")
```

- [ ] **Step 2: Run tests — verify they PASS**

```bash
python -m pytest pluggy-investment-report/tests/test_generate_report.py -v
```

Expected: all tests PASS. If any fail, fix the implementation before proceeding.

- [ ] **Step 3: Quick smoke test with real file**

```bash
cat > /tmp/test_inv.json << 'EOF'
[
  {"name":"Tesouro IPCA+ 2029","institution":"Nubank","type":"FIXED_INCOME","amount":5000,"value":5430.5,"return_amount":430.5,"return_rate":8.61,"maturity_date":"2029-05-15"},
  {"name":"PETR4","institution":"XP Investimentos","type":"STOCK","amount":2000,"value":1850,"return_amount":-150,"return_rate":-7.5,"maturity_date":null}
]
EOF
python pluggy-investment-report/scripts/generate_report.py /tmp/test_inv.json /tmp/test_report.html && echo "OK" && wc -c /tmp/test_report.html
```

Expected: `OK` and file size > 5000 bytes.

- [ ] **Step 4: Commit**

```bash
git add pluggy-investment-report/scripts/generate_report.py
git commit -m "feat: implement generate_report.py HTML dashboard generator"
```

---

## Task 5: Write SKILL.md

**Files:**
- Create: `pluggy-investment-report/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

Write `pluggy-investment-report/SKILL.md`:

```markdown
---
name: pluggy-investment-report
description: Use this skill when the user wants to generate an investment report using the Pluggy API. Fetches consolidated investment data from all connected accounts and produces a Markdown summary in the terminal plus a rich HTML dashboard with charts and PDF export.
---

# Pluggy Investment Report

Generates a consolidated investment report from all Pluggy-connected accounts.

## Prerequisites

### First-time setup (no credentials yet)

1. Go to https://pluggy.ai → **Sign Up** (free sandbox account)
2. In the dashboard: **Apps** → **New App** → copy your **Client ID** and **Client Secret**
3. To connect a test account in sandbox:
   - Use the Pluggy Connect Widget in the dashboard
   - Or connect sandbox connector ID `201` (Nubank sandbox) for pre-populated test data

### If user already has credentials

Ask the user:
> "Você tem seu Pluggy Client ID e Client Secret? Você pode fornecê-los agora ou eu posso ler das variáveis de ambiente `PLUGGY_CLIENT_ID` e `PLUGGY_CLIENT_SECRET`."

Check env vars first:
```bash
echo $PLUGGY_CLIENT_ID
echo $PLUGGY_CLIENT_SECRET
```

## Execution Steps

Read `references/pluggy-api.md` before proceeding for full endpoint documentation.

### Step 1 — Authenticate

```bash
curl -s -X POST https://api.pluggy.ai/auth \
  -H "Content-Type: application/json" \
  -d '{"clientId":"CLIENT_ID_HERE","clientSecret":"CLIENT_SECRET_HERE"}'
```

Extract `apiKey` from response. Store as `API_KEY`.

### Step 2 — Fetch all connected items

```bash
curl -s https://api.pluggy.ai/items \
  -H "X-API-KEY: API_KEY_HERE"
```

Extract all `results[].id` values (item IDs) and map `id → connector.name` for institution lookup.

### Step 3 — Fetch investments per item

For each `itemId`:

```bash
curl -s "https://api.pluggy.ai/investments?itemId=ITEM_ID_HERE" \
  -H "X-API-KEY: API_KEY_HERE"
```

Consolidate all `results` arrays from all items into one list.
Carry the institution name from the item map.

### Step 4 — Normalize to report model

Convert each investment object to:
```json
{
  "name": "<results[].name>",
  "institution": "<connector.name from item>",
  "type": "<results[].type>",
  "amount": "<results[].amount>",
  "value": "<results[].balance>",
  "return_amount": "<results[].profits OR balance - amount>",
  "return_rate": "<results[].lastTwelveMonthsRate OR profits/amount*100>",
  "maturity_date": "<results[].dueDate OR null>"
}
```

Write the normalized list to `/tmp/pluggy_investments.json`.

### Step 5 — Display Markdown summary in terminal

Output exactly this format (fill in real values):

```
## Resumo de Investimentos

| Métrica | Valor |
|---|---|
| Total Investido | R$ X.XXX,XX |
| Valor Atual | R$ X.XXX,XX |
| Rendimento Total | R$ X.XXX,XX (X,XX%) |
| Número de Ativos | XX |

### Por Tipo de Ativo
| Tipo | Valor Atual | % da Carteira |
|---|---|---|
| Renda Fixa | R$ X.XXX,XX | XX,X% |
| Ações | R$ X.XXX,XX | XX,X% |
...
```

### Step 6 — Generate HTML report

```bash
python ~/.claude/skills/pluggy-investment-report/scripts/generate_report.py \
  /tmp/pluggy_investments.json \
  relatorio.html
```

### Step 7 — Open in browser

```bash
open relatorio.html        # macOS
xdg-open relatorio.html    # Linux
start relatorio.html       # Windows
```

## Error Handling

| Error | Action |
|---|---|
| `POST /auth` returns 403 | "Credenciais inválidas. Verifique seu Client ID e Client Secret no dashboard da Pluggy." |
| `GET /items` returns empty list | "Nenhuma conta conectada. Conecte pelo menos uma conta no dashboard da Pluggy em pluggy.ai." |
| No investments in any item | Show summary with zeros, still generate HTML with empty-state message |
| `python` not found | "Python 3 não encontrado. Instale Python 3.8+ ou execute `python3` em vez de `python`." — retry with `python3` |
| `generate_report.py` fails | Show the Python error to the user, check JSON format of `/tmp/pluggy_investments.json` |

## PDF Export

Tell the user:
> "Para salvar como PDF: no browser, use **Ctrl+P** (ou Cmd+P no Mac) → **Salvar como PDF**. O layout já está formatado para A4."
```

- [ ] **Step 2: Verify frontmatter is valid**

```bash
head -6 pluggy-investment-report/SKILL.md
```

Expected: shows `---`, `name:`, `description:`, `---` correctly.

- [ ] **Step 3: Commit**

```bash
git add pluggy-investment-report/SKILL.md
git commit -m "feat: add SKILL.md with Pluggy authentication and report generation flow"
```

---

## Task 6: Install Skill and End-to-End Smoke Test

**Files:**
- Copies to: `~/.claude/skills/pluggy-investment-report/`

- [ ] **Step 1: Install skill to Claude's skills directory**

```bash
mkdir -p ~/.claude/skills/pluggy-investment-report/scripts
mkdir -p ~/.claude/skills/pluggy-investment-report/references
cp pluggy-investment-report/SKILL.md ~/.claude/skills/pluggy-investment-report/SKILL.md
cp pluggy-investment-report/scripts/generate_report.py ~/.claude/skills/pluggy-investment-report/scripts/generate_report.py
cp pluggy-investment-report/references/pluggy-api.md ~/.claude/skills/pluggy-investment-report/references/pluggy-api.md
```

- [ ] **Step 2: Verify installation**

```bash
ls ~/.claude/skills/pluggy-investment-report/
ls ~/.claude/skills/pluggy-investment-report/scripts/
ls ~/.claude/skills/pluggy-investment-report/references/
```

Expected:
```
SKILL.md  references/  scripts/
generate_report.py
pluggy-api.md
```

- [ ] **Step 3: Smoke test the script with sample data**

```bash
cat > /tmp/smoke_test.json << 'EOF'
[
  {"name":"CDB Banco Inter 120% CDI","institution":"Banco Inter","type":"FIXED_INCOME","amount":10000,"value":11200,"return_amount":1200,"return_rate":12.0,"maturity_date":"2027-06-30"},
  {"name":"XPML11","institution":"XP Investimentos","type":"REAL_ESTATE","amount":5000,"value":5350,"return_amount":350,"return_rate":7.0,"maturity_date":null},
  {"name":"BOVA11","institution":"Clear Corretora","type":"ETF","amount":3000,"value":2800,"return_amount":-200,"return_rate":-6.67,"maturity_date":null}
]
EOF
python ~/.claude/skills/pluggy-investment-report/scripts/generate_report.py /tmp/smoke_test.json /tmp/smoke_report.html
open /tmp/smoke_report.html
```

Expected: script prints `Relatório gerado: /tmp/smoke_report.html` and browser opens showing the dashboard with 3 assets, charts, and correct totals (Total Investido: R$ 18.000,00; Valor Atual: R$ 19.350,00).

- [ ] **Step 4: Run full test suite one final time**

```bash
python -m pytest pluggy-investment-report/tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Final commit**

```bash
git add pluggy-investment-report/
git commit -m "feat: complete pluggy-investment-report skill with install verification"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec requirement | Covered by |
|---|---|
| Setup instructions for new Pluggy users | Task 5 SKILL.md Prerequisites section |
| POST /auth authentication flow | Task 2 (reference doc) + Task 5 Step 1 |
| GET /items to list accounts | Task 2 + Task 5 Step 2 |
| GET /investments per item | Task 2 + Task 5 Step 3 |
| Consolidate all accounts | Task 5 Step 3 (concatenate results) |
| Markdown summary in terminal | Task 5 Step 5 |
| generate_report.py reads JSON | Task 4 implementation |
| 3 summary cards (Investido, Atual, Rendimento) | Task 4 HTML |
| Pie chart by asset type | Task 4 HTML |
| Bar chart by institution | Task 4 HTML |
| Sortable asset table with all columns | Task 4 HTML |
| Print/PDF button + @media print | Task 4 HTML |
| Error handling for all 6 scenarios | Task 5 Error Handling table |
| Python 3.8+ stdlib only | Task 4 (no imports outside stdlib + json) |
| Open HTML in browser after generation | Task 5 Step 7 |

All spec requirements covered. ✓
