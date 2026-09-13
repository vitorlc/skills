# Contrato de coleta e relatório

Python 3.10+, somente biblioteca padrão. A execução HTTP usa timeout de 30 segundos,
sem repetição automática e sem seguir redirecionamentos. Erros não incluem corpos
HTTP, credenciais ou tokens. A saída só é substituída após coleta completa.

## Endpoints

- `POST /auth`: corpo `{clientId, clientSecret}` → `{apiKey}` mantida em memória.
- `GET /v2/items`: `{results, next}`; `next` é uma query pronta, anexada ao mesmo
  endpoint. Listagem opt-in. Alternativa: `--item-id ID`, consultando `GET /items/{id}`.
- `GET /investments?itemId=...&page=...&pageSize=500`: `{results, total}`. Percorrer
  até atingir `total`; páginas vazias prematuras, IDs repetidos e cursores repetidos
  são erros. Não publicar resultados parciais.

Fontes oficiais consultadas na revisão do contrato:
[items](https://docs.pluggy.ai/reference/items-list-by-cursor),
[formato de cursor](https://slack.pluggy.ai/en/reference/items/items-list-by-cursor),
[investimentos](https://docs.pluggy.ai/reference/investments-list) e
[campos](https://docs.pluggy.ai/docs/investments).

## Modelo normalizado

Lista de objetos com campos:

| Campo | Origem / significado |
|---|---|
| `id`, `name` | Identificador e nome do investimento |
| `institution` | Nome do connector da conexão |
| `type` | Tipo; subtipos TREASURY e REAL_ESTATE_FUND viram TREASURY e REAL_ESTATE |
| `value` | `balance`, saldo líquido atual, número finito obrigatório |
| `amount` | `amountOriginal`, custo original, ou `null` se ausente |
| `return_amount` | `amountProfit`, ou `balance - amountOriginal` se ambos conhecidos |
| `return_rate` | Rendimento / custo original × 100 quando calculável; senão `null` |
| `maturity_date` | `dueDate` ou `null` |

`amount` da API é valor bruto atual, não custo original. `lastTwelveMonthsRate`
representa outro período e não substitui a taxa calculada acima. Apenas BRL é aceito;
moeda ausente segue o contexto BRL da skill, sem conversão implícita.

Os leitores também aceitam `{investments: [...]}` para arquivos locais existentes.
Validam estrutura, campos textuais e números finitos. Todos os registros recebidos,
inclusive valores zero e negativos, participam do resumo, HTML e snapshots.
Tipos desconhecidos são agrupados em Outros. Se algum custo/rendimento é desconhecido,
o total correspondente fica `null` (exibido como “não informado”).

## Arquivos e erros

- `collect_investments.py OUTPUT [--item-id ID ...]`: `0` sucesso, `1` configuração,
  dados ou arquivo, `2` API/rede. stdout informa quantidade e caminho, nunca o token.
- `summary.py INPUT`: Markdown em stdout; `0` sucesso, `1` arquivo/dados inválidos.
- `generate_report.py INPUT [OUTPUT] [--diff DIFF]`: HTML privado; `0` sucesso,
  `1` arquivo/dados inválidos. Sem diff válido, não há deltas no relatório.
- `snapshot_diff.py INPUT OUTPUT`: diff privado + snapshot; `0` sucesso,
  `1` arquivo/dados inválidos, `2` argumentos incompletos.

O diff contém `first_run`, timestamps, `totals` (`prev`, `curr`, `delta`) e `assets`
(`changed`, `new`, `removed`). Delta entre métricas desconhecidas é `null`.
Snapshots anteriores permanecem legíveis; métricas antigas de custo/rendimento podem
seguir o mapeamento anterior, portanto não representam uma série recalculada.
Metas inválidas interrompem o relatório. Categorias da carteira omitidas nas metas
entram na análise com alvo zero; desvios de pelo menos 2 pontos geram sugestões.
