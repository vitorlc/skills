# Resumo rápido

Usar `SKILL_DIR` e `RUN_DIR` preparados no `SKILL.md`, após coleta bem-sucedida.

```bash
python3 "$SKILL_DIR/scripts/summary.py" "$RUN_DIR/investments.json"
```

Apresentar o Markdown produzido. Inclui metas se `tmp/allocation_targets.json`
existir e for válido. Não gera HTML nem altera o histórico. Se o usuário também
pedir comparação histórica, executar `snapshot_diff.py` conforme o fluxo completo,
informando que isso registra uma nova observação da carteira.
