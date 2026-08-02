<required_reading>
- `references/pluggy-api.md` (field mapping, pagination)
</required_reading>

<context>
O usuário quer o **relatório completo**: sumário Markdown + HTML com gráficos e diff histórico. Os Steps 0-4 já foram executados.
</context>

<process>
### Step 5 — Calcular diff histórico

Compara o portfólio atual com o snapshot anterior. Na primeira execução cria a linha de base; nas seguintes computa o que mudou.

```bash
if python3 "$SKILL_DIR/scripts/snapshot_diff.py" \
     /tmp/pluggy_investments.json \
     /tmp/pluggy_diff.json; then
  chmod 600 /tmp/pluggy_diff.json
  DIFF_FLAG="--diff /tmp/pluggy_diff.json"
  echo "✓ Diff computed"
else
  DIFF_FLAG=""
  echo "⚠ snapshot_diff failed — report will have no evolution data"
fi
```

### Step 6 — Exibir sumário Markdown no terminal

Formato exato:

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

**Mapeamento de tipos:** `FIXED_INCOME` → Renda Fixa, `EQUITY`/`STOCK` → Ações, `FUND`/`MUTUAL_FUND` → Fundos, `ETF` → ETF, `TREASURY` → Tesouro Direto, `REAL_ESTATE` → FIIs, demais → Outros.

**Análise de alocação** (se `$SKILL_DIR/tmp/allocation_targets.json` existir): aplicar mesma lógica do quick-report.

### Step 7 — Gerar relatório HTML

```bash
python3 "$SKILL_DIR/scripts/generate_report.py" \
  /tmp/pluggy_investments.json \
  relatorio.html \
  $DIFF_FLAG \
&& echo "Relatório salvo em: $(pwd)/relatorio.html"
```

Informar o caminho completo ao usuário.

### Step 8 — Abrir no navegador

```bash
open relatorio.html        # macOS
xdg-open relatorio.html    # Linux
start relatorio.html       # Windows
```
</process>

<success_criteria>
- Sumário Markdown exibido no terminal
- Relatório HTML gerado em `relatorio.html` no diretório atual
- Relatório aberto no navegador
- Dados de evolução incluídos (se diff disponível)
- Análise de alocação incluída (se metas existirem)
</success_criteria>