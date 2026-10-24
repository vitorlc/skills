# Analisar desempenho e sugerir movimentações

Usar `SKILL_DIR` e `RUN_DIR` do `SKILL.md`. Coletar antes; se o usuário quiser rentabilidade
precisa (separando aportes e resgates), coletar com `--with-transactions`.
Executar tudo no mesmo shell e **nesta ordem** (a rentabilidade lê o histórico antes de a
coleta atual ser registrada).

```bash
S="$SKILL_DIR/scripts"; I="$RUN_DIR/investments.json"
python3 "$S/summary.py" "$I" --json > "$RUN_DIR/summary.json"
python3 "$S/performance.py" "$I" --since 30d --benchmarks --json "$RUN_DIR/performance.json"
python3 "$S/rebalance.py" "$I" --aporte VALOR --json "$RUN_DIR/rebalance.json"
python3 "$S/snapshot_diff.py" "$I" --record-only
```

Ajustes conforme o pedido:

- Período: `--since 30d | 90d | 12m | ytd | AAAA-MM-DD` (padrão 30d). Se o histórico for
  mais curto, o script usa o ponto mais antigo e avisa; repassar o aviso.
- Benchmarks: `--benchmarks` consulta a API pública do Banco Central (CDI e IPCA, sem
  credenciais, cache de 12 h). Omitir se o usuário não quiser chamadas externas.
- Aporte: perguntar o valor apenas se o usuário falou em aportar. Sem `--aporte`, o plano
  mostra o aporte mínimo para atingir as metas sem vender.
- Vendas: usar `--allow-sell` somente se o usuário pedir explicitamente.
- Limites de alerta: `--tolerance`, `--max-issuer-pct`, `--max-asset-pct`.
- Sem metas configuradas, o plano é omitido e os alertas continuam; oferecer
  [setup-targets](setup-targets.md).
- Sem histórico anterior, a rentabilidade do período não existe: informar, mostrar apenas
  o resultado desde o início e que as próximas execuções formarão o histórico.

## Como responder

Ler os JSON, não recalcular. Estrutura sugerida:

1. **Panorama**: patrimônio, rentabilidade no período, anualizada e % do CDI quando houver.
   Dizer de onde veio a variação (rendimento × aportes × ativos novos/removidos).
2. **Destaques**: categorias e ativos que mais ajudaram ou atrapalharam.
3. **Rebalanceamento**: onde colocar o aporte (R$ por classe) e o desvio das metas.
4. **Alertas**: FGC (limite por emissor, não por corretora), concentração, vencimentos
   em 30 dias com sugestão de reinvestimento.
5. **Ressalvas**: usar a lista `caveats` (custo desconhecido, aportes estimados, período
   curto) e o aviso de que não é recomendação de investimento.

Limites: valores da Pluggy são líquidos de impostos provisionados enquanto o CDI é bruto;
a checagem do FGC não agrupa conglomerados; ativos novos ou removidos ficam fora da
rentabilidade do período.
