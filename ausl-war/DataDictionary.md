# Data Dictionary

## Public raw snapshot

- `organization_2026.json`: organization team response as received.
- `teams.json`: configured 2025 teams plus discovered 2026 teams.
- `games/<season>/<team_id>.json`: public schedule response for one team.
- `schedule_summary.json`: counts by source team.
- `manifest.json`: retrieval timestamp, source, sizes, and SHA-256 hashes.

## Canonical public dataset

- `canonical_id`: stable hash of season, sorted team IDs, and start timestamp.
- `source_game_id`: GameChanger ID for one team's copy of a contest.
- `preferred_source_game_id`: initial home-side collection preference; not a
  claim that this payload is analytically superior.
- `quality_flags`: failed agreement checks between source copies.
- `game_crosswalk`: one row per source schedule ID mapped to canonical contest.

## Authenticated HTML artifacts

- `boxscore.json`: production-scraper hitting, pitching, and extra-stat tables.
- `plays.json`: exact visible pitch-sequence and play-description text.
- `source.json`: canonical/source IDs, team, URL, collector, and capture time.
- `manifest.json`: SHA-256 and byte size for every locally captured artifact.

## Normalized dataset

- `event_type`: classified PA or runner event.
- `inning`, `half`, `event_order`: chronological location reconstructed from
  GameChanger's newest-first display and batting-team transitions.
- `outs_before`, `outs_after`: event out state.
- `bases_before`, `bases_after`: three-bit base occupancy (1=first, 2=second,
  4=third).
- `runners_before`, `runners_after`: named runner maps keyed by base number.
- `runs_scored`: runs on the atomic event.
- `batter`, `pitcher`, `batting_team`, `fielding_team`: attributed identities.
- `runner_actions`: named runner movement, score, or out records.
- `player_key`: accent/punctuation-insensitive season identity key.

## Model outputs

- `re24.csv`: raw and partially pooled run expectancy by base-out state.
- `event_linear_weights.csv`: mean context-neutral PA run value.
- `batting_runs`: wOBA-derived runs above 2026 league average.
- `wRAA`: public name for `batting_runs`; Weighted Runs Above Average calculated
  directly from wOBA, league wOBA, wOBA scale, and plate appearances.
- `sb_cs_runs`: stolen-base/caught-stealing runs above average.
- `non_steal_advancement_runs`: context-matched advancement, hold, tag-up,
  advancement-out, and batter-stretch runs.
- `baserunning_runs`: SB/CS plus non-steal advancement runs.
- `double_play_avoidance_runs`: batter value versus the expected double-play
  rate in eligible ground-ball opportunities.
- `range_runs`: shrunk general-direction conversion estimate.
- `arm_runs`: league-centered and strongly shrunk arm allocation
  from unambiguous runner-advancement opportunities.
- `throwing_runs`: display value equal to `arm_runs + catcher_throwing_runs`;
  catcher throwing remains separately available in the export.
- `hitting_runs`: context-neutral batting runs above average.
- `baserunning_component_runs`: SB/CS, non-steal advancement, and double-play
  avoidance runs.
- `baserunning_war`: `baserunning_component_runs / runs_per_win`.
- `batting_war`: `wRAA / runs_per_win`.
- `catcher_stolen_bases_allowed`, `catcher_caught_stealing`,
  `catcher_steal_attempts`, `catcher_cs_rate`: official season catcher running
  totals and rate.
- `catcher_throwing_runs`: shrunk, league-centered catcher CS/SB value.
- `defense_runs`: non-pitcher-position range, arm, and catcher throwing runs.
- `defense_war`: non-pitcher range, arm, catcher throwing, and any official
  positional-adjustment runs divided by runs per win. The positional adjustment
  is currently zero.
- `offensive_war`: wRAA, baserunning, double-play avoidance, league balancing,
  and position-player replacement runs divided by runs per win.
- `defensive_war`: public alias for `defense_war`.
- `pitcher_defense_runs`: range and arm runs attributed while fielding at pitcher.
- `pitcher_defense_war`: `pitcher_defense_runs / runs_per_win`.
- `ra7_pitching_runs_above_average`: original opponent-adjusted RA7 RAA.
- `pitching_runs_above_average`: RA7 RAA with pitcher defense separated.
- `position_war`: all position components, league balancing, and replacement
  value converted to wins.
- `pitching_war`: opponent-adjusted RA7 pitching component with pitcher defense
  separated, plus pitcher replacement value.
- `pitcher_war`: `pitching_war + pitcher_defense_war`; this equals the original
  overall RA7 Pitching WAR and excludes hitting/baserunning.
- `ERA`: earned runs allowed per seven innings.
- `FIP`: seven-inning Fielding Independent Pitching using HR, BB, HBP, and SO,
  with a season-specific constant that centers league FIP on league ERA;
  excluded from WAR.
- `ERA_minus_FIP`: `ERA - FIP`; positive means actual ERA is higher.
- `FIP_BF`, `FIP_HR`, `FIP_BB`, `FIP_HBP`, `FIP_SO`: pitcher inputs retained
  for auditability.
- `total_war`: retained in model exports as Position WAR plus Pitcher WAR; not
  displayed on the role-separated leaderboard.
- `quality_flags`: small samples and unavailable-component warnings.

Season-specific primary files use the suffix `_2025` or `_2026`. The 2025 files
include all 50 completed games; official AUSL pages supply the 12-game gap in
the inherited detailed snapshot.
