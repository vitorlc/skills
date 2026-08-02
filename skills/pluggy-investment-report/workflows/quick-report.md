<required_reading>
- `references/pluggy-api.md` (field mapping, pagination)
</required_reading>

<context>
O usuário quer apenas um **resumo rápido no terminal**, sem gerar HTML. Os Steps 0-4 já foram executados (autenticação, busca e normalização dos dados).
</context>

<process>
### Step 5 — Calcular diff histórico (opcional)

Se existir snapshot anterior, computa a evolução. Na primeira execução cria a linha de base.

```bash
if python3 "$SKILL_DIR/scripts/snapshot_diff.py" \
     /tmp/pluggy_investments.json \
     /tmp/pluggy_diff.json; then
  chmod 600 /tmp/pluggy_diff.json
  echo "✓ Diff computed"
else
  echo "⚠ Sem snapshot anterior — relatório sem evolução"
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

### Análise de alocação (se metas existirem)

Se `$SKILL_DIR/tmp/allocation_targets.json` existir, ler e apendar seção de análise. Desvio = `actual% - target%`. Recomendação só quando `|desvio| >= 2%`. Desbalanceamento = categoria com maior desvio absoluto.

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
</process>

<success_criteria>
- Sumário Markdown exibido no terminal com totais corretos
- Análise de alocação incluída se metas existirem
- Nenhum arquivo HTML gerado
</success_criteria>