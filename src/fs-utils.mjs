import fs from "node:fs";
import path from "node:path";

export function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

export function exists(p) {
  try {
    fs.accessSync(p);
    return true;
  } catch {
    return false;
  }
}

export function isSymlink(p) {
  try {
    return fs.lstatSync(p).isSymbolicLink();
  } catch {
    return false;
  }
}

export function readJson(file, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

export function writeJson(file, data) {
  ensureDir(path.dirname(file));
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n", "utf8");
}

/** Recursive copy with optional filter. filter(relPath, isDir) → false to skip. */
export function copyDir(src, dest, { filter } = {}) {
  ensureDir(dest);
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const from = path.join(src, entry.name);
    const to = path.join(dest, entry.name);
    const rel = entry.name;
    if (filter && !filter(rel, entry.isDirectory())) continue;

    if (entry.isDirectory()) {
      copyDirRecursive(from, to, entry.name, filter);
    } else if (entry.isFile()) {
      fs.copyFileSync(from, to);
    }
  }
}

function copyDirRecursive(src, dest, relBase, filter) {
  ensureDir(dest);
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const from = path.join(src, entry.name);
    const to = path.join(dest, entry.name);
    const rel = path.join(relBase, entry.name);
    if (filter && !filter(rel, entry.isDirectory())) continue;

    if (entry.isDirectory()) {
      copyDirRecursive(from, to, rel, filter);
    } else if (entry.isFile()) {
      fs.copyFileSync(from, to);
    }
  }
}

/** Remove path if exists (file, dir, or symlink). */
export function rmrf(p) {
  if (!exists(p) && !isSymlink(p)) {
    try {
      fs.lstatSync(p);
    } catch {
      return;
    }
  }
  try {
    fs.rmSync(p, { recursive: true, force: true });
  } catch {
    // ignore
  }
}

/** List top-level directory names that contain SKILL.md */
export function listSkillDirs(root) {
  if (!exists(root)) return [];
  return fs
    .readdirSync(root, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .filter((name) => exists(path.join(root, name, "SKILL.md")))
    .sort();
}
