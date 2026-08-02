import fs from "node:fs";
import path from "node:path";
import {
  copyDir,
  ensureDir,
  exists,
  isSymlink,
  rmrf,
} from "./fs-utils.mjs";
import { skillSourcePath } from "./catalog.mjs";
import {
  buildMeta,
  findInstalledMeta,
  META_FILE,
  writeMeta,
} from "./manifest.mjs";
import {
  CANONICAL,
  basePath,
  resolveTargets,
  skillPath,
} from "./targets.mjs";

/** Paths relative to skill root that must never be wiped on update. */
const PRESERVE_TOP = new Set(["tmp", "data", ".env"]);

/** Skip these when copying from package → install. */
function shouldCopy(rel, isDir) {
  const top = rel.split(path.sep)[0];
  const base = path.basename(rel);

  if (top === "tests") return false;
  if (top === "tmp") return false;
  if (top === "data") return false;
  if (top === ".pytest_cache") return false;
  if (top === "__pycache__") return false;
  if (top === "node_modules") return false;
  if (top === ".git") return false;
  if (base === ".env") return false;
  if (base === META_FILE) return false;
  if (base === ".DS_Store") return false;
  if (base.endsWith(".pyc")) return false;
  if (base.endsWith(".html") && !isDir) return false;
  if (base === ".gitignore" && top === ".gitignore") return true;
  return true;
}

function preserveFilter(name) {
  if (PRESERVE_TOP.has(name)) return true;
  if (name === ".env") return true;
  if (name.endsWith(".html")) return true;
  return false;
}

/**
 * Update install dir: remove non-preserved entries, then copy fresh skill files.
 */
function syncSkillFiles(src, dest, { dryRun }) {
  if (dryRun) {
    console.log(`  would sync ${src} → ${dest}`);
    return;
  }

  ensureDir(dest);

  if (exists(dest)) {
    for (const entry of fs.readdirSync(dest, { withFileTypes: true })) {
      if (preserveFilter(entry.name)) continue;
      if (entry.name === META_FILE) continue;
      rmrf(path.join(dest, entry.name));
    }
  }

  copyDir(src, dest, { filter: shouldCopy });
}

function linkOrCopy(canonicalDir, dest, { forceCopy, dryRun }) {
  if (path.resolve(canonicalDir) === path.resolve(dest)) return { mode: "same" };

  if (dryRun) {
    console.log(
      `  would ${forceCopy ? "copy" : "symlink"} ${dest} → ${canonicalDir}`
    );
    return { mode: forceCopy ? "copy" : "symlink" };
  }

  ensureDir(path.dirname(dest));

  // Already correct symlink?
  if (isSymlink(dest)) {
    try {
      const current = fs.readlinkSync(dest);
      const resolved = path.resolve(path.dirname(dest), current);
      if (resolved === path.resolve(canonicalDir) && !forceCopy) {
        return { mode: "symlink-exists" };
      }
    } catch {
      // fall through
    }
    rmrf(dest);
  } else if (exists(dest)) {
    rmrf(dest);
  }

  if (!forceCopy) {
    try {
      fs.symlinkSync(canonicalDir, dest, "dir");
      return { mode: "symlink" };
    } catch {
      // fall back to copy
    }
  }

  copyDir(canonicalDir, dest, {
    filter: (rel) => {
      // copy everything currently in canonical including meta
      const base = path.basename(rel);
      if (base === ".DS_Store") return false;
      return true;
    },
  });
  return { mode: "copy" };
}

export function installSkill(name, options = {}) {
  const {
    target = "all",
    force = false,
    dryRun = false,
    copy = false,
  } = options;

  const targets = resolveTargets(target);
  const src = skillSourcePath(name);

  // Prefer canonical if requested; else first target gets the real files
  const primary =
    targets.includes(CANONICAL) ? CANONICAL : targets[0];
  const primaryDir = skillPath(primary, name);

  const existing = findInstalledMeta(name, targets);

  console.log(
    `${existing ? "Updating" : "Installing"} ${name} → ${targets.join(", ")}`
  );

  if (!dryRun) ensureDir(basePath(primary));
  syncSkillFiles(src, primaryDir, { dryRun });

  if (!dryRun) {
    writeMeta(
      primaryDir,
      buildMeta({ name, targets })
    );
  } else {
    console.log(`  would write ${META_FILE}`);
  }

  for (const t of targets) {
    if (t === primary) {
      console.log(`  ✓ ${t}: ${primaryDir}`);
      continue;
    }
    const dest = skillPath(t, name);
    if (!dryRun) ensureDir(basePath(t));
    const result = linkOrCopy(primaryDir, dest, {
      forceCopy: copy,
      dryRun,
    });
    console.log(`  ✓ ${t}: ${dest} (${result.mode})`);
  }

  return { name, primaryDir, targets };
}

export function uninstallSkill(name, options = {}) {
  const { target = "all", dryRun = false } = options;
  const targets = resolveTargets(target);

  // Remove non-canonical first (symlinks), then canonical
  const ordered = [
    ...targets.filter((t) => t !== CANONICAL),
    ...targets.filter((t) => t === CANONICAL),
  ];

  let removed = 0;
  for (const t of ordered) {
    const dir = skillPath(t, name);
    if (!exists(dir) && !isSymlink(dir)) {
      console.log(`  · ${t}: not installed`);
      continue;
    }
    if (dryRun) {
      console.log(`  would remove ${dir}`);
    } else {
      rmrf(dir);
      console.log(`  ✓ removed ${dir}`);
    }
    removed++;
  }

  if (removed === 0) {
    console.log(`Skill "${name}" was not installed on selected targets.`);
  }
  return { name, removed };
}

export function whichSkill(name, options = {}) {
  const targets = resolveTargets(options.target || "all");
  const rows = [];
  for (const t of targets) {
    const dir = skillPath(t, name);
    const present = exists(dir) || isSymlink(dir);
    let detail = "missing";
    if (present) {
      if (isSymlink(dir)) {
        try {
          detail = `symlink → ${fs.readlinkSync(dir)}`;
        } catch {
          detail = "symlink";
        }
      } else {
        detail = "directory";
      }
    }
    rows.push({ target: t, path: dir, present, detail });
  }
  return rows;
}
