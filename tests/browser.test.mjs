import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { readPassengerCounts } from '../skills/melhor-preco-passagens/scripts/lib/ui.js';

// Opt in after installing the flight skill's dependencies and Chromium.
test('browser fixtures: passenger counts and offline report interactions', { skip: process.env.SKILLS_BROWSER_TESTS !== '1' }, async () => {
  const { chromium } = await import('../skills/melhor-preco-passagens/scripts/node_modules/playwright/index.mjs');
  const browser = await chromium.launch({ headless: true, chromiumSandbox: true, ...(process.env.SKILLS_CHROMIUM_PATH ? { executablePath: process.env.SKILLS_CHROMIUM_PATH } : {}) });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'skills-browser-'));
  try {
    const page = await browser.newPage();
    const labels = ['Adicionar adulto', 'Adicionar criança de 2 a 11 anos', 'Adicionar bebê em assento', 'Adicionar bebê de colo'];
    await page.setContent(labels.map((label, i) => `<section><div>${i ? 'Crianças' : 'Adultos'}</div><small>De 2 a 11 anos</small><div><button>−</button><span><span>${i ? 0 : 2}</span><span aria-live="polite">${i ? 0 : 2}</span></span><button aria-label="${label}">+</button></div></section>`).join(''));
    assert.deepEqual(await page.evaluate(readPassengerCounts), { Adultos: 2, Crianças: 0, 'Bebês no assento': 0, 'Bebês no colo': 0 });
    await page.getByRole('button', { name: 'Adicionar adulto', exact: true }).evaluate(el => el.parentElement.querySelector('span').remove());
    assert.equal((await page.evaluate(readPassengerCounts)).Adultos, undefined);

    const scripts = path.resolve('skills/pluggy-investment-report/scripts');
    const html = path.join(tmp, 'report.html');
    const generation = spawnSync('python3', ['-B', '-c', `
import sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from generate_report import generate_html
history = [{"timestamp":"2026-09-12T10:00:00", "totals":{"current":10}, "investments":[{"name":"</script><img src=x onerror=alert(1)>","type":"STOCK","value":10}]}]
with patch('generate_report.load_all_snapshots', return_value=history):
    generate_html([{"name":"Example", "institution":"Bank", "type":"STOCK", "value":100, "amount":90}], sys.argv[2], targets={"Ações":100})
`, scripts, html], { encoding: 'utf8' });
    assert.equal(generation.status, 0, generation.stderr);
    await page.route('https://**/*', route => route.abort());
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(html).href);
    await page.getByRole('button', { name: /relatórios anteriores/ }).click();
    assert.equal(await page.locator('#history-list img').count(), 0);
    assert.match(await page.locator('#history-list').textContent(), /<img src=x onerror=alert\(1\)>/);
    await page.getByRole('button', { name: /Configurar/ }).click();
    assert.equal(await page.locator('#targetsPanel').isVisible(), true);
    assert.equal(await page.locator('#chart-error').isVisible(), true);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
