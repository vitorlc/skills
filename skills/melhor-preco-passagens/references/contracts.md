# Contratos de busca e monitor

## JSON de sucesso (schema_version 1)

```json
{
  "schema_version": 1,
  "route": {"origin": "GYN", "destination": "IGU", "departure": "2026-10-09", "return": "2026-10-12"},
  "adults": 1,
  "cabin": "ECONOMY",
  "fetched_at": "2026-09-13T20:00:00-03:00",
  "currency": "BRL",
  "dates_validated": true,
  "airlines": {
    "AZUL": {"cheapest": null, "count": 0, "note": "nenhum resultado encontrado nesta consulta"},
    "LATAM": {"cheapest": 1500, "count": 2},
    "GOL": {"cheapest": 1800, "count": 1}
  },
  "best": {"airline": "LATAM", "price": 1500},
  "sources": {"google_flights": "ok"}
}
```

Valores são preços em BRL encontrados nos cards de ida e volta, não soma de trechos.
`count` conta cards únicos interpretados por companhia; não representa todo o
inventário da companhia. IATA retornado é o selecionado no dropdown. Adições ao JSON
podem ser ignoradas por consumidores; mudança de significado requer nova versão.

O script não produz JSON de erro. Consumidores devem verificar código de saída antes
de ler stdout: `1` entrada/preparação/arquivo, `2` rede/captcha, `3` verificação de UI
ou parsing. Timeouts de seletores são falhas de verificação; timeouts de navegação são
falhas de rede. A classificação não substitui a mensagem em stderr.

## Estado do monitor

Persiste atomicamente `schema_version`, `route`, `adults`, `cabin`, `currency`,
`best_airline` e `best_price`, em arquivo com modo `600`. `fetched_at` não participa
da comparação. Estado antigo ou JSON corrompido causa nova notificação após busca
bem-sucedida. Erros de leitura por permissão não são tratados como primeira execução.
Saída vazia com exit `0` significa ausência de mudança, não erro nem falta de voos.
`--json` ignora `--state-file`, inclusive sua escrita.

## Limites operacionais

O calendário é selecionado por labels contendo dia, mês e ano; os resultados são
conferidos pelos campos de data visíveis (com fallback de cabeçalho). Aeroportos fora
da tabela doméstica são rejeitados. Mudanças no DOM/idioma podem interromper a busca;
nesse caso, guardar o diagnóstico e corrigir os seletores antes de voltar a cotar.
O cooldown não é um lock: usar uma execução por perfil de Chromium por vez.
