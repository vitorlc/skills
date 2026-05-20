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
