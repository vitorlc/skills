---
name: pluggy-investment-report
description: Use this skill whenever the user wants to view, analyze, or report on their investments or portfolio. Triggers on phrases like "gerar relatório de investimentos", "ver minha carteira", "quanto tenho investido", "meus rendimentos", "como estão meus ativos", "relatório financeiro", "dashboard de investimentos", "evolução da carteira", or any request to check, summarize, or visualize investment data from connected bank or broker accounts — even if the user doesn't explicitly mention "Pluggy" or "report".
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

Credentials must be set as shell environment variables — **never request, display, or transcribe credential values in the chat or terminal**.

Tell the user to export them before running the skill:
```bash
export PLUGGY_CLIENT_ID="your-client-id"
export PLUGGY_CLIENT_SECRET="your-client-secret"
```

Check presence only (without revealing values):
```bash
[ -n "$PLUGGY_CLIENT_ID" ]     && echo "✓ PLUGGY_CLIENT_ID set"     || echo "✗ PLUGGY_CLIENT_ID missing"
[ -n "$PLUGGY_CLIENT_SECRET" ] && echo "✓ PLUGGY_CLIENT_SECRET set" || echo "✗ PLUGGY_CLIENT_SECRET missing"
```

### Sandbox / test data

If the user asks for a demo or test run (or passes `--sandbox`), follow the sandbox setup in `references/pluggy-api.md` section 5. Real credentials are still required; the difference is that you connect a sandbox account (connector 201) instead of real bank accounts.

### Allocation targets (optional)

If `$SKILL_DIR/tmp/allocation_targets.json` exists (where `$SKILL_DIR` is set in Step 0), the report will include an allocation analysis section comparing targets to actual percentages.

To set up targets for the first time: generate the report, open it in a browser, click **Configurar metas**, fill in the desired percentages (must sum to 100%), and click **⬇ Salvar metas**. Move the downloaded file to `$SKILL_DIR/tmp/allocation_targets.json`.

## Execution Steps

Read `references/pluggy-api.md` before proceeding for full endpoint documentation.

### Step 0 — Locate the skill directory

Set `SKILL_DIR` so subsequent steps reference the correct script and data paths:

```bash
SKILL_DIR="$HOME/.claude/skills/pluggy-investment-report"
echo "Skill dir: $SKILL_DIR"
```

If the skill was installed elsewhere, adjust the path. The `scripts/` and `tmp/` subdirectories must exist under this path.

### Step 1 — Authenticate

Use env vars directly — never substitute literal values into the command:

```bash
export PLUGGY_API_KEY=$(curl -s -X POST https://api.pluggy.ai/auth \
  -H "Content-Type: application/json" \
  -d "{\"clientId\":\"${PLUGGY_CLIENT_ID}\",\"clientSecret\":\"${PLUGGY_CLIENT_SECRET}\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('apiKey',''))")

[ -n "$PLUGGY_API_KEY" ] \
  && echo "✓ Authenticated successfully" \
  || echo "✗ Authentication failed — check your credentials in the Pluggy dashboard"
```

The API key lives in `$PLUGGY_API_KEY` for the session — do not display or copy it to the chat.

### Step 2 — Fetch all connected items

```bash
curl -s https://api.pluggy.ai/items \
  -H "X-API-KEY: ${PLUGGY_API_KEY}"
```

Extract all `results[].id` values (item IDs) and map `id → connector.name` for institution lookup.

**Pagination:** compare `total` vs `results.length`. If `total > results.length`, fetch additional pages (`?page=2`, `?page=3`, …) until all items are collected.

### Step 3 — Fetch investments per item

For each `itemId`:

```bash
curl -s "https://api.pluggy.ai/investments?itemId=ITEM_ID_HERE" \
  -H "X-API-KEY: ${PLUGGY_API_KEY}"
```

Consolidate all `results` arrays from all items into one list. Carry the institution name from the item map.

**Pagination:** same as Step 2 — check `total` vs `results.length` per item and fetch all pages before moving on.

### Step 4 — Normalize to report model

Convert each investment object to:
```json
{
  "name": "<results[].name>",
  "institution": "<bank name from accounts COMPE code OR connector.name>",
  "type": "<results[].type>",
  "amount": "<results[].amount>",
  "value": "<results[].balance>",
  "return_amount": "<results[].profits OR balance - amount>",
  "return_rate": "<results[].lastTwelveMonthsRate OR profits/amount*100>",
  "maturity_date": "<results[].dueDate OR null>"
}
```

Write the normalized list to `/tmp/pluggy_investments.json` and restrict permissions immediately:

```bash
chmod 600 /tmp/pluggy_investments.json
```

### Step 5 — Compute historical diff

Compare the current portfolio against the previous snapshot to populate the evolution chart and per-asset delta columns in the HTML report. On first run this creates the baseline; on subsequent runs it computes what changed since last time.

```bash
python3 "$SKILL_DIR/scripts/snapshot_diff.py" \
  /tmp/pluggy_investments.json \
  /tmp/pluggy_diff.json
```

If this step fails, set `DIFF_FLAG=""` and continue — the HTML report will show "—" in delta columns and an empty evolution chart. Otherwise set `DIFF_FLAG="--diff /tmp/pluggy_diff.json"`.

### Step 6 — Display Markdown summary in terminal  <!-- was Step 5 -->

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

If `$SKILL_DIR/tmp/allocation_targets.json` exists, read it and append an allocation analysis section. Compute deviation as `actual% - target%`. Only show a recommendation when `|deviation| >= 2%`. Imbalance = category with the largest absolute deviation.

```
### Análise de Alocação
| Categoria | Meta | Atual | Desvio |
|---|---|---|---|
| Renda Fixa | 70% | 76% | +6% |
| ETF | 15% | 8% | -7% |
| Fundos | 5% | 4% | -1% |

**Recomendações:**
- ↑ Comprar ETF (7% abaixo da meta)
- ↓ Reduzir Renda Fixa (6% acima da meta)

⚠ Carteira desbalanceada em 7% — maior desvio: ETF (-7%)
```

### Step 7 — Generate HTML report

```bash
python3 "$SKILL_DIR/scripts/generate_report.py" \
  /tmp/pluggy_investments.json \
  relatorio.html \
  $DIFF_FLAG
```

### Step 8 — Open in browser  <!-- was Step 7 -->

```bash
open relatorio.html        # macOS
xdg-open relatorio.html    # Linux
start relatorio.html       # Windows
```

## Error Handling

| Error | Action |
|---|---|
| `POST /auth` returns 403 | "Invalid credentials. Check your Client ID and Client Secret in the Pluggy dashboard." |
| `GET /items` returns empty list | "No connected accounts. Connect at least one account in the Pluggy dashboard at pluggy.ai." |
| No investments in any item | Show summary with zeros, still generate HTML with empty-state message |
| `python` not found | "Python 3 not found. Install Python 3.8+ or retry with `python3`." — retry with `python3` |
| `generate_report.py` fails | Show the Python error to the user, check JSON format of `/tmp/pluggy_investments.json` |
| `snapshot_diff.py` fails | Log the error, set `DIFF_FLAG=""` and continue — delta columns will show "—" |

## PDF Export

Tell the user:
> "To save as PDF: in the browser, press **Ctrl+P** (or Cmd+P on Mac) → **Save as PDF**. The layout is already formatted for A4."
