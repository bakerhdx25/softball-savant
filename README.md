# AUSL Research and Scouting

Independent AUSL data collection, analysis, and scouting-site workspace.

## Projects

- `softball-savant/`: the unified GM-facing product surface combining player
  search and pages, WAR leaderboards, league analysis, and team scouting.
- `ausl-war/`: official AUSL public-data ingestion, WAR/RE24 analysis,
  leaderboard, and times-through-the-order research.
- `ausl-scouting-web/`: static team and player scouting site built from the
  captured AUSL outputs.
- `collector/`: AUSL-owned snapshot of the proven GameChanger scraper used
  during the initial research.

The older WAR, TTO, and scouting sites remain as validated migration references.
New product work belongs in `softball-savant/`.

## Collector setup

The collector is self-contained and does not load code or dependencies from a
Scout Em Out checkout.

```bash
cd collector
npm install
cd ../ausl-war
node scripts/capture-session.mjs
node scripts/fetch-html.mjs --snapshot <SNAPSHOT_ID> --limit 1
```

The first `fetch-html` run should remain a one-game smoke test. Raw payloads,
browser profiles, and authenticated session data are local-only and ignored by
Git.

## Verification

```bash
cd ausl-war
PYTHONPATH=src python3 -m ausl_war.cli build-official-pipeline

cd softball-savant
python3 build.py
python3 -m unittest -v test_build.py

cd ausl-war
PYTHONPATH=src python3 -m unittest discover -s tests -v

cd ../ausl-scouting-web
python3 -m unittest -v test_build.py
python3 build.py
```

See `collector/SOURCE.md` for the exact Scout Em Out revision from which the
initial collector was copied.

## Public deployment architecture

The production-friendly setup separates the frontend from the daily data update:

- Netlify hosts `softball-savant/` as a static frontend and only rebuilds when
  frontend code changes.
- GitHub Actions runs `.github/workflows/update-data-feed.yml` daily and on
  pushes to `main`.
- The workflow rebuilds from public AUSL schedule, game, player-stat, and
  franchise-stat data, runs the Softball Savant tests, and publishes JSON to
  GitHub Pages.
- `softball-savant/app.js` fetches the GitHub Pages JSON feed at runtime, then
  falls back to local `data/site-data.json` for development.

GitHub Pages also publishes a full static copy of the frontend, which is useful
as an immediate public URL even before Netlify is connected:

```text
https://bakerhdx25.github.io/softball-savant/
```

Expected data feed URL:

```text
https://bakerhdx25.github.io/softball-savant/data/site-data.json
```
