// lib/airlines.js — normalização de companhias (Azul/LATAM/GOL) + parse de preço R$
// Contrato de saída (references/contracts.md): chaves AZUL | LATAM | GOL.

export const TARGET_AIRLINES = {
  AZUL: { label: 'Azul', patterns: [/azul/i] },
  LATAM: { label: 'LATAM', patterns: [/latam/i] },
  GOL: { label: 'Gol', patterns: [/\bgol\b/i, /gol\s*linhas/i, /gol\s*transportes/i] },
};

const BY_LABEL = new Map();
for (const [key, meta] of Object.entries(TARGET_AIRLINES)) {
  BY_LABEL.set(key.toLowerCase(), key);
  BY_LABEL.set(meta.label.toLowerCase(), key);
}

/**
 * Normaliza um nome de companhia exibido pelo Google Flights (ex.: "Azul",
 * "LATAM Airlines", "Gol Linhas Aéreas") para a chave canônica AZUL/LATAM/GOL.
 * Retorna null para companhias fora do alvo (VoePass, Aerolíneas Argentinas, etc).
 */
export function normalizeAirline(rawName) {
  if (!rawName) return null;
  const name = String(rawName).trim();
  const lower = name.toLowerCase();

  const direct = BY_LABEL.get(lower);
  if (direct) return direct;

  for (const [key, meta] of Object.entries(TARGET_AIRLINES)) {
    if (meta.patterns.some((re) => re.test(name))) return key;
  }
  return null;
}

/**
 * Parse de preço em R$ para inteiro BRL.
 * Aceita "R$ 1.877", "R$2.260", "R$ 1877", "1.877", "R$ 1.234,56" (pt-BR),
 * e "R$1,234.56" (en-US). Retorna null se não achar número.
 */
export function parseBRL(text) {
  if (text == null) return null;
  const s = String(text).trim();
  // Pega o primeiro bloco numérico após "R$" (ou solto).
  const m = s.match(/R\$\s*([\d.,\s]+)/i) || s.match(/(\d[\d.,\s]*)/);
  if (!m) return null;
  let num = m[1].replace(/\s/g, '');

  // Decide separador de milhar vs decimal pelos padrões pt-BR / en-US.
  let value;
  if (num.includes(',')) {
    const lastComma = num.lastIndexOf(',');
    const lastDot = num.lastIndexOf('.');
    if (lastDot > lastComma) {
      // en-US: 1,234.56 → milhar = vírgula
      value = parseFloat(num.replace(/,/g, ''));
    } else {
      // pt-BR: 1.234,56 → milhar = ponto
      const [intPart, decPart = ''] = num.split(',');
      value = parseFloat(intPart.replace(/\./g, '') + '.' + decPart);
    }
  } else {
    value = parseFloat(num.replace(/\./g, ''));
  }
  if (!Number.isFinite(value)) return null;
  return Math.round(value);
}

export const AIRLINE_LABELS = { AZUL: 'Azul', LATAM: 'LATAM', GOL: 'Gol' };
