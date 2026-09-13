---
name: smiles-passagens
description: Consulta ida e volta em milhas Smiles, tarifa clube, com alternativas de datas no calendário GOL. Use para milhas Smiles e datas baratas em milhas; para preços em reais, use melhor-preco-passagens.
---

# Smiles — calendário em milhas

Consulta pontual, econômica, tarifa `SMILES_CLUB`. Não faz compra ou monitoramento.
Node.js ≥18 e rede para a API; sem credenciais obrigatórias. `CALENDAR_API_URL` é um
override opcional de endpoint. Não revelar hosts internos montados pelo cliente.

## Parâmetros

Coletar apenas o que faltar: origem, destino, ida e volta (`DD/MM/AAAA`). Se “preço de
passagem” estiver ambíguo entre reais e milhas, esclarecer antes de escolher a skill.
Aeroportos aceitam IATA/cidade/UF; ambiguidades retornam candidatos, sem escolher
silenciosamente. Adultos: inteiro 1–9, padrão 1. `--rate`: BRL por mil milhas,
positivo, padrão 15. Datas devem existir e a volta não pode anteceder a ida.

## Executar

```bash
SKILL_DIR=""
for d in "$HOME/.claude/skills/smiles-passagens" "$HOME/.config/opencode/skills/smiles-passagens" "$HOME/.agents/skills/smiles-passagens"; do
  if [ -f "$d/scripts/search.mjs" ]; then SKILL_DIR="$d"; break; fi
done
[ -n "$SKILL_DIR" ] || { echo 'Instale: npx @vitorlc/skills smiles-passagens'; exit 1; }
node "$SKILL_DIR/scripts/search.mjs" --origin GYN --destination REC \
  --departure 15/12/2026 --return 22/12/2026 --adults 1
```

Substituir pelos parâmetros do pedido. No repositório, usar diretamente a pasta da
skill. Acrescentar `--json` para processamento estruturado.

## Interpretar

- Exit `0`: calendário consultado. Milhas `null` num trecho significa indisponível
  naquela data; não transformar em zero nem inventar total.
- Exit `1`: entrada inválida; corrigir argumentos/ambiguidade antes de executar.
- Exit `2`: erro de API/rede ou calendário ausente. Informar a falha; não reportar preço.
- Alternativas são os **três menores preços distintos**, com todos os dias associados.
- BRL é estimativa por milhas, não cotação cash nem confirmação de taxas de embarque.
- Há timeout HTTP de 30 segundos e nenhuma repetição automática.
- Sem persistência de consultas; a base de aeroportos fica em memória durante o processo.

Ler [search-guide](references/search-guide.md) para o formato JSON, resolução de
aeroportos e limites da base local.
