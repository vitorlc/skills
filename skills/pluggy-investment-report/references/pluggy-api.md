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
- `GET /investments/{id}/transactions?page=...&pageSize=500` (somente com
  `--with-transactions`): `{results, totalPages}`. Falha ou item malformado marca as
  transações daquele investimento como desconhecidas (`null`) e emite aviso em stderr;
  não aborta a coleta. Confirmar o contrato na documentação da Pluggy antes de depender dele.

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
| `subtype` | Subtipo original (CDB, LCI, LCA, TREASURY...) ou `null` |
| `rate_type`, `rate`, `fixed_annual_rate` | Indexador (CDI, IPCA, SELIC...), percentual do indexador e taxa fixa anual |
| `issuer`, `issue_date` | Emissor e data de emissão |
| `quantity`, `as_of`, `status` | Quantidade, data de referência do valor (`date`) e status |
| `last_twelve_months_rate` | Taxa informada pela Pluggy (fundos); não substitui a taxa calculada |
| `transactions` | Só com `--with-transactions`: lista `{date, type, amount}` ou `null` (desconhecido) |

`institution` usa o nome da instituição do próprio investimento quando existe (por
exemplo B3/CEI); caso contrário, o connector da conexão. Campos informativos novos nunca
abortam a coleta: valores inválidos viram `null`. Snapshots guardam tudo, exceto `transactions`.

`amount` da API é valor bruto atual, não custo original. `lastTwelveMonthsRate`
representa outro período e não substitui a taxa calculada acima. Apenas BRL é aceito;
moeda ausente segue o contexto BRL da skill, sem conversão implícita.

Os leitores também aceitam `{investments: [...]}` para arquivos locais existentes.
Validam estrutura, campos textuais e números finitos. Todos os registros recebidos,
inclusive valores zero e negativos, participam do resumo, HTML e snapshots.
Tipos desconhecidos são agrupados em Outros. Se algum custo/rendimento é desconhecido,
o total correspondente fica `null` (exibido como “não informado”).

## Arquivos e erros

- `collect_investments.py OUTPUT [--item-id ID ...] [--with-transactions]`: `0` sucesso,
  `1` configuração, dados ou arquivo, `2` API/rede. stdout informa quantidade e caminho,
  nunca o token.
- `summary.py INPUT [--json]`: Markdown (ou JSON estruturado) em stdout; `0` sucesso,
  `1` arquivo/dados inválidos. Com custo parcial, mostra o rendimento dos ativos com custo
  informado e a cobertura; os totais gerais continuam “não informado”.
- `generate_report.py INPUT [OUTPUT] [--diff DIFF] [--performance JSON] [--rebalance JSON]`:
  HTML privado; `0` sucesso, `1` arquivo/dados inválidos. Seções opcionais ilegíveis são
  omitidas com aviso.
- `snapshot_diff.py INPUT OUTPUT [--since SPEC] [--no-record]` ou
  `snapshot_diff.py INPUT --record-only`: diff privado + snapshot; `0` sucesso,
  `1` arquivo/dados inválidos, `2` argumentos inválidos.
- `performance.py INPUT [--since SPEC] [--benchmarks] [--json OUT]`: somente leitura.
- `rebalance.py INPUT [--aporte V] [--allow-sell] [--tolerance PP] [--max-issuer-pct P]
  [--max-asset-pct P] [--json OUT]`: `0` sucesso, `1` dados inválidos, `2` argumentos.

## Histórico

Snapshot: `timestamp` com fuso, `as_of` (maior data de referência dos ativos), `totals` e
`investments`. Snapshots antigos sem fuso são lidos como horário local.
Retenção: tudo dos últimos 7 dias, o último de cada dia até 90 dias e o último de cada mês
depois. Arquivos com nome fora do padrão nunca são apagados. Gravações e leituras usam
trava de arquivo (POSIX). `--since`: `prev` (padrão), `<N>d`, `<N>m`, `ytd`, `AAAA-MM-DD`;
usa o snapshot mais recente até a data e, se o histórico for mais curto, o mais antigo,
registrando `baseline_note`.
Local: `tmp/` da instalação ou `PLUGGY_REPORT_DATA_DIR` (cópia única de `tmp/` na primeira
utilização; nunca move).

O diff contém `first_run`, timestamps, `since`, `baseline_note`, `totals` (`prev`, `curr`,
`delta`) e `assets` (`changed`, `new`, `removed`). `current_timestamp` do diff é idêntico ao
do snapshot gravado na execução, o que permite ao HTML omiti-lo do painel de anteriores.
Delta entre métricas desconhecidas é `null`.
Snapshots anteriores permanecem legíveis; métricas antigas de custo/rendimento podem
seguir o mapeamento anterior, portanto não representam uma série recalculada.
Metas inválidas interrompem o relatório, inclusive nome de categoria fora dos sete
rótulos. Categorias da carteira omitidas nas metas entram na análise com alvo zero;
desvios de pelo menos 2 pontos geram sugestões. Nome repetido sem id estável não é
pareado: entra como saiu e entrou, sem delta inventado.

## Rentabilidade (`performance.py`)

Método de Dietz modificado por ativo comparável (presente nos dois instantes):
`(V1 − V0 − F) / (V0 + Σ F·peso)`, com peso = fração do período restante após o fluxo.
Fluxos por ativo: transações do período (BUY +, SELL e AMORTIZATION −; INTEREST e TAX
contam como rendimento); sem transações, variação do custo original (momento desconhecido,
peso 0,5); sem custo, nenhum fluxo (toda a variação vira rendimento). A fonte de cada
ativo é contada em `flow_sources`. Ativos novos ou removidos ficam fora da taxa e são
listados em `new`/`removed`; `wallet_change` reconcilia a variação do patrimônio.
Anualização só com 30 dias ou mais.

Benchmarks (`--benchmarks`, API pública do Banco Central, sem credenciais): CDI série 12
(composto pelos dias do período) e IPCA série 433 (somente meses cheios dentro do período).
Cache de 12 h em `<dados>/cache/`; falhas viram notas e não interrompem a análise.

## Rebalanceamento (`rebalance.py`)

Por categoria de relatório. Padrão: só aporte, distribuído proporcionalmente à necessidade
até as metas (sobra pelo peso das metas). `--allow-sell` vende categorias fora da banda de
tolerância e compra o que o caixa permite. `min_aporte_no_sell` é o menor aporte que atinge
todas as metas só com compras. Alertas: limite FGC de R$ 250 mil por **emissor** (campo
`issuer`, subtipos CDB/LCI/LCA/LC/LF/LIG/RDB; sem agrupar conglomerados), concentração por
emissor e por ativo (Tesouro excluído), vencimentos vencidos/30/90 dias e distribuição da
renda fixa por indexador.
