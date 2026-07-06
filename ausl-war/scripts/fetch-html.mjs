import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

import {
  collectorRoot,
  ensureInsideProject,
  parseArgs,
  projectRoot,
  puppeteer,
  sleep,
} from "./browser-runtime.mjs";

const require = createRequire(import.meta.url);
// This AUSL-owned snapshot of the proven collector navigates rendered
// /box-score and /plays pages and parses their DOM.
const scraper = require(path.join(collectorRoot, "scraper.js"));
const PUPPETEER_BASE_ARGS = [
  "--no-sandbox",
  "--disable-setuid-sandbox",
  "--disable-dev-shm-usage",
  "--disable-accelerated-2d-canvas",
  "--no-first-run",
  "--no-zygote",
  "--disable-gpu",
];

const args = parseArgs(process.argv.slice(2));
const snapshotId = args.snapshot;
if (!snapshotId) throw new Error("Required argument: --snapshot <public snapshot ID>");
const limit = args.limit ? Number(args.limit) : null;
if (limit !== null && (!Number.isInteger(limit) || limit < 1)) {
  throw new Error("--limit must be a positive integer");
}
const teamPauseMs = Number(args["team-pause-ms"] || 30_000);
if (!Number.isFinite(teamPauseMs) || teamPauseMs < 0) {
  throw new Error("--team-pause-ms must be zero or a positive number");
}

const sessionPath = path.resolve(
  args.session || path.join(projectRoot, "data/session/gamechanger-session.json")
);
const session = JSON.parse(await fs.readFile(sessionPath, "utf8"));
const profilePath = ensureInsideProject(
  args.profile || path.join(projectRoot, "data/session/browser-profile")
);
const publicRoot = path.join(projectRoot, "data/snapshots", snapshotId, "public");
const canonicalGames = JSON.parse(
  await fs.readFile(path.join(publicRoot, "canonical_games.json"), "utf8")
);
const crosswalk = JSON.parse(
  await fs.readFile(path.join(publicRoot, "game_crosswalk.json"), "utf8")
);
const completed = canonicalGames.filter((game) => game.status === "completed");
const preferredIds = new Set(completed.map((game) => game.preferred_source_game_id));
let selectedRows = crosswalk
  .filter((row) => preferredIds.has(row.source_game_id))
  .sort((left, right) =>
    `${left.season}|${left.source_team_id}|${left.start_ts}`.localeCompare(
      `${right.season}|${right.source_team_id}|${right.start_ts}`
    )
  );
// A successful raw game snapshot is immutable and must not generate repeat page
// traffic on resume.
const uncapturedRows = [];
for (const row of selectedRows) {
  const gameRoot = path.join(
    projectRoot,
    "data/raw/authenticated",
    snapshotId,
    "games",
    row.source_game_id
  );
  try {
    await Promise.all([
      fs.access(path.join(gameRoot, "boxscore.json")),
      fs.access(path.join(gameRoot, "plays.json")),
      fs.access(path.join(gameRoot, "source.json")),
    ]);
  } catch {
    uncapturedRows.push(row);
  }
}
selectedRows = uncapturedRows;
if (limit !== null) selectedRows = selectedRows.slice(0, limit);

const output = ensureInsideProject(
  args.output || path.join(projectRoot, "data/raw/authenticated", snapshotId)
);
await fs.mkdir(path.join(output, "games"), { recursive: true });

