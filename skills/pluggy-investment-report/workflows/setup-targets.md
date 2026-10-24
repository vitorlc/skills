# Configurar metas

Se o usuário já informou percentuais e categorias, validar a soma de 100% e salvar
com os helpers abaixo. Perguntar apenas pelos percentuais ausentes ou inconsistentes.
Para editar visualmente, gerar um relatório seguindo `full-report.md`, abrir o HTML,
expandir **Configurar** e baixar **Salvar metas**. Em ambos os casos, instalar o JSON
validado no caminho da skill; o navegador sozinho não grava nesse diretório.

```bash
python3 - "$SKILL_DIR" /caminho/allocation_targets.json <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / 'scripts'))
from report_model import validate_targets, private_json, data_dir
targets = validate_targets(json.loads(Path(sys.argv[2]).read_text()))
if not targets:
    raise ValueError('Informe metas que somem 100%')
private_json(data_dir() / 'allocation_targets.json', targets)
print('Metas salvas')
PY
```

Categorias do relatório: Renda Fixa, Ações, Fundos, ETF, Tesouro Direto, FIIs e Outros.
Qualquer outro nome, inclusive código da API (`FIXED_INCOME`), é erro.
Valores devem ser números entre 0 e 100 e somar 100 (tolerância de 0,05 ponto).
Exemplo: `{"Renda Fixa": 70, "ETF": 20, "Ações": 10}`.
Próximos resumos e relatórios usarão as metas. Categorias omitidas têm meta zero.
