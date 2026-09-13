import os from "node:os";
import path from "node:path";

const HOME = os.homedir();

export const TARGET_KEYS = ["claude", "agents", "opencode"];

const BASES = {
  claude: path.join(HOME, ".claude", "skills"),
  agents: path.join(HOME, ".agents", "skills"),
  opencode: path.join(HOME, ".config", "opencode", "skills"),
};

/** Canonical install location (real copy). Others may symlink here. */
export const CANONICAL = "claude";

export function resolveTargets(spec = "all") {
  if (!spec || spec === "all") return [...TARGET_KEYS];
  const parts = String(spec)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  for (const p of parts) {
    if (!TARGET_KEYS.includes(p)) {
      throw new Error(
        `Unknown target "${p}". Use: ${TARGET_KEYS.join("|")}|all`
      );
    }
  }
  if (!parts.length) throw new Error("Select at least one target");
  return [...new Set(parts)];
}

export function skillPath(target, name) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name || "")) throw new Error("Invalid skill name");
  return path.join(BASES[target], name);
}

export function basePath(target) {
  return BASES[target];
}
