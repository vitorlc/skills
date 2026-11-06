# Relatório completo

Usar `SKILL_DIR` e `RUN_DIR` preparados no `SKILL.md`, após coleta bem-sucedida.
Os comandos relacionados devem executar no mesmo shell. A ordem importa: o diff é calculado
com `--no-record`, rentabilidade e rebalanceamento leem o histórico ainda intacto, e só no
fim a coleta atual é registrada. Assim, inverter a ordem não contamina a baseline.

```bash
S="$SKILL_DIR/scripts"; I="$RUN_DIR/investments.json"
python3 "$S/summary.py" "$I" || exit 1
EXTRA=()
if python3 "$S/snapshot_diff.py" "$I" "$RUN_DIR/diff.json" --no-record; then
  EXTRA+=(--diff "$RUN_DIR/diff.json")
else
  echo 'Sem evolução: o diff falhou.'
fi
python3 "$S/performance.py" "$I" --since 30d --json "$RUN_DIR/performance.json" >/dev/null \
  && EXTRA+=(--performance "$RUN_DIR/performance.json") || echo 'Sem rentabilidade no período.'
python3 "$S/rebalance.py" "$I" --json "$RUN_DIR/rebalance.json" >/dev/null \
  && EXTRA+=(--rebalance "$RUN_DIR/rebalance.json") || echo 'Sem rebalanceamento.'
python3 "$S/snapshot_diff.py" "$I" --record-only \
  || echo 'Não foi possível registrar a observação no histórico.'
python3 "$S/generate_report.py" "$I" relatorio.html "${EXTRA[@]}"
```

Para incluir CDI/IPCA, acrescentar `--benchmarks` ao `performance.py` (consulta a API
pública do Banco Central). Para simular um aporte, `--aporte VALOR` no `rebalance.py`.
Detalhes e como responder: [analyze](analyze.md).

A tabela de ativos agrupa lotes do mesmo ativo (mesmo nome, emissor, instituição e taxa) em uma
linha expansível e oculta posições resgatadas (`TOTAL_WITHDRAWAL` com saldo zero); totais e
gráficos usam todos os ativos coletados. Custo ou rendimento ausente em parte dos lotes aparece
como "(parcial)", nunca como zero.

Informar o caminho completo do HTML após sucesso. Abrir no navegador se solicitado
ou se fizer parte do pedido; usar a ferramenta de abertura disponível no host.
Chart.js é carregado de CDN, então os gráficos precisam de rede.

O botão de remover histórico **oculta** o snapshot naquele navegador; não exclui
arquivos locais. Metas editadas são baixadas como JSON e precisam ser movidas para
`allocation_targets.json` no diretório de dados (`$SKILL_DIR/tmp/` por padrão). Para PDF,
usar a impressão do navegador.

Sucesso: resumo e HTML correspondem à mesma coleta; a ausência de diff, rentabilidade ou
rebalanceamento é informada; não apresentar erro como carteira vazia nem custo
desconhecido como zero.
