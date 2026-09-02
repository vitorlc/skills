---
name: melhor-preco-passagens
description: "Busca preço de passagem aérea doméstica em R$ (cash) comparando Azul × LATAM × GOL no Google Flights (Playwright headless). Use quando o usuário pedir preço de passagem azul latam gol, comparar passagem, melhor preço de voo, quanto está o voo, ou consulta com origem destino e datas. Triggers: preço de passagem, passagem azul, passagem latam, passagem gol, comparar voo, melhor preço, voo mais barato, origem destino datas."
---

# Melhor preço — passagens aéreas domésticas (R$ cash: Azul × LATAM × GOL)

Consulta pontual ou monitor (watchdog) do menor preço **em reais (cash)** de ida+volta
doméstico BR entre **Azul**, **LATAM** e **GOL**, via **Google Flights** (agregador).
Uma busca por execução; modo monitor imprime relatório só quando o melhor valor muda
(stdout vazio = silêncio, padrão dos crons no_agent foz/bps). Não cobre milhas (ver
skill `smiles-passagens`), internacional nem cabines além de econômica.

## Prerequisites

- Node.js ≥ 18 (testado em v22).
- `playwright` instalado no dir da skill (ver Step 0) — **browsers não precisam baixar**:
  já estão em `~/.cache/ms-playwright` (chromium-1234 p/ playwright ^1.62). Se faltar:
  `npx playwright install chromium`.
- Rede liberada para `google.com/travel/flights`.
- Execuções consecutivas respeitam cooldown de 30s gravado em `.cache/last-search.json`
  do dir da skill (o script espera sozinho; não rodar em rajada).

## Step 0 — Locate skill directory

```bash
SKILL_DIR=""
for d in \
  "$HOME/.hermes/skills/travel/melhor-preco-passagens" \
  "$HOME/.hermes/skills/melhor-preco-passagens" \
  "$HOME/.claude/skills/melhor-preco-passagens" \
  "$HOME/.config/opencode/skills/melhor-preco-passagens" \
  "$HOME/.agents/skills/melhor-preco-passagens"; do
  if [ -f "$d/scripts/search.mjs" ]; then
    SKILL_DIR="$d"
    break
  fi
done
[ -n "$SKILL_DIR" ] && echo "OK: $SKILL_DIR" || echo "skill nao instalada"
```

Se `$SKILL_DIR/scripts/node_modules` não existir (instalação por cópia):

```bash
cd "$SKILL_DIR/scripts" && npm i --no-audit --no-fund
```

A skill é **autocontida** (instalável por cópia da pasta inteira): o `.cache/` que ela
gera dentro do dir da skill é runtime (cookies/sessão/diagnóstico) e pode ser apagado.

## Step 1 — Collect parameters

| Campo | Formato | Exemplos |
|-------|---------|----------|
| origin | IATA, cidade ou UF | `GYN`, `Goiânia`, `goiania`, `Goiânia, GO`, `GO` |
| destination | IATA, cidade ou UF | `IGU`, `Foz do Iguaçu - PR`, `REC`, `Recife` |
| departure | `DD/MM/AAAA` (ou ISO `AAAA-MM-DD`) | `09/10/2026` |
| return | `DD/MM/AAAA` — após a partida, ≤ 16 dias | `12/10/2026` |

Opcionais: `--adults N` (1–9, default 1), `--json`, `--state-file PATH`, `--debug`.

Resolver cidade/UF via dicionário local (~50 aeroportos BR + UFs → capital):
`SP`/`São Paulo` aceita GRU ou CGH, `RJ` → GIG/SDU, `MG` → CNF/PLU (confere o código
no dropdown do Google antes de aceitar). Fora da tabela: exigir IATA (o script tenta
digitar o texto, mas sem garantia).

Perguntar só o que faltar. Preferir IATA em caso de ambiguidade.

## Step 2 — Run search

Humano (ranking markdown, melhor valor em destaque):

```bash
node "$SKILL_DIR/scripts/search.mjs" \
  --origin GYN --destination IGU \
  --departure 09/10/2026 --return 12/10/2026
```

