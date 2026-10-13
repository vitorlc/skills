# Relatório completo

Usar `SKILL_DIR` e `RUN_DIR` preparados no `SKILL.md`, após coleta bem-sucedida.
Os comandos relacionados devem executar no mesmo shell.

```bash
python3 "$SKILL_DIR/scripts/summary.py" "$RUN_DIR/investments.json" || exit 1
if python3 "$SKILL_DIR/scripts/snapshot_diff.py" "$RUN_DIR/investments.json" "$RUN_DIR/diff.json"; then
  python3 "$SKILL_DIR/scripts/generate_report.py" "$RUN_DIR/investments.json" relatorio.html --diff "$RUN_DIR/diff.json"
else
  echo 'Sem evolução: o diff falhou.'
  python3 "$SKILL_DIR/scripts/generate_report.py" "$RUN_DIR/investments.json" relatorio.html
fi
```

Informar o caminho completo do HTML após sucesso. Abrir no navegador se solicitado
ou se fizer parte do pedido; usar a ferramenta de abertura disponível no host.
Chart.js é carregado de CDN, então os gráficos precisam de rede.

O botão de remover histórico **oculta** o snapshot naquele navegador; não exclui
arquivos locais. Metas editadas são baixadas como JSON e precisam ser movidas para
`$SKILL_DIR/tmp/allocation_targets.json`. Para PDF, usar a impressão do navegador.

Sucesso: resumo e HTML correspondem à mesma coleta; a ausência de diff é informada;
não apresentar erro como carteira vazia nem custo desconhecido como zero.
