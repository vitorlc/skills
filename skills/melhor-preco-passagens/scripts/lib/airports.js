// lib/airports.js — tabela local de aeroportos BR comuns (IATA ↔ nome de cidade).
// O Google Flights NÃO autocompleteia bem códigos IATA digitados (GYN → Granada),
// então o search.mjs digita o NOME da cidade e confere o código esperado no dropdown.
// Nomes conforme o autocomplete pt-BR do Google Flights.

export const AIRPORTS = {
  // Capitais + principais (código → nome a digitar)
  GYN: 'Goiânia',
  BSB: 'Brasília',
  GRU: 'São Paulo',
  CGH: 'São Paulo',
  VCP: 'Campinas',
  GIG: 'Rio de Janeiro',
  SDU: 'Rio de Janeiro',
  CNF: 'Belo Horizonte',
  PLU: 'Belo Horizonte',
  BPS: 'Porto Seguro',
  SSA: 'Salvador',
  REC: 'Recife',
  MCZ: 'Maceió',
  FOR: 'Fortaleza',
  NAT: 'Natal',
  JPA: 'João Pessoa',
  AJU: 'Aracaju',
  BEL: 'Belém',
  MAO: 'Manaus',
  CWB: 'Curitiba',
  IGU: 'Foz do Iguaçu',
  FLN: 'Florianópolis',
  POA: 'Porto Alegre',
  VIX: 'Vitória',
  CGB: 'Cuiabá',
  CGR: 'Campo Grande',
  SLZ: 'São Luís',
  THE: 'Teresina',
  PMW: 'Palmas',
  PVH: 'Porto Velho',
  RBR: 'Rio Branco',
  MCP: 'Macapá',
  BVB: 'Boa Vista',
  // Secundárias relevantes
  UDI: 'Uberlândia',
  LDB: 'Londrina',
  MGF: 'Maringá',
  NVT: 'Navegantes',
  JOI: 'Joinville',
  SJP: 'São José do Rio Preto',
  RAO: 'Ribeirão Preto',
  SOD: 'Sorocaba',
  IOS: 'Ilhéus',
  LEC: 'Lençóis',
  JDO: 'Juazeiro do Norte',
  IMP: 'Imperatriz',
  MOC: 'Montes Claros',
  PFB: 'Passo Fundo',
  PET: 'Pelotas',
  FEN: 'Fernando de Noronha',
  CXJ: 'Caxias do Sul',
  // Multi-aeroporto: nomes que exigem escolha de qual aeroporto
  // (via código esperado — quem digita "São Paulo" aceita o primeiro/qualquer)
};

// UF (estado) → código(s) IATA do(s) aeroporto(s) da capital.
// Múltiplos códigos = mesma cidade (GRU/CGH "São Paulo", GIG/SDU "Rio de Janeiro",
// CNF/PLU "Belo Horizonte") — aceita qualquer um; a query digitada é o nome da cidade.
export const UF_AIRPORTS = {
  AC: ['RBR'], AL: ['MCZ'], AP: ['MCP'], AM: ['MAO'], BA: ['SSA'], CE: ['FOR'],
  DF: ['BSB'], ES: ['VIX'], GO: ['GYN'], MA: ['SLZ'], MT: ['CGB'], MS: ['CGR'],
  MG: ['CNF', 'PLU'], PA: ['BEL'], PB: ['JPA'], PR: ['CWB'], PE: ['REC'],
  PI: ['THE'], RJ: ['GIG', 'SDU'], RN: ['NAT'], RS: ['POA'], RO: ['PVH'],
  RR: ['BVB'], SC: ['FLN'], SP: ['GRU', 'CGH'], SE: ['AJU'], TO: ['PMW'],
};

const CODES_BY_NAME = new Map();
for (const [code, name] of Object.entries(AIRPORTS)) {
  const key = normalize(name);
  if (!CODES_BY_NAME.has(key)) CODES_BY_NAME.set(key, []);
  CODES_BY_NAME.get(key).push(code);
}

function normalize(s) {
  return String(s)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

/**
 * Resolve o valor de --origin/--destination para o que digitar no Google Flights.
 * Aceita IATA (GYN) ou nome de cidade ("Goiânia", "goiania", "Goiânia, GO").
 * Retorna { query, expect }:
 *   query  = texto a digitar (nome da cidade)
 *   expect = Set de códigos IATA aceitáveis (null = aceitar a 1ª sugestão)
 */
export function resolveAirport(raw) {
  if (!raw || typeof raw !== 'string') return null;
  let input = raw.trim();
  // Remove sufixo "UF" e espaços extras: "Goiânia, GO", "goiania - GO", "foz do iguaçu - PR"
  input = input.replace(/[,–—-]?\s+[A-Z]{2}$/, '').trim();
  const upper = input.toUpperCase();

  if (/^[A-Z]{3}$/.test(upper)) {
    const name = AIRPORTS[upper];
    if (name) return { query: name, expect: new Set([upper]) };
    return null; // escopo doméstico: exigir código presente na tabela
  }

  if (/^[A-Z]{2}$/.test(upper)) {
    const codes = UF_AIRPORTS[upper];
    if (codes) return { query: AIRPORTS[codes[0]], expect: new Set(codes) };
    return null;
  }

  const key = normalize(input);
  const codes = CODES_BY_NAME.get(key);
  if (codes) return { query: input, expect: new Set(codes) };
  return null;
}
