import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { listSkillDirs, readJson } from "./fs-utils.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const PACKAGE_ROOT = path.resolve(__dirname, "..");
export const SKILLS_ROOT = path.join(PACKAGE_ROOT, "skills");

export function packageVersion() {
  const pkg = readJson(path.join(PACKAGE_ROOT, "package.json"), {});
  return pkg.version || "0.0.0";
}

export function packageName() {
  const pkg = readJson(path.join(PACKAGE_ROOT, "package.json"), {});
  return pkg.name || "@vitorlc/skills";
}

function parseFrontmatter(content) {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match) return {};
  const meta = {};
  for (const line of match[1].split(/\r?\n/)) {
    const m = line.match(/^(\w[\w-]*)\s*:\s*(.*)$/);
    if (!m) continue;
    let val = m[2].trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    meta[m[1]] = val;
  }
  return meta;
}

export function listCatalog() {
  return listSkillDirs(SKILLS_ROOT).map((name) => getSkill(name));
}

export function getSkill(name) {
  const dir = path.join(SKILLS_ROOT, name);
  const skillMd = path.join(dir, "SKILL.md");
  if (!fs.existsSync(skillMd)) {
    throw new Error(`Skill not found: ${name}`);
  }
  const content = fs.readFileSync(skillMd, "utf8");
  const fm = parseFrontmatter(content);
  return {
    name,
    description: fm.description || "",
    frontmatterName: fm.name || name,
    dir,
  };
}

export function skillSourcePath(name) {
  return getSkill(name).dir;
}
