# AUSL Times-Through-the-Order Methodology

## Scope

The study uses every game marked completed in the captured official AUSL 2025
and 2026 schedules. The inherited normalized GameChanger data is used where it
exists. Completed games absent from that snapshot are added from official AUSL
play-by-play, which supplies batter and pitcher IDs for every plate appearance.
Postponed games and the suspended record for the 2025 championship resumption
are excluded rather than double counted.

## Pitcher attribution

The original GameChanger normalizer carried the last named pitcher forward.
That field was complete but did not reconcile pitcher outs to the box score.
The TTO pipeline reconstructs pitcher stints as a constrained sequence:

1. An explicit `Pitcher Name pitching` PA description is binding.
2. Assigned outs must equal every pitcher's game-level innings exactly.
3. Among feasible sequences, the solution minimizes unannounced pitching
   changes, then disagreements with substitution hints and the old assignment.
4. Re-entry is allowed.
5. Equally optimal block assignments are flagged as ambiguous.

Official AUSL augmentation uses the pitcher ID recorded directly on the play.
Its PA, H, BB, SO, and HR totals must reconcile to the official box score.

## Exposure fields

- `same_game_matchup_number`: the batter's first, second, third, etc. PA against
  that exact pitcher in the game. It continues when a pitcher exits and
  re-enters.
- `mlb_tto_bf9`: MLB-comparable bands of pitcher batters faced: 1–9, 10–18,
  19–27, and 28+. Exact matchup number remains the primary softball measure.
- `series_matchup_number`: cumulative PAs between that batter and pitcher in the
  current scheduled series.
- `prior_series_game_matchups`: only meetings in earlier games of the series.
  It excludes earlier meetings in the current game.

Regular-season series are derived from the official team pairing, venue, and a
date cluster with no gap greater than four days. Postseason games use official
series metadata when present and chronological championship order otherwise.

## Statistics

Every split reports PA, AVG, OBP, SLG, OPS, K%, BB%, HR%, wOBA, and event run
value per PA. wOBA is calibrated from the shared AUSL RE24 model. Event run
value is the context-neutral event weight derived from that RE24 model, which is
available consistently for both data sources. The original contextual RE24
value remains in `re24_run_value` for GameChanger rows.

Ratio uncertainty uses game-clustered influence-function standard errors. The
adjusted linear models use batter and pitcher fixed effects with game-clustered
standard errors. The total-exposure specification controls for season and
prior-series exposure. The workload-decomposition specification additionally
controls for pitcher batters faced and inning band.

## Interpretation

The models estimate associations, not a causal removal rule. Later matchups are
selected: stronger pitchers survive longer, managers remove struggling
pitchers, lineup quality differs, and relievers enter disproportionately late.
The workload-decomposition model is intended to distinguish gradual pitcher
deterioration from a discrete repeat-matchup jump, but those variables remain
strongly related and should not be overinterpreted pitcher by pitcher.

## Primary references

- MLB third-time-through-the-order glossary:
  https://www.mlb.com/glossary/miscellaneous/third-time-through-the-order-penalty
- Baseball Savant CSV fields (`n_thruorder_pitcher` and prior PA fields):
  https://baseballsavant.mlb.com/csv-docs
- Ryan Brill, *A Bayesian Analysis of the Time Through the Order Penalty in
  Baseball*: https://arxiv.org/abs/2210.06724
