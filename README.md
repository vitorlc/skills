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

By default the skill is copied to `~/.claude/skills` and symlinked into the other two locations.

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
| `pluggy-investment-report` | Consolidated investment report from Pluggy-connected accounts |
| `smiles-passagens` | Smiles/GOL round-trip miles search (calendar, SMILES_CLUB) |

### Pluggy env vars

```bash
export PLUGGY_CLIENT_ID="..."
export PLUGGY_CLIENT_SECRET="..."
```

Never commit credentials. Local state under the installed skill (`tmp/`, `data/`) is preserved across updates.

### Smiles search (no secrets required)

```bash
node ~/.claude/skills/smiles-passagens/scripts/search.mjs \
  -o SAO -d GIG --departure 15/12/2026 --return 22/12/2026
```

Optional: `CALENDAR_API_URL` overrides the calendar endpoint. Airport DB covers GOL domestic + international destinations.

## Develop

```bash
node bin/skills.mjs list
node bin/skills.mjs install pluggy-investment-report --dry-run
node bin/skills.mjs install pluggy-investment-report
```

Add a new skill as `skills/<name>/SKILL.md` (plus optional `scripts/`, `references/`).

## Publish

```bash
npm publish --access public
```
