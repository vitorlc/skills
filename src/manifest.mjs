import path from "node:path";
import { exists, readJson, writeJson } from "./fs-utils.mjs";
import { packageName, packageVersion } from "./catalog.mjs";
import { CANONICAL, skillPath } from "./targets.mjs";

export const META_FILE = ".install-meta.json";

export function metaPath(installDir) {
  return path.join(installDir, META_FILE);
}

export function readMeta(installDir) {
  return readJson(metaPath(installDir), null);
}

export function writeMeta(installDir, data) {
  writeJson(metaPath(installDir), data);
}

export function buildMeta({ name, targets }) {
  return {
    name,
    source: packageName(),
    packageVersion: packageVersion(),
    installedAt: new Date().toISOString(),
    targets,
  };
}

/** Prefer meta from canonical path; fall back to any target. */
export function findInstalledMeta(name, targets) {
  const ordered = [
    CANONICAL,
    ...targets.filter((t) => t !== CANONICAL),
  ];
  for (const t of ordered) {
    const dir = skillPath(t, name);
    if (exists(metaPath(dir))) return { target: t, dir, meta: readMeta(dir) };
    // symlink may point to canonical which has meta
    if (exists(dir)) {
      const meta = readMeta(dir);
      if (meta) return { target: t, dir, meta };
    }
  }
  return null;
}

export function isOutdated(meta) {
  if (!meta?.packageVersion) return true;
  return meta.packageVersion !== packageVersion();
}
