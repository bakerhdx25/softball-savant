# AUSL Research and Scouting

Independent AUSL data collection, analysis, and scouting-site workspace.

## Projects

- `ausl-war/`: GameChanger ingestion, WAR/RE24 analysis, leaderboard, and
  times-through-the-order research.
- `ausl-scouting-web/`: static team and player scouting site built from the
  captured AUSL outputs.
- `collector/`: AUSL-owned snapshot of the proven GameChanger scraper used
  during the initial research.

The existing sites remain separate during this migration. Combining them is a
future project and is intentionally outside this repository migration.

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
PYTHONPATH=src python3 -m unittest discover -s tests -v

cd ../ausl-scouting-web
python3 -m unittest -v test_build.py
python3 build.py
```

See `collector/SOURCE.md` for the exact Scout Em Out revision from which the
initial collector was copied.

