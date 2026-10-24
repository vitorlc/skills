#!/usr/bin/env node
// search.mjs — núcleo Google Flights (Playwright): busca ida+volta em R$ (cash),
// valida as datas exibidas ANTES de aceitar, extrai cards e filtra Azul/LATAM/GOL.
//
// Uso:
//   node search.mjs --origin GYN --destination IGU --departure 09/10/2026 --return 12/10/2026 \
//       [--adults 1] [--json] [--state-file PATH] [--debug]
//
// Exit codes: 0 ok · 1 args inválidos · 2 bloqueio/captcha/rede · 3 datas não validadas/sem resultados
//
// Contrato de saída (JSON): ../references/contracts.md.

import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeAirline, parseBRL, AIRLINE_LABELS } from './lib/airlines.js';
import { resolveAirport } from './lib/airports.js';
import { readPassengerCounts } from './lib/ui.js';
import { parseArgs, selectAirport, datesConfirmed, updateMonitor, errorCode } from './lib/contracts.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJ_ROOT = path.resolve(__dirname, '..');
const PROFILE_DIR = path.join(PROJ_ROOT, '.cache', 'gf-profile');
const DEBUG_DIR = path.join(PROJ_ROOT, '.cache', 'debug');
const LAST_RUN_FILE = path.join(PROJ_ROOT, '.cache', 'last-search.json');


const GF_URL = 'https://www.google.com/travel/flights?hl=pt-BR&gl=BR&curr=BRL';
const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const COOLDOWN_MS = 30_000;

// ---------------------------------------------------------------- helpers
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function err(msg) {
  process.stderr.write(`[search.mjs] ${msg}\n`);
}

const PT_MONTHS = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];

function parseDateArg(raw) {
  if (!raw || typeof raw !== 'string') return null;
  const m = raw.trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) return { year: +m[3], month: +m[2], day: +m[1] };
  const m2 = raw.trim().match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m2) return { year: +m2[1], month: +m2[2], day: +m2[3] };
  return null;
}

function validDate(d) {
  if (!d) return false;
  const dt = new Date(d.year, d.month - 1, d.day);
  return dt.getFullYear() === d.year && dt.getMonth() === d.month - 1 && dt.getDate() === d.day;
}

function fmtShortDate(d) {
  // "sex., 9 de out." — mesmo formato dos inputs do Google Flights pt-BR
  const dt = new Date(d.year, d.month - 1, d.day);
  const parts = new Intl.DateTimeFormat('pt-BR', { weekday: 'short', day: 'numeric', month: 'short' }).formatToParts(dt);
  const get = (t) => (parts.find((p) => p.type === t) || {}).value || '';
  return `${get('weekday')}., ${get('day')} de ${get('month')}.`.replace(/\s+/g, ' ').replace(/\u00a0/g, ' ');
}

function fmtLongMonth(d) {
  return PT_MONTHS[d.month - 1];
}

