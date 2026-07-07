# Softball Savant

Softball Savant is a unified, independently produced AUSL analytics and
scouting site. It combines the prior team scouting report, WAR leaderboard,
and times-through-the-order explorer into one static site suitable for local
review or static hosting.

## Included surfaces

- Global search and permanent hash routes for all 2025 and 2026 players
- Player pages with standard and advanced statistics, WAR, percentiles,
  spray charts, swing decisions, game logs, baserunning, and pitcher exposure
- Position-player and pitcher leaderboards for 2025 and 2026
- League standings, Pythagorean records, count approach, TTO, and series views
- One page per team with Overview, Roster, Stats, and Scouting tabs
- Downloadable 2026 and combined 2025–26 scouting PDFs
- Public-facing methodology and data-limit explanations

Pitcher WAR remains opponent-adjusted RA7 based. FIP is shown as a parallel
defense-independent diagnostic. Pythagorean records use the transparent
standard exponent of 2.0. A grid fit over the 10 available team-seasons
produces 1.96, while exponents trained on one season perform worse on the
other season than 2.0. The data therefore does not support claiming a separate
AUSL-specific constant.

## Build and run

From this directory:

```bash
python3 build.py
python3 -m unittest -v test_build.py
python3 -m http.server 8042
```

Open `http://127.0.0.1:8042`.

The builder reads the validated analysis outputs in `../ausl-war/` and writes
one normalized browser payload to `data/site-data.json`. The existing sites
remain in the repository as migration references; Softball Savant is the
combined product surface.

## Updating the data

1. Refresh and validate the `../ausl-war/` pipeline outputs.
2. Run `python3 build.py` here.
3. Run this project's tests plus the existing WAR and scouting test suites.
4. Review the generated site at desktop and mobile widths before publishing.

The site is fully static. It has no runtime database or API dependency.
