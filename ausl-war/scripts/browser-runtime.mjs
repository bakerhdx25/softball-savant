import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
export const projectRoot = path.resolve(scriptDir, "..");
export const workspaceRoot = path.resolve(projectRoot, "..");
export const collectorRoot = path.join(workspaceRoot, "collector");
const require = createRequire(import.meta.url);
const puppeteerPath = path.join(
  collectorRoot,
  "node_modules",
  "puppeteer"
);

if (!fs.existsSync(puppeteerPath)) {
  throw new Error(
    `Puppeteer is unavailable at ${puppeteerPath}. Run npm install in ${collectorRoot} first.`
  );
}

export const puppeteer = require(puppeteerPath);

export function parseArgs(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[index + 1];
    if (next && !next.startsWith("--")) {
      values[key] = next;
      index += 1;
    } else {
      values[key] = true;
    }
  }
  return values;
}

export function ensureInsideProject(target) {
  const resolved = path.resolve(target);
  const relative = path.relative(projectRoot, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Refusing to write outside research project: ${resolved}`);
  }
  return resolved;
}

export function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