function normalizeToken(s) {
  return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function isoLocalNow() {
  const d = new Date();
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? '+' : '-';
  const pad = (n) => String(n).padStart(2, '0');
  const offH = pad(Math.floor(Math.abs(off) / 60));
  const offM = pad(Math.abs(off) % 60);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}${sign}${offH}:${offM}`;
}

async function saveScreenshot(page, name) {
  try {
    await page.screenshot({ path: path.join(DEBUG_DIR, name), fullPage: false });
  } catch { /* ignore */ }
}

// Detecta captcha/challenge do Google (ou redirect p/ /sorry/)
async function detectCaptcha(page) {
  const url = page.url();
  if (/sorry\.google\.com|google\.com\/sorry\//.test(url)) return true;
  try {
    const text = await page.evaluate(() => (document.body ? document.body.innerText : ''));
    return /tráfego incomum|unusual traffic|nossos sistemas detectaram|recaptcha|verify you'?re a human|não é possível concluir|desative seu bloqueador/i.test(text);
  } catch {
    return false;
  }
}

async function consentIfAny(page) {
  for (const label of ['Aceitar tudo', 'Concordo', 'Aceito']) {
    const btn = page.locator(`button:has-text("${label}")`).filter({ visible: true }).first();
    if (await btn.isVisible().catch(() => false)) {
      await btn.click().catch(() => {});
      await sleep(1500);
      return;
    }
  }
}

// ---------------------------------------------------------------- UI helpers
async function typeQuery(page, sel, text) {
  const field = page.locator(sel).filter({ visible: true }).first();
  await field.click();
  await sleep(500);
  await page.keyboard.press('Control+A');
  await page.keyboard.type(text, { delay: 55 });
  await sleep(3200);
}

// Lê as opções do dropdown (código IATA + texto da linha)
async function dropdownOptions(page) {
  return page.evaluate(() => {
    const out = [];
    for (const codeEl of document.querySelectorAll('div.P1pPOe')) {
      if (!(codeEl.offsetWidth || codeEl.offsetHeight)) continue;
      const code = (codeEl.innerText || '').trim().toUpperCase();
      let el = codeEl;
      let rowText = '';
      for (let i = 0; i < 8 && el; i++) {
        const t = (el.innerText || '').trim();
        if (t && t.length > rowText.length) rowText = t;
        el = el.parentElement;
      }
      out.push({ code, rowText: rowText.replace(/\s+/g, ' ').slice(0, 150) });
    }
    return out;
  });
}

// Preenche um campo origem/destino: digita o nome, escolhe a linha do aeroporto certo e clica.
// returns true quando o campo ficou preenchido.
async function fillAirportField(page, labelRe, resolved, label) {
  const sel = `input[aria-label^="${labelRe}"]`;
  await typeQuery(page, sel, resolved.query);

  const opts = await dropdownOptions(page);
  const target = selectAirport(opts, resolved.expect);
  if (!target) {
    err(`aeroporto esperado não encontrado para ${label}; selecione um IATA doméstico conhecido`);
    return null;
  }
  const code = page.locator('div.P1pPOe').filter({ visible: true }).filter({ hasText: new RegExp(`^${target.code}$`) }).first();
  await code.click();
  await sleep(1500);
  if ((await dropdownOptions(page)).length) {
    err(`seleção de ${label} não confirmada`);
    return null;
  }

  const value = await page.locator(sel).filter({ visible: true }).first().inputValue().catch(() => '');
  if (!value || !value.trim()) {
    err(`campo "${label}" ficou vazio após seleção (query="${resolved.query}")`);
    return false;
  }
  return target.code;
}

// Seleciona um dia no calendário aberto. monthRe ex.: "de outubro de 2026".
async function clickCalendarDay(page, d) {
  const monthLong = fmtLongMonth(d);
  const re = new RegExp(`de ${monthLong} de ${d.year}`);
  const box = await page.evaluate(({ reSrc, day }) => {
    const re = new RegExp(reSrc);
    for (const el of document.querySelectorAll('[aria-label]')) {
      const aria = el.getAttribute('aria-label') || '';
      if (!re.test(aria)) continue;
      const m = aria.match(/(\d+) de (\w+)/);
      if (m && String(parseInt(m[1], 10)) === String(day)) {
        const r = el.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 20) };
      }
    }
    return null;
  }, { reSrc: re.source, day: d.day });
  if (box) {
    await page.mouse.click(box.x, box.y);
    return true;
  }
  return false;
}

// ---------------------------------------------------------------- parse cards
function parseCardText(text) {
  const t = text.replace(/\u00a0/g, ' ');
  const airlineMatch = t.match(/(Azul|LATAM|Gol)(?=Operado por|\s|\n|$)/i);
  const priceMatch = t.match(/R\$\s*([\d.,]+)/);
  const depMatch = t.match(/(?:^|\n)\s*(\d{2}:\d{2})\s*\n/);
  const arrMatch = t.match(/–\s*(\d{2}:\d{2}(?:\+\d+)?)/);
  const stopsMatch = t.match(/Sem escalas|\d+ paradas?|\d+ escala/i);
  const airline = airlineMatch ? normalizeAirline(airlineMatch[1]) : null;
  const price = priceMatch ? parseBRL(priceMatch[1]) : null;
  const stops = stopsMatch
    ? /sem escalas/i.test(stopsMatch[0]) ? 0 : parseInt(stopsMatch[0], 10) || 1
    : null;
  return {
    airline,
    price,
    dep: depMatch ? depMatch[1] : null,
    arr: arrMatch ? arrMatch[1] : null,
    stops,
  };
}

// ---------------------------------------------------------------- main
async function main() {
  let argv;
  try { argv = parseArgs(process.argv.slice(2)); }
  catch (e) { err(e.message); process.exitCode = 1; return; }
  if (argv.help) {
    console.log('Uso: --origin IATA --destination IATA --departure DD/MM/AAAA --return DD/MM/AAAA [--adults 1..9] [--json] [--state-file PATH]');
    return;
  }
  const originArg = argv.origin;
  const destArg = argv.destination;
  const depArg = argv.departure;
  const retArg = argv.return;
  const adultsArg = argv.adults === undefined ? 1 : Number(argv.adults);
  const wantJson = !!argv.json;
  const stateFile = typeof argv['state-file'] === 'string' ? argv['state-file'] : null;
  const debug = !!argv.debug;

  // ---- validação de args (exit 1)
  if (!originArg || !destArg || !depArg || !retArg) {
    err('faltam argumentos. Uso: --origin IATA --destination IATA --departure dd/mm/aaaa --return dd/mm/aaaa [--adults N] [--json] [--state-file PATH]');
    process.exit(1);
  }
  if (!Number.isInteger(adultsArg) || adultsArg < 1 || adultsArg > 9) {
    err('--adults deve ser inteiro entre 1 e 9');
    process.exit(1);
  }
  const dep = parseDateArg(depArg);
  const ret = parseDateArg(retArg);
  if (!validDate(dep)) { err(`data de partida inválida: "${depArg}" (use dd/mm/aaaa)`); process.exit(1); }
  if (!validDate(ret)) { err(`data de volta inválida: "${retArg}" (use dd/mm/aaaa)`); process.exit(1); }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const depDate = new Date(dep.year, dep.month - 1, dep.day);
  const retDate = new Date(ret.year, ret.month - 1, ret.day);
  if (depDate < today) { err('data de partida no passado'); process.exit(1); }
  if (retDate < depDate) { err('data de volta antes da partida'); process.exit(1); }
  const dayDiff = Math.round((retDate - depDate) / 86400000);
  if (dayDiff > 16) { err('Esta implementação aceita viagens de até 16 dias'); process.exit(1); }

  const origin = resolveAirport(originArg);
  const dest = resolveAirport(destArg);
  if (!origin?.expect || !dest?.expect) { err('use aeroportos domésticos da tabela local; origem/destino não resolvidos'); process.exit(1); }
  mkdirSync(PROFILE_DIR, { recursive: true });
  mkdirSync(DEBUG_DIR, { recursive: true });

  // ---- cooldown entre execuções
  if (existsSync(LAST_RUN_FILE)) {
    try {
      const last = JSON.parse(readFileSync(LAST_RUN_FILE, 'utf8')).last || 0;
      const wait = COOLDOWN_MS - (Date.now() - last);
      if (wait > 0) {
        err(`cooldown: aguardando ${Math.ceil(wait / 1000)}s desde a última busca`);
        await sleep(wait);
      }
    } catch { /* sem marca */ }
  }

  let ctx = null;
  try {
    const { chromium } = await import('playwright').catch(() => { throw Object.assign(new Error('Instale as dependências em scripts/ com npm ci'), { exitCode: 1 }); });
    ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
      headless: true,
      userAgent: UA,
      locale: 'pt-BR',
      viewport: { width: 1440, height: 900 },
      args: ['--lang=pt-BR'],
      chromiumSandbox: true,
    }).catch(() => { throw Object.assign(new Error("Falha ao iniciar Chromium; verifique a instalação do navegador e o suporte ao sandbox"), { exitCode: 1 }); });
    const page = ctx.pages()[0] ?? (await ctx.newPage());
    if (debug) {
      page.on('console', (m) => { if (m.type() === 'error') err(`[console] ${m.text().slice(0, 200)}`); });
      page.on('pageerror', (e) => err(`[pageerror] ${String(e).slice(0, 200)}`));
    }

    // ---- abre o Google Flights
    await page.goto(GF_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(3500);
    await consentIfAny(page);
    if (await detectCaptcha(page)) {
      await saveScreenshot(page, 'error-captcha-landing.png');
      err('captcha/challenge detectado na página inicial — abortando (exit 2). Evidência: .cache/debug/error-captcha-landing.png');
      process.exitCode = 2;
      return;
    }

    // ---- preenche origem e destino
    const okOrigin = await fillAirportField(page, 'De onde?', origin, 'origem');
    if (!okOrigin) { err('não foi possível preencher a origem — verifique o nome/código'); process.exitCode = 3; return; }
    const okDest = await fillAirportField(page, 'Para onde?', dest, 'destino');
    if (!okDest) { err('não foi possível preencher o destino — verifique o nome/código'); process.exitCode = 3; return; }

    // A persistent profile may carry another trip/cabin/passenger selection.
    const trip = page.getByRole('combobox').filter({ hasText: /^Ida e volta$/ }).first();
    const cabin = page.getByRole('combobox').filter({ hasText: /^Econômica$/ }).first();
    if (!(await trip.isVisible()) || !(await cabin.isVisible())) {
      err('ida e volta/econômica não confirmadas no formulário'); process.exitCode = 3; return;
    }
    const paxBtn = page.locator('[aria-label*="passageiro"], [aria-label*="Passageiro"]').filter({ visible: true }).first();
    if (!(await paxBtn.isVisible())) {
      err('controle de passageiros não encontrado'); process.exitCode = 3; return;
    }
    await paxBtn.click();
    await sleep(500);
    const passengerCounts = () => page.evaluate(readPassengerCounts);
    let counts = await passengerCounts();
    if (!Number.isInteger(counts.Adultos) || counts.Crianças !== 0 || counts['Bebês no assento'] !== 0 || counts['Bebês no colo'] !== 0) {
      err('composição de passageiros não confirmada; somente adultos são suportados'); process.exitCode = 3; return;
    }
    const delta = adultsArg - counts.Adultos;
    const change = page.getByRole('button', { name: delta > 0 ? /Adicionar adulto/i : /Remover adulto/i }).first();
    for (let i = 0; i < Math.abs(delta); i++) await change.click();
    counts = await passengerCounts();
    if (counts.Adultos !== adultsArg) {
      err('quantidade de adultos não confirmada'); process.exitCode = 3; return;
    }
    await page.getByRole('button', { name: 'Concluído', exact: true }).filter({ visible: true }).first().click();

    // ---- datas no formulário
    const partidaInput = page.locator('input[aria-label="Partida"]').filter({ visible: true }).first();
    await partidaInput.click();
    await sleep(3500);
    if (await detectCaptcha(page)) { err('captcha após abrir calendário — abortando (exit 2)'); process.exitCode = 2; return; }

    const clickedDep = await clickCalendarDay(page, dep);
    if (!clickedDep) {
      await saveScreenshot(page, 'error-calendar-dep.png');
      err(`dia de partida ${dep.day}/${dep.month}/${dep.year} não encontrado no calendário (exit 3). Evidência: .cache/debug/error-calendar-dep.png`);
      process.exitCode = 3;
      return;
    }
    await sleep(2800);
    const clickedRet = await clickCalendarDay(page, ret);
    if (!clickedRet) {
      await saveScreenshot(page, 'error-calendar-ret.png');
      err(`dia de volta ${ret.day}/${ret.month}/${ret.year} não encontrado no calendário (exit 3). Evidência: .cache/debug/error-calendar-ret.png`);
      process.exitCode = 3;
      return;
    }
    await sleep(2200);
    // confirma o diálogo do calendário
    const doneBtn = page.locator('button:has-text("Concluído")').filter({ visible: true }).first();
    if (await doneBtn.isVisible().catch(() => false)) {
      await doneBtn.click().catch(() => {});
      await sleep(2200);
    }

    // ---- submete a busca
    const submit = page.locator('button[aria-label="Pesquisar"], button:has-text("Pesquisar")').filter({ visible: true }).first();
    if (await submit.isVisible().catch(() => false)) {
      await submit.click();
    } else {
      const submit2 = page.locator('button[aria-label="Encontrar voos"]').filter({ visible: true }).first();
      if (await submit2.isVisible().catch(() => false)) await submit2.click();
    }
    // marca o cooldown no momento em que a busca é disparada
    writeFileSync(LAST_RUN_FILE, JSON.stringify({ last: Date.now() }));

    // ---- aguarda os resultados
    let resultsOk = false;
    for (let i = 0; i < 30; i++) {
      await sleep(2500);
      if (await detectCaptcha(page)) {
        await saveScreenshot(page, 'error-captcha-results.png');
        err('captcha/challenge nos resultados — abortando (exit 2). Evidência: .cache/debug/error-captcha-results.png');
        process.exitCode = 2;
        return;
      }
      const n = await page.locator('li.pIav2d').count().catch(() => 0);
      if (n > 0) { resultsOk = true; break; }
      const emptyTxt = await page.evaluate(() => (document.body ? document.body.innerText : ''));
      if (/não foram encontrados voos|nenhum voo|nenhum resultado|sem voos/i.test(emptyTxt)) break;
    }
    if (!resultsOk) {
      await saveScreenshot(page, 'error-no-results.png');
      err('nenhum resultado de voo encontrado para a rota/datas (exit 3). Evidência: .cache/debug/error-no-results.png');
      process.exitCode = 3;
      return;
    }

    // ---- VALIDAÇÃO RÍGIDA: datas exibidas nos inputs do topo
    const shownDates = await page.evaluate(() =>
      [...document.querySelectorAll('input[aria-label="Partida"], input[aria-label="Volta"]')]
        .filter((i) => i.offsetWidth && i.offsetHeight)
        .map((i) => ({ kind: i.getAttribute('aria-label'), val: (i.value || '').trim() })));
    const expectedDep = normalizeToken(fmtShortDate(dep));
    const expectedRet = normalizeToken(fmtShortDate(ret));
    const depShown = [...new Set(shownDates.filter((s) => s.kind === 'Partida' && normalizeToken(s.val)).map((s) => normalizeToken(s.val)))];
    const retShown = [...new Set(shownDates.filter((s) => s.kind === 'Volta' && normalizeToken(s.val)).map((s) => normalizeToken(s.val)))];
    const bodyText = await page.evaluate(() => (document.body ? document.body.innerText : ''));
    const bodyNorm = normalizeToken(bodyText);
    const depOk = datesConfirmed(depShown, expectedDep);
    const retOk = datesConfirmed(retShown, expectedRet);

    if (!depOk || !retOk) {
      await saveScreenshot(page, 'error-dates-mismatch.png');
      err(`datas NÃO validadas: esperado partida="${fmtShortDate(dep)}" volta="${fmtShortDate(ret)}"; exibido=${JSON.stringify(shownDates)} (exit 3). Evidência: .cache/debug/error-dates-mismatch.png`);
      process.exitCode = 3;
      return;
    }
    const datesValidated = true;

    // ---- rota exibida contém as cidades pedidas? (pega troca de aeroporto tipo Granada)
    // query é o NOME digitado no GF (ex.: Goiânia) — o cabeçalho do resultado usa o mesmo nome.
    if (origin.query !== originArg || dest.query !== destArg) {
      for (const q of [origin.query, dest.query]) {
        const tok = normalizeToken(q);
        if (tok.length < 4) continue; // código IATA puro digitado — GF pode exibir nome diferente
        if (!bodyNorm.includes(tok)) {
          err(`rota exibida não contém "${q}" — aeroporto errado foi selecionado? (exit 3)`);
          process.exitCode = 3;
          return;
        }
      }
    }

    // ---- expande a lista de resultados ("Mostrar mais voos")
    for (let i = 0; i < 8; i++) {
      const more = page.locator('li:has-text("Mostrar mais voos"), button:has-text("Mostrar mais voos")').filter({ visible: true }).first();
      if (!(await more.isVisible().catch(() => false))) break;
      const before = await page.locator('li.pIav2d').count();
      await more.click().catch(() => {});
      await sleep(5000);
      const after = await page.locator('li.pIav2d').count();
      if (after <= before) break;
    }

    // ---- parse dos cards
    const cards = await page.evaluate(() =>
      [...document.querySelectorAll('li.pIav2d')].map((c) => (c.innerText || '').trim()));
    if (debug) writeFileSync(path.join(DEBUG_DIR, 'cards-raw.json'), JSON.stringify(cards, null, 1));

    const airlines = { AZUL: { cheapest: null, count: 0 }, LATAM: { cheapest: null, count: 0 }, GOL: { cheapest: null, count: 0 } };
    let parsedTotal = 0;
    const seen = new Set();
    for (const raw of cards) {
      const parsed = parseCardText(raw);
      if (!parsed.airline || parsed.price == null) continue;
      const dedupeKey = `${raw}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      parsedTotal++;
      const A = airlines[parsed.airline];
      A.count++;
      if (A.cheapest == null || parsed.price < A.cheapest) A.cheapest = parsed.price;
    }

    if (parsedTotal === 0) {
      await saveScreenshot(page, 'error-no-parseable.png');
      err('nenhum card parseável (nenhuma das companhias Azul/LATAM/GOL com preço) — exit 3');
      process.exitCode = 3;
      return;
    }

    // companhias sem resultados ganham nota
    for (const [k, v] of Object.entries(airlines)) {
      if (v.count === 0) v.note = 'nenhum resultado encontrado nesta consulta';
    }

    let best = null;
    for (const [k, v] of Object.entries(airlines)) {
      if (v.cheapest != null && (!best || v.cheapest < best.price)) best = { airline: k, price: v.cheapest };
    }

    const out = {
      schema_version: 1,
      adults: adultsArg,
      cabin: "ECONOMY",
      route: {
        origin: okOrigin,
        destination: okDest,
        departure: `${dep.year}-${String(dep.month).padStart(2, '0')}-${String(dep.day).padStart(2, '0')}`,
        return: `${ret.year}-${String(ret.month).padStart(2, '0')}-${String(ret.day).padStart(2, '0')}`,
      },
      fetched_at: isoLocalNow(),
      currency: 'BRL',
      dates_validated: datesValidated,
      airlines,
      best,
      sources: { google_flights: 'ok' },
    };

    // ---- saída
    const rankingMd = () => {
      const rows = Object.entries(airlines).map(([k, v]) => {
        const price = v.cheapest != null ? `R$ ${v.cheapest.toLocaleString('pt-BR')}` : '—';
        const extra = v.note ? ` (${v.note})` : '';
        return `| ${AIRLINE_LABELS[k]} | ${price}${extra} |`;
      }).join('\n');
      const bestTxt = best ? `**Melhor valor: ${AIRLINE_LABELS[best.airline]} — R$ ${best.price.toLocaleString('pt-BR')}**` : 'sem voos na rota';
      const rota = `${out.route.origin} → ${out.route.destination}`;
      return `## ${rota} — ${out.route.departure} a ${out.route.return}\nAdultos: ${out.adults} · Econômica\nAtualizado: ${out.fetched_at}\n\n| Companhia | Menor preço (ida e volta) |\n|---|---|\n${rows}\n\n${bestTxt}\n\n_Confirme o preço no site da companhia antes de comprar._`;
    };

    if (wantJson) {
      process.stdout.write(JSON.stringify(out, null, 2) + '\n');
    } else if (stateFile) {
      if (updateMonitor(stateFile, out)) process.stdout.write(rankingMd() + '\n');
    } else {
      process.stdout.write(rankingMd() + '\n');
    }
    process.exitCode = 0;
  } catch (e) {
    err(`erro inesperado: ${e && e.stack ? e.stack.slice(0, 800) : e}`);
    process.exitCode = errorCode(e);
  } finally {
    if (ctx) await ctx.close().catch(() => {});
  }
}

main().catch(e => { err(e.message); process.exitCode = 1; });
