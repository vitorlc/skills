import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import {
  copyDir,
  ensureDir,
  exists,
  isSymlink,
  rmrf,
} from "./fs-utils.mjs";
import { packageVersion, skillSourcePath } from "./catalog.mjs";
import {
  buildMeta,
  findInstalledMeta,
  META_FILE,
  writeMeta,
  readMeta,
} from "./manifest.mjs";
import {
  CANONICAL,
  basePath,
  resolveTargets,
  skillPath,
  TARGET_KEYS,
} from "./targets.mjs";

/** Paths relative to skill root that must never be wiped on update. */
const PRESERVE_TOP = new Set(["tmp", "data", ".env", ".cache"]);

/** Skip these when copying from package → install. */
function shouldCopy(rel, isDir) {
  const top = rel.split(path.sep)[0];
  const base = path.basename(rel);

  if (PRESERVE_TOP.has(top)) return false;
  if (rel.split(path.sep).some((part) => ["node_modules", "__pycache__", ".pytest_cache"].includes(part))) return false;
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

  // Keep dependencies only while their lockfile is unchanged.
  const lock = path.join("scripts", "package-lock.json");
  if (exists(path.join(dest, lock)) && exists(path.join(src, lock)) &&
      !fs.readFileSync(path.join(dest, lock)).equals(fs.readFileSync(path.join(src, lock)))) {
    rmrf(path.join(dest, "scripts", "node_modules"));
  }
  function clean(dir, root = false) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if ((root && preserveFilter(entry.name)) || entry.name === META_FILE ||
          entry.name === "node_modules" || entry.name === ".env") continue;
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        clean(file);
        if (fs.readdirSync(file).length === 0) fs.rmdirSync(file);
      } else rmrf(file);
    }
  }
  clean(dest, true);

  copyDir(src, dest, { filter: shouldCopy });
}

function fingerprint(dir) {
  const hash = createHash("sha256");
  function visit(base, rel = "") {
    for (const entry of fs.readdirSync(base, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const name = path.join(rel, entry.name);
      if (!shouldCopy(name, entry.isDirectory())) continue;
      if (entry.isDirectory()) visit(path.join(base, entry.name), name);
      else if (entry.isFile()) hash.update(name).update("\0").update(fs.readFileSync(path.join(base, entry.name)));
    }
  }
  visit(dir);
  return hash.digest("hex");
}

function detachLink(dest, dryRun) {
  if (!isSymlink(dest)) return;
  if (dryRun) { console.log(`  would detach symlink ${dest}, preserving its state`); return; }
  // Stage before unlinking so a failed copy leaves the original installation intact.
  const staged = fs.mkdtempSync(path.join(path.dirname(dest), ".skill-copy-"));
  const originalLink = fs.readlinkSync(dest);
  try {
    if (exists(dest)) fs.cpSync(fs.realpathSync(dest), staged, { recursive: true, dereference: false, verbatimSymlinks: true, preserveTimestamps: true });
    fs.unlinkSync(dest);
    try { fs.renameSync(staged, dest); }
    catch (error) { fs.symlinkSync(originalLink, dest, "dir"); throw error; }
  } finally { if (exists(staged)) rmrf(staged); }
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

  const sourceHash = fingerprint(src);
  function syncTarget(dest) {
    const meta = readMeta(dest);
    const current = exists(dest) && meta?.packageVersion === packageVersion() &&
      meta?.sourceHash === sourceHash && fingerprint(dest) === sourceHash;
    if (!force && current) {
      console.log(`  up to date: ${dest}`);
      return;
    }
    syncSkillFiles(src, dest, { dryRun });
    if (!dryRun) writeMeta(dest, { ...buildMeta({ name, targets }), sourceHash });
    else console.log(`  would write ${META_FILE}`);
  }

  if (!dryRun) ensureDir(basePath(primary));
  // A selected symlink must not update an unselected host through its target.
  detachLink(primaryDir, dryRun);
  syncTarget(primaryDir);

  for (const t of targets) {
    if (t === primary) continue;
    const dest = skillPath(t, name);
    if (!dryRun) ensureDir(basePath(t));
    if (copy || (exists(dest) && !isSymlink(dest))) {
      // Existing independent copies stay independent and keep their own state.
      detachLink(dest, dryRun);
      syncTarget(dest);
      continue;
    }
    if (dryRun) {
      console.log(`  would symlink ${dest} → ${primaryDir}`);
      continue;
    }
    if (isSymlink(dest)) {
      const resolved = path.resolve(path.dirname(dest), fs.readlinkSync(dest));
      if (resolved === path.resolve(primaryDir)) continue;
      // Preserve a different installation rather than discarding its state.
      detachLink(dest, false);
      syncTarget(dest);
      continue;
    }
    try { fs.symlinkSync(primaryDir, dest, "dir"); }
    catch { syncTarget(dest); }
  }

  return { name, primaryDir, targets };
}

export function uninstallSkill(name, options = {}) {
  const { target = "all", dryRun = false } = options;
  const targets = resolveTargets(target);

  // Refuse to strand an unselected host that shares this installation.
  for (const t of targets) {
    const dir = skillPath(t, name);
    if (!exists(dir) || isSymlink(dir)) continue;
    for (const other of TARGET_KEYS.filter(key => !targets.includes(key))) {
      const link = skillPath(other, name);
      if (isSymlink(link) && exists(link) && fs.realpathSync(link) === fs.realpathSync(dir)) {
        throw new Error(`${other} shares ${t}'s installation. Detach it with install --target ${other} --copy, or uninstall all shared targets together.`);
      }
    }
  }

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