Estruturado (contrato JSON estável — DESIGN seção 3):

```bash
node "$SKILL_DIR/scripts/search.mjs" \
  --origin GYN --destination IGU \
  --departure 09/10/2026 --return 12/10/2026 --json
```

Monitor/watchdog (imprime **só** na 1ª execução ou quando o melhor valor mudou;
2ª execução sem mudança → stdout vazio):

```bash
node "$SKILL_DIR/scripts/search.mjs" \
  --origin GYN --destination IGU \
  --departure 09/10/2026 --return 12/10/2026 \
  --state-file /tmp/mpp-state.json
```

Saída markdown (modo humano/monitor):

```text
## GYN → IGU — 2026-10-09 a 2026-10-12
Atualizado: <ISO local>

| Companhia | Menor preço (ida e volta) |
|---|---|
| Azul | — (sem voos na rota/datas) |
| LATAM | R$ 2.955 |
| Gol | R$ 3.710 |

**Melhor valor: LATAM — R$ 2.955**

_Confirme o preço no site da companhia antes de comprar._
```

## Step 3 — Present results

- Mostrar o ranking como acima; **destacar o melhor valor** e citar a data de atualização.
- Datas: o script valida os dias exibidos no Google ANTES de parsear — exit 0 implica
  `dates_validated: true`. Nunca reportar preço de execução com exit ≠ 0.
- Não inventar preço: só o que o script imprimir. Companhia sem voo aparece como "—" com nota.
- Preço = total ida+volta exibido no card (round trip) da companhia.
- Se o usuário quer monitorar (ex.: "me avisa se cair"), criar cron no_agent (abaixo),
  não re-executar manualmente.

## Monitor mode (cron no_agent — padrão foz/bps)

Wrapper de exemplo (`~/.hermes/scripts/melhor-preco-monitor.sh`, `chmod +x`):

```bash
#!/usr/bin/env bash
SKILL_DIR="$HOME/.hermes/skills/travel/melhor-preco-passagens"
mkdir -p "$HOME/.hermes/state"
exec node "$SKILL_DIR/scripts/search.mjs" \
  --origin GYN --destination IGU \
  --departure 09/10/2026 --return 12/10/2026 \
  --state-file "$HOME/.hermes/state/mpp-GYN-IGU.json"
```

Agendar (stdout vazio = cron não entrega nada; só alerta quando mudou):

```text
cronjob action=create no_agent=true script=melhor-preco-monitor.sh schedule="0 20 * * *"
```

## Exit codes

| Código | Significado |
|---|---|
| 0 | ok (datas validadas + ranking/JSON; watchdog: pode ter stdout vazio = sem mudança) |
| 1 | argumentos inválidos (faltando/forma errada, data no passado, viagem > 16 dias, aeroporto não resolvido) |
| 2 | bloqueio/rede (captcha/challenge → aborta no 1º sinal, com screenshot em `.cache/debug/`) |
| 3 | datas não validadas na resposta OU nenhum resultado/card parseável — NUNCA reportar preço |

## Rules

- **Volume baixo**: 1 busca por execução; nunca rodar em rajada nem re-executar em loop
  para "tentar de novo" — cooldown ≥ 30s é embutido; monitorar = cron diário, não chamadas manuais.
- **Validar datas**: só reportar preço com exit 0 (datas conferidas na tela antes do parse).
- **Confirmar antes de comprar**: Google Flights é agregador — preço pode defasar do site
  da companhia. Sempre avisar e conferir no site da Azul/LATAM/GOL antes de comprar.
- **ToS/risco**: scraping de agregador com volume baixo pode violar ToS; captcha/challenge
  → abortar (exit 2) e **nunca** contornar nem insistir; reportar o bloqueio ao usuário.
- Escopo: doméstico BR, econômica, cash, Azul/LATAM/GOL apenas (VoePass e outras ignoradas).
- Não rodar com `--json` + `--state-file` juntos (JSON vence).
