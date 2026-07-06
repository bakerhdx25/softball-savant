import fs from "node:fs/promises";
import path from "node:path";

import {
  ensureInsideProject,
  parseArgs,
  projectRoot,
  puppeteer,
  sleep,
} from "./browser-runtime.mjs";

const args = parseArgs(process.argv.slice(2));
const output = ensureInsideProject(
  args.output || path.join(projectRoot, "data/session/gamechanger-session.json")
);
const profile = ensureInsideProject(
  args.profile || path.join(projectRoot, "data/session/browser-profile")
);
const timeoutMs = Number(args["timeout-minutes"] || 15) * 60 * 1000;

await fs.mkdir(path.dirname(output), { recursive: true });
await fs.mkdir(profile, { recursive: true });

const browser = await puppeteer.launch({
  headless: false,
  userDataDir: profile,
  defaultViewport: null,
  args: ["--start-maximized"],
});

try {
  const pages = await browser.pages();
  let page = pages[0] || (await browser.newPage());
  await page.goto("https://web.gc.com/login", {
    waitUntil: "domcontentloaded",
    timeout: 60_000,
  });
  process.stdout.write(
    "A GameChanger window is open. Sign in there; this process will detect completion automatically.\n"
  );

  const deadline = Date.now() + timeoutMs;
  let authenticated = false;
  while (Date.now() < deadline) {
    const openPages = await browser.pages();
    for (const candidate of openPages) {
      if (!candidate.url().includes("web.gc.com")) continue;
      try {
        authenticated = await candidate.evaluate(() => {
          const root = localStorage.getItem("persist:root") || "";
          return root.includes('"isAuthenticated":true');
        });
        if (authenticated) {
          page = candidate;
          break;
        }
      } catch {
        // Navigation may temporarily destroy the page context during login.
      }
    }
    if (authenticated) break;
    await sleep(2_000);
  }
  if (!authenticated) {
    throw new Error("Timed out before GameChanger reported an authenticated session.");
  }

  const cookies = await page.cookies(
    "https://web.gc.com",
    "https://api.team-manager.gc.com"
  );
  const localStorage = await page.evaluate(() =>
    Object.fromEntries(
      Array.from({ length: window.localStorage.length }, (_, index) => {
        const key = window.localStorage.key(index);
        return [key, window.localStorage.getItem(key)];
      })
    )
  );
  const session = {
    capturedAt: new Date().toISOString(),
    source: "interactive GameChanger login",
    cookies,
    localStorage,
  };
  await fs.writeFile(output, `${JSON.stringify(session, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  process.stdout.write(`Saved session state to ${output}\n`);
} finally {
  await browser.close();
}
