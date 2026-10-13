---
name: pluggy-investment-report
description: Gera resumo e relatório HTML da carteira de investimentos conectada à Pluggy, com histórico e metas de alocação. Use para consultar a própria carteira, rendimentos ou configurar suas metas.
---

# Relatório de investimentos Pluggy

Python 3.10+, acesso a `api.pluggy.ai` e credenciais exportadas no ambiente:
`PLUGGY_CLIENT_ID` e `PLUGGY_CLIENT_SECRET`. Nunca pedir valores no chat nem imprimir
credenciais. A autenticação ocorre dentro do coletor, sem tokens em argumentos.
Para criar uma conexão, usar o dashboard/Pluggy Connect; esta skill consulta conexões
existentes. Para demo, usar uma conexão sandbox já configurada.

## Escolher o resultado

Inferir o modo do pedido; perguntar apenas se estiver ambíguo:

- Resumo no terminal: [quick-report](workflows/quick-report.md).
- HTML com gráficos e histórico: [full-report](workflows/full-report.md).
- Configurar metas: [setup-targets](workflows/setup-targets.md).

## Localizar a instalação

```bash
SKILL_DIR=""
for d in "$HOME/.claude/skills/pluggy-investment-report" "$HOME/.config/opencode/skills/pluggy-investment-report" "$HOME/.agents/skills/pluggy-investment-report"; do
  if [ -f "$d/scripts/collect_investments.py" ]; then SKILL_DIR="$d"; break; fi
done
[ -n "$SKILL_DIR" ] || { echo 'Instale: npx @vitorlc/skills pluggy-investment-report'; exit 1; }
```

Se estiver trabalhando diretamente no repositório, usar a pasta desta skill.
Manter `SKILL_DIR` e `RUN_DIR` no mesmo shell ou passar seus caminhos explicitamente
nas chamadas seguintes; variáveis não são automaticamente compartilhadas pelo host.

## Coletar uma carteira completa

```bash
RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pluggy-report.XXXXXXXX")
python3 "$SKILL_DIR/scripts/collect_investments.py" "$RUN_DIR/investments.json"
```

A listagem `/v2/items` precisa estar habilitada pela Pluggy. Se retornar 403, usar
IDs de conexões já conhecidos, repetindo `--item-id ID` para cada conta desejada.
Não inventar IDs nem substituir uma carteira completa por uma única conexão sem
informar o escopo ao usuário. Ler [contrato Pluggy](references/pluggy-api.md) quando
for necessário resolver erros, paginação ou significado dos campos.

O coletor só escreve após concluir todas as páginas. Uma conexão fora do estado
`UPDATED`, página inconsistente ou moeda não BRL interrompe a coleta. Não gerar
relatório de uma coleta com erro. Uma conexão atualizada sem investimentos produz
lista vazia válida. Ausência de conexões é reportada como erro.

## Resultados e estado

- Usar `summary.py` para o Markdown; não recalcular os totais pelo agente.
- `generate_report.py` e `snapshot_diff.py` consomem a mesma lista normalizada.
- Custo/rendimento ausente é **não informado**, nunca inferido como zero.
- `tmp/snapshots/` mantém até 12 execuções; `tmp/allocation_targets.json` guarda metas.
- Intermediários, snapshots e HTML são escritos atomicamente com modo `600`.
  O diretório de cada execução criado acima tem modo `700`.
- Evitar duas execuções simultâneas para a mesma carteira: o histórico é compartilhado
  por instalação. Cópias independentes de hosts têm históricos independentes.
- Atualizações preservam `tmp/`; desinstalação remove os dados daquele destino.

Erros do coletor: `1` configuração/dados/arquivo, `2` API/rede. O diff é opcional:
se falhar, continuar com o relatório atual sem evolução e informar a ausência.
Metas inválidas devem ser corrigidas; não descartá-las silenciosamente.
