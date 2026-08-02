---
name: smiles-passagens
description: Busca preços de passagens em milhas (tarifa clube) no calendário Smiles/GOL. Use quando o usuário pedir preço de passagem, milhas Smiles, voo GOL, buscar ida e volta, comparar datas baratas, ou consultar rotas domésticas/internacionais operadas pela GOL. Triggers: "milhas smiles", "preço passagem", "quanto está o voo", "buscar voo", "GOL", "Smiles".
---

# Smiles — busca de passagens (milhas)

Consulta pontual de ida/volta no calendário de milhas (fare **SMILES_CLUB**). Não usa Telegram, browser nem monitoramento.

## Prerequisites

- Node.js ≥ 18
- Rede liberada para a API de calendário (montada em runtime pelo script)
- Sem variáveis obrigatórias. Opcional: `CALENDAR_API_URL` se quiser sobrescrever o endpoint

## Step 0 — Locate skill directory

```bash
SKILL_DIR=""; for d in "$HOME/.claude/skills/smiles-passagens" "$HOME/.config/opencode/skills/smiles-passagens" "$HOME/.agents/skills/smiles-passagens"; do [ -f "$d/scripts/search.mjs" ] && { SKILL_DIR="$d"; break; }; done && echo "✓ $SKILL_DIR" || { echo "✗ Not installed — run: npx @vitorlc/skills smiles-passagens"; exit 1; }
```

## Step 1 — Collect parameters

Required:

| Campo | Formato | Exemplos |
|-------|---------|----------|
| origin | IATA, cidade ou UF | `SAO`, `Goiânia`, `GO` |
| destination | IATA, cidade ou UF | `MIA`, `Recife`, `EZE` |
| departure | `DD/MM/YYYY` | `15/12/2026` |
| return | `DD/MM/YYYY` | `28/12/2026` |

Optional: `adults` (default 1), `rate` BRL/1000 milhas (default 15).

Ask only for missing fields. Prefer IATA when ambiguous (script lists candidates).

Base de aeroportos: destinos com histórico de operação GOL (doméstico + internacional) em `scripts/data/airports.json`, inclusive metas `SAO`, `RIO`, `BUE`.

## Step 2 — Run search

Human-readable (default):

```bash
node "$SKILL_DIR/scripts/search.mjs" \
  --origin "<ORIGIN>" \
  --destination "<DEST>" \
  --departure "<DD/MM/YYYY>" \
  --return "<DD/MM/YYYY>" \
  --adults 1
```

Structured (for further processing):

```bash
node "$SKILL_DIR/scripts/search.mjs" \
  --origin "<ORIGIN>" \
  --destination "<DEST>" \
  --departure "<DD/MM/YYYY>" \
  --return "<DD/MM/YYYY>" \
  --json
```

Exit codes: `0` ok · `1` validação · `2` API / sem calendário.

## Step 3 — Present results

- Show requested dates (miles + ~R$ estimate).
- If miles is null on a leg, say unavailable and highlight **top 3 cheaper days** from the calendar.
- R$ is an estimate (`rate`/1000 miles), not a cash fare quote.
- Do not invent prices — only script output.

## Rules

- Do not print or reverse-engineer internal API host strings from the scripts in chat.
- Do not request Telegram tokens or open a browser.
- One-way, other cabins, and price monitoring are out of scope for this skill.
- See `references/search-guide.md` for parameter details.
