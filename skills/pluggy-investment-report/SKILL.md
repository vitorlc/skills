---
name: pluggy-investment-report
description: Gera relatório consolidado de investimentos de contas Pluggy. Use para "relatório de investimentos", "ver carteira", "meus rendimentos", "dashboard financeiro".
---

<essential_principles>
- Gera relatório a partir de contas conectadas via Pluggy
- **Nunca exiba credenciais** no chat ou terminal
- Dados sensíveis salvos em `/tmp` com `chmod 600`
- Scripts e referências em `$SKILL_DIR/` (descoberto no Step 0)
</essential_principles>

<prerequisites>
<first_time_setup>
1. Acessar https://pluggy.ai → **Sign Up** (conta sandbox gratuita)
2. No dashboard: **Apps** → **New App** → copiar **Client ID** e **Client Secret**
3. Para conta de teste em sandbox: conector `201` (Nubank sandbox)
</first_time_setup>

<credentials>
Exportar antes de executar — **nunca peça para o usuário colar valores no chat**:

```bash
export PLUGGY_CLIENT_ID="seu-client-id"
export PLUGGY_CLIENT_SECRET="seu-client-secret"
```

Verificar sem revelar valores:

```bash
[ -n "$PLUGGY_CLIENT_ID" ]     && echo "✓ PLUGGY_CLIENT_ID set"     || echo "✗ PLUGGY_CLIENT_ID missing"
[ -n "$PLUGGY_CLIENT_SECRET" ] && echo "✓ PLUGGY_CLIENT_SECRET set" || echo "✗ PLUGGY_CLIENT_SECRET missing"
```
</credentials>

<sandbox>
Se o usuário pedir demo/teste (ou passar `--sandbox`), seguir o setup em `references/pluggy-api.md` seção 5. Conector `201` para dados de teste.
</sandbox>
</prerequisites>

<intake>
Pergunte ao usuário: **"O que você quer fazer?"**

1. **Resumo rápido** — Apenas sumário Markdown no terminal (steps 1-6)
2. **Relatório completo** — Sumário + HTML com gráficos e diff histórico (steps 1-8)
3. **Configurar metas de alocação** — Definir ou atualizar percentuais alvo por categoria
</intake>

<routing>
- Resposta **1** → `workflows/quick-report.md`
- Resposta **2** → `workflows/full-report.md`
- Resposta **3** → `workflows/setup-targets.md`
</routing>

<shared_process>
Leia `references/pluggy-api.md` antes de prosseguir para documentação completa dos endpoints.

### Step 0 — Localizar diretório da skill

```bash
SKILL_DIR=""; for d in "$HOME/.claude/skills/pluggy-investment-report" "$HOME/.config/opencode/skills/pluggy-investment-report" "$HOME/.agents/skills/pluggy-investment-report"; do [ -d "$d/scripts" ] && { SKILL_DIR="$d"; break; }; done && echo "✓ $SKILL_DIR" || { echo "✗ Not installed — run: npx @vitorlc/skills pluggy-investment-report"; exit 1; }
```

### Step 1 — Autenticar

Usar env vars diretamente — **nunca substituir valores literais no comando**:

```bash
export PLUGGY_API_KEY=$(curl -s -X POST https://api.pluggy.ai/auth \
  -H "Content-Type: application/json" \
  -d "{\"clientId\":\"${PLUGGY_CLIENT_ID}\",\"clientSecret\":\"${PLUGGY_CLIENT_SECRET}\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('apiKey',''))")

[ -n "$PLUGGY_API_KEY" ] \
  && echo "✓ Authenticated successfully" \
  || echo "✗ Authentication failed — check your credentials in the Pluggy dashboard"
```

A API key vive em `$PLUGGY_API_KEY` — não exibir nem copiar para o chat.

### Step 2 — Buscar todos os itens conectados

```bash
curl -s https://api.pluggy.ai/items \
  -H "X-API-KEY: ${PLUGGY_API_KEY}"
```

Extrair todos `results[].id` e mapear `id → connector.name` para lookup de instituição.

**Paginação:** comparar `total` vs `results.length`. Se `total > results.length`, buscar páginas adicionais (`?page=2`, `?page=3`, …).

### Step 3 — Buscar investimentos por item

Para cada `itemId`:

```bash
curl -s "https://api.pluggy.ai/investments?itemId=ITEM_ID_HERE" \
  -H "X-API-KEY: ${PLUGGY_API_KEY}"
```

Consolidar todos os `results` em uma lista. Carregar o nome da instituição do mapa de itens.

**Paginação:** mesma lógica do Step 2.

### Step 4 — Normalizar para o modelo do relatório

Converter cada investimento para:

```json
{
  "id": "<results[].id>",
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

Escrever para `/tmp/pluggy_investments.json` e restringir permissões:

```bash
chmod 600 /tmp/pluggy_investments.json
```

Após o Step 4, seguir para o workflow selecionado no routing acima.
</shared_process>

<error_handling>
| Erro | Ação |
|---|---|
| `POST /auth` retorna 403 | "Credenciais inválidas. Verifique Client ID e Client Secret no dashboard Pluggy." |
| `GET /items` retorna lista vazia | "Nenhuma conta conectada. Conecte pelo menos uma conta no dashboard pluggy.ai." |
| Nenhum investimento em qualquer item | Mostrar sumário com zeros, gerar HTML com mensagem de estado vazio |
| `python` não encontrado | "Python 3 não encontrado. Instale Python 3.8+ ou tente com `python3`." — tentar com `python3` |
| `generate_report.py` falha | Mostrar erro do Python, verificar formato JSON de `/tmp/pluggy_investments.json` |
| `snapshot_diff.py` falha | Logar erro, setar `DIFF_FLAG=""` e continuar — colunas de delta mostram "—" |
</error_handling>

<pdf_export>
Informe o usuário:
> "Para salvar como PDF: no navegador, pressione **Ctrl+P** (ou Cmd+P no Mac) → **Save as PDF**. O layout já está formatado para A4."
</pdf_export>