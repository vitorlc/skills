---
name: pluggy-investment-report
description: Resume e analisa a carteira de investimentos conectada à Pluggy - rentabilidade no período (vs CDI/IPCA), evolução histórica, rebalanceamento por aporte e alertas de FGC, concentração e vencimentos - e gera relatório HTML. Use para consultar a carteira, rendimentos, metas ou sugestões de movimentação.
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
- HTML com gráficos, histórico, rentabilidade e rebalanceamento: [full-report](workflows/full-report.md).
- Analisar desempenho e sugerir movimentações (rentabilidade, CDI, aporte, alertas): [analyze](workflows/analyze.md).
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

Para medir rentabilidade separando aportes e resgates, acrescentar `--with-transactions`
(uma requisição extra por investimento; falhas viram "desconhecido" e não abortam a coleta).
Sem esse flag, os aportes são estimados pela variação do custo original.

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

- Usar `summary.py` para o Markdown (`--json` para dados estruturados); não recalcular
  os totais pelo agente. `performance.py` e `rebalance.py` também aceitam `--json`.
- `generate_report.py`, `snapshot_diff.py`, `performance.py` e `rebalance.py` consomem a
  mesma lista normalizada.
- Custo/rendimento ausente é **não informado**, nunca inferido como zero. O resumo mostra
  também o rendimento parcial dos ativos com custo informado, com a cobertura.
- Histórico em `tmp/snapshots/` (ou `$PLUGGY_REPORT_DATA_DIR/snapshots`; metas em
  `allocation_targets.json` no mesmo diretório). Retenção: tudo dos últimos 7 dias, um por
  dia até 90 dias e um por mês depois. Ao definir `PLUGGY_REPORT_DATA_DIR`, o conteúdo de
  `tmp/` é copiado uma única vez (nunca movido), permitindo um histórico compartilhado
  entre hosts.
- Intermediários, snapshots e HTML são escritos atomicamente com modo `600`.
  O diretório de cada execução criado acima tem modo `700`.
- O histórico é protegido por trava de arquivo contra execuções simultâneas. Cópias
  independentes de hosts têm históricos independentes, salvo com `PLUGGY_REPORT_DATA_DIR`.
- Atualizações preservam `tmp/`; desinstalação remove os dados daquele destino.
- Ordem importa: `performance.py` lê o histórico e deve rodar **antes** de
  `snapshot_diff.py` registrar a coleta atual.

Erros do coletor: `1` configuração/dados/arquivo, `2` API/rede. O diff, a rentabilidade e
o rebalanceamento são opcionais: se falharem, continuar com o relatório atual sem essas
seções e informar a ausência. Metas inválidas devem ser corrigidas; não descartá-las
silenciosamente.

## Salvaguardas das sugestões

- Sugerir por **classe de ativo**; nunca recomendar um título ou ativo específico.
- Por padrão, só indicar para onde vai dinheiro novo (sem vender). Sugerir vendas apenas
  se o usuário pedir, lembrando IR, IOF, come-cotas e liquidez.
- Não inventar CDI, IPCA ou preços: usar só números retornados pelos scripts e dizer
  quando o benchmark estiver indisponível.
- Concluir com o aviso de que não é recomendação de investimento.
