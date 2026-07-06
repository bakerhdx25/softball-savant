# AUSL WAR Research

This directory is an isolated research pipeline for AUSL Wins Above
Replacement model. It does not import data into Scout Em Out, modify the web
application, write to its database, or deploy anything.

## Current stage

The pipeline runs end to end for all 50 completed 2025 games and 48 completed
2026 games available at the captured cutoff. Official AUSL pages fill the 12
2025 and three 2026 games absent from the inherited detailed snapshot. It
produces season-specific RE24/WAR components and passes `ValidationReport.md`.

## Commands

Run from this directory with Python 3.11 or newer and Node.js 20 or newer:

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 -m ausl_war.cli fetch-public
PYTHONPATH=src python3 -m ausl_war.cli canonicalize
node scripts/capture-session.mjs
node scripts/fetch-html.mjs --snapshot <SNAPSHOT_ID> --limit 1
node scripts/fetch-html.mjs --snapshot <SNAPSHOT_ID>
PYTHONPATH=src python3 -m ausl_war.cli audit-authenticated --snapshot <SNAPSHOT_ID>
PYTHONPATH=src python3 -m ausl_war.cli normalize-html --snapshot <SNAPSHOT_ID>
PYTHONPATH=src python3 -m ausl_war.cli build-re24 --snapshot <SNAPSHOT_ID>
PYTHONPATH=src python3 -m ausl_war.cli build-war --snapshot <SNAPSHOT_ID>
python3 scripts/build-official-player-assets.py
python3 scripts/build-mobile-leaderboard.py
PYTHONPATH=src python3 -m ausl_war.cli research-positions --snapshot <SNAPSHOT_ID>
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m ausl_war.cli validate --snapshot <SNAPSHOT_ID>
PYTHONPATH=src python3 -m ausl_war.cli build-tto --snapshot <SNAPSHOT_ID>
```

`fetch-public` creates a timestamped immutable snapshot. `canonicalize` creates
the crosswalk and one row per real contest. The first `fetch-html` command is a
one-game smoke test. Run `validate` last; it exits nonzero when an invariant
fails and regenerates the audit and validation reports.

Raw schedules, authenticated HTML-derived player data, browser sessions, and
derived snapshots are gitignored and remain local.

The browser collector is owned by this repository under `../collector`. Run
`npm install` there before using `capture-session.mjs` or `fetch-html.mjs`.

## Times-through-the-order study

`build-tto` is an isolated AUSL research output. It does not modify the Scout Em
Out application or database. It combines the normalized GameChanger games with
official AUSL play-by-play for completed games absent from that snapshot,
reconstructs pitcher stints against box-score innings, derives exact same-game
and same-series batter-pitcher encounter numbers, and writes the study under
`output/tto/`.

The main artifacts are `Report.md`, `plate_appearances.csv`,
`league_splits.json`, `pitcher_splits.csv`, `pitcher_penalties.csv`,
`adjusted_models.json`, and `validation.json`. See `TTO-Methodology.md` for the
definitions and limitations.

## Authenticated collection

`capture-session.mjs` opens an isolated browser for manual GameChanger login.
The saved session has owner-only permissions under `data/session/`.

The first command is a one-game smoke test. The collector calls the
repository-owned copy of `scrapeDataFromSchedulePage`. It preserves the
production-proven browser settings, resource interception, selectors, paywall
checks, and error handling used when the AUSL research was created. The legacy
internal API client is not used. See `../collector/SOURCE.md` for provenance.

The collector selects exactly one home-owned schedule row per canonical contest
before navigation, preventing double counting and avoiding reciprocal page
traffic. It never overwrites an existing game artifact. Away-owned rows remain
available as a targeted fallback only when the selected copy fails validation.
Completed artifacts are skipped on resume, and team schedule batches are
separated by a 30-second pause by default.

The audit inventories extracted fields and verifies complete selected-game
coverage. The reciprocal schedule ID remains in the crosswalk as a fallback but
is not fetched during a successful run.

## Principal outputs

- `output/ausl_<season>_war.csv`: Position WAR, Pitcher WAR, Total WAR, and components.
- `output/position_players_2026.csv`: hitting, baserunning, double-play avoidance, range/arm defense, and Position WAR.
- `output/baserunning_2026.csv`: SB/CS and context-matched non-steal advancement.
- `output/double_play_avoidance_2026.csv`: eligible opportunities and batter DP runs.
- `output/arm_value_2026.csv`: fielder arm opportunities and shrunk runs.
- `output/old_vs_new_player_impact.csv`: player changes from the preserved pre-fix baseline.
- `output/pitchers_<season>.csv`: opponent-adjusted pitcher WAR, pitcher defense,
  ERA, FIP, and ERA minus FIP.
- `output/catcher_throwing_<season>.csv`: catcher SB/CS opportunities and runs.
- `output/mobile-leaderboard.html`: light, DARKO-inspired sortable tables with
  separate Position Players and Pitchers views; mobile-contained horizontal
  metric scrolling, season/team/PA/IP filters, official leader headshots,
  pagination, and CSV download.
- `output/position_player_team_splits_2026.csv`: team-level batting splits.
- `data/snapshots/<id>/model/re24.csv`: raw and smoothed 24-state run expectancy.
- `data/snapshots/<id>/model/event_linear_weights.csv`: AUSL event run values.
- `DataAudit.md`, `ValidationReport.md`, and `Recommendation.md`: readiness evidence and limitations.
- `PositionalAdjustmentResearch.md` and `output/positional_*`: reproducible
  positional-adjustment feasibility evidence. The current recommendation is
  insufficient data, so official positional adjustment remains zero.

## Reproducibility rules

- Never overwrite a raw snapshot.
- Every raw file is recorded with byte size and SHA-256 in `manifest.json`.
- Every source schedule ID maps to exactly one canonical contest ID.
- A contest is keyed by season, both team IDs, and start time—not by either
  team's GameChanger schedule ID.
- One home-side copy is collected per canonical contest; the away copy is a
  targeted fallback, never an automatic duplicate request.
