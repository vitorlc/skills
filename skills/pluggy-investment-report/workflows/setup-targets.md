<required_reading>
- `SKILL.md` (prerequisites, Step 0)
</required_reading>

<context>
O usuário quer **configurar ou atualizar as metas de alocação** por categoria de investimento.
</context>

<process>
### Verificar se skill está instalada

```bash
SKILL_DIR=""; for d in "$HOME/.claude/skills/pluggy-investment-report" "$HOME/.config/opencode/skills/pluggy-investment-report" "$HOME/.agents/skills/pluggy-investment-report"; do [ -d "$d/scripts" ] && { SKILL_DIR="$d"; break; }; done && echo "✓ $SKILL_DIR" || { echo "✗ Not installed — run: npx @vitorlc/skills pluggy-investment-report"; exit 1; }
```

### Gerar relatório uma vez (steps 1-4 do SKILL.md + step 7 de full-report)

Executar autenticação, buscar dados, normalizar e gerar o HTML para ter a interface de configuração.

### Abrir relatório no navegador e configurar

```bash
open relatorio.html        # macOS
xdg-open relatorio.html    # Linux
start relatorio.html       # Windows
```

Dizer ao usuário:
1. No relatório aberto, clicar em **"Configurar metas"**
2. Preencher os percentuais desejados (devem somar 100%)
3. Clicar em **⬇ Salvar metas**
4. Mover o arquivo baixado para `$SKILL_DIR/tmp/allocation_targets.json`

```bash
# Exemplo: após o download, o usuário deve mover o arquivo
# mv ~/Downloads/allocation_targets.json "$SKILL_DIR/tmp/allocation_targets.json"
```

### Verificar

```bash
[ -f "$SKILL_DIR/tmp/allocation_targets.json" ] \
  && echo "✓ Metas salvas em $SKILL_DIR/tmp/allocation_targets.json" \
  || echo "✗ Arquivo de metas não encontrado"
```

**Formato esperado** do arquivo (exemplo):

```json
{
  "Renda Fixa": 70,
  "ETF": 15,
  "Fundos": 5,
  "Ações": 10
}
```
</process>

<success_criteria>
- `$SKILL_DIR/tmp/allocation_targets.json` existe e tem JSON válido
- Percentuais somam 100
- Próximo relatório (quick ou full) incluirá a seção de análise de alocação
</success_criteria>