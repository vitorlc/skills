---
name: melhor-preco-passagens
description: Compara preços em reais de ida e volta doméstica entre Azul, LATAM e GOL no Google Flights, com opção de monitoramento. Use para cotação cash; para milhas Smiles, use smiles-passagens.
---

# Passagens domésticas em reais

Busca única, econômica, ida e volta, somente adultos. Usa Google Flights como fonte;
não faz compra. Se a moeda do pedido estiver ambígua, esclarecer reais ou milhas.

## Preparação

Node.js ≥20, Playwright e Chromium. Não presumir dependências ou navegador instalados.

```bash
SKILL_DIR=""
for d in "$HOME/.hermes/skills/travel/melhor-preco-passagens" "$HOME/.hermes/skills/melhor-preco-passagens" "$HOME/.claude/skills/melhor-preco-passagens" "$HOME/.config/opencode/skills/melhor-preco-passagens" "$HOME/.agents/skills/melhor-preco-passagens"; do
  if [ -f "$d/scripts/search.mjs" ]; then SKILL_DIR="$d"; break; fi
done
[ -n "$SKILL_DIR" ] || { echo 'Instale: npx @vitorlc/skills melhor-preco-passagens'; exit 1; }
```

No repositório, usar diretamente a pasta desta skill. Se faltarem dependências,
executar `npm ci --no-audit --no-fund` em `$SKILL_DIR/scripts`; se faltar o navegador,
executar `npx playwright install chromium` no mesmo diretório. Chromium utiliza seu
sandbox; falha de inicialização deve ser resolvida no ambiente, não desabilitando-o.

## Parâmetros e execução

Origem/destino: IATA doméstico conhecido, cidade ou UF da tabela local. Para cidades
com vários aeroportos, respeitar IATA explícito; se apenas cidade/UF foi pedida, o
script pode selecionar um dos aeroportos mapeados e retorna o código selecionado.
Texto fora da tabela deve ser esclarecido, sem aceitar a primeira sugestão do Google.

Datas: `DD/MM/AAAA` ou ISO. Ida não pode estar no passado, volta não pode antecedê-la.
Esta implementação limita a viagem a 16 dias; isso não é uma regra do Google Flights.
Adultos: inteiro 1–9, padrão 1. Perguntar apenas pelos campos ausentes.

```bash
node "$SKILL_DIR/scripts/search.mjs" --origin GYN --destination IGU \
  --departure 09/10/2026 --return 12/10/2026 --adults 1
```

Substituir os exemplos pelos parâmetros solicitados. `--json` produz dados estruturados;
`--debug` grava os cards coletados. Ler [contratos](references/contracts.md) para
schemas, critérios de sucesso e estado do monitor.

## Apresentação e falhas

- Só apresentar preço com exit `0`. Sucesso requer seleção do aeroporto esperado,
  confirmação de passageiros, ida e volta/econômica e datas exibidas.
- Apresentar a rota selecionada, adultos e horário da consulta. Destacar o menor
  valor observado e informar que deve ser confirmado antes de comprar.
- Ausência de resultado de uma companhia não prova ausência de voos. Usar
  “nenhum resultado encontrado nesta consulta”.
- Exit `1`: argumentos/preparação/arquivo; `2`: rede ou captcha detectado;
  `3`: página ou resultados não verificados. Não reaproveitar preços após erro.
- Captcha/challenge: abortar, informar bloqueio; não contornar nem repetir em loop.
- Uma busca por execução, com cooldown de 30 segundos. Não executar em rajada.

## Monitoramento solicitado pelo usuário

Usar `--state-file /caminho/estado.json`. Primeira execução ou mudança de rota,
passageiros, companhia vencedora ou preço imprime Markdown; sem mudança, stdout vazio.
Alerta em qualquer mudança, inclusive aumento. Se o pedido for “apenas quando cair”,
explicar que essa condição exige um filtro adicional no agendador.

Usar o agendador disponível no host, com periodicidade diária por padrão e um arquivo
por consulta. Hermes pode usar seu `cronjob no_agent`; o instalador deste repositório
não instala no Hermes nem fornece agendador. Não combinar execuções simultâneas que
compartilhem `.cache/gf-profile` ou o arquivo de estado.

`--json` tem precedência e não atualiza o arquivo de monitor. `.cache/` guarda perfil,
cooldown e diagnósticos; atualizações preservam esse estado. Apagar o cache reinicia a
sessão. Desinstalar remove os dados dentro da pasta da skill; estado externo permanece.
