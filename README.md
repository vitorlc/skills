# @vitorlc/skills

Personal AI agent skills. Install or update globally from any machine with `npx`.

## Install

```bash
npx @vitorlc/skills pluggy-investment-report
npx @vitorlc/skills smiles-passagens
```

Installs into:

| Target | Path |
|--------|------|
| Claude Code | `~/.claude/skills/<name>/` |
| Agent Skills | `~/.agents/skills/<name>/` |
| OpenCode | `~/.config/opencode/skills/<name>/` |

By default a new skill is copied to `~/.claude/skills` and symlinked into the other two locations. Existing independent copies stay independent. Updating a symlink target on its own detaches it into a copy, retaining its state, so unselected hosts are not modified.

## Commands

```bash
npx @vitorlc/skills <skill>              # install or update
npx @vitorlc/skills install --all
npx @vitorlc/skills list
npx @vitorlc/skills update               # update all installed
npx @vitorlc/skills uninstall <skill>
npx @vitorlc/skills info <skill>
npx @vitorlc/skills which <skill>
```

### Flags

- `--target claude|agents|opencode|all` (default: `all`)
- `--force` reinstall
- `--dry-run`
- `--copy` copy to every target instead of symlink

## Catalog

| Skill | Description |
|-------|-------------|
| `pluggy-investment-report` | Portfolio report from Pluggy-connected accounts: history, period performance vs CDI/IPCA, deposit-first rebalancing and FGC/concentration/maturity alerts |
| `smiles-passagens` | Smiles/GOL round-trip miles search (calendar, SMILES_CLUB) |
| `melhor-preco-passagens` | Cheapest round-trip fare in BRL comparing Azul × LATAM × GOL (Google Flights, Playwright) |

### Pluggy env vars

```bash
export PLUGGY_CLIENT_ID="..."
export PLUGGY_CLIENT_SECRET="..."
```

Optional Pluggy settings:

- `PLUGGY_REPORT_DATA_DIR`: keep history and targets outside the installation (one history shared by every host). `tmp/` is copied once, never moved.
- `collect_investments.py --with-transactions`: fetch each investment's transactions so returns can be separated from deposits/withdrawals.
- `performance.py --benchmarks` queries the public Banco Central API (CDI, IPCA); it is opt-in and needs no credentials.

Never commit credentials. Local state under each installed skill (`tmp/`, `data/`, `.cache/`, root `.env` and root HTML reports) is preserved across updates, including independent copies. `.env` is not loaded automatically. Uninstall removes that target and its local state; it refuses to remove a directory still shared by an unselected host. Dependencies in `scripts/node_modules` survive updates unless the dependency lockfile changes; then run the skill setup again.

### Smiles search (no secrets required)

```bash
node ~/.claude/skills/smiles-passagens/scripts/search.mjs \
  -o SAO -d GIG --departure 15/12/2026 --return 22/12/2026
```

Optional: `CALENDAR_API_URL` overrides the calendar endpoint. Airport DB covers GOL domestic + international destinations.

## Runtime requirements

- Installer and Smiles: Node.js 18+.
- Google Flights: Node.js 20+, Playwright dependencies and Chromium installed separately.
- Pluggy: Python 3.10+, exported credentials; no third-party Python packages.
- Hermes paths/cron are optional host-specific usage, not installer targets.

`install` skips intact installations matching the packaged source; `--force` reinstalls.
`update` always refreshes selected installed skills. Package version status compares
to the currently running npm package; it does not query the registry.

## Develop

```bash
node bin/skills.mjs list
node bin/skills.mjs install pluggy-investment-report --dry-run
node bin/skills.mjs install pluggy-investment-report
```

Run offline regression tests with `npm test`. Tests use temporary installations,
synthetic API responses and monitor files; they do not access personal accounts.
PRs run the same tests; publishing only runs for pushes to `main`.
After installing the Google Flights dependencies and Chromium, run `npm run test:browser`
for offline DOM/report checks. Set `SKILLS_CHROMIUM_PATH` to use a system Chromium.

Add a new skill as `skills/<name>/SKILL.md` (plus optional `scripts/`, `references/`).

## Publish

```bash
npm publish --access public
```
