import {
  getSkill,
  listCatalog,
  packageName,
  packageVersion,
} from "./catalog.mjs";
import { installSkill, uninstallSkill, whichSkill } from "./install.mjs";
import {
  findInstalledMeta,
  isOutdated,
} from "./manifest.mjs";
import { TARGET_KEYS, resolveTargets } from "./targets.mjs";

function printHelp() {
  const pkg = packageName();
  console.log(`
${pkg} v${packageVersion()}

Usage:
  npx ${pkg} <skill>                 Install or update a skill
  npx ${pkg} install <skill...>      Install or update skill(s)
  npx ${pkg} install --all           Install all catalog skills
  npx ${pkg} list                    List catalog and install status
  npx ${pkg} update [skill...]       Update installed skills (or all)
  npx ${pkg} uninstall <skill>       Remove from selected targets
  npx ${pkg} info <skill>            Show skill details
  npx ${pkg} which <skill>           Show install paths
  npx ${pkg} help                    Show this help

Flags:
  --target <t>   ${TARGET_KEYS.join("|")}|all  (default: all)
  --force        Reinstall even if up to date
  --dry-run      Print actions without writing
  --copy         Copy to all targets instead of symlink
`.trim());
}

function parseArgs(argv) {
  const flags = {
    target: "all",
    force: false,
    dryRun: false,
    copy: false,
    all: false,
  };
  const positional = [];

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--target" || a === "-t") {
      flags.target = argv[++i];
    } else if (a.startsWith("--target=")) {
      flags.target = a.slice("--target=".length);
    } else if (a === "--force" || a === "-f") {
      flags.force = true;
    } else if (a === "--dry-run") {
      flags.dryRun = true;
    } else if (a === "--copy") {
      flags.copy = true;
    } else if (a === "--all") {
      flags.all = true;
    } else if (a === "--help" || a === "-h") {
      positional.push("help");
    } else if (a.startsWith("-")) {
      throw new Error(`Unknown flag: ${a}`);
    } else {
      positional.push(a);
    }
  }

  return { flags, positional };
}

const COMMANDS = new Set([
  "install",
  "list",
  "update",
  "uninstall",
  "info",
  "which",
  "help",
  "--help",
  "-h",
]);

export async function main(argv) {
  if (argv.length === 0) {
    printHelp();
    return;
  }

  const { flags, positional } = parseArgs(argv);
  let [cmd, ...rest] = positional;

  // Bare skill name → install
  if (!COMMANDS.has(cmd)) {
    rest = [cmd, ...rest];
    cmd = "install";
  }

  const opts = {
    target: flags.target,
    force: flags.force,
    dryRun: flags.dryRun,
    copy: flags.copy,
  };

  // validate target early
  resolveTargets(opts.target);

  switch (cmd) {
    case "help":
    case "--help":
    case "-h":
      printHelp();
      break;

    case "list":
      cmdList(opts);
      break;

    case "install":
      cmdInstall(rest, flags, opts);
      break;

    case "update":
      cmdUpdate(rest, opts);
      break;

    case "uninstall":
      if (rest.length === 0) throw new Error("Usage: uninstall <skill>");
      for (const name of rest) {
        console.log(`Uninstalling ${name}...`);
        uninstallSkill(name, opts);
      }
      break;

    case "info":
      if (rest.length === 0) throw new Error("Usage: info <skill>");
      cmdInfo(rest[0], opts);
      break;

    case "which":
      if (rest.length === 0) throw new Error("Usage: which <skill>");
      cmdWhich(rest[0], opts);
      break;

    default:
      throw new Error(`Unknown command: ${cmd}`);
  }
}

function cmdList(opts) {
  const catalog = listCatalog();
  const targets = resolveTargets(opts.target);

  if (catalog.length === 0) {
    console.log("No skills in catalog.");
    return;
  }

  console.log(`${packageName()}@${packageVersion()}\n`);
  for (const skill of catalog) {
    const found = findInstalledMeta(skill.name, targets);
    let status = "not installed";
    if (found?.meta) {
      status = isOutdated(found.meta)
        ? `outdated (local ${found.meta.packageVersion} → ${packageVersion()})`
        : `installed ${found.meta.packageVersion}`;
    } else if (found) {
      status = "installed (no meta)";
    }
    console.log(`  ${skill.name}`);
    console.log(`    ${status}`);
    if (skill.description) {
      const desc =
        skill.description.length > 100
          ? skill.description.slice(0, 97) + "..."
          : skill.description;
      console.log(`    ${desc}`);
    }
    console.log();
  }
}

function cmdInstall(names, flags, opts) {
  let toInstall = names;
  if (flags.all) {
    toInstall = listCatalog().map((s) => s.name);
  }
  if (toInstall.length === 0) {
    throw new Error("Usage: install <skill...> | install --all");
  }
  for (const name of toInstall) {
    getSkill(name); // validate
    installSkill(name, opts);
  }
}

function cmdUpdate(names, opts) {
  const catalog = listCatalog();
  const catalogNames = new Set(catalog.map((s) => s.name));
  const targets = resolveTargets(opts.target);

  let toUpdate;
  if (names.length === 0) {
    toUpdate = catalog
      .map((s) => s.name)
      .filter((name) => findInstalledMeta(name, targets));
    if (toUpdate.length === 0) {
      console.log("No installed skills to update.");
      return;
    }
  } else {
    toUpdate = names;
  }

  for (const name of toUpdate) {
    if (!catalogNames.has(name)) {
      throw new Error(`Skill not found: ${name}`);
    }
    const found = findInstalledMeta(name, targets);
    if (!found && names.length > 0) {
      console.log(`${name}: not installed, installing...`);
    }
    installSkill(name, { ...opts, force: true });
  }
}

function cmdInfo(name, opts) {
  const skill = getSkill(name);
  const targets = resolveTargets(opts.target);
  const found = findInstalledMeta(name, targets);

  console.log(`Name:        ${skill.name}`);
  console.log(`Package:     ${packageName()}@${packageVersion()}`);
  console.log(`Source:      ${skill.dir}`);
  if (skill.description) {
    console.log(`Description: ${skill.description}`);
  }
  if (found?.meta) {
    console.log(`Installed:   ${found.meta.packageVersion} at ${found.meta.installedAt}`);
    console.log(`Targets:     ${(found.meta.targets || []).join(", ")}`);
    console.log(`Status:      ${isOutdated(found.meta) ? "outdated" : "up to date"}`);
  } else {
    console.log(`Installed:   no`);
  }
}

function cmdWhich(name, opts) {
  getSkill(name);
  const rows = whichSkill(name, opts);
  for (const r of rows) {
    const mark = r.present ? "✓" : "✗";
    console.log(`${mark} ${r.target.padEnd(10)} ${r.path}  (${r.detail})`);
  }
}