async function loadCapturedSession(page) {
  const client = await page.target().createCDPSession();
  for (const cookie of session.cookies || []) {
    try {
      await client.send("Network.setCookie", {
        name: cookie.name,
        value: cookie.value,
        domain: cookie.domain,
        path: cookie.path || "/",
        secure: cookie.secure !== false,
        httpOnly: Boolean(cookie.httpOnly),
        sameSite: cookie.sameSite,
        expires: cookie.expires > 0 ? cookie.expires : undefined,
      });
    } catch {
      // Production's session loader also tolerates individual ancillary cookie failures.
    }
  }
  await page.goto("https://web.gc.com", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.evaluate((entries) => {
    for (const [key, value] of Object.entries(entries || {})) {
      if (value !== null && value !== undefined) localStorage.setItem(key, value);
    }
  }, session.localStorage || {});
  await page.goto("https://web.gc.com/teams", { waitUntil: "networkidle2", timeout: 30_000 });
  await page.waitForSelector('span[data-testid="teams-title"]', { timeout: 15_000 });
}

async function scheduleGameUrls(page, scheduleUrl) {
  await page.goto(scheduleUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.waitForSelector("div.ScheduleSection__section", { timeout: 30_000 });
  return page.evaluate(() =>
    Array.from(document.querySelectorAll("a.ScheduleListByMonth__event"))
      .map((link) => {
        const href = link.getAttribute("href");
        if (!href) return null;
        return (href.startsWith("http") ? href : `https://web.gc.com${href}`)
          .replace(/\/$/, "")
          .split("?")[0];
      })
      .filter(Boolean)
  );
}

let browser = await puppeteer.launch({
  headless: true,
  args: PUPPETEER_BASE_ARGS,
  userDataDir: profilePath,
});
let page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
const failures = [];
let capturedGames = 0;

try {
  await loadCapturedSession(page);
  const byTeam = new Map();
  for (const row of selectedRows) {
    const key = `${row.season}|${row.source_team_id}`;
    if (!byTeam.has(key)) byTeam.set(key, []);
    byTeam.get(key).push(row);
  }

  const teamBatches = Array.from(byTeam.values());
  for (let batchIndex = 0; batchIndex < teamBatches.length; batchIndex += 1) {
    const rows = teamBatches[batchIndex];
    if (batchIndex > 0 && teamPauseMs > 0) {
      process.stdout.write(`Pausing ${teamPauseMs}ms between team schedule batches.\n`);
      await sleep(teamPauseMs);
    }
    const teamId = rows[0].source_team_id;
    const scheduleUrl = `https://web.gc.com/teams/${teamId}/schedule`;
    const availableUrls = await scheduleGameUrls(page, scheduleUrl);
    const selections = [];
    const rowByUrl = new Map();
    for (const row of rows) {
      const matches = availableUrls.filter((url) => url.includes(row.source_game_id));
      if (matches.length !== 1) {
        throw new Error(
          `Expected one rendered schedule link for ${row.source_game_id}, found ${matches.length}`
        );
      }
      selections.push(matches[0]);
      rowByUrl.set(matches[0], row);
    }

    process.stdout.write(
      `HTML scrape: ${rows[0].season} ${rows[0].source_team_name}, ${selections.length} selected game(s)\n`
    );
    try {
      const result = await scraper.scrapeDataFromSchedulePage(
        browser,
        page,
        scheduleUrl,
        (message) => process.stdout.write(`[Scout Em Out] ${message}\n`),
        selections
      );
      browser = result.browser;
      page = result.page;
      for (const game of result.allGamesData || []) {
        const normalizedUrl = String(game.gameUrl || "").replace(/\/$/, "").split("?")[0];
        const row = rowByUrl.get(normalizedUrl);
        if (!row) throw new Error(`Scraper returned unexpected game URL: ${normalizedUrl}`);
        const gameDir = path.join(output, "games", row.source_game_id);
        await fs.mkdir(gameDir, { recursive: true });
        const files = {
          "boxscore.json": game.boxScore,
          "plays.json": { plays: game.plays },
          "source.json": {
            collector: "collector/scraper.js:scrapeDataFromSchedulePage",
            canonical_id: row.canonical_id,
            source_game_id: row.source_game_id,
            source_team_id: row.source_team_id,
            source_team_name: row.source_team_name,
            game_url: normalizedUrl,
            captured_at: new Date().toISOString(),
          },
        };
        for (const [name, payload] of Object.entries(files)) {
          try {
            await fs.writeFile(path.join(gameDir, name), `${JSON.stringify(payload, null, 2)}\n`, {
              encoding: "utf8",
              flag: "wx",
            });
          } catch (error) {
            if (error.code !== "EEXIST") throw error;
          }
        }
        capturedGames += 1;
      }
      if ((result.allGamesData || []).length !== selections.length) {
        throw new Error(
          `Production scraper returned ${result.allGamesData?.length || 0}/${selections.length} selected games`
        );
      }
    } catch (error) {
      failures.push({
        season: rows[0].season,
        source_team_id: teamId,
        source_game_ids: rows.map((row) => row.source_game_id),
        message: String(error?.message || error).slice(0, 500),
      });
      throw error;
    }
  }
} finally {
  if (browser?.isConnected()) await browser.close();
  const manifestFiles = [];
  async function walk(directory) {
    for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name);
      if (entry.isDirectory()) await walk(target);
      else if (entry.name.endsWith(".json") && entry.name !== "manifest.json") {
        const buffer = await fs.readFile(target);
        manifestFiles.push({
          path: path.relative(output, target),
          bytes: buffer.length,
          sha256: crypto.createHash("sha256").update(buffer).digest("hex"),
        });
      }
    }
  }
  await walk(output);
  manifestFiles.sort((left, right) => left.path.localeCompare(right.path));
  await fs.writeFile(
    path.join(output, "manifest.json"),
    `${JSON.stringify({
      public_snapshot_id: snapshotId,
      updated_at: new Date().toISOString(),
      completed_canonical_contests: completed.length,
      selected_contests_in_this_run: selectedRows.length,
      captured_games_in_this_run: capturedGames,
      collector: "collector/scraper.js:scrapeDataFromSchedulePage",
      transport: "rendered HTML navigation only",
      inter_team_pause_ms: teamPauseMs,
      files: manifestFiles,
      failures,
    }, null, 2)}\n`,
    "utf8"
  );
}
