# Resumo rápido

Usar `SKILL_DIR` e `RUN_DIR` preparados no `SKILL.md`, após coleta bem-sucedida.

```bash
python3 "$SKILL_DIR/scripts/summary.py" "$RUN_DIR/investments.json" || exit 1
python3 "$SKILL_DIR/scripts/snapshot_diff.py" "$RUN_DIR/investments.json" --record-only \
  || echo 'Não foi possível registrar a observação no histórico.'
```

Apresentar o Markdown produzido. Inclui metas se `allocation_targets.json` existir e for
válido, e o rendimento parcial quando alguns ativos não informam custo. Não gera HTML.

O resumo também **registra a observação no histórico** (`--record-only`), para que o
histórico cresça mesmo sem relatórios completos; a retenção em camadas evita que muitas
execuções apaguem o passado. Se o usuário pedir para não registrar, omitir o segundo
comando. Para rentabilidade ou sugestões de movimentação, usar [analyze](analyze.md).
